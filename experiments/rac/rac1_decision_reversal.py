"""Gate 1: does a T-depth-oriented compiler pick the wrong implementation?

For every pilot program and every supply regime the script enumerates the
implementations a library-style compiler could emit, records their static
metrics and their constrained execution time, and asks two questions:

1. Pairwise: how often is a lower-T-depth implementation actually slower?
2. Selection: how much slower is the T-depth-optimal implementation than the
   fastest one?

Two controls run alongside the main sweep and exist to falsify the claim.
``unconstrained`` removes the supply limit; every reversal must disappear
there, otherwise the effect was never about magic states. ``clifford_weight=0``
makes Clifford operations free, which removes the possibility that the effect
is merely T-depth ignoring Clifford cost.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import (
    RESULT_DIR,
    assignment_space,
    assignment_token,
    circuit_metrics,
    program_meta,
    programs,
    ratio,
    site_count,
    summarize,
    variant_profile,
    write_csv,
)

from ftqc_delivery.rac.analysis import t_count
from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.regimes import main_regimes, unconstrained_regime
from ftqc_delivery.rac.select import uniform_assignments


CANDIDATE_FIELDS = [
    "program",
    "kernel",
    "concurrency",
    "decision_sites",
    "assignment_space",
    "regime",
    "rate",
    "buffer",
    "clifford_weight",
    "candidate",
    "variant_profile",
    "t_count",
    "t_depth",
    "logical_depth",
    "peak_demand",
    "burstiness",
    "ancilla_width",
    "makespan",
    "supply_stall_cycles",
    "overflow",
]

CASE_FIELDS = [
    "program",
    "kernel",
    "concurrency",
    "regime",
    "rate",
    "clifford_weight",
    "num_candidates",
    "t_depth_choice",
    "best_choice",
    "t_depth_makespan",
    "t_count_makespan",
    "best_makespan",
    "regret_t_depth",
    "regret_t_count",
    "selection_reversal",
    "pairs_compared",
    "pairs_reversed",
    "pair_reversal_rate",
    "min_t_depth",
    "best_candidate_t_depth",
    "t_depth_ratio_of_best",
]

SUMMARY_FIELDS = [
    "regime",
    "rate",
    "clifford_weight",
    "cases",
    "selection_reversal_rate",
    "pair_reversal_rate",
    "regret_t_depth_mean",
    "regret_t_depth_median",
    "regret_t_depth_p90",
    "regret_t_depth_p95",
    "regret_t_depth_max",
    "regret_t_count_median",
    "regret_t_count_max",
]


def _candidate_rows(program, regime, clifford_weight):
    rows = []
    for index, assignment in enumerate(uniform_assignments(program)):
        dag = program.instantiate(assignment)
        trace = execute(
            dag, regime.supply, clifford_weight=clifford_weight, record_trace=False
        )
        metrics = circuit_metrics(dag, clifford_weight)
        rows.append(
            {
                "assignment": assignment,
                "token": assignment_token(assignment),
                "index": index,
                "metrics": metrics,
                "makespan": trace.makespan,
                "stalls": trace.supply_stall_cycles,
                "overflow": trace.overflow,
            }
        )
    return rows


def _pair_reversals(rows):
    compared = 0
    reversed_pairs = 0
    for left in rows:
        for right in rows:
            if left is right:
                continue
            if left["metrics"]["t_depth"] >= right["metrics"]["t_depth"]:
                continue
            compared += 1
            if left["makespan"] > right["makespan"]:
                reversed_pairs += 1
    return compared, reversed_pairs


def main() -> None:
    """Run the Gate 1 sweep and write candidate, per-case and summary tables."""

    candidate_rows: list[dict[str, object]] = []
    case_rows: list[dict[str, object]] = []

    for program in programs():
        meta = program_meta(program)
        states = t_count(program.instantiate(program.default_assignment()))
        regimes = list(main_regimes()) + [unconstrained_regime(states)]
        for clifford_weight in (1, 0):
            for regime in regimes:
                rows = _candidate_rows(program, regime, clifford_weight)
                if len(rows) < 2:
                    continue

                for row in rows:
                    candidate_rows.append(
                        {
                            "program": program.name,
                            "kernel": meta.get("kernel", ""),
                            "concurrency": meta.get("concurrency", ""),
                            "decision_sites": site_count(program),
                            "assignment_space": assignment_space(program),
                            "regime": regime.name,
                            "rate": round(regime.rate, 4),
                            "buffer": regime.supply.buffer_capacity,
                            "clifford_weight": clifford_weight,
                            "candidate": variant_profile(row["assignment"]),
                            "variant_profile": row["token"],
                            "makespan": row["makespan"],
                            "supply_stall_cycles": row["stalls"],
                            "overflow": row["overflow"],
                            **row["metrics"],
                        }
                    )

                by_t_depth = min(
                    rows,
                    key=lambda row: (
                        row["metrics"]["t_depth"],
                        row["metrics"]["t_count"],
                        row["index"],
                    ),
                )
                by_t_count = min(
                    rows,
                    key=lambda row: (
                        row["metrics"]["t_count"],
                        row["metrics"]["t_depth"],
                        row["index"],
                    ),
                )
                best = min(rows, key=lambda row: (row["makespan"], row["index"]))
                compared, reversed_pairs = _pair_reversals(rows)

                case_rows.append(
                    {
                        "program": program.name,
                        "kernel": meta.get("kernel", ""),
                        "concurrency": meta.get("concurrency", ""),
                        "regime": regime.name,
                        "rate": round(regime.rate, 4),
                        "clifford_weight": clifford_weight,
                        "num_candidates": len(rows),
                        "t_depth_choice": variant_profile(by_t_depth["assignment"]),
                        "best_choice": variant_profile(best["assignment"]),
                        "t_depth_makespan": by_t_depth["makespan"],
                        "t_count_makespan": by_t_count["makespan"],
                        "best_makespan": best["makespan"],
                        "regret_t_depth": round(
                            ratio(by_t_depth["makespan"], best["makespan"]), 4
                        ),
                        "regret_t_count": round(
                            ratio(by_t_count["makespan"], best["makespan"]), 4
                        ),
                        "selection_reversal": int(
                            by_t_depth["makespan"] > best["makespan"]
                        ),
                        "pairs_compared": compared,
                        "pairs_reversed": reversed_pairs,
                        "pair_reversal_rate": round(ratio(reversed_pairs, compared), 4)
                        if compared
                        else 0.0,
                        "min_t_depth": by_t_depth["metrics"]["t_depth"],
                        "best_candidate_t_depth": best["metrics"]["t_depth"],
                        "t_depth_ratio_of_best": round(
                            ratio(
                                best["metrics"]["t_depth"],
                                by_t_depth["metrics"]["t_depth"],
                            ),
                            4,
                        ),
                    }
                )

    summary_rows = []
    keys = sorted({(row["regime"], row["clifford_weight"]) for row in case_rows})
    for regime_name, clifford_weight in keys:
        subset = [
            row
            for row in case_rows
            if row["regime"] == regime_name and row["clifford_weight"] == clifford_weight
        ]
        rate = (
            round(sum(row["rate"] for row in subset) / len(subset), 4)
            if regime_name != "unconstrained"
            else float("inf")
        )
        regret_depth = summarize(row["regret_t_depth"] for row in subset)
        regret_count = summarize(row["regret_t_count"] for row in subset)
        compared = sum(row["pairs_compared"] for row in subset)
        reversed_pairs = sum(row["pairs_reversed"] for row in subset)
        summary_rows.append(
            {
                "regime": regime_name,
                "rate": rate,
                "clifford_weight": clifford_weight,
                "cases": len(subset),
                "selection_reversal_rate": round(
                    sum(row["selection_reversal"] for row in subset) / len(subset), 4
                ),
                "pair_reversal_rate": round(ratio(reversed_pairs, compared), 4)
                if compared
                else 0.0,
                "regret_t_depth_mean": regret_depth["mean"],
                "regret_t_depth_median": regret_depth["median"],
                "regret_t_depth_p90": regret_depth["p90"],
                "regret_t_depth_p95": regret_depth["p95"],
                "regret_t_depth_max": regret_depth["max"],
                "regret_t_count_median": regret_count["median"],
                "regret_t_count_max": regret_count["max"],
            }
        )

    write_csv(RESULT_DIR / "rac1_candidates.csv", candidate_rows, CANDIDATE_FIELDS)
    write_csv(RESULT_DIR / "rac1_cases.csv", case_rows, CASE_FIELDS)
    write_csv(RESULT_DIR / "rac1_summary.csv", summary_rows, SUMMARY_FIELDS)

    print(f"candidates: {len(candidate_rows)} rows")
    print(f"cases:      {len(case_rows)} rows")
    print()
    header = f"{'regime':14s} {'cw':>2s} {'cases':>5s} {'sel.rev':>7s} {'pair.rev':>8s} {'median':>7s} {'p90':>6s} {'p95':>6s} {'max':>6s}"
    print(header)
    for row in summary_rows:
        print(
            f"{row['regime']:14s} {row['clifford_weight']:2d} {row['cases']:5d} "
            f"{row['selection_reversal_rate']:7.3f} {row['pair_reversal_rate']:8.3f} "
            f"{row['regret_t_depth_median']:7.3f} {row['regret_t_depth_p90']:6.3f} "
            f"{row['regret_t_depth_p95']:6.3f} {row['regret_t_depth_max']:6.3f}"
        )


if __name__ == "__main__":
    main()
