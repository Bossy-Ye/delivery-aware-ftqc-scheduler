"""Robustness check: the ebit baseline at its best across every computed plan.

Usage:  python experiments/ftprim/best_baseline.py WORKLOADS.csv OUT.json

Where CP-SAT did not prove the ebit plan A optimal, another computed plan
(C, a threshold plan or the static plan) can use fewer ebit batches. A_best is
the lowest-failure plan among those with the fewest batches over all computed
plans, which is what the contract's "resource baseline at its best" intends.
The frozen verdict uses A as run; this file reports how the benefit changes.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys

POLICIES = ["static", "A", "C"] + [f"B{K}" for K in range(1, 31)]


def main() -> None:
    rows = list(csv.DictReader(open(sys.argv[1])))
    out, changed = [], 0
    for r in rows:
        if float(r["static_remote"]) < 10:
            continue
        cand = [(float(r[f"{p}_ebit_pairs"]), float(r[f"{p}_fail_sum"]), p) for p in POLICIES]
        bmin = min(c[0] for c in cand)
        best = min((c for c in cand if c[0] == bmin), key=lambda c: c[1])
        fa, fc = float(r["A_fail_sum"]), float(r["C_fail_sum"])
        changed += best[2] != "A" and float(r["A_ebit_pairs"]) > bmin
        out.append(dict(workload=r["workload"], regime=r["regime"], regime_class=r["regime_class"],
                        A_batches_ebits=float(r["A_ebit_pairs"]), best_ebits=bmin, best_policy=best[2],
                        ratio_as_run=fa / fc, ratio_best_baseline=best[1] / fc))
    summary = {}
    for cls in ("realistic", "near-term", "idealised"):
        xs = [x for x in out if x["regime_class"] == cls]
        if xs:
            summary[cls] = dict(
                instances=len(xs),
                median_ratio_as_run=statistics.median(x["ratio_as_run"] for x in xs),
                max_ratio_as_run=max(x["ratio_as_run"] for x in xs),
                median_ratio_best_baseline=statistics.median(x["ratio_best_baseline"] for x in xs),
                max_ratio_best_baseline=max(x["ratio_best_baseline"] for x in xs),
                instances_where_A_was_not_ebit_best=sum(1 for x in xs if x["A_batches_ebits"] > x["best_ebits"]))
    json.dump(dict(summary=summary, rows=out), open(sys.argv[2], "w"), indent=1, default=float)
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
