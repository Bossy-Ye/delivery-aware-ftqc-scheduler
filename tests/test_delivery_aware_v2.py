"""Tests for DA-v2 candidate generation and schedule validity."""

from __future__ import annotations

from ftqc_delivery.schedulers import generate_candidate_subsets, schedule_delivery_aware_v2
from ftqc_delivery.workloads import make_high_compressibility


def test_candidate_subsets_include_mandatory_and_empty_when_feasible() -> None:
    ready_t = ["a", "b", "c"]
    latest = {"a": 1, "b": 3, "c": 4}
    downstream = {"a": 0.2, "b": 1.0, "c": 0.5}

    candidates = generate_candidate_subsets(
        ready_t,
        latest,
        downstream,
        time_step=1,
        capacity=1,
        buffer=0,
    )

    assert ["a"] in candidates
    assert [] not in candidates
    assert all("a" in candidate for candidate in candidates)


def test_candidate_subsets_allow_empty_when_no_latest_start_risk() -> None:
    ready_t = ["a", "b"]
    latest = {"a": 3, "b": 4}
    downstream = {"a": 0.2, "b": 1.0}

    candidates = generate_candidate_subsets(
        ready_t,
        latest,
        downstream,
        time_step=1,
        capacity=1,
        buffer=0,
    )

    assert [] in candidates


def test_delivery_aware_v2_returns_valid_schedule() -> None:
    dag = make_high_compressibility(seed=0, n=8)
    schedule = schedule_delivery_aware_v2(dag, capacity=2, buffer=4)

    assert dag.is_valid_schedule(schedule)
