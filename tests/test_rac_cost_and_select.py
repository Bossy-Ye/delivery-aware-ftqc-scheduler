"""Tests for the analytic cost models and the compilation policies."""

from __future__ import annotations

import random

import pytest

from ftqc_delivery.rac.analysis import t_count, t_depth
from ftqc_delivery.rac.cost import estimate, sccp_bound
from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.library import make_adder_variants, make_mcx_variants
from ftqc_delivery.rac.programs import (
    decision_sites,
    pilot_programs,
    reduction_tree_multiplier,
    schoolbook_multiplier,
    trotter_layers,
)
from ftqc_delivery.rac.select import (
    best_uniform,
    concurrent_site_counts,
    select_oracle,
    select_resource_aware,
    select_share_aware_greedy,
    select_static,
    uniform_assignments,
)
from ftqc_delivery.rac.supply import SupplyModel


SUPPLIES = [
    SupplyModel(num_factories=1, production_latency=10, buffer_capacity=8),
    SupplyModel(num_factories=10, production_latency=10, buffer_capacity=32),
    SupplyModel(num_factories=40, production_latency=10, buffer_capacity=32),
    SupplyModel(num_factories=8, production_latency=4, buffer_capacity=-1),
]


def _random_assignment(program, rng):
    return {
        site.site_id: rng.choice(site.variant_names) for site in program.sites
    }


@pytest.mark.parametrize("supply", SUPPLIES)
def test_sccp_is_a_lower_bound_on_the_simulated_makespan(supply):
    """The window bound must never exceed what the machine actually achieves."""

    rng = random.Random(11)
    programs = [
        schoolbook_multiplier(width=16, rows=2),
        reduction_tree_multiplier(width=16, rows=4),
        trotter_layers(terms=3, layers=2, t_budget=16),
    ]
    for program in programs:
        for _ in range(6):
            dag = program.instantiate(_random_assignment(program, rng))
            bound = sccp_bound(dag, supply)
            actual = execute(dag, supply, record_trace=False).makespan
            assert bound <= actual


def test_sccp_is_at_least_the_dependency_critical_path():
    program = schoolbook_multiplier(width=16, rows=2)
    dag = program.instantiate(program.default_assignment())
    supply = SupplyModel(num_factories=200, production_latency=1, buffer_capacity=-1)
    from ftqc_delivery.rac.analysis import logical_depth

    assert sccp_bound(dag, supply) >= logical_depth(dag)


def test_cost_model_ladder_is_ordered_by_information():
    program = trotter_layers(terms=3, layers=2, t_budget=16)
    dag = program.instantiate(program.default_assignment())
    supply = SupplyModel(num_factories=5, production_latency=10, buffer_capacity=16)
    deps = estimate(dag, supply, "deps_only")
    combined = estimate(dag, supply, "deps_plus_count")
    window = estimate(dag, supply, "sccp")
    assert deps <= combined <= window


def test_unknown_cost_model_is_rejected():
    program = schoolbook_multiplier(width=16, rows=2)
    dag = program.instantiate(program.default_assignment())
    with pytest.raises(ValueError):
        estimate(dag, SUPPLIES[0], "does_not_exist")


def test_static_selection_minimises_its_own_metric():
    program = reduction_tree_multiplier(width=32, rows=4)
    depth_choice = program.instantiate(select_static(program, "t_depth"))
    count_choice = program.instantiate(select_static(program, "t_count"))
    for assignment in uniform_assignments(program):
        candidate = program.instantiate(assignment)
        assert t_depth(depth_choice) <= t_depth(candidate)
        assert t_count(count_choice) <= t_count(candidate)


def test_exhaustive_oracle_is_at_least_as_good_as_every_policy():
    program = trotter_layers(terms=2, layers=2, t_budget=16)
    supply = SupplyModel(num_factories=15, production_latency=10, buffer_capacity=32)
    _, optimum, _, complete = select_oracle(program, supply, limit=100_000)
    assert complete
    for assignment in (
        select_static(program, "t_depth"),
        select_static(program, "t_count"),
        select_share_aware_greedy(program, supply)[0],
        select_resource_aware(program, supply)[0],
    ):
        makespan = execute(
            program.instantiate(assignment), supply, record_trace=False
        ).makespan
        assert makespan >= optimum


def test_resource_aware_selection_never_uses_the_simulator():
    """The policy must be reachable without ever executing a circuit."""

    program = trotter_layers(terms=2, layers=2, t_budget=16)
    supply = SupplyModel(num_factories=15, production_latency=10, buffer_capacity=32)
    calls = {"count": 0}
    import ftqc_delivery.rac.select as select_module

    original = select_module.execute

    def counting_execute(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    select_module.execute = counting_execute
    try:
        select_resource_aware(program, supply)
    finally:
        select_module.execute = original
    assert calls["count"] == 0


def test_concurrency_counts_are_one_for_a_serial_program():
    program = schoolbook_multiplier(width=16, rows=3)
    counts = concurrent_site_counts(program)
    assert max(counts[site.site_id] for site in decision_sites(program)) == 1


def test_concurrency_counts_grow_with_stage_width():
    program = trotter_layers(terms=4, layers=2, t_budget=16)
    counts = concurrent_site_counts(program)
    assert max(counts[site.site_id] for site in decision_sites(program)) == 4


def test_best_uniform_is_one_of_the_uniform_assignments():
    program = reduction_tree_multiplier(width=16, rows=4)
    supply = SupplyModel(num_factories=10, production_latency=10, buffer_capacity=32)
    assignment, makespan = best_uniform(program, supply)
    assert assignment in uniform_assignments(program)
    assert (
        execute(program.instantiate(assignment), supply, record_trace=False).makespan
        == makespan
    )


def test_variant_families_offer_a_real_trade_off():
    """Lower T-depth must cost either more T gates or a burstier demand profile."""

    adders = {
        variant.name: variant.fragment.to_dag(variant.name)
        for variant in make_adder_variants("a", 32)
    }
    ripple, lookahead = adders["ripple"], adders["lookahead"]
    assert t_depth(lookahead) < t_depth(ripple)
    assert t_count(lookahead) > t_count(ripple)

    mcx = {
        variant.name: variant.fragment.to_dag(variant.name)
        for variant in make_mcx_variants("m", 16)
    }
    assert t_count(mcx["tree"]) == t_count(mcx["linear"])
    assert t_depth(mcx["tree"]) < t_depth(mcx["linear"])


def test_every_pilot_program_instantiates_into_a_valid_dag():
    for program in pilot_programs():
        dag = program.instantiate(program.default_assignment())
        assert dag.topological_order()
        assert dag.num_t_gates() > 0
