"""Tests for the distributed placement model and the branch-aware oracle."""

from __future__ import annotations

import numpy as np
import pytest

from ftqc_delivery.ddqc.census import Region
from ftqc_delivery.ddqc.placement import (
    DynamicProgram,
    Segment,
    build_network,
    evaluate,
    exhaustive_optimum,
    local_search,
    reconfiguration_oracle,
    weighted_cost,
    weights,
)


def divergent_control(p: float, m: int = 4) -> DynamicProgram:
    """q1 talks to q2 (group X) in one branch and to q5 (group Y) in the other.

    Group X = {2, 3, 4} and group Y = {5, 6, 7} are tightly coupled, so on two
    QPUs of capacity four they sit on different QPUs. Branch A couples q1 to
    q2 ``m`` times; branch B couples it to q5 ``2m`` times. Flattened, B always
    dominates; in expectation A dominates once p exceeds 2/3.
    """

    tight = [(2, 3), (3, 4), (2, 4), (5, 6), (6, 7), (5, 7)] * 10
    return DynamicProgram(
        "divergent_control",
        8,
        [
            Segment(pairs=tight),
            Segment(branches=[(p, [(1, 2)] * m), (1 - p, [(1, 5)] * (2 * m))]),
        ],
    )


def identical_control(p: float, m: int = 4) -> DynamicProgram:
    tight = [(2, 3), (3, 4), (2, 4), (5, 6), (6, 7), (5, 7)] * 10
    return DynamicProgram(
        "identical_control",
        8,
        [Segment(pairs=tight), Segment(branches=[(p, [(1, 2)] * m), (1 - p, [(1, 2)] * m)])],
    )


def best_static_expected(program: DynamicProgram, network, mode: str) -> float:
    """Return the expected cost of a compiler's optimum, ties broken in its favour."""

    w = weights(program, mode)
    _, optimal = exhaustive_optimum(w, program.n_qubits, network)
    return min(evaluate(program, placement, network)["expected_epr"] for placement in optimal)


def test_network_distances():
    line = build_network(4, 2, "line")
    assert line.distance[0, 3] == 3 and line.distance[1, 2] == 1
    ring = build_network(4, 2, "ring")
    assert ring.distance[0, 3] == 1 and ring.distance[0, 2] == 2
    grid = build_network(4, 2, "grid")
    assert grid.distance[0, 3] == 2
    full = build_network(4, 2, "full")
    assert (full.distance[np.triu_indices(4, 1)] == 1).all()


def test_flat_weights_every_branch_one_and_expected_weights_by_probability():
    program = divergent_control(0.9, m=1)
    flat = weights(program, "flat")
    expected = weights(program, "expected")
    blind = weights(program, "blind")
    assert flat[(1, 2)] == 1 and flat[(1, 5)] == 2
    assert expected[(1, 2)] == pytest.approx(0.9) and expected[(1, 5)] == pytest.approx(0.2)
    assert (1, 2) not in blind and (1, 5) not in blind


def test_strong_divergence_control_shows_headroom_and_the_placement_flips():
    network = build_network(2, 4, "line")
    # p = 0.9: branch A is likely, so q1 belongs with group X.
    flat = best_static_expected(divergent_control(0.9), network, "flat")
    aware = best_static_expected(divergent_control(0.9), network, "expected")
    assert flat == pytest.approx(0.9 * 4)  # flat puts q1 with Y; A (p=.9, 4 gates) is remote
    assert aware == pytest.approx(0.1 * 8)  # aware puts q1 with X; B (p=.1, 8 gates) is remote
    assert (flat - aware) / flat > 0.75
    # p = 0.5: flattening already makes the right call.
    flat_half = best_static_expected(divergent_control(0.5), network, "flat")
    aware_half = best_static_expected(divergent_control(0.5), network, "expected")
    assert flat_half == pytest.approx(aware_half)


def test_identical_branches_give_no_headroom():
    network = build_network(2, 4, "line")
    for p in (0.1, 0.5, 0.9):
        flat = best_static_expected(identical_control(p), network, "flat")
        aware = best_static_expected(identical_control(p), network, "expected")
        assert flat == pytest.approx(aware)


def test_reconfiguration_oracle_is_charged_for_moves_and_never_worse_than_static():
    network = build_network(2, 4, "line")
    program = divergent_control(0.5, m=6)
    aware = best_static_expected(program, network, "expected")
    oracle = reconfiguration_oracle(program, network)
    assert oracle is not None
    assert oracle["expected_epr"] <= aware + 1e-9
    # With six-fold interactions, moving q1 (and swapping out q0) pays.
    assert oracle["reconfiguration_epr"] > 0
    assert oracle["expected_epr"] >= oracle["reconfiguration_epr"] - 1e-9


def test_reconfiguration_does_not_pay_for_a_single_conditional_gate():
    """Teleporting a qubit costs as much as the one remote gate it would save."""

    network = build_network(2, 2, "line")
    program = DynamicProgram(
        "single_gate",
        4,
        [Segment(pairs=[(0, 1), (2, 3)] * 5), Segment(branches=[(0.5, [(0, 2)]), (0.5, [])])],
    )
    aware = best_static_expected(program, network, "expected")
    oracle = reconfiguration_oracle(program, network)
    assert oracle["expected_epr"] == pytest.approx(aware)
    assert oracle["reconfiguration_epr"] == 0


def test_local_search_matches_the_exhaustive_optimum_on_small_cases():
    rng = np.random.default_rng(7)
    for trial in range(12):
        n, k, cap = 8, 3, 3
        pairs = [tuple(sorted(rng.choice(n, 2, replace=False))) for _ in range(20)]
        w: dict = {}
        for pair in pairs:
            w[pair] = w.get(pair, 0.0) + float(rng.integers(1, 4))
        for topology in ("line", "full"):
            network = build_network(k, cap, topology)
            exact, _ = exhaustive_optimum(w, n, network)
            found, placement = local_search(w, n, network, seed=trial)
            assert found == pytest.approx(exact)
            assert np.bincount(placement, minlength=k).max() <= cap
            assert weighted_cost(w, placement, network.distance) == pytest.approx(found)


def test_census_classifies_the_motivating_example_as_divergent():
    region = Region(kind="if", branches=[[("cx", (1, 2))], [("cx", (1, 8))]])
    assert region.classify() == "divergent"
    assert Region(kind="if", branches=[[("x", (3,))], []]).classify() == "local"
    assert Region(kind="if", branches=[[("cz", (1, 2))], []]).classify() == "present_absent"
    assert Region(kind="if", branches=[[("cx", (1, 2))], [("cx", (2, 1))]]).classify() == "identical"


def test_every_route_uses_only_real_links_on_every_topology():
    for k, topology in ((4, "line"), (4, "ring"), (4, "grid"), (4, "full"), (3, "ring")):
        network = build_network(k, 2, topology)
        links = set(network.links)
        for (a, b), route in network.routes.items():
            assert len(route) == network.distance[a, b]
            assert set(route) <= links
