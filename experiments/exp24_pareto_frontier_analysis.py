"""Experiment 24: Pareto frontier analysis for resource-aware strategies."""

from __future__ import annotations

from common_v6 import (
    FIGURE_DIR_V6,
    POLICIES_V6,
    RESULT_DIR_V6,
    ResourceWeights,
    load_v6_settings,
    oracle_strategy,
    pareto_status,
    policy_strategy,
    read_csv,
    strategy_metrics,
    write_csv,
)
import random


PER_CASE_FIELDNAMES = [
    "case_id",
    "workload",
    "family",
    "seed",
    "n",
    "policy",
    "chosen_strategy",
    "T_exe_over_T_ref",
    "BacklogArea",
    "DeltaC",
    "DeltaB",
    "pareto_optimal",
    "near_pareto",
    "nontrivial_case",
]

SUMMARY_FIELDNAMES = [
    "policy",
    "pareto_optimal_rate",
    "near_pareto_rate",
    "pareto_optimal_rate_nontrivial",
    "near_pareto_rate_nontrivial",
]


def main() -> None:
    settings = load_v6_settings()
    rng = random.Random(608)
    weights = ResourceWeights(lambda_A=0.01, lambda_C=0.05, lambda_B=0.01)
    rows = []
    for setting in settings:
        case_id = "|".join(map(str, setting.key))
        for policy in POLICIES_V6:
            chosen = policy_strategy(setting, policy, weights, rng)
            metrics = strategy_metrics(setting, chosen)
            optimal, near = pareto_status(setting, chosen)
            rows.append(
                {
                    "case_id": case_id,
                    "workload": setting.workload,
                    "family": setting.family,
                    "seed": setting.seed,
                    "n": setting.n,
                    "policy": policy,
                    "chosen_strategy": chosen,
                    "T_exe_over_T_ref": metrics["T_exe_over_T_ref"],
                    "BacklogArea": metrics["BacklogArea"],
                    "DeltaC": metrics["DeltaC"],
                    "DeltaB": metrics["DeltaB"],
                    "pareto_optimal": int(optimal),
                    "near_pareto": int(near),
                    "nontrivial_case": int(setting.nontrivial),
                }
            )
    out_path = RESULT_DIR_V6 / "exp24_pareto_frontier_per_case.csv"
    write_csv(out_path, rows, PER_CASE_FIELDNAMES)
    summary = _summary(rows)
    write_csv(RESULT_DIR_V6 / "exp24_pareto_frontier_summary.csv", summary, SUMMARY_FIELDNAMES)
    _fig_pareto(summary)
    _write_report()
    print(f"Wrote {len(rows)} rows to {out_path}")


def _summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    from collections import defaultdict

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["policy"]].append(row)
    summary = []
    for policy, group in sorted(grouped.items()):
        nontrivial = [row for row in group if int(row["nontrivial_case"]) == 1]
        summary.append(
            {
                "policy": policy,
                "pareto_optimal_rate": sum(int(row["pareto_optimal"]) for row in group) / len(group),
                "near_pareto_rate": sum(int(row["near_pareto"]) for row in group) / len(group),
                "pareto_optimal_rate_nontrivial": sum(int(row["pareto_optimal"]) for row in nontrivial) / len(nontrivial)
                if nontrivial
                else 0.0,
                "near_pareto_rate_nontrivial": sum(int(row["near_pareto"]) for row in nontrivial) / len(nontrivial)
                if nontrivial
                else 0.0,
            }
        )
    return summary


def _fig_pareto(summary: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    policies = [row["policy"] for row in summary]
    x = list(range(len(policies)))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(
        [value - 0.18 for value in x],
        [float(row["pareto_optimal_rate"]) for row in summary],
        width=0.36,
        label="Pareto optimal",
    )
    ax.bar(
        [value + 0.18 for value in x],
        [float(row["near_pareto_rate"]) for row in summary],
        width=0.36,
        label="Near Pareto",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(policies, rotation=25, ha="right")
    ax.set_ylabel("rate")
    ax.set_title("Pareto frontier selection rate")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V6 / "fig4_pareto_optimality_rate.pdf")


def _write_report() -> None:
    exp22 = read_csv(RESULT_DIR_V6 / "exp22_resource_penalty_sweep_summary.csv")
    exp23 = read_csv(RESULT_DIR_V6 / "exp23_budget_constrained_summary.csv")
    exp24 = read_csv(RESULT_DIR_V6 / "exp24_pareto_frontier_summary.csv")
    main_rows = [
        row
        for row in exp22
        if abs(float(row["lambda_A"]) - 0.01) < 1e-12
        and abs(float(row["lambda_C"]) - 0.05) < 1e-12
        and abs(float(row["lambda_B"]) - 0.01) < 1e-12
    ]
    unpenalized = [
        row
        for row in exp22
        if abs(float(row["lambda_A"])) < 1e-12
        and abs(float(row["lambda_C"])) < 1e-12
        and abs(float(row["lambda_B"])) < 1e-12
    ]
    high_capacity_penalty = [
        row
        for row in exp22
        if abs(float(row["lambda_A"]) - 0.01) < 1e-12
        and abs(float(row["lambda_C"]) - 0.20) < 1e-12
        and abs(float(row["lambda_B"]) - 0.01) < 1e-12
    ]

    def row_for(rows, policy):
        return next(row for row in rows if row["policy"] == policy)

    regime = row_for(main_rows, "regime_aware")
    inc_c = row_for(main_rows, "always_increase_C")
    inc_c_free = row_for(unpenalized, "always_increase_C")
    smooth = row_for(main_rows, "always_smooth")
    regime_high_c = row_for(high_capacity_penalty, "regime_aware")
    inc_c_high_c = row_for(high_capacity_penalty, "always_increase_C")
    budget_regime = [
        row for row in exp23 if row["policy"] == "regime_aware" and row["C_budget"] == "1" and row["B_budget"] == "8"
    ][0]
    pareto_regime = row_for(exp24, "regime_aware")
    pareto_inc_c = row_for(exp24, "always_increase_C")

    if float(regime["mean_regret"]) < float(inc_c["mean_regret"]) and float(regime["mean_regret"]) <= float(smooth["mean_regret"]):
        recommendation = "resource-aware decision-tool claim supported"
    elif float(regime["mean_regret"]) <= float(smooth["mean_regret"]):
        recommendation = "resource-aware framework useful, but not dominant"
    else:
        recommendation = "diagnostic framing only"

    report = f"""# Preliminary Report V6

## Summary

Recommendation: **{recommendation}**.

V6 fixes the V5 caveat by charging for extra delivery capacity and buffer.

## Questions

1. Does always_increase_C dominate only when capacity is free?

   With zero resource penalties, always_increase_C mean regret is
   {float(inc_c_free['mean_regret']):.4f}. Under lambda_A=0.01,
   lambda_C=0.05, lambda_B=0.01, always_increase_C mean regret becomes
   {float(inc_c['mean_regret']):.4f}. This means the V5 caveat is reduced but
   not eliminated at the default resource prices: capacity expansion is still
   near-oracle for this workload/parameter set. At a stronger capacity penalty
   (lambda_C=0.20, lambda_B=0.01), regime-aware mean regret is
   {float(regime_high_c['mean_regret']):.4f} versus always_increase_C
   {float(inc_c_high_c['mean_regret']):.4f}.

2. Under positive capacity and buffer penalties, does regime_aware keep lower
   regret than naive policies?

   Regime-aware mean regret is {float(regime['mean_regret']):.4f};
   always_smooth is {float(smooth['mean_regret']):.4f};
   always_increase_C is {float(inc_c['mean_regret']):.4f}. Regime-aware clearly
   improves over always_smooth and capacity-aware style fixed policies, but it
   does not beat always_increase_C under the default cost setting.

3. How sensitive are conclusions to lambda_C, lambda_B, and lambda_A?

   See `exp22_resource_penalty_sweep_summary.csv` and Figures 1-2. The
   lambda_C=0 slice intentionally reproduces the V5 caveat.

4. Under budget constraints, does regime_aware remain close to budget oracle?

   At C_budget=1, B_budget=8, regime-aware mean regret is
   {float(budget_regime['mean_regret']):.4f} with infeasibility rate
   {float(budget_regime['infeasibility_rate']):.4f}.

5. Does regime-aware selection choose Pareto-optimal or near-Pareto strategies?

   Regime-aware Pareto optimal rate is
   {float(pareto_regime['pareto_optimal_rate']):.3f}; near-Pareto rate is
   {float(pareto_regime['near_pareto_rate']):.3f}. Always-increase-C Pareto
   optimal rate is {float(pareto_inc_c['pareto_optimal_rate']):.3f}.

6. Does the result still hold on nontrivial cases only?

   Regime-aware nontrivial mean regret is
   {float(regime['mean_regret_nontrivial']):.4f}; always_smooth nontrivial mean
   regret is {float(smooth['mean_regret_nontrivial']):.4f}; always-increase-C
   nontrivial mean regret is {float(inc_c['mean_regret_nontrivial']):.4f}.

7. What scoring settings should be used in the paper?

   Use lambda_A=0.01, lambda_C=0.05, lambda_B=0.01 as a transparent default,
   but do not claim it fully resolves the capacity-free caveat. The paper
   should show the full lambda_C/lambda_B sensitivity, and capacity-free scores
   should be shown only as a caveat/reproduction of V5.

8. Is Paper 2 ready to write as a regime-aware, resource-aware framework paper?

   Current answer: **{recommendation}**. If always_increase_C remains best under
   positive capacity penalties, the framework should be presented as diagnostic
   rather than prescriptive.
"""
    (RESULT_DIR_V6 / "PRELIMINARY_REPORT_V6.md").write_text(report)


if __name__ == "__main__":
    main()
