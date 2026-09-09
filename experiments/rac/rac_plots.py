"""Figures for the resource-aware compilation go/no-go study.

Run after ``rac1``-``rac5``. Each figure answers one question:

1. Does lower T-depth mean faster execution?
2. How costly is the decision T-depth makes?
3. How do the policies compare as supply grows?
4. How much of the remaining headroom does the mechanism capture?
5. What does the mechanism do to the machine, cycle by cycle?
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from common_rac import FIGURE_DIR, POLICY_COLORS, POLICY_LABELS, RESULT_DIR, read_csv


def _save(figure, name: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(FIGURE_DIR / f"{name}.pdf")
    figure.savefig(FIGURE_DIR / f"{name}.png", dpi=160)
    plt.close(figure)
    print(f"  wrote {name}")


def figure1_t_depth_versus_runtime() -> None:
    """Plot 1: T-depth against constrained runtime, normalised per case."""

    rows = [
        row
        for row in read_csv(RESULT_DIR / "rac1_candidates.csv")
        if row["clifford_weight"] == "1"
    ]
    regimes = ["rate0.1", "rate1", "rate4", "unconstrained"]
    figure, axes = plt.subplots(1, len(regimes), figsize=(14, 3.6), sharey=True)

    for axis, regime in zip(axes, regimes):
        subset = [row for row in rows if row["regime"] == regime]
        groups: dict[str, list[dict[str, str]]] = {}
        for row in subset:
            groups.setdefault(row["program"], []).append(row)
        xs, ys = [], []
        for candidates in groups.values():
            depths = [float(row["t_depth"]) for row in candidates]
            times = [float(row["makespan"]) for row in candidates]
            if not depths or min(depths) <= 0 or min(times) <= 0:
                continue
            xs.extend(depth / min(depths) for depth in depths)
            ys.extend(time / min(times) for time in times)
        axis.scatter(xs, ys, s=14, alpha=0.45, color="#4c78a8", edgecolors="none")
        limit = max([1.05] + xs + ys)
        axis.plot([1, limit], [1, limit], color="#999999", lw=1, ls="--")
        axis.axhline(1.0, color="#e45756", lw=0.8, ls=":")
        axis.set_xlabel("T-depth / best T-depth")
        axis.set_title(
            "unconstrained" if regime == "unconstrained" else f"supply {regime[4:]} states/cycle"
        )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xticks([1, 2, 4, 8])
        axis.set_xticklabels(["1x", "2x", "4x", "8x"])
        axis.set_yticks([1, 2, 4])
        axis.set_yticklabels(["1x", "2x", "4x"])
        axis.minorticks_off()
    axes[0].set_ylabel("runtime / best runtime")
    figure.suptitle(
        "Points below the diagonal are implementations that are deeper in T "
        "yet faster to execute",
        fontsize=9,
    )
    _save(figure, "fig1_t_depth_vs_constrained_runtime")


def figure2_decision_regret() -> None:
    """Plot 2: distribution of the penalty paid by T-depth selection."""

    rows = [
        row
        for row in read_csv(RESULT_DIR / "rac1_cases.csv")
        if row["clifford_weight"] == "1"
    ]
    regimes = sorted(
        {row["regime"] for row in rows},
        key=lambda name: float("inf") if name == "unconstrained" else float(name[4:]),
    )
    data = [
        [float(row["regret_t_depth"]) for row in rows if row["regime"] == regime]
        for regime in regimes
    ]
    counts = [
        [float(row["regret_t_count"]) for row in rows if row["regime"] == regime]
        for regime in regimes
    ]

    figure, axis = plt.subplots(figsize=(8.5, 4.0))
    positions = range(len(regimes))
    first = axis.boxplot(
        data,
        positions=[position - 0.18 for position in positions],
        widths=0.3,
        patch_artist=True,
        showfliers=False,
    )
    second = axis.boxplot(
        counts,
        positions=[position + 0.18 for position in positions],
        widths=0.3,
        patch_artist=True,
        showfliers=False,
    )
    for patch in first["boxes"]:
        patch.set_facecolor(POLICY_COLORS["min_t_depth"])
        patch.set_alpha(0.75)
    for patch in second["boxes"]:
        patch.set_facecolor(POLICY_COLORS["min_t_count"])
        patch.set_alpha(0.75)
    axis.axhline(1.0, color="#333333", lw=1)
    axis.set_xticks(list(positions))
    axis.set_xticklabels(
        ["inf" if name == "unconstrained" else name[4:] for name in regimes]
    )
    axis.set_xlabel("magic states produced per logical cycle")
    axis.set_ylabel("runtime of the chosen implementation / best")
    axis.set_title("Decision regret of static-metric selection")
    axis.legend(
        [first["boxes"][0], second["boxes"][0]],
        ["selected by minimum T-depth", "selected by minimum T-count"],
        loc="upper right",
        fontsize=9,
    )
    _save(figure, "fig2_decision_regret")


def figure3_runtime_versus_supply() -> None:
    """Plot 3: every policy's regret as supply grows, at the median and the tail."""

    rows = read_csv(RESULT_DIR / "rac2_summary.csv")
    rows.sort(key=lambda row: float(row["rate"]))
    rates = [float(row["rate"]) for row in rows]
    cases = read_csv(RESULT_DIR / "rac2_cases.csv")

    series = (
        "min_t_count",
        "min_t_depth",
        "best_static",
        "legacy_smooth",
        "local_resource_greedy",
        "share_aware_greedy",
        "best_uniform",
        "resource_aware",
    )
    styles = {
        "share_aware_greedy": (2.4, (4, 2)),
        "best_uniform": (1.8, (1, 2)),
        "resource_aware": (1.4, None),
    }

    figure, axes = plt.subplots(1, 2, figsize=(13.0, 4.4), sharex=True)
    for name in series:
        medians, tails = [], []
        for rate in rates:
            values = sorted(
                float(row[f"regret_{name}"])
                for row in cases
                if float(row["rate"]) == rate
            )
            index = min(len(values) - 1, int(round(0.9 * (len(values) - 1))))
            medians.append(values[len(values) // 2])
            tails.append(values[index])
        width, dashes = styles.get(name, (1.5, None))
        for axis, data in ((axes[0], medians), (axes[1], tails)):
            line, = axis.plot(
                rates,
                data,
                marker="o",
                ms=4,
                color=POLICY_COLORS.get(name, "#888888"),
                label=POLICY_LABELS.get(name, name),
                lw=width,
            )
            if dashes:
                line.set_dashes(dashes)
    for axis, title in (
        (axes[0], "median over 28 programs"),
        (axes[1], "90th percentile over 28 programs"),
    ):
        axis.axhline(1.0, color="#333333", lw=1, ls="--")
        axis.set_xscale("log")
        axis.set_xlabel("magic states produced per logical cycle")
        axis.set_title(title)
    axes[0].set_ylabel("runtime / reference optimum")
    axes[0].legend(fontsize=7.5, loc="upper center")
    figure.suptitle(
        "Static metrics each fail in one half of the regime space; every "
        "resource-aware policy, however simple, lands on the optimum",
        fontsize=9,
    )
    _save(figure, "fig3_runtime_vs_supply")


def figure4_headroom_captured() -> None:
    """Plot 4: how much room is left once the strongest simple baseline is in place."""

    rows = read_csv(RESULT_DIR / "rac2_cases.csv")
    rates = sorted({float(row["rate"]) for row in rows})

    figure, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))

    none_left, small, large = [], [], []
    for rate in rates:
        subset = [row for row in rows if float(row["rate"]) == rate]
        fractions = [
            (int(row["strongest_baseline_makespan"]) - int(row["reference"]))
            / int(row["strongest_baseline_makespan"])
            for row in subset
        ]
        none_left.append(sum(1 for value in fractions if value <= 0.0))
        small.append(sum(1 for value in fractions if 0.0 < value <= 0.05))
        large.append(sum(1 for value in fractions if value > 0.05))

    labels = [f"{rate:g}" for rate in rates]
    axes[0].bar(labels, none_left, color="#9ecae1", label="baseline already optimal")
    axes[0].bar(labels, small, bottom=none_left, color="#f58518", label="under 5% left")
    axes[0].bar(
        labels,
        large,
        bottom=[a + b for a, b in zip(none_left, small)],
        color="#e45756",
        label="over 5% left",
    )
    axes[0].set_xlabel("magic states produced per logical cycle")
    axes[0].set_ylabel("programs (of 28)")
    axes[0].set_title(
        "One fungible resource:\nroom left beyond the strongest simple baseline"
    )
    axes[0].legend(fontsize=8, loc="lower left")

    probe_path = RESULT_DIR / "rac6_multiresource_probe.csv"
    if probe_path.exists():
        probe = read_csv(probe_path)
        imbalance = [
            max(float(row["t_rate"]), float(row["ccz_rate"]))
            / min(float(row["t_rate"]), float(row["ccz_rate"]))
            for row in probe
        ]
        gains = [float(row["headroom_beyond_uniform_pct"]) for row in probe]
        mixed = [int(row["optimum_heterogeneous"]) for row in probe]
        axes[1].scatter(
            [value for value, flag in zip(imbalance, mixed) if flag],
            [value for value, flag in zip(gains, mixed) if flag],
            s=46,
            color="#54a24b",
            label="optimum mixes the two factories",
        )
        axes[1].scatter(
            [value for value, flag in zip(imbalance, mixed) if not flag],
            [value for value, flag in zip(gains, mixed) if not flag],
            s=46,
            facecolors="none",
            edgecolors="#54595d",
            label="a single factory suffices",
        )
        axes[1].set_xlabel("imbalance between the two production rates")
        axes[1].set_ylabel("headroom beyond the best uniform choice (%)")
        axes[1].set_title(
            "Two kinds of magic state:\nheadroom returns when the banks are imbalanced"
        )
        axes[1].legend(fontsize=8, loc="upper left")
    _save(figure, "fig4_headroom_captured")


def figure5_demand_timeline() -> None:
    """Plot 5: demand, production, buffer occupancy and stalls, cycle by cycle."""

    rows = read_csv(RESULT_DIR / "rac4_mechanism_traces.csv")
    cases = read_csv(RESULT_DIR / "rac4_mechanism_cases.csv")
    keys = []
    for row in rows:
        key = (row["program"], row["regime"])
        if key not in keys:
            keys.append(key)

    figure, axes = plt.subplots(
        len(keys), 2, figsize=(12.5, 3.0 * len(keys)), squeeze=False
    )
    for index, (program, regime) in enumerate(keys):
        for column, policy in enumerate(("min_t_depth", "resource_aware")):
            axis = axes[index][column]
            trace = [
                row
                for row in rows
                if row["program"] == program
                and row["regime"] == regime
                and row["policy"] == policy
            ]
            cycles = [int(row["cycle"]) for row in trace]
            demand = [int(row["demand"]) for row in trace]
            arrivals = [int(row["arrivals"]) for row in trace]
            stock = [int(row["stock"]) for row in trace]
            axis.fill_between(cycles, demand, step="mid", alpha=0.55, color="#4c78a8",
                              label="states consumed")
            axis.plot(cycles, arrivals, color="#f58518", lw=0.9, label="states delivered")
            axis.plot(cycles, stock, color="#54a24b", lw=1.1, label="buffer occupancy")
            for row in trace:
                if row["stalled"] == "1":
                    axis.axvspan(
                        int(row["cycle"]) - 0.5,
                        int(row["cycle"]) + 0.5,
                        color="#e45756",
                        alpha=0.12,
                        lw=0,
                    )
            summary = next(
                (
                    case
                    for case in cases
                    if case["program"] == program
                    and case["regime"] == regime
                    and case["policy"] == policy
                ),
                None,
            )
            title = POLICY_LABELS.get(policy, policy)
            if summary is not None:
                title += (
                    f"  |  makespan {summary['makespan']}, "
                    f"stalls {summary['supply_stall_cycles']}"
                )
            axis.set_title(f"{program} @ {regime}\n{title}", fontsize=8)
            axis.set_xlabel("logical cycle")
            axis.set_ylabel("states")
            if index == 0 and column == 0:
                axis.legend(fontsize=7, loc="upper right")
    figure.suptitle("Red bands are cycles stalled waiting for a magic state", fontsize=9)
    _save(figure, "fig5_demand_timeline")


def figure6_ablation() -> None:
    """Supporting figure: what each rung of the cost model is worth."""

    rows = read_csv(RESULT_DIR / "rac3_ablation_summary.csv")
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
    labels = [row["model"] for row in rows]
    axes[0].barh(labels, [float(row["regret_median"]) for row in rows], color="#4c78a8")
    axes[0].set_xlabel("median runtime / reference optimum")
    axes[0].set_title("Selection quality by cost-model information")
    axes[0].invert_yaxis()
    axes[1].barh(
        labels,
        [float(row["prediction_error_mean"]) for row in rows],
        color="#f58518",
    )
    axes[1].set_xlabel("mean relative prediction error")
    axes[1].set_title("Prediction accuracy by cost-model information")
    axes[1].invert_yaxis()
    _save(figure, "fig6_cost_model_ablation")


FIGURES = (
    ("rac1_candidates.csv", figure1_t_depth_versus_runtime),
    ("rac1_cases.csv", figure2_decision_regret),
    ("rac2_summary.csv", figure3_runtime_versus_supply),
    ("rac2_cases.csv", figure4_headroom_captured),
    ("rac4_mechanism_traces.csv", figure5_demand_timeline),
    ("rac3_ablation_summary.csv", figure6_ablation),
)


def main() -> None:
    """Draw every figure whose input table is present."""

    for source, builder in FIGURES:
        if (RESULT_DIR / source).exists():
            builder()
        else:
            print(f"  skipped {builder.__name__}: {source} not found")


if __name__ == "__main__":
    main()
