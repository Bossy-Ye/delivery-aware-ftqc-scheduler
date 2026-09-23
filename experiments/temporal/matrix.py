"""The full frozen matrix, run to confirm the screening's verdict."""

from __future__ import annotations

import statistics as st
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_temporal import ASSIGNMENTS, FIELDS, MACHINES, TRANSFORMS, run_case

from ftqc_delivery.mrc.corpus import CORPUS
from ftqc_delivery.utils.io import write_csv_rows

RESULT_DIR = Path(__file__).resolve().parents[2] / "results" / "temporal_transform_go_nogo"
EXTRA = ["baseline_makespan", "improvement", "baseline_depth", "depth_reduction", "supply_bound"]


def _job(args):
    workload, assignment, machine = args
    rows = []
    base = None
    base_depth = None
    for transformation in TRANSFORMS:
        row = run_case(workload, transformation, machine, assignment)
        if transformation == "conventional":
            base, base_depth = row["makespan"], row["depth"]
        row["baseline_makespan"] = base
        row["baseline_depth"] = base_depth
        row["improvement"] = round((base - row["makespan"]) / base, 4) if base else 0.0
        row["depth_reduction"] = round((base_depth - row["depth"]) / base_depth, 4) if base_depth else 0.0
        # A run is supply bound when waiting for magic states, not the
        # dependency chain, is what keeps it from finishing sooner.
        row["supply_bound"] = int(row["makespan"] > 1.10 * row["depth"])
        rows.append(row)
    return rows


def main() -> None:
    jobs = [
        (w.name, a, m[0])
        for w in CORPUS
        for a in ASSIGNMENTS
        for m in MACHINES
    ]
    rows = []
    with Pool(processes=3) as pool:
        for done, produced in enumerate(pool.imap_unordered(_job, jobs), 1):
            rows.extend(produced)
            if done % 40 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}", flush=True)
    rows.sort(key=lambda r: (r["role"], r["workload"], r["assignment"], r["machine"], r["transformation"]))
    write_csv_rows(RESULT_DIR / "RAW_RESULTS.csv", rows, FIELDS + EXTRA)
    print(f"wrote {len(rows)} rows")

    print(f"\n== is anything supply bound? ==")
    for regime in ("constrained", "moderate", "abundant"):
        sub = [r for r in rows if r["regime"] == regime and r["transformation"] == "conventional"]
        print(f"  {regime:12s} n={len(sub):4d} supply-bound={sum(r['supply_bound'] for r in sub):4d} "
              f"median stalls={st.median([r['total_stalls'] for r in sub]):7.1f} "
              f"median makespan/depth={st.median([r['makespan'] / max(1, r['depth']) for r in sub]):.3f}")

    print(f"\n== improvement by transformation and regime (targets) ==")
    print(f"  {'transformation':20s} {'regime':12s} {'n':>4s} {'median':>8s} {'mean':>8s} {'max':>8s} {'>=10%':>6s}")
    for transformation in TRANSFORMS:
        if transformation == "conventional":
            continue
        for regime in ("constrained", "moderate", "abundant"):
            sub = [r for r in rows if r["transformation"] == transformation
                   and r["regime"] == regime and r["role"] == "target"]
            v = [r["improvement"] for r in sub]
            if v:
                print(f"  {transformation:20s} {regime:12s} {len(v):4d} {st.median(v):+8.3f} "
                      f"{st.fmean(v):+8.3f} {max(v):+8.3f} {sum(1 for x in v if x >= 0.10):6d}")

    print(f"\n== controls ==")
    for transformation in TRANSFORMS:
        if transformation == "conventional":
            continue
        sub = [r for r in rows if r["transformation"] == transformation and r["role"] == "control"]
        v = [r["improvement"] for r in sub]
        print(f"  {transformation:20s} n={len(v):4d} median={st.median(v):+.3f} max={max(v):+.3f}")

    print(f"\n== does the gain track supply tightness or depth? (commuting, targets) ==")
    for regime in ("constrained", "moderate", "abundant"):
        sub = [r for r in rows if r["transformation"] == "commuting"
               and r["regime"] == regime and r["role"] == "target"]
        imp = [r["improvement"] for r in sub]
        dep = [r["depth_reduction"] for r in sub]
        print(f"  {regime:12s} median improvement={st.median(imp):+.3f}  median depth reduction={st.median(dep):+.3f}")


if __name__ == "__main__":
    main()
