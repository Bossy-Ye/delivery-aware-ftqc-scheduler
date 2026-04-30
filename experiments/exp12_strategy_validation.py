"""Experiment 12: validate recommended strategies by regime."""

from __future__ import annotations

from common_v4 import (
    EPSILON_VALUES,
    RESULT_DIR_V4,
    candidate_strategy_results,
    empirical_best_strategy,
    read_csv,
    relative_gain,
    backlog_area_gain,
    strategy_success_reason,
    threshold_scan_for_strategy,
    workload_index,
    write_csv,
    FIGURE_DIR_V4,
    SCHEDULE_COLORS,
)


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "regime_label",
    "recommended_strategy",
    "baseline_strategy",
    "candidate_strategy",
    "T_ref_asap",
    "baseline_T_exe",
    "candidate_T_exe",
    "strategy_gain_Texe",
    "baseline_BacklogArea",
    "candidate_BacklogArea",
    "strategy_gain_BacklogArea",
    "baseline_L_backlog",
    "candidate_L_backlog",
    "strategy_gain_Lbacklog",
    "C_ref_star_0.05",
    "C_ref_star_0.10",
    "B_ref_star_0.05",
    "B_ref_star_0.10",
    "strategy_success",
    "strategy_reason",
]


def main() -> None:
    exp11 = read_csv(RESULT_DIR_V4 / "exp11_regime_stability.csv")
    smooth_rows = [row for row in exp11 if row["schedule"] == "smooth"]
    index = workload_index()
    rows = []
    for row in smooth_rows:
        case = index[(row["workload"], int(row["seed"]))]
        capacity = int(row["C"])
        buffer = int(row["B"])
        t_ref = int(float(row["T_ref_asap"]))
        strategies = candidate_strategy_results(case, capacity, buffer, t_ref)
        baseline_name = "none/static"
        baseline = strategies[baseline_name]
        thresholds = threshold_scan_for_strategy(case, capacity, buffer, t_ref, "smooth")
        for candidate_name, candidate in strategies.items():
            success, reason = strategy_success_reason(row["regime_label"], candidate_name, baseline, candidate)
            rows.append(
                {
                    "workload": row["workload"],
                    "family": row["family"],
                    "seed": row["seed"],
                    "n": row["n"],
                    "C": capacity,
                    "B": buffer,
                    "regime_label": row["regime_label"],
                    "recommended_strategy": row["recommended_strategy"],
                    "baseline_strategy": baseline_name,
                    "candidate_strategy": candidate_name,
                    "T_ref_asap": t_ref,
                    "baseline_T_exe": baseline.T_exe,
                    "candidate_T_exe": candidate.T_exe,
                    "strategy_gain_Texe": relative_gain(baseline.T_exe, candidate.T_exe),
                    "baseline_BacklogArea": baseline.BacklogArea,
                    "candidate_BacklogArea": candidate.BacklogArea,
                    "strategy_gain_BacklogArea": backlog_area_gain(
                        baseline.BacklogArea, candidate.BacklogArea
                    ),
                    "baseline_L_backlog": baseline.L_backlog,
                    "candidate_L_backlog": candidate.L_backlog,
                    "strategy_gain_Lbacklog": relative_gain(baseline.L_backlog, candidate.L_backlog),
                    "C_ref_star_0.05": thresholds["C_ref_star_0.05"],
                    "C_ref_star_0.10": thresholds["C_ref_star_0.10"],
                    "B_ref_star_0.05": thresholds["B_ref_star_0.05"],
                    "B_ref_star_0.10": thresholds["B_ref_star_0.10"],
                    "strategy_success": success,
                    "strategy_reason": reason,
                }
            )
    out_path = RESULT_DIR_V4 / "exp12_strategy_validation.csv"
    write_csv(out_path, rows, FIELDNAMES)
    _fig_strategy_gain(rows)
    _fig_cstar_bstar(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


def _fig_strategy_gain(rows: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    regimes = sorted({str(row["regime_label"]) for row in rows})
    strategies = ["smooth", "capacity_aware", "increase_B", "increase_C", "robust_smooth"]
    fig, ax = plt.subplots(figsize=(11, 5))
    width = 0.14
    xs = list(range(len(regimes)))
    for index, strategy in enumerate(strategies):
        values = []
        for regime in regimes:
            selected = [
                float(row["strategy_gain_Texe"])
                for row in rows
                if row["regime_label"] == regime and row["candidate_strategy"] == strategy
            ]
            values.append(sum(selected) / len(selected) if selected else 0.0)
        offsets = [x + (index - 2) * width for x in xs]
        ax.bar(offsets, values, width=width, label=strategy, color=SCHEDULE_COLORS.get(strategy))
    ax.set_xticks(xs)
    ax.set_xticklabels(regimes, rotation=35, ha="right")
    ax.set_ylabel("mean T_exe gain vs static")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncols=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V4 / "fig3_strategy_gain_by_regime.pdf")


def _fig_cstar_bstar(rows: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    regimes = sorted({str(row["regime_label"]) for row in rows})
    smooth_rows = [row for row in rows if row["candidate_strategy"] == "smooth"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, field, title in [
        (axes[0], "C_ref_star_0.05", "C_ref_star_0.05"),
        (axes[1], "B_ref_star_0.05", "B_ref_star_0.05"),
    ]:
        values = []
        for regime in regimes:
            selected = [
                float(row[field])
                for row in smooth_rows
                if row["regime_label"] == regime and str(row[field]) != ""
            ]
            values.append(sum(selected) / len(selected) if selected else 0.0)
        ax.bar(regimes, values, color="#4c78a8")
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=35)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V4 / "fig4_Cstar_Bstar_by_regime.pdf")


if __name__ == "__main__":
    main()
