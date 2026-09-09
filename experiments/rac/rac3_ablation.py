"""Ablation: which information does the cost model actually need?

The resource-aware compiler is run once per rung of an information ladder,
from a model that sees only dependencies to one that sees dependencies,
T-count, factory arrival timing and buffer capacity. Two things are measured
for each rung: how accurately it predicts constrained execution time, and how
good the implementation it selects turns out to be.

If a cheap rung selects as well as the full model, the extra machinery is not
justified and the proposed abstraction is too heavy for what it buys.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import (
    RESULT_DIR,
    program_meta,
    programs,
    ratio,
    summarize,
    write_csv,
)

from ftqc_delivery.rac.cost import estimate
from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.regimes import main_regimes
from ftqc_delivery.rac.select import (
    reference_best,
    select_resource_aware,
    uniform_assignments,
)


LADDER = (
    ("deps_only", "dependencies only (what T-depth sees)"),
    ("t_count_only", "T-count and average supply rate"),
    ("deps_plus_count", "dependencies + T-count"),
    ("deps_plus_throughput", "dependencies + arrival timing"),
    ("sccp", "dependencies + arrival timing + buffer"),
    ("sccp_plus", "full model with the fluid buffer-loss term"),
)

CASE_FIELDS = [
    "program",
    "kernel",
    "regime",
    "rate",
    "model",
    "description",
    "makespan",
    "reference",
    "regret",
    "reference_exhaustive",
    "prediction_error_mean",
    "prediction_error_max",
    "selected_best_candidate",
]

SUMMARY_FIELDS = [
    "model",
    "description",
    "cases",
    "regret_median",
    "regret_mean",
    "regret_p90",
    "regret_max",
    "prediction_error_mean",
    "prediction_error_max",
    "candidate_selection_accuracy",
]


def _prediction_quality(program, supply, model):
    """Return mean/max relative prediction error and whether the model ranks best."""

    errors = []
    best_true = None
    best_by_model = None
    best_model_value = None
    for assignment in uniform_assignments(program):
        dag = program.instantiate(assignment)
        true = execute(dag, supply, record_trace=False).makespan
        predicted = estimate(dag, supply, model=model)
        errors.append(abs(true - predicted) / true if true else 0.0)
        if best_true is None or true < best_true:
            best_true = true
        if best_model_value is None or predicted < best_model_value:
            best_model_value = predicted
            best_by_model = true
    if not errors:
        return 0.0, 0.0, 1
    return (
        sum(errors) / len(errors),
        max(errors),
        int(best_by_model == best_true),
    )


def _rows_for_program(index: int) -> list[dict[str, object]]:
    """Return every ablation row for one pilot program."""

    case_rows: list[dict[str, object]] = []
    program = programs()[index]
    if True:
        meta = program_meta(program)
        for regime in main_regimes():
            supply = regime.supply
            reference = reference_best(program, supply)
            for model, description in LADDER:
                assignment, _ = select_resource_aware(program, supply, model=model)
                makespan = execute(
                    program.instantiate(assignment), supply, record_trace=False
                ).makespan
                mean_error, max_error, ranked = _prediction_quality(
                    program, supply, model
                )
                case_rows.append(
                    {
                        "program": program.name,
                        "kernel": meta.get("kernel", ""),
                        "regime": regime.name,
                        "rate": round(regime.rate, 4),
                        "model": model,
                        "description": description,
                        "makespan": makespan,
                        "reference": reference.makespan,
                        "regret": round(ratio(makespan, reference.makespan), 4),
                        "reference_exhaustive": int(reference.exhaustive),
                        "prediction_error_mean": round(mean_error, 4),
                        "prediction_error_max": round(max_error, 4),
                        "selected_best_candidate": ranked,
                    }
                )
    return case_rows


def main() -> None:
    """Run the ablation over the pilot programs and the main rate sweep."""

    indices = list(range(len(programs())))
    case_rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for done, rows in enumerate(pool.imap_unordered(_rows_for_program, indices), 1):
            case_rows.extend(rows)
            print(f"  done {done}/{len(indices)}", flush=True)
    case_rows.sort(key=lambda row: (str(row["program"]), float(row["rate"]), str(row["model"])))

    summary_rows = []
    for model, description in LADDER:
        subset = [row for row in case_rows if row["model"] == model]
        regret = summarize(row["regret"] for row in subset)
        summary_rows.append(
            {
                "model": model,
                "description": description,
                "cases": len(subset),
                "regret_median": regret["median"],
                "regret_mean": regret["mean"],
                "regret_p90": regret["p90"],
                "regret_max": regret["max"],
                "prediction_error_mean": round(
                    sum(row["prediction_error_mean"] for row in subset) / len(subset), 4
                ),
                "prediction_error_max": round(
                    max(row["prediction_error_max"] for row in subset), 4
                ),
                "candidate_selection_accuracy": round(
                    sum(row["selected_best_candidate"] for row in subset) / len(subset),
                    4,
                ),
            }
        )

    write_csv(RESULT_DIR / "rac3_ablation_cases.csv", case_rows, CASE_FIELDS)
    write_csv(RESULT_DIR / "rac3_ablation_summary.csv", summary_rows, SUMMARY_FIELDS)

    print()
    print(f"{'model':22s} {'regret_med':>10s} {'regret_p90':>10s} {'pred_err':>9s} {'rank_acc':>8s}")
    for row in summary_rows:
        print(
            f"{row['model']:22s} {row['regret_median']:10.4f} {row['regret_p90']:10.4f} "
            f"{row['prediction_error_mean']:9.4f} {row['candidate_selection_accuracy']:8.3f}"
        )



if __name__ == "__main__":
    main()
