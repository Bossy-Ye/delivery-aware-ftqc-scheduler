"""Tests for the magic-state supply process."""

from __future__ import annotations

import pytest

from ftqc_delivery.rac.supply import (
    UNBOUNDED,
    StochasticSupplyModel,
    SupplyModel,
    saturating_supply,
    supply_for_rate,
)


def test_rate_and_period():
    supply = SupplyModel(num_factories=4, production_latency=8)
    assert supply.period == 8
    assert supply.rate == pytest.approx(0.5)


def test_staggered_bank_spreads_arrivals():
    supply = SupplyModel(num_factories=4, production_latency=8, stagger=True)
    steady_state = [supply.arrivals(cycle) for cycle in range(17, 25)]
    assert sum(steady_state) == 4
    assert max(steady_state) == 1


def test_synchronised_bank_bursts():
    supply = SupplyModel(num_factories=4, production_latency=8, stagger=False)
    assert supply.arrivals(8) == 4
    assert supply.arrivals(9) == 0


def test_cumulative_matches_series():
    supply = SupplyModel(num_factories=3, production_latency=5)
    series = supply.arrival_series(60)
    for cycle in (1, 7, 20, 41, 60):
        assert supply.cumulative_arrivals(cycle) == sum(series[1 : cycle + 1])


def test_cycles_to_produce_is_the_first_sufficient_cycle():
    supply = SupplyModel(num_factories=2, production_latency=6)
    cycle = supply.cycles_to_produce(5)
    assert supply.cumulative_arrivals(cycle) >= 5
    assert supply.cumulative_arrivals(cycle - 1) < 5


def test_pipelined_factory_has_higher_rate_than_its_latency_suggests():
    supply = SupplyModel(num_factories=1, production_latency=20, factory_period=4)
    assert supply.rate == pytest.approx(0.25)
    assert supply.arrivals(20) == 1
    assert supply.arrivals(24) == 1


def test_supply_for_rate_round_trips():
    supply = supply_for_rate(0.4, production_latency=10)
    assert supply.rate == pytest.approx(0.4)


def test_saturating_supply_never_binds():
    supply = saturating_supply(12)
    assert supply.unbounded_buffer
    assert supply.initial_stock >= 12


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        SupplyModel(num_factories=0)
    with pytest.raises(ValueError):
        SupplyModel(num_factories=1, production_latency=0)
    with pytest.raises(ValueError):
        SupplyModel(num_factories=1, buffer_capacity=-5)


def test_unbounded_buffer_flag():
    assert SupplyModel(buffer_capacity=UNBOUNDED).unbounded_buffer
    assert not SupplyModel(buffer_capacity=4).unbounded_buffer


def test_stochastic_supply_loses_a_fraction_of_deliveries():
    base = SupplyModel(num_factories=10, production_latency=10)
    stochastic = StochasticSupplyModel(base, p_accept=0.5, seed=3, horizon=4000)
    assert stochastic.rate == pytest.approx(0.5)
    produced = stochastic.cumulative_arrivals(2000)
    nominal = base.cumulative_arrivals(2000)
    assert 0 < produced < nominal
