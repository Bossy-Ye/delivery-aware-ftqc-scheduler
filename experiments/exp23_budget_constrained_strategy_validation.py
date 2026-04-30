"""Experiment 23: budget-constrained strategy validation."""

from __future__ import annotations

import random

from common_v6 import (
    B_BUDGET_VALUES,
    C_BUDGET_VALUES,
    FIGURE_DIR_V6,
    POLICIES_V6,
    RESULT_DIR_V6,
    budget_oracle,
    load_v6_settings,
    policy_budget_strategy,
    strategy_metrics,
    write_csv,
)


PER_CASE_FIELDNAMES = [
    "case_id",
    "workload",
    "family",
    "seed",
    "n",
    "C_budget",
    "B_budget",
    "policy",
    "desired_strategy",
    "chosen_strategy",
    "strict_feasible",
    "fallback_used",
    "oracle_strategy",
    "chosen_score",
    "oracle_score",
    "regret",
    "match",
    "nontrivial_case",
]

SUMMARY_FIELDNAMES = [
    "C_budget",
    "B_budget",
    "policy",
    "match_rate_to_budget_oracle",
    "mean_regret",
    "median_regret",
    "p95_regret",
    "infeasibility_rate",
    "mean_regret_nontrivial",
]


def main() -> None:
    settings = load_v6_settings()
    rng = random.Random(607)
    rows = []
    for c_budget in C_BUDGET_VALUES:
        for b_budget in B_BUDGET_VALUES:
            for setting in settings:
                oracle_name, oracle_score, oracle_ties = budget_oracle(setting, c_budget, b_budget)
                case_id = "|".join(map(str, setting.key))
                for policy in POLICIES_V6:
                    desired, strict_feasible, chosen = policy_budget_strategy(
                        setting, policy, c_budget, b_budget, rng
                    )
                    metrics = strategy_metrics(setting, chosen)
                    chosen_score = metrics["T_exe_over_T_ref"] + 0.01 * metrics["normalized_BacklogArea"]
                    rows.append(
                        {
                            "case_id": case_id,
                            "workload": setting.workload,
                            "family": setting.family,
                            "seed": setting.seed,
                            "n": setting.n,
                            "C_budget": c_budget,
                            "B_budget": b_budget,
                            "policy": policy,
                            "desired_strategy": desired,
                            "chosen_strategy": chosen,
                            "strict_feasible": int(strict_feasible),
                            "fallback_used": int(desired != chosen),
                            "oracle_strategy": oracle_name,
                            "chosen_score": chosen_score,
                            "oracle_score": oracle_score,
                            "regret": chosen_score - oracle_score,
                            "match": int(chosen in oracle_ties),
                            "nontrivial_case": int(setting.nontrivial),
                        }
                    )
    out_path = RESULT_DIR_V6 / "exp23_budget_constrained_policy_comparison.csv"
    write_csv(out_path, rows, PER_CASE_FIELDNAMES)
    summary = _summary(rows)
    write_csv(RESULT_DIR_V6 / "exp23_budget_constrained_summary.csv", summary, SUMMARY_FIELDNAMES)
    _fig_budget(summary)
    print(f"Wrote {len(rows)} rows to {out_path}")


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(0.95 * (len(values) - 1)))]


def _summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    from collections import defaultdict
    from statistics import median

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["C_budget"], row["B_budget"], row["policy"])].append(row)
    summary = []
    for (c_budget, b_budget, policy), group in sorted(grouped.items()):
        regrets = [float(row["regret"]) for row in group]
        nontrivial = [row for row in group if int(row["nontrivial_case"]) == 1]
        nontrivial_regrets = [float(row["regret"]) for row in nontrivial]
        summary.append(
            {
                "C_budget": c_budget,
                "B_budget": b_budget,
                "policy": policy,
                "match_rate_to_budget_oracle": sum(int(row["match"]) for row in group) / len(group),
                "mean_regret": sum(regrets) / len(regrets),
                "median_regret": median(regrets),
                "p95_regret": _p95(regrets),
                "infeasibility_rate": 1.0 - sum(int(row["strict_feasible"]) for row in group) / len(group),
                "mean_regret_nontrivial": sum(nontrivial_regrets) / len(nontrivial_regrets)
                if nontrivial_regrets
                else 0.0,
            }
        )
    return summary


def _fig_budget(summary: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in summary
        if int(row["B_budget"]) in {0, 8, 16}
        and row["policy"] in {
            "regime_aware",
            "always_smooth",
            "always_increase_C",
            "always_increase_B",
            "always_capacity_aware",
            "random",
        }
    ]
    budgets = sorted({int(row["B_budget"]) for row in rows})
    fig, axes = plt.subplots(1, len(budgets), figsize=(14, 4.5), sharey=True)
    if len(budgets) == 1:
        axes = [axes]
    for ax, b_budget in zip(axes, budgets, strict=True):
        selected_b = [row for row in rows if int(row["B_budget"]) == b_budget]
        for policy in sorted({row["policy"] for row in selected_b}):
            selected = sorted(
                [row for row in selected_b if row["policy"] == policy],
                key=lambda row: int(row["C_budget"]),
            )
            ax.plot(
                [int(row["C_budget"]) for row in selected],
                [float(row["mean_regret"]) for row in selected],
                marker="o",
                label=policy,
            )
        ax.set_title(f"B_budget={b_budget}")
        ax.set_xlabel("C_budget")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("mean regret")
    axes[-1].legend(fontsize=7)
    fig.suptitle("Budget-constrained regret")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V6 / "fig3_budget_constrained_regret.pdf")


if __name__ == "__main__":
    main()
