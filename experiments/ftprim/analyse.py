"""Evaluate the frozen GO/HOLD/NO_GO criteria (EXPERIMENT_CONTRACT.md section 9).

Usage (main env):  python experiments/ftprim/analyse.py RESULT_DIR

Reads CLEAN_PATTERN.csv, FITS.json, THRESHOLDS.json and WORKLOADS_slack*.csv
from RESULT_DIR and writes SUMMARY.json. Every number in REPORT.md is taken
from SUMMARY.json by report.py.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

KS = range(1, 31)
COMM_MIN_REMOTE = 10


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def load_csv(path):
    with open(path) as f:
        return [{k: _num(v) for k, v in r.items()} for r in csv.DictReader(f)]


def clean_summary(rows, fits):
    out = {}
    for cls in ("realistic", "near-term", "idealised"):
        for scen in ("oneway", "return"):
            rs = [r for r in rows if r["regime_class"] == cls and r["scenario"] == scen]
            if not rs:
                continue
            inv = [r for r in rs if r["inversion"] in (True, "True")]
            ebits_T_fail_R = [r for r in inv if r["choice_ebits"] != "R" and r["choice_failure"] == "R"]
            ebits_R_fail_T = [r for r in inv if r["choice_ebits"] == "R" and r["choice_failure"] != "R"]
            ratios = [r["failure_ratio"] for r in inv]
            out[f"{cls}|{scen}"] = dict(
                points=len(rs), inversions=len(inv), inversion_rate=len(inv) / len(rs),
                ebits_teleport_failure_remote=len(ebits_T_fail_R),
                ebits_remote_failure_teleport=len(ebits_R_fail_T),
                failure_ratio_median=statistics.median(ratios) if ratios else 1.0,
                failure_ratio_max=max(ratios) if ratios else 1.0,
                failure_ratio_ge_10=sum(1 for x in ratios if x >= 10))
    # Break-even k (smallest k where the failure objective teleports), per regime.
    kstar = defaultdict(dict)
    for r in rows:
        key = f"{r['code']}|p={r['p']:g}|r={r['ratio']:g}|rho={r['rho']:g}"
        slot = kstar[key].setdefault(r["scenario"], dict(k=None, cls=r["regime_class"]))
        if r["choice_failure"] != "R" and (slot["k"] is None or r["k"] < slot["k"]):
            slot["k"] = int(r["k"])
    fit_k = {name: dict(k_star_oneway=f["derived"].get("k_star_oneway"),
                        k_star_oneway_ci=f["ci"].get("k_star_oneway"),
                        k_star_return=f["derived"].get("k_star_return"),
                        k_star_return_ci=f["ci"].get("k_star_return"),
                        delta=f["derived"]["delta"], delta_ci=f["ci"].get("delta"),
                        c_tel=f["derived"]["c_tel"], c_tel_ci=f["ci"].get("c_tel"),
                        s_mem=f["derived"]["s_mem"])
             for name, f in fits.items()}
    return out, dict(kstar), fit_k


def workload_summary(rows, realistic_kstar_spread):
    comm = [r for r in rows if r["static_remote"] >= COMM_MIN_REMOTE]
    real = [r for r in comm if r["regime_class"] == "realistic"]
    res = dict(instances=len(rows), communicating_instances=len(comm), realistic_instances=len(real),
               communicating_workloads=sorted({r["workload"] for r in comm}))

    # Criteria use the expected number of logical faults (fail_sum), which equals
    # the failure-probability ratio in the rare-failure regime programs run in and
    # does not saturate for long programs (contract section 9 clarification).
    def ratio(r):
        return r["A_fail_sum"] / r["C_fail_sum"] if r["C_fail_sum"] > 0 else 1.0

    by_regime = defaultdict(list)
    for r in real:
        by_regime[r["regime"]].append(r)
    per_regime = {}
    for reg, rs in sorted(by_regime.items()):
        ratios = [ratio(r) for r in rs]
        dis = [r["decision_disagreement"] for r in rs]
        per_regime[reg] = dict(
            workloads=len(rs), median_failure_ratio=statistics.median(ratios), max_failure_ratio=max(ratios),
            share_disagree_ge_10pct=sum(d >= 0.10 for d in dis) / len(rs),
            median_disagreement=statistics.median(dis),
            g1_in_regime=sum(d >= 0.10 for d in dis) / len(rs) >= 0.5,
            g3_in_regime=statistics.median(ratios) >= 10)
    res["per_realistic_regime"] = per_regime

    dis_all = [r["decision_disagreement"] for r in real]
    g1_share = sum(d >= 0.10 for d in dis_all) / len(dis_all) if dis_all else 0.0
    agree_share = sum(d < 0.05 for d in dis_all) / len(dis_all) if dis_all else 1.0
    g2_regimes = [k for k, v in per_regime.items() if v["g1_in_regime"] and v["g3_in_regime"]]
    median_by_regime = {k: v["median_failure_ratio"] for k, v in per_regime.items()}

    wins = [r for r in real if r["C_fail_sum"] < r["A_fail_sum"] * 0.99]
    ok = [r for r in wins if r["C_ebit_pairs"] <= 3 * max(r["A_ebit_pairs"], 1)
          and r["C_run_rounds"] <= 2 * r["A_run_rounds"]]
    g4_share = len(ok) / len(wins) if wins else 1.0

    def recovery(select):
        num = den = 0.0
        for r in real:
            K = select(r)
            num += r["A_fail_sum"] - r[f"B{K}_fail_sum"]
            den += r["A_fail_sum"] - r["C_fail_sum"]
        return (num / den) if den > 1e-15 else float("nan"), den

    fixed = {K: recovery(lambda r, K=K: K)[0] for K in KS}
    finite = {K: v for K, v in fixed.items() if v == v}
    best_K = max(finite, key=lambda K: finite[K]) if finite else None
    total_benefit = recovery(lambda r: 1)[1]
    per_reg_K = {}
    for reg, rs in by_regime.items():
        per_reg_K[reg] = min(KS, key=lambda K: (sum(r[f"B{K}_fail_sum"] for r in rs), K))
    hw_rec = recovery(lambda r: per_reg_K[r["regime"]])[0]
    paper_rec = recovery(lambda r: 10)[0]

    any_real = [r for r in comm if r["decision_disagreement"] >= 0.10 and ratio(r) >= 1.1]
    res.update(
        workload_inversions_any_regime=len(any_real),
        workload_inversions_any_regime_by_class={
            cls: sum(1 for r in any_real if r["regime_class"] == cls)
            for cls in ("realistic", "near-term", "idealised")},
        g1_share_instances_disagree_ge_10pct=g1_share,
        share_instances_disagree_lt_5pct=agree_share,
        g2_regimes_passing=g2_regimes,
        median_failure_ratio_by_realistic_regime=median_by_regime,
        total_oracle_benefit_realistic=total_benefit,
        c_wins_realistic=len(wins), g4_share_within_overhead=g4_share,
        best_fixed_K=best_K, best_fixed_recovery=finite.get(best_K) if best_K else float("nan"),
        fixed_K_recovery=fixed, hardware_conditioned_K=per_reg_K,
        hardware_conditioned_recovery=hw_rec, paper_K10_recovery=paper_rec,
        realistic_kstar_spread=realistic_kstar_spread)
    return res


def verdict(clean, kstar, wl, slack_rows):
    real_kstars = [v["oneway"]["k"] for v in kstar.values()
                   if v.get("oneway", {}).get("cls") == "realistic" and v["oneway"]["k"] is not None]
    spread = (max(real_kstars) / min(real_kstars)) if real_kstars else float("nan")
    rec = wl["best_fixed_recovery"]
    hw = wl["hardware_conditioned_recovery"]
    gates = dict(
        G1=wl["g1_share_instances_disagree_ge_10pct"] >= 0.5,
        G2=len(wl["g2_regimes_passing"]) >= 2,
        G3=any(v >= 10 for v in wl["median_failure_ratio_by_realistic_regime"].values()),
        G4=wl["g4_share_within_overhead"] >= 0.75,
        G5=(rec == rec) and rec < 0.80,
        G6=True,
        G7=(hw == hw) and hw < 0.95 and (spread == spread) and spread >= 3)
    no_go = dict(
        subsumed=False,
        decisions_almost_always_agree=wl["share_instances_disagree_lt_5pct"] >= 0.9,
        threshold_recovers_95pct=(rec == rec) and rec >= 0.95,
        inversions_only_constructed=any(v["inversions"] for v in clean.values())
        and wl["workload_inversions_any_regime"] == 0,
        small_improvement=all(v < 1.25 for v in wl["median_failure_ratio_by_realistic_regime"].values()),
        prohibitive_overhead=wl["c_wins_realistic"] > 0 and wl["g4_share_within_overhead"] < 0.5)
    if any(no_go.values()):
        decision = "NO_GO"
    elif all(gates.values()):
        decision = "GO"
    else:
        decision = "HOLD"
    return dict(decision=decision, gates=gates, no_go_triggers=no_go, realistic_kstar_spread=spread,
                realistic_kstars=real_kstars)


def main() -> None:
    d = Path(sys.argv[1])
    clean_rows = load_csv(d / "CLEAN_PATTERN.csv")
    fits = json.load(open(d / "FITS.json"))
    thresholds = json.load(open(d / "THRESHOLDS.json"))
    clean, kstar, fit_k = clean_summary(clean_rows, fits["fits"])
    slack_files = sorted(d.glob("WORKLOADS_slack*.csv"))
    primary = load_csv(d / "WORKLOADS_slack1.csv")
    wl = workload_summary(primary, None)
    v = verdict(clean, kstar, wl, None)
    wl["realistic_kstar_spread"] = v["realistic_kstar_spread"]
    sens = {}
    for f in slack_files:
        if f.name != "WORKLOADS_slack1.csv":
            s = workload_summary(load_csv(f), None)
            sens[f.stem] = dict(verdict=verdict(clean, kstar, s, None), summary=s)
    summary = dict(decision=v["decision"], verdict=v, clean_pattern=clean, clean_thresholds=thresholds,
                   break_even_k=kstar, fitted_break_even=fit_k, workloads=wl, sensitivity=sens,
                   holdout=fits.get("holdouts"))
    json.dump(summary, open(d / "SUMMARY.json", "w"), indent=1, default=float)
    print(json.dumps(dict(decision=v["decision"], gates=v["gates"], no_go=v["no_go_triggers"]), indent=1))


if __name__ == "__main__":
    main()
