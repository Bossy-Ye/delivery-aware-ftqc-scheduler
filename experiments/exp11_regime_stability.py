"""Experiment 11: wider-sweep regime stability."""

from __future__ import annotations

from common_v4 import (
    B_VALUES_V4,
    C_VALUES_V4,
    EXP11_FIELDNAMES,
    FIGURE_DIR_V4,
    REGIME_COLORS,
    RESULT_DIR_V4,
    SCHEDULES_V4,
    classify_setting,
    core_workloads_v4,
    distribution_summary,
    evaluate_schedule_row,
    read_csv,
    write_csv,
)


SUMMARY_FIELDNAMES = ["group", "regime_label", "count", "fraction"]


def main() -> None:
    rows = []
    for case in core_workloads_v4():
        for capacity in C_VALUES_V4:
            for buffer in B_VALUES_V4:
                decision, shared = classify_setting(case, capacity, buffer)
                for schedule_name in SCHEDULES_V4:
                    rows.append(
                        evaluate_schedule_row(case, capacity, buffer, schedule_name, decision, shared)
                    )
    out_path = RESULT_DIR_V4 / "exp11_regime_stability.csv"
    write_csv(out_path, rows, EXP11_FIELDNAMES)
    summary = distribution_summary(rows)
    write_csv(RESULT_DIR_V4 / "exp11_regime_distribution_summary.csv", summary, SUMMARY_FIELDNAMES)
    _fig_regime_distribution(summary)
    _fig_regime_map(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


def _fig_regime_distribution(summary: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    rows = [row for row in summary if row["group"] != "OVERALL"]
    workloads = sorted({str(row["group"]) for row in rows})
    regimes = sorted({str(row["regime_label"]) for row in rows})
    fig, ax = plt.subplots(figsize=(13, 5.2))
    bottoms = [0.0 for _ in workloads]
    for regime in regimes:
        values = [
            float(next((row["fraction"] for row in rows if row["group"] == workload and row["regime_label"] == regime), 0.0))
            for workload in workloads
        ]
        ax.bar(
            workloads,
            values,
            bottom=bottoms,
            label=regime,
            color=REGIME_COLORS.get(regime, None),
        )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values, strict=True)]
    ax.set_ylabel("regime fraction")
    ax.set_title("Regime distribution by workload")
    ax.tick_params(axis="x", rotation=65, labelsize=7)
    ax.legend(fontsize=7, ncols=2)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V4 / "fig1_regime_distribution_by_workload.pdf")


def _fig_regime_map(rows: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    smooth_rows = [row for row in rows if row["schedule"] == "smooth"]
    regimes = sorted({str(row["regime_label"]) for row in smooth_rows})
    family_markers = {
        "high_compressibility": "o",
        "medium_compressibility": "s",
        "low_compressibility": "^",
        "semi_real_adder": "D",
        "semi_real_multiplier": "P",
        "semi_real_qft": "X",
        "semi_real_multiplier_larger": "*",
        "semi_real_phase_estimation_like": "v",
        "semi_real_qft_larger": "<",
    }
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for regime in regimes:
        selected = [row for row in smooth_rows if row["regime_label"] == regime]
        for family in sorted({str(row["family"]) for row in selected}):
            family_rows = [row for row in selected if row["family"] == family]
            ax.scatter(
                [float(row["slack_ratio"]) for row in family_rows],
                [float(row["supply_tightness"]) for row in family_rows],
                s=24,
                alpha=0.55,
                color=REGIME_COLORS.get(regime),
                marker=family_markers.get(family, "o"),
                label=regime if family == sorted({str(row["family"]) for row in selected})[0] else None,
            )
    ax.set_xlabel("slack_ratio")
    ax.set_ylabel("supply_tightness")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V4 / "fig2_regime_map_slack_vs_pressure.pdf")


if __name__ == "__main__":
    main()
