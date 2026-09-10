"""Extract the headline numbers of the T/CCZ study from the result tables.

The memo quotes these figures directly, so they are computed here from the
committed CSVs rather than copied by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, SIMPLE_BASELINES, POLICY_LABELS, read_csv, summarize


def _pct(value: float) -> str:
    return f"{100 * value:5.1f}%"


def headroom() -> None:
    """Print the core headroom result and the regret of every policy."""

    path = RESULT_DIR / "mrc1_cases.csv"
    if not path.exists():
        print("mrc1_cases.csv missing")
        return
    rows = read_csv(path)
    exact = [row for row in rows if row["oracle_exhaustive"] == "1"]
    print(f"== Headroom ({len(rows)} cases, {len(exact)} with a proven optimum) ==")

    for label, subset in (("all cases", rows), ("proven optimum only", exact)):
        uniform = summarize(float(row["headroom_over_uniform_oracle"]) for row in subset)
        simple = summarize(float(row["headroom_over_best_simple"]) for row in subset)
        over5 = sum(1 for row in subset if float(row["headroom_over_best_simple"]) > 0.05)
        over10 = sum(1 for row in subset if float(row["headroom_over_best_simple"]) > 0.10)
        print(f"  {label}:")
        print(
            f"    over the best uniform choice: median {_pct(uniform['median'])} "
            f"p90 {_pct(uniform['p90'])} max {_pct(uniform['max'])}"
        )
        print(
            f"    over the best simple baseline: median {_pct(simple['median'])} "
            f"p90 {_pct(simple['p90'])} max {_pct(simple['max'])}"
        )
        print(
            f"    cases above 5%: {over5}/{len(subset)}  above 10%: {over10}/{len(subset)}"
        )

    print()
    print("  regret relative to the global optimum:")
    policies = list(SIMPLE_BASELINES) + ["sim_descent"]
    for policy in policies:
        stats = summarize(float(row[f"regret_{policy}"]) for row in rows)
        seconds = summarize(float(row[f"seconds_{policy}"]) for row in rows)
        print(
            f"    {POLICY_LABELS.get(policy, policy):46s} mean {stats['mean']:.3f} "
            f"median {stats['median']:.3f} p90 {stats['p90']:.3f} max {stats['max']:.3f} "
            f"({seconds['median']:.2f}s median)"
        )
    best_simple: dict[str, int] = {}
    for row in rows:
        key = row["best_simple_baseline"]
        best_simple[key] = best_simple.get(key, 0) + 1
    print(f"    strongest simple baseline per case: {dict(sorted(best_simple.items()))}")

    print()
    print("  by supply pressure (demand over capacity, along the critical path):")
    for low, high, label in ((0.0, 0.5, "below 0.5"), (0.5, 1.0, "0.5 to 1"),
                             (1.0, 2.0, "1 to 2"), (2.0, 1e9, "above 2")):
        subset = [
            row for row in rows if low <= float(row["supply_pressure"]) < high
        ]
        if not subset:
            continue
        simple = summarize(float(row["headroom_over_best_simple"]) for row in subset)
        print(
            f"    pressure {label:10s} n={len(subset):4d} median {_pct(simple['median'])} "
            f"p90 {_pct(simple['p90'])} max {_pct(simple['max'])}"
        )

    print()
    print("  by kernel family:")
    families = sorted({row["family"] for row in rows})
    for family in families:
        subset = [row for row in rows if row["family"] == family]
        simple = summarize(float(row["headroom_over_best_simple"]) for row in subset)
        het = summarize(float(row["oracle_heterogeneity"]) for row in subset)
        print(
            f"    {family:16s} n={len(subset):4d} median {_pct(simple['median'])} "
            f"max {_pct(simple['max'])} mixing {het['mean']:.2f}"
        )

    space = summarize(float(row["space_time_ratio"]) for row in rows)
    print()
    print(
        f"  space-time of the optimum over the best uniform choice: "
        f"median {space['median']:.3f} max {space['max']:.3f}"
    )


def controls() -> None:
    """Print the falsification controls and robustness sweeps."""

    path = RESULT_DIR / "mrc2_controls.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    print()
    print("== Falsification controls ==")
    print(
        f"  {'control':12s} {'setting':18s} {'n':>4s} {'vsUnif_med':>10s} "
        f"{'vsUnif_p90':>10s} {'vsSimple_med':>12s} {'mixing':>7s}"
    )
    seen: list[tuple[str, str]] = []
    for row in rows:
        token = (row["control"], row["setting"])
        if token not in seen:
            seen.append(token)
    for control, setting in seen:
        subset = [
            row for row in rows if row["control"] == control and row["setting"] == setting
        ]
        uniform = summarize(float(row["headroom_over_uniform_oracle"]) for row in subset)
        simple = summarize(float(row["headroom_over_best_simple"]) for row in subset)
        het = summarize(float(row["oracle_heterogeneity"]) for row in subset)
        print(
            f"  {control:12s} {setting:18s} {len(subset):4d} {_pct(uniform['median']):>10s} "
            f"{_pct(uniform['p90']):>10s} {_pct(simple['median']):>12s} {het['mean']:7.2f}"
        )


def scaling() -> None:
    """Print the scaling behaviour."""

    path = RESULT_DIR / "mrc3_scaling.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    print()
    print("== Scaling ==")
    print(
        f"  {'family':16s} {'conc':>5s} {'size':>5s} {'exact':>6s} {'vsUnif_med':>10s} "
        f"{'vsSimple_med':>12s} {'mixing':>7s} {'descent':>8s} {'oracle_s':>9s}"
    )
    keys: list[tuple[str, int, int]] = []
    for row in rows:
        token = (row["family"], int(row["concurrency"]), int(row["size"]))
        if token not in keys:
            keys.append(token)
    for family, concurrency, size in keys:
        subset = [
            row
            for row in rows
            if row["family"] == family
            and int(row["concurrency"]) == concurrency
            and int(row["size"]) == size
        ]
        uniform = summarize(float(row["headroom_over_uniform_oracle"]) for row in subset)
        simple = summarize(float(row["headroom_over_best_simple"]) for row in subset)
        het = summarize(float(row["oracle_heterogeneity"]) for row in subset)
        descent = summarize(float(row["sim_descent_regret"]) for row in subset)
        seconds = summarize(float(row["seconds_global_oracle"]) for row in subset)
        exact = sum(int(row["oracle_exhaustive"]) for row in subset)
        print(
            f"  {family:16s} {concurrency:5d} {size:5d} {exact:>3d}/{len(subset):<2d} "
            f"{_pct(uniform['median']):>10s} {_pct(simple['median']):>12s} "
            f"{het['mean']:7.2f} {descent['mean']:8.3f} {seconds['mean']:9.2f}"
        )


def sensitivity() -> None:
    """Print how the result depends on the relative cost of the two routes."""

    path = RESULT_DIR / "mrc4_sensitivity.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    print()
    print("== Sensitivity to the relative cost of the two rotation routes ==")
    print(
        f"  {'scale':>6s} {'cheaper':>8s} {'n':>4s} {'vsUnif_med':>10s} "
        f"{'vsSimple_med':>12s} {'vsSimple_p90':>12s} {'mixing':>7s}"
    )
    for scale in sorted({float(row["toffoli_scale"]) for row in rows}):
        subset = [row for row in rows if float(row["toffoli_scale"]) == scale]
        uniform = summarize(float(row["headroom_over_uniform_oracle"]) for row in subset)
        simple = summarize(float(row["headroom_over_best_simple"]) for row in subset)
        het = summarize(float(row["oracle_heterogeneity"]) for row in subset)
        print(
            f"  {scale:6.2f} {subset[0]['cheaper_route']:>8s} {len(subset):4d} "
            f"{_pct(uniform['median']):>10s} {_pct(simple['median']):>12s} "
            f"{_pct(simple['p90']):>12s} {het['mean']:7.2f}"
        )


def main() -> None:
    """Print every number quoted by the memo."""

    headroom()
    controls()
    scaling()
    sensitivity()


if __name__ == "__main__":
    main()
