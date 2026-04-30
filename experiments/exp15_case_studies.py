"""Experiment 15: representative V4 case-study plots."""

from __future__ import annotations

from common_v4 import (
    FIGURE_DIR_V4,
    RESULT_DIR_V4,
    read_csv,
    schedule_for_v4,
    workload_index,
    write_csv,
)
from ftqc_delivery.metrics.backlog import buffer_adjusted_backlog
from ftqc_delivery.metrics.delta_max import cumulative_demand, t_demand_trace
from ftqc_delivery.simulator.deterministic import simulate_deterministic


FIELDNAMES = [
    "case_id",
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "regime_label",
    "intervention",
    "T_ref_asap",
    "T_exe",
    "ratio_to_T_ref",
    "BacklogArea",
    "L_backlog",
]


def main() -> None:
    exp11 = read_csv(RESULT_DIR_V4 / "exp11_regime_stability.csv")
    smooth_rows = [row for row in exp11 if row["schedule"] == "smooth"]
    cases = {
        "case1_smooth_solvable": _select(smooth_rows, "peak_dominated_smooth_solvable"),
        "case2_buffer_limited": _select(smooth_rows, "peak_dominated_buffer_limited"),
        "case3_persistent_underprovisioning": _select(smooth_rows, "persistent_underprovisioning"),
        "case4_effective_capacity_sensitive": _select_effective_case(smooth_rows),
    }
    index = workload_index()
    rows = []
    for case_id, row in cases.items():
        if row is None:
            continue
        case = index[(row["workload"], int(row["seed"]))]
        capacity = int(row["C"])
        buffer = int(row["B"])
        t_ref = int(float(row["T_ref_asap"]))
        interventions = _interventions(case_id, capacity, buffer)
        for intervention, c_value, b_value, schedule_name in interventions:
            schedule = schedule_for_v4(schedule_name, case, c_value, b_value)
            result = simulate_deterministic(case.dag, schedule, c_value, b_value)
            backlog = buffer_adjusted_backlog(case.dag, schedule, c_value, b_value)
            rows.append(
                {
                    "case_id": case_id,
                    "workload": case.workload,
                    "family": case.family,
                    "seed": case.seed,
                    "n": case.n,
                    "C": c_value,
                    "B": b_value,
                    "regime_label": row["regime_label"],
                    "intervention": intervention,
                    "T_ref_asap": t_ref,
                    "T_exe": result.T_exe,
                    "ratio_to_T_ref": result.T_exe / t_ref,
                    "BacklogArea": sum(backlog.values()),
                    "L_backlog": sum(1 for value in backlog.values() if value > 0),
                }
            )
        _plot_case(case_id, case, capacity, buffer, t_ref)
    write_csv(RESULT_DIR_V4 / "exp15_case_studies.csv", rows, FIELDNAMES)
    print(f"Wrote {len(rows)} rows to {RESULT_DIR_V4 / 'exp15_case_studies.csv'}")


def _select(rows: list[dict[str, str]], regime: str) -> dict[str, str] | None:
    selected = [row for row in rows if row["regime_label"] == regime]
    if not selected:
        return None
    return sorted(selected, key=lambda row: float(row["BacklogArea"]), reverse=True)[0]


def _select_effective_case(rows: list[dict[str, str]]) -> dict[str, str] | None:
    selected = [
        row
        for row in rows
        if row["regime_label"] in {"peak_dominated_smooth_solvable", "peak_dominated_buffer_limited"}
        and int(row["C"]) >= 2
    ]
    return selected[0] if selected else (rows[0] if rows else None)


def _interventions(case_id: str, capacity: int, buffer: int) -> list[tuple[str, int, int, str]]:
    if case_id == "case2_buffer_limited":
        return [
            ("B_base", capacity, buffer, "smooth"),
            ("B_plus_8", capacity, buffer + 8, "smooth"),
            ("B_plus_16", capacity, buffer + 16, "smooth"),
        ]
    if case_id == "case3_persistent_underprovisioning":
        return [
            ("C_base", capacity, buffer, "smooth"),
            ("C_plus_1", capacity + 1, buffer, "smooth"),
            ("C_plus_2", capacity + 2, buffer, "smooth"),
        ]
    if case_id == "case4_effective_capacity_sensitive":
        return [
            ("smooth_eta_1", capacity, buffer, "smooth"),
            ("smooth_eta_0.75", max(1, int(0.75 * capacity)), buffer, "smooth"),
            ("robust_eta_0.75", max(1, int(0.75 * capacity)), buffer, "robust_smooth"),
        ]
    return [
        ("static", capacity, buffer, "static"),
        ("smooth", capacity, buffer, "smooth"),
    ]


def _plot_case(case_id: str, case, capacity: int, buffer: int, t_ref: int) -> None:
    import matplotlib.pyplot as plt

    schedules = {
        "static": schedule_for_v4("static", case, capacity, buffer),
        "smooth": schedule_for_v4("smooth", case, capacity, buffer),
    }
    fig, axes = plt.subplots(3, 1, figsize=(8.5, 7), sharex=False)
    for name, schedule in schedules.items():
        demand = t_demand_trace(case.dag, schedule)
        cumulative = cumulative_demand(case.dag, schedule)
        backlog = buffer_adjusted_backlog(case.dag, schedule, capacity, buffer)
        axes[0].step(demand.keys(), demand.values(), where="mid", label=name)
        axes[1].plot(cumulative.keys(), cumulative.values(), label=f"A(t) {name}")
        axes[2].step(backlog.keys(), backlog.values(), where="mid", label=name)
    horizon = max(max(schedule) for schedule in schedules.values())
    supply = {time: capacity * time + buffer for time in range(1, horizon + 1)}
    axes[1].plot(supply.keys(), supply.values(), color="black", linestyle="--", label="Ct+B")
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("D(t)")
    axes[1].set_ylabel("A(t)")
    axes[2].set_ylabel("backlog(t)")
    axes[2].set_xlabel("logical time")
    fig.suptitle(f"{case_id}: {case.workload} C={capacity} B={buffer} T_ref={t_ref}")
    fig.tight_layout()
    filename = {
        "case1_smooth_solvable": "case1_smooth_solvable.pdf",
        "case2_buffer_limited": "case2_buffer_limited.pdf",
        "case3_persistent_underprovisioning": "case3_persistent_underprovisioning.pdf",
        "case4_effective_capacity_sensitive": "case4_effective_capacity_sensitive.pdf",
    }[case_id]
    fig.savefig(FIGURE_DIR_V4 / filename)
    plt.close(fig)


if __name__ == "__main__":
    main()
