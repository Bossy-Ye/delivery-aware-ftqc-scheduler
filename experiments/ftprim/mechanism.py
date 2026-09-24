"""Mechanism analysis (contract section 9b and brief section 10).

Usage (main env):  python experiments/ftprim/mechanism.py RESULT_DIR

* Teleport overhead split: a_T - a_R from the main fit versus the same quantity
  for the ablated teleports (noiseless Bell-pair blocks / noiseless Bell-state
  measurement / both), from MECHANISM.csv.
* Ebit-noise sensitivity, code family, waiting for entanglement, parallel links,
  future interactions and the return need, from FITS.json and CLEAN_PATTERN.csv.
Writes MECHANISM.json.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ftqc_delivery.ftprim import costs as C  # noqa: E402


def teleport_split(d: Path, fits: dict) -> dict:
    path = d / "MECHANISM.csv"
    if not path.exists():
        return {}
    rows = C.load_rows(path)
    groups = defaultdict(lambda: defaultdict(list))
    for r in rows:
        groups[(r["code"], r["p"], r["ratio"])][r["strategy"]].append((r["k"], r["errors"], r["shots"]))
    out = {}
    for key, by in sorted(groups.items()):
        name = f"{key[0]}|p={key[1]:g}|r={key[2]:g}"
        if name not in fits:
            continue
        f = fits[name]
        aR = f["lines"]["R"][0]
        c_full = f["derived"]["c_tel"]
        entry = dict(c_tel=c_full, delta=f["derived"]["delta"])
        for strat, pts in by.items():
            if len(pts) >= 2:
                a, b = C._line(pts)
                entry[f"c_tel_{strat}"] = a - aR
        if "c_tel_T_qbell" in entry:
            entry["share_bell_block_settle"] = (c_full - entry["c_tel_T_qbell"]) / c_full
        if "c_tel_T_qbsm" in entry:
            entry["share_bsm_feedforward"] = (c_full - entry["c_tel_T_qbsm"]) / c_full
        if "c_tel_T_qbell_qbsm" in entry:
            entry["share_remaining"] = entry["c_tel_T_qbell_qbsm"] / c_full
            entry["k_star_without_both"] = (entry["c_tel_T_qbell_qbsm"] / entry["delta"]
                                            if entry["delta"] > 0 else float("inf"))
        out[name] = entry
    return out


def sensitivities(fits: dict, clean_rows) -> dict:
    ebit = defaultdict(dict)
    for name, f in fits.items():
        ebit[f"{f['code']}|p={f['p']:g}"][f["ratio"]] = dict(
            delta=f["derived"]["delta"], c_tel=f["derived"]["c_tel"],
            k_star_oneway=f["derived"].get("k_star_oneway"), k_star_return=f["derived"].get("k_star_return"),
            k_star_oneway_ci=f["ci"].get("k_star_oneway"))
    waiting = defaultdict(dict)
    for r in clean_rows:
        if r["scenario"] != "oneway":
            continue
        key = f"{r['code']}|p={r['p']:g}|r={r['ratio']:g}"
        slot = waiting[key].setdefault(str(r["rho"]), None)
        if r["choice_failure"] != "R" and (slot is None or r["k"] < slot):
            waiting[key][str(r["rho"])] = int(r["k"])
    ret = defaultdict(dict)
    for r in clean_rows:
        key = f"{r['code']}|p={r['p']:g}|r={r['ratio']:g}|rho={r['rho']:g}"
        slot = ret[key].get(r["scenario"])
        if r["choice_failure"] != "R" and (slot is None or r["k"] < slot):
            ret[key][r["scenario"]] = int(r["k"])
    return dict(ebit_noise=ebit, break_even_k_vs_rho=waiting, break_even_oneway_vs_return=ret,
                parallel_links_note="rho scales as 1/links at a fixed per-link rate; the rho axis "
                                    "therefore also reads as 300, 100, 30, 10, 3, 1 rounds for 1, 3, 10, "
                                    "30, 100, 300 parallel links at rho(1 link) = 300.")


def main() -> None:
    d = Path(sys.argv[1])
    fits = json.load(open(d / "FITS.json"))["fits"]
    with open(d / "CLEAN_PATTERN.csv") as f:
        clean_rows = []
        for r in csv.DictReader(f):
            for k in ("p", "ratio", "rho", "k"):
                r[k] = float(r[k])
            clean_rows.append(r)
    out = dict(teleport_overhead_split=teleport_split(d, fits), **sensitivities(fits, clean_rows))
    json.dump(out, open(d / "MECHANISM.json", "w"), indent=1, default=float)
    print(json.dumps(out["teleport_overhead_split"], indent=1, default=float)[:3000])


if __name__ == "__main__":
    main()
