"""Basic scheduler validity tests."""

from __future__ import annotations

from ftqc_delivery.metrics.delta_max import t_demand_trace
from ftqc_delivery.schedulers import (
    schedule_capacity_aware,
    schedule_delivery_aware,
    schedule_smooth,
    schedule_static,
)
from ftqc_delivery.workloads import make_high_compressibility, make_low_compressibility


def test_all_schedulers_return_valid_schedules() -> None:
    dag = make_high_compressibility(seed=0, n=8)
    schedules = [
        schedule_static(dag),
        schedule_capacity_aware(dag, capacity=2),
        schedule_smooth(dag, capacity=2),
        schedule_delivery_aware(dag, capacity=2, buffer=4),
    ]

    assert all(dag.is_valid_schedule(schedule) for schedule in schedules)


def test_capacity_aware_respects_quota() -> None:
    dag = make_high_compressibility(seed=0, n=8)
    schedule = schedule_capacity_aware(dag, capacity=2)
    demand = t_demand_trace(dag, schedule)

    assert max(demand.values()) <= 2


def test_delivery_aware_does_not_badly_degrade_low_control() -> None:
    dag = make_low_compressibility(seed=0, n=8)
    static_schedule = schedule_static(dag)
    da_schedule = schedule_delivery_aware(dag, capacity=1, buffer=0)

    assert dag.is_valid_schedule(da_schedule)
    assert max(da_schedule) <= max(static_schedule) + 2
