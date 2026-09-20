"""The full frozen matrix: every corpus workload on every frozen machine."""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_marsq import (
    RESULT_DIR,
    counts_above,
    machine_grid,
    machine_meta,
    read_csv,
    summarise,
    write_csv,
)
from marsq_run import CASE_FIELDS, run_case

EXTRA_FIELDS = ["model", "tiles", "regime"]


def _job(args):
    name, role, label = args
    machine = dict(machine_grid())[label]
    row = run_case(name, label, machine, role, exact_time_budget=40.0, search_budget=20.0)
    row.update(machine_meta(label, machine))
    return row


def report(rows: list[dict]) -> None:
    def block(label: str, subset: list[dict]) -> None:
        if not subset:
            return
        residual = [float(r["residual_headroom_vs_stagedp"]) for r in subset]
        versus = [float(r["headroom_vs_best_non_stateful"]) for r in subset]
        ceiling = [float(r["max_possible_headroom_vs_stagedp"]) for r in subset]
        proven = sum(1 for r in subset if r["oracle_status"] == "proven")
        res, ver = summarise(residual), summarise(versus)
        above = counts_above(residual)
        above_v = counts_above(versus)
        print(
            f"  {label:30s} n={len(subset):3d} proven={proven:3d} | "
            f"residual vs stage-DP med={res['median']:+.3f} mean={res['mean']:+.3f} "
            f"p75={res['p75']:+.3f} p90={res['p90']:+.3f} max={res['max']:+.3f} "
            f">2/5/10/20%={above['gt2pct']}/{above['gt5pct']}/{above['gt10pct']}/{above['gt20pct']} | "
            f"vs non-stateful med={ver['median']:+.3f} max={ver['max']:+.3f} "
            f">10%={above_v['gt10pct']} | bound-ceiling med={summarise(ceiling)['median']:.3f}"
        )

    targets = [r for r in rows if r["role"] == "target"]
    controls = [r for r in rows if r["role"] == "control"]
    print("\n== primary ==")
    block("TARGETS", targets)
    block("CONTROLS", controls)
    print("\n== by source (targets) ==")
    for source in sorted({r["source"] for r in targets}):
        block(source, [r for r in targets if r["source"] == source])
    print("\n== by family (targets) ==")
    for family in sorted({r["family"] for r in targets}):
        block(family, [r for r in targets if r["family"] == family])
    print("\n== by machine regime (targets) ==")
    for model in ("A", "B", "C"):
        block(f"model {model}", [r for r in targets if r["model"] == model])
    for regime in ("standard", "scarce", "abundant"):
        block(f"regime {regime}", [r for r in targets if r["regime"] == regime])
    for tiles in ("400", "800", "3200"):
        block(f"{tiles} tiles", [r for r in targets if r["tiles"] == tiles])
    print("\n== per workload (targets) ==")
    for name in sorted({r["workload"] for r in targets}):
        block(name, [r for r in targets if r["workload"] == name])
    print("\n== per workload (controls) ==")
    for name in sorted({r["workload"] for r in controls}):
        block(name, [r for r in controls if r["workload"] == name])


def main() -> None:
    features = {r["workload"]: r for r in read_csv(RESULT_DIR / "WORKLOAD_FEATURES.csv")}
    jobs = [
        (name, row["role"], label)
        for name, row in features.items()
        for label, _ in machine_grid()
    ]
    rows = []
    with Pool(processes=3) as pool:
        for done, row in enumerate(pool.imap_unordered(_job, jobs), 1):
            rows.append(row)
            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}", flush=True)
    rows.sort(key=lambda r: (r["role"], r["workload"], r["machine"]))
    write_csv(RESULT_DIR / "RAW_RESULTS.csv", rows, CASE_FIELDS + EXTRA_FIELDS)
    print(f"wrote {len(rows)} rows")
    report(rows)


if __name__ == "__main__":
    main()
