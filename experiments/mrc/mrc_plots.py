"""Figures for the T/CCZ implementation-selection study."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from common_mrc import (
    FIGURE_DIR,
    POLICY_COLORS,
    POLICY_LABELS,
    RESULT_DIR,
    SIMPLE_BASELINES,
    read_csv,
)


def _save(figure, name: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(FIGURE_DIR / f"{name}.pdf")
    figure.savefig(FIGURE_DIR / f"{name}.png", dpi=160)
    plt.close(figure)
    print(f"  wrote {name}")


def figure1_headroom_map() -> None:
    """Where in the machine's operating space does mixing pay?"""

    rows = read_csv(RESULT_DIR / "mrc1_cases.csv")
    capacities = sorted({float(row["capacity_target"]) for row in rows})
    shares = sorted({float(row["ccz_share"]) for row in rows})

    figure, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
    for axis, column, title in (
        (
            axes[0],
            "headroom_over_uniform_oracle",
            "over the best uniform implementation",
        ),
        (
            axes[1],
            "headroom_over_best_simple",
            "over the best of every simple baseline",
        ),
    ):
        for capacity in capacities:
            medians = []
            for share in shares:
                subset = [
                    100 * float(row[column])
                    for row in rows
                    if float(row["capacity_target"]) == capacity
                    and float(row["ccz_share"]) == share
                ]
                subset.sort()
                medians.append(subset[len(subset) // 2] if subset else 0.0)
            axis.plot(
                shares,
                medians,
                marker="o",
                ms=5,
                lw=1.8,
                label=f"capacity {capacity:g} T-equiv/cycle",
            )
        axis.axhline(0, color="#333333", lw=1)
        axis.axhline(5, color="#e45756", lw=0.9, ls="--")
        axis.set_xlabel("share of capacity held by the CCZ bank")
        axis.set_ylabel("median headroom (% of makespan)")
        axis.set_title(title)
        axis.legend(fontsize=8)
    figure.suptitle(
        "Headroom from mixing implementations within a family; "
        "the dashed line is the 5% continue threshold",
        fontsize=9,
    )
    _save(figure, "fig1_headroom_map")


def figure2_regret_by_policy() -> None:
    """How far is each policy from the global optimum?"""

    rows = read_csv(RESULT_DIR / "mrc1_cases.csv")
    policies = list(SIMPLE_BASELINES) + ["sim_descent"]
    data = [[float(row[f"regret_{policy}"]) for row in rows] for policy in policies]

    figure, axis = plt.subplots(figsize=(10.5, 4.4))
    box = axis.boxplot(data, patch_artist=True, showfliers=False)
    for patch, policy in zip(box["boxes"], policies):
        patch.set_facecolor(POLICY_COLORS.get(policy, "#888888"))
        patch.set_alpha(0.8)
    axis.axhline(1.0, color="#333333", lw=1, ls="--")
    axis.set_xticklabels(
        [POLICY_LABELS.get(policy, policy) for policy in policies],
        rotation=20,
        ha="right",
        fontsize=8,
    )
    axis.set_ylabel("makespan / global optimum")
    axis.set_title("Distance from the global optimum, over the whole matrix")
    _save(figure, "fig2_regret_by_policy")


def figure3_controls() -> None:
    """Do the controls remove the headroom, as they should if it is real?"""

    path = RESULT_DIR / "mrc2_controls.csv"
    if not path.exists():
        print("  skipped figure3_controls: mrc2_controls.csv not found")
        return
    rows = read_csv(path)
    groups = [
        ("baseline", "two banks", "two separate banks"),
        ("conversion", "CCZ->2T only", "plus catalyzed CCZ to 2T"),
        ("conversion", "both directions", "plus both conversions"),
        ("pooled", "pooled into T", "all capacity in the T bank"),
        ("pooled", "pooled into CCZ", "all capacity in the CCZ bank"),
    ]
    labels, data = [], []
    for control, setting, label in groups:
        subset = [
            100 * float(row["headroom_over_uniform_oracle"])
            for row in rows
            if row["control"] == control and row["setting"] == setting
        ]
        if subset:
            labels.append(label)
            data.append(subset)

    figure, axis = plt.subplots(figsize=(9.5, 4.4))
    box = axis.boxplot(data, patch_artist=True, showfliers=False)
    colors = ["#54a24b", "#f58518", "#e45756", "#4c78a8", "#9d755d"]
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
    axis.axhline(0, color="#333333", lw=1)
    axis.set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    axis.set_ylabel("headroom over the best uniform choice (%)")
    axis.set_title(
        "Falsification controls: making the resources fungible should remove the effect"
    )
    _save(figure, "fig3_controls")


def figure4_scaling() -> None:
    """Does the mixture stay optimal and stay worth having as programs grow?"""

    path = RESULT_DIR / "mrc3_scaling.csv"
    if not path.exists():
        print("  skipped figure4_scaling: mrc3_scaling.csv not found")
        return
    rows = read_csv(path)
    families = sorted({row["family"] for row in rows if "size" not in row["family"]})

    figure, axes = plt.subplots(1, 3, figsize=(14.0, 4.2))
    for family in families:
        subset = [row for row in rows if row["family"] == family]
        concurrencies = sorted({int(row["concurrency"]) for row in subset})
        for axis, column, label in (
            (axes[0], "headroom_over_best_simple", "median headroom over simple (%)"),
            (axes[1], "oracle_heterogeneity", "mean within-family mixing"),
            (axes[2], "seconds_global_oracle", "seconds to find the optimum"),
        ):
            values = []
            for concurrency in concurrencies:
                picked = [
                    float(row[column])
                    for row in subset
                    if int(row["concurrency"]) == concurrency
                ]
                picked.sort()
                value = picked[len(picked) // 2] if picked else 0.0
                values.append(100 * value if column == "headroom_over_best_simple" else value)
            axis.plot(concurrencies, values, marker="o", ms=5, label=family)
            axis.set_xlabel("concurrent decision sites")
            axis.set_ylabel(label)
    axes[0].axhline(5, color="#e45756", lw=0.9, ls="--")
    axes[2].set_yscale("log")
    for axis in axes:
        axis.legend(fontsize=8)
    figure.suptitle("Scaling in concurrency", fontsize=9)
    _save(figure, "fig4_scaling")


def figure5_mixture() -> None:
    """Does the optimum match the demand mixture to the supply mixture?"""

    rows = read_csv(RESULT_DIR / "mrc1_cases.csv")
    supply = []
    demand = []
    uniform = []
    for row in rows:
        t_rate = float(row["t_rate"])
        ccz_rate = float(row["ccz_rate"])
        capacity = t_rate + 2 * ccz_rate
        if capacity <= 0:
            continue
        supply.append(2 * ccz_rate / capacity)
        demand.append(float(row["oracle_ccz_share_of_demand"]))
        uniform.append(float(row["uniform_ccz_share_of_demand"]))

    figure, axis = plt.subplots(figsize=(6.4, 5.6))
    axis.scatter(supply, uniform, s=22, alpha=0.35, color="#e45756",
                 label="best uniform implementation")
    axis.scatter(supply, demand, s=22, alpha=0.55, color="#54a24b",
                 label="global optimum")
    axis.plot([0, 1], [0, 1], color="#333333", lw=1, ls="--", label="demand matches supply")
    axis.set_xlabel("share of supply capacity in the CCZ bank")
    axis.set_ylabel("share of demand drawn from the CCZ bank")
    axis.set_title("The optimum tracks the supply mixture;\nuniform choices cannot")
    axis.legend(fontsize=8, loc="upper left")
    _save(figure, "fig5_mixture")


FIGURES = (
    ("mrc1_cases.csv", figure1_headroom_map),
    ("mrc1_cases.csv", figure2_regret_by_policy),
    ("mrc2_controls.csv", figure3_controls),
    ("mrc3_scaling.csv", figure4_scaling),
    ("mrc1_cases.csv", figure5_mixture),
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
