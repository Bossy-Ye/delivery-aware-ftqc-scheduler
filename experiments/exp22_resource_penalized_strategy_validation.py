"""Experiment 22: resource-penalized strategy validation."""

from __future__ import annotations

import random

from common_v6 import (
    FIGURE_DIR_V6,
    LAMBDA_A_VALUES,
    LAMBDA_B_VALUES,
    LAMBDA_C_VALUES,
    POLICIES_V6,
    RESULT_DIR_V6,
    ResourceWeights,
    load_v6_settings,
    oracle_strategy,
    policy_strategy,
    score_strategy,
    strategy_metrics,
    summarize_policy_rows,
    write_csv,
)


PER_CASE_FIELDNAMES = [
    "case_id",
    "workload",
    "family",
    "seed",
    "n",
    "C_base",
    "B_base",
    "regime_label",
    "recommended_strategy",
    "policy",
    "chosen_strategy",
    "lambda_A",
    "lambda_C",
    "lambda_B",
    "T_ref",
    "T_exe",
    "T_exe_over_T_ref",
    "BacklogArea",
    "normalized_BacklogArea",
    "DeltaC",
    "DeltaB",
    "score",
    "oracle_strategy",
    "oracle_score",
    "regret",
    "match",
    "nontrivial_case",
    "tie_case",
]


SUMMARY_FIELDNAMES = [
    "lambda_A",
    "lambda_C",
    "lambda_B",
    "policy",
    "match_rate",
    "match_rate_nontrivial",
    "mean_regret",
    "median_regret",
    "p95_regret",
    "mean_regret_nontrivial",
    "median_regret_nontrivial",
    "p95_regret_nontrivial",
]


def main() -> None:
    settings = load_v6_settings()
    rng = random.Random(606)
    rows = []
    for lambda_a in LAMBDA_A_VALUES:
        for lambda_c in LAMBDA_C_VALUES:
            for lambda_b in LAMBDA_B_VALUES:
                weights = ResourceWeights(lambda_A=lambda_a, lambda_C=lambda_c, lambda_B=lambda_b)
                for setting in settings:
                    oracle_name, oracle_score, oracle_ties = oracle_strategy(setting, weights)
                    case_id = "|".join(map(str, setting.key))
                    for policy in POLICIES_V6:
                        chosen = policy_strategy(setting, policy, weights, rng)
                        metrics = strategy_metrics(setting, chosen)
                        score = score_strategy(setting, chosen, weights)
                        rows.append(
                            {
                                "case_id": case_id,
                                "workload": setting.workload,
                                "family": setting.family,
                                "seed": setting.seed,
                                "n": setting.n,
                                "C_base": setting.C,
                                "B_base": setting.B,
                                "regime_label": setting.v4_regime_label,
                                "recommended_strategy": setting.v4_recommended_strategy,
                                "policy": policy,
                                "chosen_strategy": chosen,
                                "lambda_A": lambda_a,
                                "lambda_C": lambda_c,
                                "lambda_B": lambda_b,
                                "T_ref": metrics["T_ref"],
                                "T_exe": metrics["T_exe"],
                                "T_exe_over_T_ref": metrics["T_exe_over_T_ref"],
                                "BacklogArea": metrics["BacklogArea"],
                                "normalized_BacklogArea": metrics["normalized_BacklogArea"],
                                "DeltaC": metrics["DeltaC"],
                                "DeltaB": metrics["DeltaB"],
                                "score": score,
                                "oracle_strategy": oracle_name,
                                "oracle_score": oracle_score,
                                "regret": score - oracle_score,
                                "match": int(chosen in oracle_ties),
                                "nontrivial_case": int(setting.nontrivial),
                                "tie_case": int(len(oracle_ties) > 1),
                            }
                        )
    out_path = RESULT_DIR_V6 / "exp22_resource_penalized_policy_comparison.csv"
    write_csv(out_path, rows, PER_CASE_FIELDNAMES)
    summary = summarize_policy_rows(rows, ["lambda_A", "lambda_C", "lambda_B", "policy"])
    write_csv(
        RESULT_DIR_V6 / "exp22_resource_penalty_sweep_summary.csv",
        summary,
        SUMMARY_FIELDNAMES,
    )
    _fig_resource_sweep(summary, "mean_regret", "fig1_resource_penalty_sweep_mean_regret.pdf")
    _fig_resource_sweep(
        summary,
        "mean_regret_nontrivial",
        "fig2_nontrivial_regret_resource_penalty.pdf",
        title="Nontrivial mean regret",
    )
    print(f"Wrote {len(rows)} rows to {out_path}")


def _fig_resource_sweep(
    summary: list[dict[str, object]],
    field: str,
    filename: str,
    title: str = "Resource penalty sweep",
) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in summary
        if float(row["lambda_A"]) == 0.01
        and float(row["lambda_B"]) in {0.0, 0.01, 0.05}
        and row["policy"] in {
            "regime_aware",
            "always_smooth",
            "always_increase_C",
            "always_increase_B",
            "always_capacity_aware",
            "random",
        }
    ]
    policies = sorted({row["policy"] for row in rows})
    lambda_bs = sorted({float(row["lambda_B"]) for row in rows})
    fig, axes = plt.subplots(1, len(lambda_bs), figsize=(14, 4.5), sharey=True)
    if len(lambda_bs) == 1:
        axes = [axes]
    for ax, lambda_b in zip(axes, lambda_bs, strict=True):
        selected_b = [row for row in rows if float(row["lambda_B"]) == lambda_b]
        for policy in policies:
            selected = sorted(
                [row for row in selected_b if row["policy"] == policy],
                key=lambda row: float(row["lambda_C"]),
            )
            ax.plot(
                [float(row["lambda_C"]) for row in selected],
                [float(row[field]) for row in selected],
                marker="o",
                label=policy,
            )
        ax.set_title(f"lambda_B={lambda_b}")
        ax.set_xlabel("lambda_C")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel(field)
    axes[-1].legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V6 / filename)


if __name__ == "__main__":
    main()
