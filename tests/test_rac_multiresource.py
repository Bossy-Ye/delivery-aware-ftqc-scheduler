"""Tests for the exploratory multi-resource extension."""

from __future__ import annotations

import pytest

from ftqc_delivery.rac.multiresource import (
    and_bank,
    balanced_selection,
    execute_multi,
    factories,
    resource_counts,
    resource_of,
    two_term_estimate,
    weighted_depth,
)


def _uniform(program, choice):
    return {
        site.site_id: (
            choice if choice in site.variant_names else site.variants[0].name
        )
        for site in program.sites
    }


def test_resources_are_recognised_by_operation_type():
    assert resource_of("T") == "T"
    assert resource_of("Tdg") == "T"
    assert resource_of("CCZ") == "CCZ"
    assert resource_of("Clifford") is None


def test_uniform_assignments_load_a_single_factory():
    program = and_bank(lanes=3, stages=2)
    assert resource_counts(program.instantiate(_uniform(program, "t4"))) == {"T": 24}
    assert resource_counts(program.instantiate(_uniform(program, "ccz1"))) == {"CCZ": 6}


def test_a_mixed_assignment_loads_both_factories():
    program = and_bank(lanes=2, stages=1)
    sites = [site for site in program.sites if len(site.variants) > 1]
    assignment = _uniform(program, "t4")
    assignment[sites[0].site_id] = "ccz1"
    counts = resource_counts(program.instantiate(assignment))
    assert counts["T"] > 0 and counts["CCZ"] > 0


def test_more_supply_never_slows_execution_down():
    program = and_bank(lanes=3, stages=2)
    dag = program.instantiate(_uniform(program, "t4"))
    slow = execute_multi(dag, factories(0.5, 0.5))
    fast = execute_multi(dag, factories(4.0, 0.5))
    assert fast <= slow


def test_the_two_term_estimate_is_a_lower_bound_here_too():
    program = and_bank(lanes=3, stages=2)
    for choice in ("t4", "ccz1", "t7_d1", "ccz2_shallow"):
        dag = program.instantiate(_uniform(program, choice))
        for supplies in (factories(1.0, 0.5), factories(0.5, 2.0), factories(2.0, 2.0)):
            assert two_term_estimate(dag, supplies) <= execute_multi(dag, supplies) + 1


def test_weighted_depth_counts_every_operation():
    program = and_bank(lanes=2, stages=1)
    dag = program.instantiate(_uniform(program, "ccz1"))
    assert weighted_depth(dag) > 0
    assert weighted_depth(dag, clifford_weight=0) < weighted_depth(dag)


def test_balanced_selection_returns_a_complete_assignment():
    program = and_bank(lanes=3, stages=2)
    assignment = balanced_selection(program, factories(1.0, 0.25))
    assert set(assignment) == {site.site_id for site in program.sites}


def test_an_imbalanced_factory_bank_rewards_mixing():
    """With one factory much slower, splitting the load beats either extreme."""

    program = and_bank(lanes=4, stages=1)
    supplies = factories(1.0, 0.5)
    pure = min(
        execute_multi(program.instantiate(_uniform(program, choice)), supplies)
        for choice in ("t4", "ccz1", "t7_d1", "ccz2_shallow")
    )
    best_mixed = min(
        execute_multi(program.instantiate(assignment), supplies)
        for assignment in program.iter_assignments()
    )
    assert best_mixed < pure


def test_unknown_resource_bank_is_rejected():
    with pytest.raises(KeyError):
        factories(1.0, 1.0).bank("Y")
