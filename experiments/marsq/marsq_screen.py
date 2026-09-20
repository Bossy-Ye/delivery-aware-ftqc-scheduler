"""Screening phase: is there any oracle opportunity worth scaling up?

Three controls and five wide or heterogeneous targets on five machines. If
every credible wide workload shows at most 2% residual headroom over the
stage-DP, and the lower bound proves no more is available, the study stops
here with a likely NO-GO rather than spending a full matrix on it.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_marsq import RESULT_DIR, machine_grid, machine_meta, summarise, write_csv
from marsq_run import CASE_FIELDS, run_case

SCREEN_TARGETS = ("qmpa_draper8", "qmpa_draper16", "qt_aliassamp8", "qb_multiplier_n15", "qt_qft6")
SCREEN_CONTROLS = ("qt_add16", "qt_multiand10", "qt_qrom16x5")
SCREEN_MACHINES = ("A_400_0.5", "B_400_0.5", "C_400_0.5", "A_800_0.5", "C_800_0.5")


def _job(args):
    name, role, label = args
    machines = dict(machine_grid())
    machine = machines[label]
    row = run_case(name, label, machine, role)
    row.update(machine_meta(label, machine))
    return row


def main() -> None:
    jobs = [(n, "target", m) for n in SCREEN_TARGETS for m in SCREEN_MACHINES]
    jobs += [(n, "control", m) for n in SCREEN_CONTROLS for m in SCREEN_MACHINES]
    rows = []
    with Pool(processes=3) as pool:
        for done, row in enumerate(pool.imap_unordered(_job, jobs), 1):
            rows.append(row)
            print(f"  {done}/{len(jobs)} {row['workload']} on {row['machine']}: "
                  f"dp={row['makespan_stagedp']} oracle={row['makespan_oracle']} "
                  f"({row['oracle_status']}) residual={row['residual_headroom_vs_stagedp']:+.3f}",
                  flush=True)
    rows.sort(key=lambda r: (r["role"], r["workload"], r["machine"]))
    write_csv(RESULT_DIR / "SCREENING_RESULTS.csv", rows, CASE_FIELDS + ["model", "tiles", "regime"])

    targets = [r for r in rows if r["role"] == "target"]
    controls = [r for r in rows if r["role"] == "control"]
    print("\n== screening summary ==")
    for label, subset in (("targets", targets), ("controls", controls)):
        residual = [r["residual_headroom_vs_stagedp"] for r in subset]
        versus = [r["headroom_vs_best_non_stateful"] for r in subset]
        ceiling = [r["max_possible_headroom_vs_stagedp"] for r in subset]
        print(f"{label}: n={len(subset)} proven={sum(1 for r in subset if r['oracle_status']=='proven')}")
        print(f"   residual vs stage-DP : {summarise(residual)}")
        print(f"   vs best non-stateful : {summarise(versus)}")
        print(f"   max possible (bound) : {summarise(ceiling)}")
    decisive = [r for r in targets if r["residual_headroom_vs_stagedp"] > 0.02]
    print(f"\ntarget cases with residual > 2%: {len(decisive)} of {len(targets)}")
    provable_dead = [r for r in targets if r["max_possible_headroom_vs_stagedp"] <= 0.02]
    print(f"target cases where the bound proves <= 2% is available: {len(provable_dead)} of {len(targets)}")


if __name__ == "__main__":
    main()
