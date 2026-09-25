"""Clean interaction pattern: decisions for k = 1..30 under each objective.

Usage (main env):  python experiments/ftprim/clean_pattern.py CALIBRATION.csv OUTDIR

Writes CLEAN_PATTERN.csv (one row per regime x rho x k x scenario), FITS.json
(fitted lines, derived costs, bootstrap CIs, hold-out checks) and
THRESHOLDS.json (best fixed / hardware-conditioned thresholds vs the oracle).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ftqc_delivery.ftprim import costs as C  # noqa: E402
from ftqc_delivery.utils.io import write_csv_rows  # noqa: E402

RHOS = (0, 1, 3, 10, 30, 100, 300)
KS = range(1, 31)
SCENARIOS = {"oneway": ("R", "T"), "return": ("R", "T_rt")}


def realistic(ratio: float, rho: float, p: float) -> str:
    """Regime class fixed in EXPERIMENT_CONTRACT.md section 5."""
    if ratio >= 10 and rho >= 10 and p <= 2e-3:
        return "realistic"
    if ratio >= 3 and rho >= 1:
        return "near-term"
    return "idealised"


def main() -> None:
    calib, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    rows = C.load_rows(calib)
    fits, holdouts, table = {}, {}, []
    for key, pts in sorted(C.group(rows).items()):
        strategies = {r["strategy"] for r in pts}
        if not {"R", "T", "MEM"} <= strategies:  # T_rt may be absent (SC d=7: return = outbound)
            continue
        fit = C.fit_point(key, pts)
        name = f"{key[0]}|p={key[1]:g}|r={key[2]:g}"
        fits[name] = dict(code=key[0], p=key[1], ratio=key[2], n=fit.n, d=fit.d, code_k=fit.code_k,
                          lines=fit.lines, derived=fit.derived, ci=fit.ci)
        holdouts[name] = C.holdout_check(fit, pts)
        for rho in RHOS:
            for scen, (s1, s2) in SCENARIOS.items():
                for k in KS:
                    opts = [C.pattern_metrics(fit, s, k, rho) for s in (s1, s2)]
                    pick = {obj: C.decide(opts, obj) for obj in ("ebits", "latency", "failure")}
                    by = {o["strategy"]: o for o in opts}
                    table.append(dict(
                        code=key[0], d=fit.d, p=key[1], ratio=key[2], p_ebit=key[1] * key[2], rho=rho,
                        regime_class=realistic(key[2], rho, key[1]), scenario=scen, k=k,
                        fail_R=by["R"]["fail"], fail_T=by[s2]["fail"],
                        ebits_R=by["R"]["ebit_pairs"], ebits_T=by[s2]["ebit_pairs"],
                        latency_R=by["R"]["latency_rounds"], latency_T=by[s2]["latency_rounds"],
                        choice_ebits=pick["ebits"]["strategy"], choice_latency=pick["latency"]["strategy"],
                        choice_failure=pick["failure"]["strategy"],
                        fail_of_ebits_choice=pick["ebits"]["fail"], fail_of_failure_choice=pick["failure"]["fail"],
                        inversion=pick["ebits"]["strategy"] != pick["failure"]["strategy"],
                        failure_ratio=pick["ebits"]["fail"] / pick["failure"]["fail"]))
    write_csv_rows(outdir / "CLEAN_PATTERN.csv", table, list(table[0]))
    json.dump(dict(fits=fits, holdouts=holdouts), open(outdir / "FITS.json", "w"), indent=1, default=float)
    json.dump(threshold_tests(table), open(outdir / "THRESHOLDS.json", "w"), indent=1, default=float)
    print(f"{len(fits)} fitted points, {len(table)} pattern rows")


def threshold_tests(table):
    """Best single K (per scenario) against the failure oracle, and K per regime."""
    out = {}
    for scen in SCENARIOS:
        rows = [r for r in table if r["scenario"] == scen]
        by_regime = defaultdict(list)
        for r in rows:
            by_regime[(r["code"], r["p"], r["ratio"], r["rho"])].append(r)

        def evaluate(select_K):
            agree = benefit = gained = 0.0
            for reg, rs in by_regime.items():
                K = select_K(reg)
                for r in rs:
                    choice = "T" if r["k"] >= K else "R"
                    oracle = "R" if r["choice_failure"] == "R" else "T"
                    agree += choice == oracle
                    f_choice = r["fail_T"] if choice == "T" else r["fail_R"]
                    b = r["fail_of_ebits_choice"] - r["fail_of_failure_choice"]
                    benefit += b
                    gained += r["fail_of_ebits_choice"] - f_choice
            return agree / len(rows), (gained / benefit if benefit > 0 else float("nan"))

        fixed = {K: evaluate(lambda reg, K=K: K) for K in range(1, 32)}
        best_K = max(fixed, key=lambda K: (fixed[K][1] if fixed[K][1] == fixed[K][1] else -1, fixed[K][0]))
        per_regime = {}
        for reg, rs in by_regime.items():
            cand = {}
            for K in range(1, 32):
                cand[K] = sum(r["fail_T"] if r["k"] >= K else r["fail_R"] for r in rs)
            per_regime[reg] = min(cand, key=lambda K: (cand[K], K))
        hw = evaluate(lambda reg: per_regime[reg])
        paper = evaluate(lambda reg: 10 if scen == "oneway" else 10)
        ebits_rule = evaluate(lambda reg: 2 if scen == "oneway" else 3)
        out[scen] = dict(
            best_fixed_K=best_K, best_fixed=dict(decision_agreement=fixed[best_K][0], benefit_recovered=fixed[best_K][1]),
            fixed_curve={K: dict(decision_agreement=a, benefit_recovered=b) for K, (a, b) in fixed.items()},
            hardware_conditioned=dict(decision_agreement=hw[0], benefit_recovered=hw[1],
                                      K_by_regime={"|".join(map(str, k)): v for k, v in per_regime.items()}),
            paper_rule_K10=dict(decision_agreement=paper[0], benefit_recovered=paper[1]),
            ebit_rule=dict(decision_agreement=ebits_rule[0], benefit_recovered=ebits_rule[1]))
    return out


if __name__ == "__main__":
    main()
