"""Shared utilities for V6 resource-aware validation."""

from __future__ import annotations

import csv
import os
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
EXPERIMENTS = ROOT / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))
MPLCONFIGDIR = Path("/private/tmp/delivery_aware_ftqc_scheduler_mpl")
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

from common_v5 import load_settings, outcome_blind_label, strategy_for_label
from common_v4 import (
    B_VALUES_STRATEGY,
    C_VALUES_STRATEGY,
    deterministic_result,
    schedule_for_v4,
    workload_index,
)
from ftqc_delivery.metrics.resource_objective import (
    ResourceWeights,
    budget_feasible,
    near_pareto,
    pareto_dominated,
    resource_penalized_score,
)


RESULT_DIR_V6 = ROOT / "results" / "prelim_v6"
FIGURE_DIR_V6 = ROOT / "figures" / "prelim_v6"
POLICIES_V6 = [
    "regime_aware",
    "always_smooth",
    "always_increase_B",
    "always_increase_C",
    "always_capacity_aware",
    "random",
    "oracle_resource_aware",
]
STRATEGY_FOR_POLICY = {
    "always_smooth": "smooth",
    "always_increase_B": "increase_B",
    "always_increase_C": "increase_C",
    "always_capacity_aware": "capacity_aware",
}
LAMBDA_C_VALUES = [0.0, 0.01, 0.03, 0.05, 0.10, 0.20]
LAMBDA_B_VALUES = [0.0, 0.002, 0.005, 0.01, 0.02, 0.05]
LAMBDA_A_VALUES = [0.0, 0.005, 0.01]
C_BUDGET_VALUES = [0, 1, 2]
B_BUDGET_VALUES = [0, 4, 8, 16]
_RESOURCE_METRICS_CACHE: dict[tuple[tuple[str, str, str, str, str, str], str], dict[str, float]] = {}


def ensure_output_dirs() -> None:
    RESULT_DIR_V6.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR_V6.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_output_dirs()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def strategy_metrics(setting, strategy: str) -> dict[str, float]:
    cache_key = (setting.key, strategy)
    if cache_key in _RESOURCE_METRICS_CACHE:
        return _RESOURCE_METRICS_CACHE[cache_key]
    row = setting.strategy_rows[strategy]
    t_ref = float(row["T_ref_asap"])
    if strategy in {"increase_C", "increase_B"}:
        metrics = _recomputed_resource_strategy_metrics(setting, strategy, t_ref)
        _RESOURCE_METRICS_CACHE[cache_key] = metrics
        return metrics
    t_exe = float(row["candidate_T_exe"])
    backlog_area = float(row["candidate_BacklogArea"])
    metrics = {
        "T_ref": t_ref,
        "T_exe": t_exe,
        "T_exe_over_T_ref": t_exe / t_ref,
        "BacklogArea": backlog_area,
        "normalized_BacklogArea": backlog_area / max(1.0, t_ref),
        "DeltaC": 0.0,
        "DeltaB": 0.0,
    }
    _RESOURCE_METRICS_CACHE[cache_key] = metrics
    return metrics


def _recomputed_resource_strategy_metrics(setting, strategy: str, t_ref: float) -> dict[str, float]:
    """Recompute V4 resource interventions and recover actual resource deltas.

    V4 stored the best increase_B/increase_C result but not the buffer/capacity
    value that produced it. V6 needs that value because resources are no longer
    free. We therefore replay the same V4 candidate set, restricted to
    no-decrease interventions, and break ties by the smallest added resource.
    """

    case = workload_index()[(setting.workload, setting.seed)]
    t_ref_int = int(t_ref)
    candidates: list[tuple[int, int, Any]] = []
    if strategy == "increase_C":
        candidate_capacities = sorted({setting.C, *[c for c in C_VALUES_STRATEGY if c >= setting.C]})
        for candidate_c in candidate_capacities:
            schedule = schedule_for_v4("smooth", case, candidate_c, setting.B)
            result = deterministic_result(case, schedule, candidate_c, setting.B, t_ref_int, strategy)
            candidates.append((candidate_c - setting.C, 0, result))
    elif strategy == "increase_B":
        candidate_buffers = sorted({setting.B, *[b for b in B_VALUES_STRATEGY if b >= setting.B]})
        for candidate_b in candidate_buffers:
            schedule = schedule_for_v4("smooth", case, setting.C, candidate_b)
            result = deterministic_result(case, schedule, setting.C, candidate_b, t_ref_int, strategy)
            candidates.append((0, candidate_b - setting.B, result))
    else:
        raise ValueError(f"Unsupported resource strategy {strategy}")

    delta_c, delta_b, best = min(
        candidates,
        key=lambda item: (item[2].T_exe, item[2].BacklogArea, item[0] + item[1], item[0], item[1]),
    )
    return {
        "T_ref": t_ref,
        "T_exe": float(best.T_exe),
        "T_exe_over_T_ref": float(best.T_exe) / t_ref,
        "BacklogArea": float(best.BacklogArea),
        "normalized_BacklogArea": float(best.BacklogArea) / max(1.0, t_ref),
        "DeltaC": float(delta_c),
        "DeltaB": float(delta_b),
    }


def score_strategy(setting, strategy: str, weights: ResourceWeights) -> float:
    metrics = strategy_metrics(setting, strategy)
    return resource_penalized_score(
        t_exe=metrics["T_exe"],
        t_ref=metrics["T_ref"],
        backlog_area=metrics["BacklogArea"],
        delta_c=metrics["DeltaC"],
        delta_b=metrics["DeltaB"],
        weights=weights,
    )


def all_strategy_scores(setting, weights: ResourceWeights) -> dict[str, float]:
    return {
        strategy: score_strategy(setting, strategy, weights)
        for strategy in setting.strategy_rows
    }


def oracle_strategy(setting, weights: ResourceWeights) -> tuple[str, float, list[str]]:
    scores = all_strategy_scores(setting, weights)
    best = min(scores.values())
    ties = [strategy for strategy, score in scores.items() if score <= best + 1e-9]
    return sorted(ties)[0], best, ties


def policy_strategy(setting, policy: str, weights: ResourceWeights, rng: random.Random) -> str:
    if policy == "regime_aware":
        return strategy_for_label(outcome_blind_label(setting.features))
    if policy == "oracle_resource_aware":
        return oracle_strategy(setting, weights)[0]
    if policy == "random":
        return rng.choice(sorted(setting.strategy_rows))
    return STRATEGY_FOR_POLICY[policy]


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, int(0.95 * (len(values) - 1)))
    return values[index]


def summarize_policy_rows(rows: list[dict[str, Any]], group_fields: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in group_fields)].append(row)
    summaries = []
    for key, group in sorted(grouped.items()):
        regrets = [float(row["regret"]) for row in group]
        nontrivial = [row for row in group if int(row["nontrivial_case"]) == 1]
        nontrivial_regrets = [float(row["regret"]) for row in nontrivial]
        summary = {field: value for field, value in zip(group_fields, key, strict=True)}
        summary.update(
            {
                "match_rate": sum(int(row["match"]) for row in group) / len(group),
                "match_rate_nontrivial": sum(int(row["match"]) for row in nontrivial) / len(nontrivial)
                if nontrivial
                else 0.0,
                "mean_regret": sum(regrets) / len(regrets),
                "median_regret": median(regrets),
                "p95_regret": p95(regrets),
                "mean_regret_nontrivial": sum(nontrivial_regrets) / len(nontrivial_regrets)
                if nontrivial_regrets
                else 0.0,
                "median_regret_nontrivial": median(nontrivial_regrets)
                if nontrivial_regrets
                else 0.0,
                "p95_regret_nontrivial": p95(nontrivial_regrets),
            }
        )
        summaries.append(summary)
    return summaries


def budget_oracle(setting, c_budget: int, b_budget: int, lambda_A: float = 0.01) -> tuple[str, float, list[str]]:
    feasible_scores = {}
    for strategy in setting.strategy_rows:
        metrics = strategy_metrics(setting, strategy)
        if budget_feasible(metrics["DeltaC"], metrics["DeltaB"], c_budget, b_budget):
            score = metrics["T_exe_over_T_ref"] + lambda_A * metrics["normalized_BacklogArea"]
            feasible_scores[strategy] = score
    if not feasible_scores:
        strategy = "smooth" if "smooth" in setting.strategy_rows else "none/static"
        metrics = strategy_metrics(setting, strategy)
        return strategy, metrics["T_exe_over_T_ref"] + lambda_A * metrics["normalized_BacklogArea"], [strategy]
    best = min(feasible_scores.values())
    ties = [strategy for strategy, score in feasible_scores.items() if score <= best + 1e-9]
    return sorted(ties)[0], best, ties


def policy_budget_strategy(setting, policy: str, c_budget: int, b_budget: int, rng: random.Random) -> tuple[str, bool, str]:
    if policy == "regime_aware":
        desired = strategy_for_label(outcome_blind_label(setting.features))
    elif policy == "oracle_resource_aware":
        desired = budget_oracle(setting, c_budget, b_budget)[0]
    elif policy == "random":
        desired = rng.choice(sorted(setting.strategy_rows))
    else:
        desired = STRATEGY_FOR_POLICY[policy]
    metrics = strategy_metrics(setting, desired)
    feasible = budget_feasible(metrics["DeltaC"], metrics["DeltaB"], c_budget, b_budget)
    if feasible:
        return desired, True, desired
    for fallback in ["smooth", "none/static", "capacity_aware"]:
        if fallback in setting.strategy_rows:
            fallback_metrics = strategy_metrics(setting, fallback)
            if budget_feasible(fallback_metrics["DeltaC"], fallback_metrics["DeltaB"], c_budget, b_budget):
                return desired, False, fallback
    return desired, False, desired


def pareto_status(setting, strategy: str) -> tuple[bool, bool]:
    metrics_by_strategy = {
        name: strategy_metrics(setting, name)
        for name in setting.strategy_rows
    }
    points = {
        name: (
            metrics["T_exe_over_T_ref"],
            metrics["BacklogArea"],
            metrics["DeltaC"],
            metrics["DeltaB"],
        )
        for name, metrics in metrics_by_strategy.items()
    }
    candidate = points[strategy]
    dominated = pareto_dominated(candidate, [point for name, point in points.items() if name != strategy])
    pareto_points = [
        point
        for name, point in points.items()
        if not pareto_dominated(point, [other for other_name, other in points.items() if other_name != name])
    ]
    return not dominated, near_pareto(candidate, pareto_points)


def load_v6_settings():
    return load_settings()
