"""Extract the headline numbers of the go/no-go study from the result tables.

The memo quotes these figures directly, so they are computed in one place from
the committed CSVs rather than copied by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import RESULT_DIR, ratio, read_csv, summarize


def _rate_key(name: str) -> float:
    return float("inf") if name == "unconstrained" else float(name[4:])


def gate1() -> None:
    """Print the Gate 1 reversal and regret figures, including the controls."""

    path = RESULT_DIR / "rac1_summary.csv"
    if not path.exists():
        print("gate 1: rac1_summary.csv missing")
        return
    rows = read_csv(path)
    print("== Gate 1: does T-depth pick the wrong implementation? ==")
    print(
        f"{'regime':14s} {'cliffords':>9s} {'sel.rev':>8s} {'pair.rev':>8s} "
        f"{'median':>7s} {'p90':>6s} {'p95':>6s} {'max':>6s}"
    )
    for row in sorted(rows, key=lambda row: (_rate_key(row["regime"]), row["clifford_weight"])):
        weight = "charged" if row["clifford_weight"] == "1" else "free"
        print(
            f"{row['regime']:14s} {weight:>9s} {float(row['selection_reversal_rate']):8.3f} "
            f"{float(row['pair_reversal_rate']):8.3f} "
            f"{float(row['regret_t_depth_median']):7.3f} "
            f"{float(row['regret_t_depth_p90']):6.3f} "
            f"{float(row['regret_t_depth_p95']):6.3f} "
            f"{float(row['regret_t_depth_max']):6.3f}"
        )

    cases = read_csv(RESULT_DIR / "rac1_cases.csv")
    charged = [row for row in cases if row["clifford_weight"] == "1"]
    constrained = [row for row in charged if row["regime"] != "unconstrained"]
    control = [row for row in charged if row["regime"] == "unconstrained"]
    print()
    print(
        f"constrained cases: {len(constrained)}, "
        f"reversal in {sum(int(row['selection_reversal']) for row in constrained)}"
    )
    print(
        f"control (unconstrained): {len(control)}, "
        f"reversal in {sum(int(row['selection_reversal']) for row in control)}"
    )
    by_kernel: dict[str, list[float]] = {}
    for row in constrained:
        by_kernel.setdefault(row["kernel"], []).append(float(row["regret_t_depth"]))
    print()
    print("median T-depth regret by kernel (constrained regimes):")
    for kernel, values in sorted(by_kernel.items()):
        stats = summarize(values)
        print(f"  {kernel:14s} n={stats['n']:4d} median {stats['median']:.3f} max {stats['max']:.3f}")


def gate2() -> None:
    """Print the Gate 2 baseline ladder and captured-headroom figures."""

    path = RESULT_DIR / "rac2_summary.csv"
    if not path.exists():
        print("gate 2: rac2_summary.csv missing")
        return
    rows = sorted(read_csv(path), key=lambda row: float(row["rate"]))
    print()
    print("== Gate 2: median runtime relative to the reference optimum ==")
    header = (
        f"{'rate':>6s} {'Tcount':>7s} {'Tdepth':>7s} {'bStatic':>8s} {'legacy':>7s} "
        f"{'greedy':>7s} {'share':>7s} {'bUnif':>7s} {'ours':>7s} {'capt':>6s} {'wins':>5s} {'exh':>4s}"
    )
    print(header)
    for row in rows:
        print(
            f"{float(row['rate']):6.2f} {float(row['regret_min_t_count_median']):7.3f} "
            f"{float(row['regret_min_t_depth_median']):7.3f} "
            f"{float(row['regret_best_static_median']):8.3f} "
            f"{float(row['regret_legacy_smooth_median']):7.3f} "
            f"{float(row['regret_local_resource_greedy_median']):7.3f} "
            f"{float(row['regret_share_aware_greedy_median']):7.3f} "
            f"{float(row['regret_best_uniform_median']):7.3f} "
            f"{float(row['regret_resource_aware_median']):7.3f} "
            f"{float(row['headroom_captured_median']):6.3f} "
            f"{int(row['ours_beats_strongest_baseline']):5d} {int(row['exhaustive_cases']):4d}"
        )

    cases = read_csv(RESULT_DIR / "rac2_cases.csv")
    exhaustive = [row for row in cases if row["reference_exhaustive"] == "1"]
    print()
    print(f"cases: {len(cases)}, with a proven optimum: {len(exhaustive)}")
    for label, subset in (("all", cases), ("proven optimum only", exhaustive)):
        ours = summarize(float(row["regret_resource_aware"]) for row in subset)
        share = summarize(float(row["regret_share_aware_greedy"]) for row in subset)
        uniform = summarize(float(row["regret_best_uniform"]) for row in subset)
        depth = summarize(float(row["regret_min_t_depth"]) for row in subset)
        static = summarize(float(row["regret_best_static"]) for row in subset)
        print(
            f"  {label:20s} T-depth {depth['median']:.3f} | best-static {static['median']:.3f} | "
            f"share-greedy {share['median']:.3f} | best-uniform {uniform['median']:.3f} | "
            f"ours {ours['median']:.3f} (p90 {ours['p90']:.3f}, max {ours['max']:.3f})"
        )
    beats = sum(
        1
        for row in cases
        if int(row["makespan_resource_aware"]) < int(row["strongest_baseline_makespan"])
    )
    ties = sum(
        1
        for row in cases
        if int(row["makespan_resource_aware"]) == int(row["strongest_baseline_makespan"])
    )
    print(
        f"  ours beats the strongest baseline in {beats}/{len(cases)} cases, "
        f"ties in {ties}, loses in {len(cases) - beats - ties}"
    )
    het = [row for row in cases if row["ours_heterogeneous"] == "1"]
    print(f"  heterogeneous assignments chosen in {len(het)}/{len(cases)} cases")
    strongest: dict[str, int] = {}
    for row in cases:
        strongest[row["strongest_baseline"]] = strongest.get(row["strongest_baseline"], 0) + 1
    print(f"  strongest baseline per case: {dict(sorted(strongest.items()))}")

    gaps = [
        (
            row["program"],
            row["regime"],
            int(row["strongest_baseline_makespan"]),
            int(row["makespan_resource_aware"]),
            int(row["reference"]),
        )
        for row in cases
        if int(row["strongest_baseline_makespan"]) > int(row["makespan_resource_aware"])
    ]
    gaps.sort(key=lambda item: -ratio(item[2], item[3]))
    print()
    print("largest wins over the strongest baseline:")
    for program, regime, baseline, ours_value, reference in gaps[:8]:
        print(
            f"  {program:28s} {regime:8s} baseline {baseline:6d} -> ours {ours_value:6d} "
            f"({ratio(baseline, ours_value):.2f}x), optimum {reference}"
        )


def ablation() -> None:
    """Print the cost-model information ladder."""

    path = RESULT_DIR / "rac3_ablation_summary.csv"
    if not path.exists():
        print("\nablation: rac3_ablation_summary.csv missing")
        return
    print()
    print("== Ablation: what the cost model needs to know ==")
    print(f"{'model':22s} {'regret_med':>10s} {'regret_p90':>10s} {'pred_err':>9s} {'rank_acc':>9s}")
    for row in read_csv(path):
        print(
            f"{row['model']:22s} {float(row['regret_median']):10.3f} "
            f"{float(row['regret_p90']):10.3f} {float(row['prediction_error_mean']):9.4f} "
            f"{float(row['candidate_selection_accuracy']):9.3f}"
        )


def stress() -> None:
    """Print the stress-test summaries."""

    print()
    print("== Stress tests ==")
    space_path = RESULT_DIR / "rac5_space.csv"
    if space_path.exists():
        rows = read_csv(space_path)
        for policy in ("min_t_depth", "min_t_count", "share_aware_greedy", "resource_aware"):
            subset = [row for row in rows if row["policy"] == policy]
            time_stats = summarize(float(row["time_ratio_vs_t_depth"]) for row in subset)
            volume_stats = summarize(float(row["volume_ratio_vs_t_depth"]) for row in subset)
            print(
                f"  space {policy:20s} time x{time_stats['median']:.3f} "
                f"volume x{volume_stats['median']:.3f} (max volume x{volume_stats['max']:.3f})"
            )
    for label, filename in (
        ("machine width", "rac5_width.csv"),
        ("stochastic supply", "rac5_stochastic.csv"),
        ("factory configuration", "rac5_configurations.csv"),
    ):
        path = RESULT_DIR / filename
        if not path.exists():
            continue
        rows = read_csv(path)
        ours = summarize(float(row["regret_resource_aware"]) for row in rows)
        depth = summarize(float(row["regret_min_t_depth"]) for row in rows)
        print(
            f"  {label:22s} ours median {ours['median']:.3f} p90 {ours['p90']:.3f} max {ours['max']:.3f} | "
            f"T-depth median {depth['median']:.3f} max {depth['max']:.3f}"
        )


def cost_model_cost() -> None:
    """Print how the cost model's cost compares with simulating."""

    path = RESULT_DIR / "rac7_cost_model_timing.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    ratios = [float(row["simulation_over_cost_model"]) for row in rows]
    slower = sum(1 for value in ratios if value < 1.0)
    stats = summarize(ratios)
    print()
    print("== Is the cost model cheaper than simulating? ==")
    print(
        f"  simulation time / cost-model time: median {stats['median']:.2f}, "
        f"min {min(ratios):.2f}, max {stats['max']:.2f}"
    )
    print(f"  cost model slower than simulating in {slower}/{len(rows)} pairs")


def multiresource() -> None:
    """Print the follow-up probe on a non-fungible resource."""

    path = RESULT_DIR / "rac6_multiresource_probe.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    gains = summarize(float(row["headroom_beyond_uniform_pct"]) for row in rows)
    lifted = summarize(float(row["regret_balanced_two_term"]) for row in rows)
    heterogeneous = sum(int(row["optimum_heterogeneous"]) for row in rows)
    print()
    print("== Follow-up probe: two kinds of magic state ==")
    print(
        f"  headroom beyond the best uniform implementation: median "
        f"{gains['median']:.1f}%, p90 {gains['p90']:.1f}%, max {gains['max']:.1f}%"
    )
    print(f"  optimum is a mixed assignment in {heterogeneous}/{len(rows)} configurations")
    print(
        f"  lifted two-term rule regret: median {lifted['median']:.3f}, "
        f"max {lifted['max']:.3f}"
    )


def main() -> None:
    """Print every headline number quoted by the memo."""

    gate1()
    gate2()
    ablation()
    stress()
    cost_model_cost()
    multiresource()


if __name__ == "__main__":
    main()
