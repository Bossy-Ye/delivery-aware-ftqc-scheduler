"""Evaluate the frozen gate table against the raw results.

Gate definitions come from the contract and are not adjustable here. Where
the contract left a term open ("the effect appears in a family"), both a
strict and a lenient reading are reported so the choice cannot quietly decide
the outcome.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_marsq import RESULT_DIR, counts_above, read_csv, summarise

RESIDUAL = "residual_headroom_vs_stagedp"
VERSUS = "headroom_vs_best_non_stateful"
CEILING = "max_possible_headroom_vs_stagedp"
EXISTING = "residual_headroom_vs_existing_search"


def main() -> None:
    rows = read_csv(RESULT_DIR / "RAW_RESULTS.csv")
    for row in rows:
        for key in (RESIDUAL, VERSUS, CEILING, EXISTING):
            row[key] = float(row[key])
    targets = [r for r in rows if r["role"] == "target"]
    controls = [r for r in rows if r["role"] == "control"]
    rotation_workloads = {"qt_qft6", "qt_qft8", "qt_prepunif6"}
    rotations = [r for r in targets if r["workload"] in rotation_workloads]

    res_t = summarise(r[RESIDUAL] for r in targets)
    ver_t = summarise(r[VERSUS] for r in targets)
    above_t = counts_above([r[RESIDUAL] for r in targets])
    above_v = counts_above([r[VERSUS] for r in targets])

    families_strict = sorted({r["family"] for r in targets if r[RESIDUAL] > 0.05})
    families_lenient = sorted({
        f for f in {r["family"] for r in targets}
        if summarise(r[RESIDUAL] for r in targets if r["family"] == f)["median"] > 0.02
    })
    sources_strict = sorted({r["source"] for r in targets if r[RESIDUAL] > 0.05})
    control_max = max((r[RESIDUAL] for r in controls), default=0.0)

    by_model = {
        m: summarise(r[RESIDUAL] for r in targets if r["model"] == m) for m in ("A", "B", "C")
    }
    by_regime = {
        g: summarise(r[RESIDUAL] for r in targets if r["regime"] == g)
        for g in ("standard", "scarce", "abundant")
    }
    robust = all(by_model[m]["median"] is not None for m in by_model) and (
        sum(1 for m in by_model if by_model[m]["max"] > 0.05) >= 2
    )

    print("== raw counts ==")
    print(f"cases={len(rows)} targets={len(targets)} controls={len(controls)} "
          f"proven={sum(1 for r in rows if r['oracle_status']=='proven')}")
    print(f"targets residual : {res_t}")
    print(f"targets vs non-stateful : {ver_t}")
    print(f"targets residual counts : {above_t}")
    print(f"targets vs-non-stateful counts : {above_v}")
    print(f"controls residual : {summarise(r[RESIDUAL] for r in controls)}")
    print(f"targets vs existing search (sim_descent) : {summarise(r[EXISTING] for r in targets)}")
    print(f"targets bound ceiling : {summarise(r[CEILING] for r in targets)}")
    print(f"rotation workloads residual : {summarise(r[RESIDUAL] for r in rotations)} (n={len(rotations)})")
    print(f"by model : { {m: (v['median'], v['max']) for m, v in by_model.items()} }")
    print(f"by regime : { {g: (v['median'], v['max']) for g, v in by_regime.items()} }")

    gates = [
        ("Wide-workload oracle gain vs best non-stateful", ">=10% median",
         f"{ver_t['median']:+.1%} median", ver_t["median"] >= 0.10),
        ("Residual oracle gain vs stage-DP", ">=5% median",
         f"{res_t['median']:+.1%} median", res_t["median"] >= 0.05),
        ("Independent workload families", ">=3",
         f"{len(families_strict)} with a case >5% ({', '.join(families_strict) or 'none'}); "
         f"{len(families_lenient)} with median >2%", len(families_strict) >= 3),
        ("Independent workload sources", ">=2",
         f"{len(sources_strict)} ({', '.join(sources_strict) or 'none'})", len(sources_strict) >= 2),
        ("Multiple >10% external cases", "yes",
         f"{above_t['gt10pct']} of {len(targets)} target cases", above_t["gt10pct"] >= 2),
        ("Negative controls near zero", "yes",
         f"max {control_max:+.1%} over {len(controls)} cases", control_max <= 0.01),
        ("Robust to machine variation", "yes",
         f"median by model A/B/C = {by_model['A']['median']:+.1%}/{by_model['B']['median']:+.1%}/"
         f"{by_model['C']['median']:+.1%}", robust),
        ("Second resource family", "supported",
         f"rotation workloads median {summarise(r[RESIDUAL] for r in rotations)['median']:+.1%}, "
         f"max {summarise(r[RESIDUAL] for r in rotations)['max']:+.1%}",
         summarise(r[RESIDUAL] for r in rotations)["median"] >= 0.05),
    ]

    print("\n| Gate | Required | Observed | Pass/Fail |")
    print("| --- | ---: | ---: | --- |")
    for name, required, observed, passed in gates:
        print(f"| {name} | {required} | {observed} | {'PASS' if passed else 'FAIL'} |")
    print(f"\ngates passed: {sum(1 for *_, p in gates if p)} of {len(gates)}")


if __name__ == "__main__":
    main()
