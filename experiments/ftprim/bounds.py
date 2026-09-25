"""Solver-independent upper bound on the true oracle benefit F(A*) / F(C*).

Usage:  python experiments/ftprim/bounds.py WORKLOADS.csv OUT.json

A* is a true ebit-optimal trajectory (B* batches, the minimum over all feasible
trajectories) and C* a true failure-optimal one. All cost terms are
non-negative (costs clamped as in the runner). With e = max(e_remote - e_local,
e_tel), n_q qubits, L CX layers, |CX| gates and rho rounds per batch:

    F(A*) <= e_local |CX| + e B* + s_mem n_q max(4 + 3L + 3B*, rho B*)
             (at most B* teleports, each adding at most 3 rounds), and
    F(C*) >= e_local |CX| + s_mem n_q max(4 + 3L, rho B*)
             (C* has at least B* batches and at least the move-free compute time).

B* is unknown but lies in [0, B_A], where B_A is the batch count of the
trajectory A found by the solver, so the supremum of the ratio over that range
bounds the true benefit without relying on any optimality certificate. The
bound is tight only when generation dominates (rho large); at rho = 0 it is
weak, and those regimes are reported with the achieved values only.
"""

from __future__ import annotations

import csv
import json
import sys


def bound(row) -> float:
    e_l, e_r, e_t = float(row["e_local"]), float(row["e_remote"]), float(row["e_tel"])
    s, rho = float(row["s_mem"]), float(row["rho"])
    nq, L, cx = int(float(row["nq"])), int(float(row["layers"])), int(float(row["cx"]))
    e = max(e_r - e_l, e_t)
    B_A = int(float(row["A_ebit_pairs"]) / float(row["n"]))
    best = 1.0
    for B in range(0, B_A + 1):
        num = e_l * cx + e * B + s * nq * max(4 + 3 * L + 3 * B, rho * B)
        den = e_l * cx + s * nq * max(4 + 3 * L, rho * B)
        if den > 0:
            best = max(best, num / den)
    return best


def main() -> None:
    rows = list(csv.DictReader(open(sys.argv[1])))
    out = []
    for r in rows:
        if float(r["static_remote"]) < 10:
            continue
        fa, fc = float(r["A_fail_sum"]), float(r["C_fail_sum"])
        out.append(dict(workload=r["workload"], regime=r["regime"], regime_class=r["regime_class"],
                        rho=float(r["rho"]), achieved_ratio=fa / fc, true_ratio_upper_bound=bound(r)))
    summary = {}
    for cls in ("realistic", "near-term", "idealised"):
        xs = sorted(x["true_ratio_upper_bound"] for x in out if x["regime_class"] == cls)
        if xs:
            summary[cls] = dict(instances=len(xs), median_bound=xs[len(xs) // 2], max_bound=xs[-1])
    by_regime = {}
    for x in out:
        if x["regime_class"] == "realistic":
            by_regime.setdefault(x["regime"], []).append(x["true_ratio_upper_bound"])
    summary["realistic_by_regime_max_bound"] = {k: max(v) for k, v in sorted(by_regime.items())}
    json.dump(dict(summary=summary, rows=out), open(sys.argv[2], "w"), indent=1, default=float)
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
