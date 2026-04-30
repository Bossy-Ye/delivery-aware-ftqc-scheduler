"""Experiment 13: larger and synthetic workload regime expansion."""

from __future__ import annotations

from common_v4 import (
    EXP11_FIELDNAMES,
    FIGURE_DIR_V4,
    REGIME_COLORS,
    RESULT_DIR_V4,
    SCHEDULES_V4,
    classify_setting,
    evaluate_schedule_row,
    expanded_workloads_v4,
    write_csv,
)


C_VALUES = [1, 2, 3, 4, 5]
B_VALUES = [0, 4, 8, 16]


def main() -> None:
    rows = []
    for case in expanded_workloads_v4():
        for capacity in C_VALUES:
            for buffer in B_VALUES:
                decision, shared = classify_setting(case, capacity, buffer)
                for schedule_name in SCHEDULES_V4:
                    rows.append(
                        evaluate_schedule_row(case, capacity, buffer, schedule_name, decision, shared)
                    )
    out_path = RESULT_DIR_V4 / "exp13_workload_expansion.csv"
    write_csv(out_path, rows, EXP11_FIELDNAMES)
    _fig_workload_expansion(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


def _fig_workload_expansion(rows: list[dict[str, object]]) -> None:
    import matplotlib.pyplot as plt

    smooth_rows = [row for row in rows if row["schedule"] == "smooth"]
    workloads = sorted({str(row["workload"]) for row in smooth_rows})
    regimes = sorted({str(row["regime_label"]) for row in smooth_rows})
    fig, ax = plt.subplots(figsize=(10, 4.8))
    bottoms = [0.0 for _ in workloads]
    for regime in regimes:
        values = []
        for workload in workloads:
            selected = [row for row in smooth_rows if row["workload"] == workload]
            count = sum(1 for row in selected if row["regime_label"] == regime)
            values.append(count / len(selected) if selected else 0.0)
        ax.bar(
            workloads,
            values,
            bottom=bottoms,
            label=regime,
            color=REGIME_COLORS.get(regime),
        )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values, strict=True)]
    ax.set_ylabel("regime fraction")
    ax.set_title("Expanded workload regime distribution")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=7, ncols=2)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V4 / "fig5_workload_expansion_regimes.pdf")


if __name__ == "__main__":
    main()
