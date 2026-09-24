"""Real workloads: resource-optimal vs threshold vs failure-optimal decisions.

Usage (main env):
    python experiments/ftprim/workloads_run.py FITS.json OUTDIR [--names a,b] [--slack 1]

For every workload and regime the same static partition and capacity are used by
all policies:

* A      exact ebit-optimal trajectory (CP-SAT); ties broken toward the lowest
         failure for the regime (the resource baseline at its best);
* B(K)   the myopic burst threshold rule for K = 1..30 (regime-independent
         trajectories, scored per regime); the best fixed K and the best K per
         regime are selected afterwards over the realistic set;
* C      failure-optimal trajectory: CP-SAT optimum warm-started from A and the
         threshold trajectories, reported as the best of all candidates with the
         solver's proven bound.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ftqc_delivery.ftprim import oracle as O  # noqa: E402
from ftqc_delivery.ftprim import workloads as W  # noqa: E402
from ftqc_delivery.utils.io import write_csv_rows  # noqa: E402

KS = range(1, 31)


def regimes(fits: dict, spec: list):
    """Explicit regime list (WORKLOAD_REGIMES.json) resolved against the fits."""
    by = {(f["code"], f["p"], f["ratio"]): (name, f) for name, f in fits.items()}
    for reg in spec:
        name, f = by[(reg["code"], reg["p"], reg["ratio"])]
        d = f["derived"]
        yield dict(regime=f"{name}|rho={reg['rho']:g}", regime_class=reg["regime_class"], code=f["code"],
                   d=f["d"], n=f["n"], p=f["p"], ratio=f["ratio"], rho=reg["rho"]), O.Costs(
            e_remote=d["e_remote"], e_local=d["e_local"], e_tel=d["e_tel"], s_mem=d["s_mem"],
            n=f["n"], rho=float(reg["rho"]))


def _moves(homes, loc):
    full = np.concatenate([np.array(homes)[:, None], loc], axis=1)
    return full[:, 1:] != full[:, :-1]


def _decision_disagreement(w, homes, a_loc, c_loc) -> float:
    """Share of decisions that differ: CX local/remote statuses plus teleport
    placements (qubit, layer), over all CX and all teleports made by either."""
    if not w.gates:
        return 0.0
    status = sum((a_loc[a, l] != a_loc[b, l]) != (c_loc[a, l] != c_loc[b, l])
                 for (a, b), l in zip(w.gates, w.layer))
    ma, mc = _moves(homes, a_loc), _moves(homes, c_loc)
    moved = int((ma ^ mc).sum())
    return (status + moved) / (len(w.gates) + int((ma | mc).sum()))


def run_workload(entry, fits, spec, slack, limits, out_rows, traj_dir, workers=1):
    w = W.load(entry)
    homes = W.initial_partition(w)
    cap = O.capacities(w.nq, homes, slack)
    static = O.static_loc(w, homes)
    remote0 = sum(1 for a, b in w.gates if homes[a] != homes[b])
    base = dict(workload=w.name, category=w.category, source=w.source, nq=w.nq, cx=len(w.gates),
                layers=w.n_layers, static_remote=remote0, slack=slack, cap0=cap[0], cap1=cap[1])
    t0 = time.perf_counter()
    thresholds = {K: O.threshold_policy(w, homes, cap, K) for K in KS}
    t_thr = time.perf_counter() - t0
    dummy = O.Costs(1e-4, 1e-4, 1e-4, 0.0, 1, 0.0)
    if remote0 == 0:
        a0 = O.Solution(loc=static, status="TRIVIAL", seconds=0.0, objective=0.0, bound=0.0)
    else:
        seeds = [static] + list(thresholds.values())
        best_hint = min(seeds, key=lambda L: O.score(w, homes, L, dummy)["batches"])
        a0 = O.solve(w, homes, cap, "ebits", dummy, time_limit=limits["ebits"], hint=best_hint,
                     workers=workers)
    a0_batches = O.score(w, homes, a0.loc, dummy)["batches"]
    for reg, costs in regimes(fits, spec):
        row = dict(base, **reg)
        cands = {"static": static, **{f"B{K}": L for K, L in thresholds.items()}}
        if remote0 == 0:
            a_loc, a_status, c_loc, c_status, c_bound = static, "TRIVIAL", static, "TRIVIAL", None
            a_sec = c_sec = 0.0
        else:
            tie = O.solve(w, homes, cap, "failure", costs, time_limit=limits["tiebreak"],
                          fix_batches=a0_batches, hint=a0.loc, workers=workers)
            a_loc = min([a0.loc, tie.loc] if tie.status in ("OPTIMAL", "FEASIBLE") else [a0.loc],
                        key=lambda L: O.score(w, homes, L, costs)["fail_sum"])
            a_status, a_sec = f"{a0.status}/{tie.status}", a0.seconds + tie.seconds
            cands["A"] = a_loc
            hint = min(cands.values(), key=lambda L: O.score(w, homes, L, costs)["fail_sum"])
            c = O.solve(w, homes, cap, "failure", costs, time_limit=limits["failure"], hint=hint,
                        workers=workers)
            c_status, c_sec, c_bound = c.status, c.seconds, c.bound
            pool = list(cands.values()) + ([c.loc] if c.status in ("OPTIMAL", "FEASIBLE") else [])
            c_loc = min(pool, key=lambda L: O.score(w, homes, L, costs)["fail_sum"])
        cands["A"] = a_loc
        cands["C"] = c_loc
        scores = {k: O.score(w, homes, L, costs) for k, L in cands.items()}
        a_sc, c_sc = scores["A"], scores["C"]
        unit = None
        if c_bound is not None and remote0:
            unit = O._scale(costs, w.nq)["unit"]
        row.update(
            a_status=a_status, a_seconds=round(a_sec, 2), a_ebits_batches=a0_batches,
            c_status=c_status, c_seconds=round(c_sec, 2),
            c_bound_fail_sum=(None if c_bound is None or unit is None else
                              c_bound * unit + costs.e_local * len(w.gates)),
            threshold_seconds=round(t_thr, 3),
            location_disagreement=float(np.mean(a_loc != c_loc)) if w.n_layers else 0.0,
            decision_disagreement=_decision_disagreement(w, homes, a_loc, c_loc),
            remote_status_disagreement=float(np.mean([
                (a_loc[a, l] != a_loc[b, l]) != (c_loc[a, l] != c_loc[b, l])
                for (a, b), l in zip(w.gates, w.layer)])) if w.gates else 0.0)
        for pol in ["static", "A", "C"] + [f"B{K}" for K in KS]:
            s = scores[pol]
            for key in ("remote_ops", "teleports", "ebit_pairs", "run_rounds", "fail_sum", "fail_prob",
                        "fail_ops", "fail_memory"):
                row[f"{pol}_{key}"] = s[key]
        out_rows.append(row)
        np.savez_compressed(traj_dir / f"{w.name}__{reg['regime'].replace('|', '_')}.npz",
                            A=a_loc, C=c_loc, homes=np.array(homes))
    return w


def _job(args):
    entry, fits, spec, slack, limits, traj = args
    warnings.filterwarnings("ignore")
    rows = []
    t0 = time.perf_counter()
    run_workload(entry, fits, spec, slack, limits, rows, traj, workers=1)
    return entry[0], rows, time.perf_counter() - t0


def main() -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    ap = argparse.ArgumentParser()
    ap.add_argument("fits")
    ap.add_argument("outdir")
    ap.add_argument("--spec", required=True, help="WORKLOAD_REGIMES.json")
    ap.add_argument("--names", default="")
    ap.add_argument("--slack", type=int, default=1)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--limits", default='{"ebits": 120, "tiebreak": 20, "failure": 60}')
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    fits = json.load(open(args.fits))["fits"]
    spec = json.loads(Path(args.spec).read_text())
    limits = json.loads(args.limits)
    outdir = Path(args.outdir)
    traj = outdir / f"trajectories_slack{args.slack}"
    traj.mkdir(parents=True, exist_ok=True)
    names = [n for n in args.names.split(",") if n]
    entries = [e for e in W.WORKLOADS if not names or e[0] in names]
    rows = []
    with ProcessPoolExecutor(args.procs) as pool:
        futs = [pool.submit(_job, (e, fits, spec, args.slack, limits, traj)) for e in entries]
        for fut in as_completed(futs):
            name, r, sec = fut.result()
            rows.extend(r)
            rows.sort(key=lambda x: (x["workload"], x["regime"]))
            write_csv_rows(outdir / f"WORKLOADS_slack{args.slack}.csv", rows, list(rows[0]))
            print(f"{name}: {sec:.0f}s ({len(r)} rows)", flush=True)


if __name__ == "__main__":
    main()
