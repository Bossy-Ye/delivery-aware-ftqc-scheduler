"""Analyse the placement matrix against the frozen criteria.

Every number the report quotes is produced here from RAW_RESULTS.csv and
written to ANALYSIS.json, so nothing is copied by hand.
"""

from __future__ import annotations

import json
import statistics as st
import sys
import warnings
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from ftqc_delivery.ddqc.placement import build_network, evaluate
from ftqc_delivery.utils.io import read_csv_rows

RESULT_DIR = ROOT / "results" / "ddqc_go_nogo"


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def summarise(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(values),
        "median": round(st.median(values), 4),
        "mean": round(st.fmean(values), 4),
        "p90": round(ordered[int(0.9 * (len(ordered) - 1))], 4),
        "max": round(max(values), 4),
        "ge10": sum(1 for v in values if v >= 0.10),
        "ge25": sum(1 for v in values if v >= 0.25),
    }


def main() -> None:
    warnings.simplefilter("ignore")
    rows = read_csv_rows(RESULT_DIR / "RAW_RESULTS.csv")
    for r in rows:
        for k in list(r):
            if k.endswith(("_epr", "_remote", "_load")) or k.startswith("headroom") or k in (
                "probability", "qpus", "capacity", "slack", "n_qubits", "conditional_pairs",
                "unconditional_pairs", "placement_changed", "runtime_s",
            ):
                r[k] = f(r[k])
    groups = {
        "real_with_conditional_pairs": [r for r in rows if r["source"] in ("qualtran", "qasmbench") and r["program"] in REAL_COND],
        "real_local_only": [r for r in rows if r["program"] in LOCAL_ONLY],
        "control_divergent": [r for r in rows if r["program"] == "ctl_divergent"],
        "control_identical": [r for r in rows if r["program"] == "ctl_identical"],
    }
    out: dict = {"groups": {}}
    for label, sub in groups.items():
        out["groups"][label] = {
            "cases": len(sub),
            "programs": sorted({r["program"] for r in sub}),
            "headroom_expected_vs_flat": summarise(r["headroom_expected_vs_flat"] for r in sub),
            "headroom_case3_vs_flat": summarise(r["headroom_case3_vs_flat"] for r in sub),
            "headroom_likely_vs_flat": summarise(r["headroom_likely_vs_flat"] for r in sub),
            "headroom_expected_vs_blind": summarise(r["headroom_expected_vs_blind"] for r in sub),
            "placement_changed_cases": int(sum(r["placement_changed"] for r in sub)),
        }

    # Physical probability for qualtran: measurement-based uncomputation fires
    # with probability exactly 1/2.
    physical = [r for r in groups["real_with_conditional_pairs"] if r["source"] == "qualtran" and r["probability"] == 0.5]
    out["qualtran_at_physical_probability"] = {
        "headroom_expected_vs_flat": summarise(r["headroom_expected_vs_flat"] for r in physical),
        "placement_changed_cases": int(sum(r["placement_changed"] for r in physical)),
        "cases": len(physical),
    }

    # Per program: best headroom at any probability and network, and at p = 1/2.
    per_program = {}
    for name in sorted({r["program"] for r in rows}):
        sub = [r for r in rows if r["program"] == name]
        per_program[name] = {
            "source": sub[0]["source"],
            "n_qubits": sub[0]["n_qubits"],
            "conditional_pairs": sub[0]["conditional_pairs"],
            "unconditional_pairs": sub[0]["unconditional_pairs"],
            "median_headroom": round(st.median(r["headroom_expected_vs_flat"] for r in sub), 4),
            "max_headroom": round(max(r["headroom_expected_vs_flat"] for r in sub), 4),
            "cases_ge25": sum(1 for r in sub if r["headroom_expected_vs_flat"] >= 0.25),
            "placement_changed": int(sum(r["placement_changed"] for r in sub)),
            "cases": len(sub),
        }
    out["per_program"] = per_program

    # Probability sweep: is the branch-aware decision probability dependent?
    # Cross-evaluate each probability's optimum at every other probability.
    from matrix import build_program

    sweep = {}
    by_config = defaultdict(list)
    for r in rows:
        if r["program"] in LOCAL_ONLY:
            continue
        by_config[(r["program"], int(r["qpus"]), int(r["capacity"]), r["topology"])].append(r)
    dependent = defaultdict(int)
    configs = defaultdict(int)
    for (name, k, cap, topology), sub in by_config.items():
        if len(sub) < 2:
            continue
        network = build_network(k, cap, topology)
        programs = {r["probability"]: build_program(name, r["probability"]) for r in sub}
        placements = {r["probability"]: np.array([int(c) for c in r["expected_placement"]]) for r in sub}
        classes = 0
        is_dependent = False
        for p_i, placement in placements.items():
            for p_j, program in programs.items():
                mine = evaluate(program, placement, network)["expected_epr"]
                best = evaluate(program, placements[p_j], network)["expected_epr"]
                if mine > best + 1e-9:
                    is_dependent = True
        configs[name] += 1
        dependent[name] += int(is_dependent)
    out["probability_sweep"] = {
        name: {"configs": configs[name], "probability_dependent_configs": dependent[name]}
        for name in sorted(configs)
    }

    # Mechanism: H2 — does headroom exist at p = 1/2 for divergent regions?
    div = groups["control_divergent"]
    out["mechanism"] = {
        "divergent_control_headroom_by_probability": {
            str(p): summarise(r["headroom_expected_vs_flat"] for r in div if r["probability"] == p)
            for p in sorted({r["probability"] for r in div})
        },
        "real_headroom_by_probability": {
            str(p): summarise(r["headroom_expected_vs_flat"] for r in groups["real_with_conditional_pairs"] if r["probability"] == p)
            for p in sorted({r["probability"] for r in groups["real_with_conditional_pairs"]})
        },
        "real_headroom_by_slack": {
            str(s): summarise(r["headroom_expected_vs_flat"] for r in groups["real_with_conditional_pairs"] if r["slack"] == s)
            for s in (0.0, 2.0)
        },
        "real_headroom_by_topology": {
            t: summarise(r["headroom_expected_vs_flat"] for r in groups["real_with_conditional_pairs"] if r["topology"] == t)
            for t in ("line", "ring", "grid", "full")
        },
        "divergent_headroom_by_topology": {
            t: summarise(r["headroom_expected_vs_flat"] for r in div if r["topology"] == t)
            for t in ("line", "ring", "grid", "full")
        },
    }

    # Heuristic capture: share of the branch-aware gain the trivial
    # "most probable branch" heuristic already obtains.
    def capture(sub):
        shares = []
        for r in sub:
            gain = r["flat_expected_epr"] - r["expected_expected_epr"]
            if gain > 1e-9:
                shares.append((r["flat_expected_epr"] - r["likely_expected_epr"]) / gain)
        return summarise(shares)

    out["heuristic_capture"] = {label: capture(sub) for label, sub in groups.items()}
    (RESULT_DIR / "ANALYSIS.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["groups"], indent=1))
    print("\nqualtran at physical p=1/2:", out["qualtran_at_physical_probability"])
    print("\nprobability sweep:", json.dumps(out["probability_sweep"], indent=0))
    print("\nheuristic capture:", json.dumps(out["heuristic_capture"], indent=0))


REAL_COND = [
    "qt_add8", "qt_sub8", "qt_cadd8", "qt_addk8", "qt_ltc8", "qt_gt8", "qt_equals8",
    "qt_modadd8", "qt_modneg8", "qt_qrom16", "qt_add3", "qt_add4", "qt_equals3", "qt_qrom8", "qb_cc_n12",
]
LOCAL_ONLY = [
    "qb_ipea_n2", "qb_inverseqft_n4", "qb_qec_sm_n5", "qb_shor_n5", "vq_teleportation", "vq_bitflip",
    "vq_phaseflip", "vq_state_injection_T", "mq_ghz_dynamic_6", "mq_iqpe_6", "mq_dynamic_qft_6",
]

if __name__ == "__main__":
    main()
