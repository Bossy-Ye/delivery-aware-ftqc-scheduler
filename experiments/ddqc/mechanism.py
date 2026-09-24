"""Separate the competing explanations for any branch-aware advantage.

H1  mutually exclusive communication edges
H2  unequal branch probabilities
H3  an artefact of QPU capacity
H4  an artefact of network topology

The discriminating construction for H1 against H2: take a divergent region,
where branch A and branch B are mutually exclusive, and build a twin in which
the same interactions occur *independently*, each with the same marginal
probability. By linearity of expectation a single placement has identical
expected cost on both, so if Case 2 headroom differs between them, exclusivity
matters; if it does not, only the marginal probabilities do. Case 3 and the
worst case can still tell the twins apart, because only there does knowing
which branch ran change what can be done.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from ftqc_delivery.ddqc.placement import (
    DynamicProgram,
    Segment,
    build_network,
    evaluate,
    exhaustive_optimum,
    reconfiguration_oracle,
    weights,
)

RESULT_DIR = ROOT / "results" / "ddqc_go_nogo"
TIGHT = [(2, 3), (3, 4), (2, 4), (5, 6), (6, 7), (5, 7)] * 10


def exclusive(p: float, m: int) -> DynamicProgram:
    return DynamicProgram("exclusive", 8, [
        Segment(pairs=TIGHT),
        Segment(branches=[(p, [(1, 2)] * m), (1 - p, [(1, 5)] * (2 * m))]),
    ])


def independent(p: float, m: int) -> DynamicProgram:
    """The same interactions, occurring independently with the same marginals."""

    return DynamicProgram("independent", 8, [
        Segment(pairs=TIGHT),
        Segment(branches=[(p, [(1, 2)] * m), (1 - p, [])]),
        Segment(branches=[(1 - p, [(1, 5)] * (2 * m)), (p, [])]),
    ])


def best_expected(program, network, mode):
    _, optimal = exhaustive_optimum(weights(program, mode), program.n_qubits, network)
    scored = [evaluate(program, placement, network) for placement in optimal]
    return min(scored, key=lambda s: s["expected_epr"])


def main() -> None:
    network = build_network(2, 4, "line")
    rows = []
    for p in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95):
        for m in (1, 4):
            record = {"p": p, "m": m}
            for label, build in (("exclusive", exclusive), ("independent", independent)):
                program = build(p, m)
                flat = best_expected(program, network, "flat")
                aware = best_expected(program, network, "expected")
                oracle = reconfiguration_oracle(program, network)
                record[f"{label}_flat"] = flat["expected_epr"]
                record[f"{label}_case2"] = aware["expected_epr"]
                record[f"{label}_case3"] = oracle["expected_epr"]
                record[f"{label}_worst_case2"] = aware["worst_epr"]
            rows.append(record)

    same_case2 = all(abs(r["exclusive_case2"] - r["independent_case2"]) < 1e-9 for r in rows)
    same_flat = all(abs(r["exclusive_flat"] - r["independent_flat"]) < 1e-9 for r in rows)
    case3_differs = [r for r in rows if abs(r["exclusive_case3"] - r["independent_case3"]) > 1e-9]
    worst_differs = [r for r in rows if abs(r["exclusive_worst_case2"] - r["independent_worst_case2"]) > 1e-9]
    at_half = [r for r in rows if r["p"] == 0.5]
    out = {
        "case2_identical_for_exclusive_and_independent_twins": same_case2,
        "flat_identical_for_twins": same_flat,
        "case3_differs_in": len(case3_differs),
        "worst_case_differs_in": len(worst_differs),
        "cases": len(rows),
        "divergent_headroom_at_p_half": [
            round((r["exclusive_flat"] - r["exclusive_case2"]) / r["exclusive_flat"], 4) if r["exclusive_flat"] else 0.0
            for r in at_half
        ],
        "rows": rows,
    }
    (RESULT_DIR / "MECHANISM_H1_H2.json").write_text(json.dumps(out, indent=1))
    print(f"Case 2 identical for exclusive vs independent twins: {same_case2} (over {len(rows)} cases)")
    print(f"Flat identical for twins: {same_flat}")
    print(f"Case 3 differs between twins in {len(case3_differs)} of {len(rows)} cases")
    print(f"Worst-case cost differs between twins in {len(worst_differs)} of {len(rows)} cases")
    print(f"Divergent-region headroom of Case 2 over flat at p = 1/2: {out['divergent_headroom_at_p_half']}")
    print(f"\n{'p':>5s} {'m':>2s} | {'excl flat':>9s} {'excl C2':>7s} {'excl C3':>7s} | {'indep flat':>10s} {'indep C2':>8s} {'indep C3':>8s}")
    for r in rows:
        print(f"{r['p']:5.2f} {r['m']:2d} | {r['exclusive_flat']:9.2f} {r['exclusive_case2']:7.2f} {r['exclusive_case3']:7.2f} | "
              f"{r['independent_flat']:10.2f} {r['independent_case2']:8.2f} {r['independent_case3']:8.2f}")


if __name__ == "__main__":
    main()
