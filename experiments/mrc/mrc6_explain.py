"""Phase 3-4: when does local (per-site or uniform) selection fail, and why?

Every case of the main matrix is described by structural features that a
compiler could compute *before* selecting anything: how hard the factories are
pressed, how far the two banks are from balanced, how far the best uniform
choice's demand mix sits from the supply mix, how many sites run concurrently,
how many stages there are, and how diverse the implementations on offer are.
The question is whether those features predict the cases where the global
optimum beats every simple policy by more than 5%.

Rules are evaluated leave-one-kernel-out, so a threshold tuned on one kernel
family has to work on kernels it never saw.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, kernels, read_csv, summarize, write_csv

from ftqc_delivery.mrc.execution import resource_counts
from ftqc_delivery.mrc.kernels import decision_sites
from ftqc_delivery.mrc.policies import symmetric_groups, t_equivalents

THRESHOLD = 0.05


def kernel_structure(program) -> dict[str, float]:
    """Return structural features of a kernel that do not depend on the machine."""

    groups = symmetric_groups(program)
    sites = decision_sites(program)
    signatures: dict[tuple, int] = {}
    for group in groups:
        key = (
            tuple(sorted(p for p, s in program.edges if s == group[0].site_id)),
            tuple(sorted(s for p, s in program.edges if p == group[0].site_id)),
        )
        signatures[key] = signatures.get(key, 0) + len(group)
    widths = list(signatures.values())

    cross_ratios = []
    variant_counts = []
    for site in sites:
        costs = {}
        for name in site.variant_names:
            counts = resource_counts(site.variant(name).fragment.to_dag(name))
            present = tuple(sorted(r for r, c in counts.items() if c > 0))
            costs.setdefault(present, []).append(t_equivalents(counts))
        variant_counts.append(len(site.variant_names))
        pure = {k: min(v) for k, v in costs.items() if len(k) == 1}
        if len(pure) >= 2:
            values = sorted(pure.values())
            cross_ratios.append(values[1] / values[0])
    return {
        "stages": len(signatures),
        "max_stage_width": max(widths) if widths else 0,
        "serial_fraction": sum(1 for w in widths if w == 1) / len(widths) if widths else 1.0,
        "mean_variants_per_site": sum(variant_counts) / len(variant_counts) if variant_counts else 0,
        "min_cross_resource_cost_ratio": min(cross_ratios) if cross_ratios else float("nan"),
        "families": len({site.family for site in sites}),
    }


def build_features() -> list[dict[str, object]]:
    from ftqc_delivery.mrc.policies import select_uniform_oracle
    from ftqc_delivery.mrc.resources import machine_for_capacity

    rows = read_csv(RESULT_DIR / "mrc1_cases.csv")
    catalogue = {k.name: k for k in kernels()}
    structure = {name: kernel_structure(program) for name, program in catalogue.items()}
    out = []
    for row in rows:
        t_rate = float(row["t_rate"]); ccz_rate = float(row["ccz_rate"])
        capacity = t_rate + 2 * ccz_rate
        supply_ccz_share = 2 * ccz_rate / capacity if capacity > 0 else 0.0
        uniform_mix = float(row["uniform_ccz_share_of_demand"])
        # Wasted production under the best uniform choice: the share of the
        # machine's T-equivalent output over that plan's runtime that nothing
        # consumes. A compiler can estimate it from static counts and rates.
        machine = machine_for_capacity(float(row["capacity_target"]), float(row["ccz_share"]))
        program = catalogue[row["kernel"]]
        uniform = select_uniform_oracle(program, machine)
        demand_teq = t_equivalents(uniform.counts)
        produced_teq = capacity * uniform.makespan
        uniform_waste = max(0.0, 1.0 - demand_teq / produced_teq) if produced_teq > 0 else 0.0
        feat = {
            "kernel": row["kernel"],
            "family": row["family"],
            "capacity_target": float(row["capacity_target"]),
            "ccz_share": float(row["ccz_share"]),
            "supply_pressure": float(row["supply_pressure"]),
            "imbalance": float(row["imbalance"]),
            "supply_ccz_share": round(supply_ccz_share, 4),
            "uniform_mix_mismatch": round(abs(uniform_mix - supply_ccz_share), 4),
            "uniform_waste": round(uniform_waste, 4),
            "concurrency": int(row["concurrency"]),
            "decision_sites": int(row["decision_sites"]),
            **structure[row["kernel"]],
            "headroom_over_best_simple": float(row["headroom_over_best_simple"]),
            "headroom_over_uniform": float(row["headroom_over_uniform_oracle"]),
            "oracle_exhaustive": int(row["oracle_exhaustive"]),
            "fails": int(float(row["headroom_over_best_simple"]) > THRESHOLD),
        }
        out.append(feat)
    return out


NUMERIC = (
    "supply_pressure", "imbalance", "supply_ccz_share", "uniform_mix_mismatch", "uniform_waste",
    "concurrency", "decision_sites", "stages", "max_stage_width",
    "serial_fraction", "mean_variants_per_site", "min_cross_resource_cost_ratio",
    "families", "capacity_target",
)


def _f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return (2 * p * r / (p + r) if p + r else 0.0), p, r


def best_threshold(rows, feature, direction):
    """Return the threshold on ``feature`` maximising F1 for predicting failure."""

    values = sorted({r[feature] for r in rows if r[feature] == r[feature]})
    best = (0.0, None, 0, 0)
    for value in values:
        pred = [(r[feature] >= value) if direction == ">=" else (r[feature] <= value) for r in rows]
        tp = sum(1 for p, r in zip(pred, rows) if p and r["fails"])
        fp = sum(1 for p, r in zip(pred, rows) if p and not r["fails"])
        fn = sum(1 for p, r in zip(pred, rows) if not p and r["fails"])
        f1, p, rc = _f1(tp, fp, fn)
        if f1 > best[0]:
            best = (f1, value, p, rc)
    return best


def loko_rule(rows, feature, direction):
    """Leave-one-kernel-out evaluation of a single-feature threshold rule."""

    kernels_ = sorted({r["kernel"] for r in rows})
    tp = fp = fn = tn = 0
    for held in kernels_:
        train = [r for r in rows if r["kernel"] != held]
        test = [r for r in rows if r["kernel"] == held]
        _, thr, _, _ = best_threshold(train, feature, direction)
        if thr is None:
            continue
        for r in test:
            pred = (r[feature] >= thr) if direction == ">=" else (r[feature] <= thr)
            if pred and r["fails"]: tp += 1
            elif pred and not r["fails"]: fp += 1
            elif not pred and r["fails"]: fn += 1
            else: tn += 1
    f1, p, rc = _f1(tp, fp, fn)
    return f1, p, rc, tp, fp, fn, tn


def loko_pair(rows, fa, da, fb, db):
    """Leave-one-kernel-out evaluation of a conjunction of two threshold rules."""

    kernels_ = sorted({r["kernel"] for r in rows})
    tp = fp = fn = 0
    for held in kernels_:
        train = [r for r in rows if r["kernel"] != held]
        test = [r for r in rows if r["kernel"] == held]
        _, ta, _, _ = best_threshold(train, fa, da)
        if ta is None:
            continue
        sub = [r for r in train if ((r[fa] >= ta) if da == ">=" else (r[fa] <= ta))]
        _, tb, _, _ = best_threshold(sub, fb, db) if sub else (0, None, 0, 0)
        for r in test:
            pa = (r[fa] >= ta) if da == ">=" else (r[fa] <= ta)
            pb = True if tb is None else ((r[fb] >= tb) if db == ">=" else (r[fb] <= tb))
            pred = pa and pb
            if pred and r["fails"]: tp += 1
            elif pred and not r["fails"]: fp += 1
            elif not pred and r["fails"]: fn += 1
    return _f1(tp, fp, fn) + (tp, fp, fn)


def main() -> None:
    rows = build_features()
    write_csv(RESULT_DIR / "mrc6_features.csv", rows, list(rows[0].keys()))
    fails = sum(r["fails"] for r in rows)
    print(f"cases {len(rows)}, local selection fails (>5% headroom over every simple policy) in {fails} ({100*fails/len(rows):.1f}%)")

    print("\n== Univariate: failure rate and mean headroom by feature tercile ==")
    for feature in NUMERIC:
        vals = sorted(r[feature] for r in rows if r[feature] == r[feature])
        if not vals or vals[0] == vals[-1]:
            continue
        cuts = (vals[len(vals)//3], vals[2*len(vals)//3])
        parts = []
        for lo, hi, label in ((None, cuts[0], "low"), (cuts[0], cuts[1], "mid"), (cuts[1], None, "high")):
            sub = [r for r in rows if r[feature] == r[feature] and (lo is None or r[feature] >= lo) and (hi is None or r[feature] < hi)]
            if not sub:
                continue
            parts.append(f"{label}(n={len(sub)}) fail={100*sum(x['fails'] for x in sub)/len(sub):4.1f}% head={100*summarize(x['headroom_over_best_simple'] for x in sub)['mean']:4.1f}%")
        print(f"  {feature:30s} " + " | ".join(parts))

    print("\n== Single-feature rules, leave-one-kernel-out ==")
    rule_rows = []
    for feature in NUMERIC:
        for direction in (">=", "<="):
            f1, p, rc, tp, fp, fn, tn = loko_rule(rows, feature, direction)
            _, thr, _, _ = best_threshold(rows, feature, direction)
            rule_rows.append({"rule": f"{feature} {direction} {thr}", "f1": round(f1, 3), "precision": round(p, 3), "recall": round(rc, 3), "tp": tp, "fp": fp, "fn": fn})
    rule_rows.sort(key=lambda r: -r["f1"])
    for r in rule_rows[:10]:
        print(f"  {r['rule']:50s} F1={r['f1']:.3f} P={r['precision']:.3f} R={r['recall']:.3f} (tp {r['tp']}, fp {r['fp']}, fn {r['fn']})")

    print("\n== Two-feature conjunctions, leave-one-kernel-out ==")
    pair_rows = []
    candidates = [("supply_pressure", ">="), ("uniform_mix_mismatch", ">="), ("uniform_waste", ">="), ("imbalance", "<="), ("imbalance", ">="),
                  ("stages", ">="), ("serial_fraction", ">="), ("max_stage_width", ">="), ("concurrency", "<="),
                  ("min_cross_resource_cost_ratio", ">="), ("min_cross_resource_cost_ratio", "<="), ("families", ">=")]
    for i, (fa, da) in enumerate(candidates):
        for fb, db in candidates[i+1:]:
            if fa == fb:
                continue
            f1, p, rc, tp, fp, fn = loko_pair(rows, fa, da, fb, db)
            pair_rows.append({"rule": f"{fa}{da} & {fb}{db}", "f1": round(f1, 3), "precision": round(p, 3), "recall": round(rc, 3), "tp": tp, "fp": fp, "fn": fn})
    pair_rows.sort(key=lambda r: -r["f1"])
    for r in pair_rows[:10]:
        print(f"  {r['rule']:60s} F1={r['f1']:.3f} P={r['precision']:.3f} R={r['recall']:.3f}")
    write_csv(RESULT_DIR / "mrc6_rules.csv", rule_rows + pair_rows, ["rule", "f1", "precision", "recall", "tp", "fp", "fn"])

    print("\n== By family: structure and failure ==")
    fams = sorted({r["family"] for r in rows})
    print(f"  {'family':16s} {'n':>3s} {'fail%':>6s} {'head_mean':>9s} {'head_max':>8s} {'stages':>6s} {'width':>5s} {'serial':>6s} {'xratio':>6s} {'mismatch':>8s}")
    for fam in fams:
        sub = [r for r in rows if r["family"] == fam]
        print(f"  {fam:16s} {len(sub):3d} {100*sum(r['fails'] for r in sub)/len(sub):6.1f} "
              f"{100*summarize(r['headroom_over_best_simple'] for r in sub)['mean']:9.1f} "
              f"{100*summarize(r['headroom_over_best_simple'] for r in sub)['max']:8.1f} "
              f"{summarize(r['stages'] for r in sub)['mean']:6.1f} {summarize(r['max_stage_width'] for r in sub)['mean']:5.1f} "
              f"{summarize(r['serial_fraction'] for r in sub)['mean']:6.2f} {summarize(r['min_cross_resource_cost_ratio'] for r in sub)['mean']:6.2f} "
              f"{summarize(r['uniform_mix_mismatch'] for r in sub)['mean']:8.2f}")


if __name__ == "__main__":
    main()
