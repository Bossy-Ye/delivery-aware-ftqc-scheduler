"""Tests for the compilation policies and the optimality reference."""

from __future__ import annotations

import pytest

from ftqc_delivery.mrc.execution import execute, resource_counts
from ftqc_delivery.mrc.kernels import (
    and_ladder,
    decision_sites,
    modular_exponentiation,
    oracle_bank,
    trotter_layers,
)
from ftqc_delivery.mrc.policies import (
    POLICIES,
    concurrent_site_counts,
    feasible_names,
    global_oracle,
    heterogeneity,
    mixture,
    run_policy,
    space_time,
    t_equivalents,
    two_term_bound,
    uniform_assignments,
)
from ftqc_delivery.mrc.resources import CCZ, T, build_machine, machine_for_capacity


MACHINE = machine_for_capacity(0.5, 0.5)


def test_t_equivalents_price_a_ccz_as_two_t():
    assert t_equivalents({T: 4, CCZ: 3}) == pytest.approx(10.0)
    assert mixture({T: 4, CCZ: 2}) == pytest.approx(0.5)


def test_uniform_assignments_compile_each_family_the_same_way():
    program = trotter_layers(terms=2, layers=2, bits=6)
    for assignment in uniform_assignments(program, MACHINE):
        by_family: dict[str, set[str]] = {}
        for site in decision_sites(program):
            by_family.setdefault(site.family, set()).add(assignment[site.site_id])
        assert all(len(names) == 1 for names in by_family.values())


def test_heterogeneity_ignores_differences_between_families():
    program = trotter_layers(terms=2, layers=2, bits=6)
    uniform = uniform_assignments(program, MACHINE)[0]
    assert heterogeneity(program, uniform) == 0.0
    sites = decision_sites(program)
    mixed = dict(uniform)
    other = [n for n in sites[0].variant_names if n != mixed[sites[0].site_id]][0]
    mixed[sites[0].site_id] = other
    assert heterogeneity(program, mixed) > 0.0


def test_feasible_names_drop_variants_the_machine_cannot_run():
    t_only = build_machine(t_factories=4, ccz_factories=0)
    program = trotter_layers(terms=1, layers=1, bits=6)
    site = decision_sites(program)[0]
    allowed = feasible_names(site, t_only)
    assert allowed
    for name in allowed:
        counts = resource_counts(site.variant(name).fragment.to_dag(name))
        assert CCZ not in counts


def test_every_policy_runs_on_a_single_bank_machine():
    t_only = build_machine(t_factories=4, ccz_factories=0)
    program = trotter_layers(terms=2, layers=1, bits=6)
    for policy in POLICIES:
        outcome = run_policy(policy, program, t_only)
        assert outcome.makespan > 0


def test_concurrency_counts_reflect_the_kernel_shape():
    serial = modular_exponentiation(width=16, steps=2)
    wide = oracle_bank(controls=8, lanes=4)
    assert max(
        concurrent_site_counts(serial)[site.site_id] for site in decision_sites(serial)
    ) == 1
    assert max(
        concurrent_site_counts(wide)[site.site_id] for site in decision_sites(wide)
    ) == 4


def test_the_exhaustive_oracle_dominates_every_policy():
    program = and_ladder(stages=2, lanes=2)
    machine = machine_for_capacity(0.5, 0.5)
    oracle = global_oracle(program, machine, limit=100_000)
    assert oracle.exhaustive
    for policy in POLICIES:
        assert run_policy(policy, program, machine).makespan >= oracle.makespan


def test_the_two_term_bound_never_exceeds_the_simulated_makespan():
    program = trotter_layers(terms=2, layers=2, bits=6)
    for share in (0.25, 0.5, 0.75):
        machine = machine_for_capacity(0.5, share)
        for assignment in uniform_assignments(program, machine):
            dag = program.instantiate(assignment)
            assert two_term_bound(dag, machine) <= execute(dag, machine).makespan + 1


def test_space_time_charges_for_the_factories():
    program = trotter_layers(terms=2, layers=1, bits=6)
    assignment = uniform_assignments(program, MACHINE)[0]
    small = machine_for_capacity(0.25, 0.5)
    large = machine_for_capacity(2.0, 0.5)
    assert space_time(program, assignment, large, 100, 32) > space_time(
        program, assignment, small, 100, 32
    )


def test_an_unknown_policy_is_rejected():
    with pytest.raises(ValueError):
        run_policy("does_not_exist", oracle_bank(controls=8, lanes=2), MACHINE)
