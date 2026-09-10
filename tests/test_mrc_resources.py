"""Tests for the two-resource machine model."""

from __future__ import annotations

import pytest

from ftqc_delivery.mrc.resources import (
    CATALYZED_CCZ_TO_T,
    CCZ,
    FACTORY_REFERENCE,
    T,
    FactoryBank,
    Machine,
    build_machine,
    machine_for_capacity,
    machine_for_rates,
)


def test_reference_factories_match_the_cited_designs():
    """The defaults are the published footprints and periods."""

    assert FACTORY_REFERENCE[CCZ]["tiles"] == 72
    assert FACTORY_REFERENCE[CCZ]["period"] == 6
    assert FACTORY_REFERENCE[T]["tiles"] == 11
    assert FACTORY_REFERENCE[T]["period"] == 11


def test_bank_rate_and_tiles_scale_with_count():
    bank = FactoryBank(resource=T, count=4, period=8, tiles_per_factory=11)
    assert bank.rate == pytest.approx(0.5)
    assert bank.tiles == 44


def test_first_output_waits_for_latency_and_period():
    bank = FactoryBank(resource=T, count=1, period=10, latency=7)
    assert bank.first_output == 17
    series = bank.arrival_series(40)
    assert series[17] == 1
    assert sum(series[:17]) == 0


def test_staggering_spreads_arrivals():
    bank = FactoryBank(resource=T, count=4, period=8, stagger=True)
    steady = bank.arrival_series(40)[25:33]
    assert sum(steady) == 4
    assert max(steady) == 1


def test_failures_reduce_throughput_without_changing_the_nominal_rate():
    bank = FactoryBank(resource=T, count=10, period=10, p_success=0.5)
    assert bank.nominal_rate == pytest.approx(1.0)
    assert bank.rate == pytest.approx(0.5)
    produced = sum(bank.arrival_series(2000))
    assert 800 < produced < 1200


def test_imbalance_is_measured_in_t_equivalents():
    """One CCZ is worth two T states, so equal value means imbalance 1."""

    machine = build_machine(t_factories=11, ccz_factories=3)
    assert machine.rate(T) == pytest.approx(1.0)
    assert machine.rate(CCZ) == pytest.approx(0.5)
    assert machine.imbalance == pytest.approx(1.0)


def test_capacity_split_holds_capacity_roughly_fixed():
    capacities = []
    for share in (0.1, 0.25, 0.5, 0.75, 0.9):
        machine = machine_for_capacity(2.0, share)
        capacities.append(machine.rate(T) + 2 * machine.rate(CCZ))
    assert min(capacities) > 1.6
    assert max(capacities) < 2.4


def test_factory_tiles_charge_for_both_banks_and_conversions():
    plain = build_machine(t_factories=2, ccz_factories=2)
    converting = build_machine(
        t_factories=2, ccz_factories=2, conversions=(CATALYZED_CCZ_TO_T,)
    )
    assert plain.factory_tiles == 2 * 11 + 2 * 72
    assert converting.factory_tiles > plain.factory_tiles


def test_machine_rejects_two_banks_of_the_same_resource():
    bank = FactoryBank(resource=T, count=1, period=10)
    with pytest.raises(ValueError):
        Machine(banks=(bank, bank))


def test_machine_for_rates_approximates_the_request():
    machine = machine_for_rates(1.0, 0.5)
    assert machine.rate(T) == pytest.approx(1.0)
    assert machine.rate(CCZ) == pytest.approx(0.5)


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        FactoryBank(resource="Y", count=1, period=1)
    with pytest.raises(ValueError):
        FactoryBank(resource=T, count=0, period=1)
    with pytest.raises(ValueError):
        FactoryBank(resource=T, count=1, period=1, p_success=0.0)
    with pytest.raises(ValueError):
        machine_for_capacity(1.0, 1.5)
