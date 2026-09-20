"""One case of the stateful-oracle study: a workload on a machine.

Used unchanged by the screening phase and by the full frozen matrix, so the
two cannot drift apart.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_marsq import ALL_POLICIES, P0, P1, P2, SEED, SIMPLE_POOL, ratio

from ftqc_delivery.mrc.corpus import BY_NAME, build_workload
from ftqc_delivery.mrc.execution import execute
from ftqc_delivery.mrc.features import structural_features
from ftqc_delivery.mrc.kernels import decision_sites
from ftqc_delivery.mrc.oracle import stateful_oracle
from ftqc_delivery.mrc.policies import heterogeneity, run_policy
from ftqc_delivery.mrc.resources import CCZ, T, Machine
from ftqc_delivery.mrc.stagedp import select_stage_dp

CASE_FIELDS = [
    "workload", "source", "family", "role", "machine", "model", "tiles", "ccz_share", "regime",
    "decision_sites", "stages", "max_stage_width", "wide_stage_fraction", "consuming_families",
    "mix_drift", "alternation_rate",
    "t_rate", "ccz_rate", "factory_tiles",
    *[f"makespan_{policy}" for policy in ALL_POLICIES],
    "makespan_best_simple", "best_simple_policy",
    "makespan_best_non_stateful", "best_non_stateful_policy",
    "makespan_stagedp", "seconds_stagedp",
    "makespan_oracle", "oracle_status", "oracle_seconds", "oracle_simulations", "lower_bound",
    "headroom_vs_best_non_stateful", "residual_headroom_vs_stagedp",
    "max_possible_headroom_vs_stagedp",
    "oracle_heterogeneity", "stagedp_heterogeneity",
    "oracle_t_stalls", "oracle_ccz_stalls", "oracle_t_waste", "oracle_ccz_waste",
    "stagedp_t_stalls", "stagedp_ccz_stalls", "stagedp_t_waste", "stagedp_ccz_waste",
    "oracle_space_time", "stagedp_space_time",
    "policy_seconds_total",
]


def _trace_metrics(program, assignment, machine: Machine, prefix: str) -> dict[str, object]:
    trace = execute(program.instantiate(assignment), machine)
    return {
        f"{prefix}_t_stalls": trace.stalls.get(T, 0),
        f"{prefix}_ccz_stalls": trace.stalls.get(CCZ, 0),
        f"{prefix}_t_waste": trace.overflow.get(T, 0),
        f"{prefix}_ccz_waste": trace.overflow.get(CCZ, 0),
        f"{prefix}_space_time": trace.makespan * machine.factory_tiles,
    }


def run_case(
    workload_name: str,
    machine_label: str,
    machine: Machine,
    role: str,
    exact_time_budget: float = 45.0,
    search_budget: float = 30.0,
) -> dict[str, object]:
    """Return one fully measured case."""

    workload = BY_NAME[workload_name]
    program = build_workload(workload_name).program
    features = structural_features(program)

    policy_start = time.perf_counter()
    outcomes = {policy: run_policy(policy, program, machine) for policy in ALL_POLICIES}
    policy_seconds = time.perf_counter() - policy_start

    start = time.perf_counter()
    stagedp = select_stage_dp(program, machine, mode="analytic", refine=5, include_uniform=True)
    stagedp_seconds = time.perf_counter() - start

    oracle = stateful_oracle(
        program,
        machine,
        exact_time_budget=exact_time_budget,
        search_budget=search_budget,
        extra_seeds=(stagedp.assignment,),
        seed=SEED,
    )

    best_simple = min(SIMPLE_POOL, key=lambda name: outcomes[name].makespan)
    non_stateful = {name: outcomes[name].makespan for name in (P0, P1, P2)}
    non_stateful[best_simple] = outcomes[best_simple].makespan
    best_non_stateful_policy = min(non_stateful, key=lambda name: non_stateful[name])
    best_non_stateful = non_stateful[best_non_stateful_policy]

    row: dict[str, object] = {
        "workload": workload_name,
        "source": workload.source,
        "family": workload.family,
        "role": role,
        "machine": machine_label,
        "decision_sites": len(decision_sites(program)),
        "stages": features["stages"],
        "max_stage_width": features["max_stage_width"],
        "wide_stage_fraction": round(features["wide_stage_fraction"], 4),
        "consuming_families": features["consuming_families"],
        "mix_drift": round(features["mix_drift"], 4),
        "alternation_rate": round(features["alternation_rate"], 4),
        "makespan_best_simple": outcomes[best_simple].makespan,
        "best_simple_policy": best_simple,
        "makespan_best_non_stateful": best_non_stateful,
        "best_non_stateful_policy": best_non_stateful_policy,
        "makespan_stagedp": stagedp.makespan,
        "seconds_stagedp": round(stagedp_seconds, 3),
        "makespan_oracle": oracle.makespan,
        "oracle_status": oracle.status,
        "oracle_seconds": round(oracle.seconds, 3),
        "oracle_simulations": oracle.simulations,
        "lower_bound": round(oracle.lower_bound, 2),
        "headroom_vs_best_non_stateful": round(
            ratio(best_non_stateful - oracle.makespan, best_non_stateful), 4
        ),
        "residual_headroom_vs_stagedp": round(
            ratio(stagedp.makespan - oracle.makespan, stagedp.makespan), 4
        ),
        "max_possible_headroom_vs_stagedp": round(
            max(0.0, ratio(stagedp.makespan - oracle.lower_bound, stagedp.makespan)), 4
        ),
        "oracle_heterogeneity": round(heterogeneity(program, oracle.assignment), 4),
        "stagedp_heterogeneity": round(heterogeneity(program, stagedp.assignment), 4),
        "policy_seconds_total": round(policy_seconds, 3),
    }
    for policy, outcome in outcomes.items():
        row[f"makespan_{policy}"] = outcome.makespan
    row.update(_trace_metrics(program, oracle.assignment, machine, "oracle"))
    row.update(_trace_metrics(program, stagedp.assignment, machine, "stagedp"))

    # The bound must never exceed anything actually executed: a violation
    # would mean the bound is wrong, and must stop the study rather than be
    # quietly reported.
    observed = min([oracle.makespan, stagedp.makespan] + [o.makespan for o in outcomes.values()])
    if oracle.lower_bound > observed + 1e-6:
        raise AssertionError(
            f"lower bound {oracle.lower_bound} exceeds observed {observed} "
            f"on {workload_name} / {machine_label}"
        )
    return row
