"""Per-operation failure costs fitted from the TMCBS pattern simulations.

For one (code, p, p_ebit) point the pattern failures are fitted as lines in k:

    F_R(k)    = a_R  + b_R k      (k non-local CNOTs)
    F_T(k)    = a_T  + b_T k      (teleport, k local CNOTs)
    F_Trt(k)  = a_Tr + b_Tr k     (teleport, k local CNOTs, teleport back)
    F_MEM(r)  = a_M  + 2 s_mem r  (two idle blocks, r extra rounds)

by weighted least squares with binomial variances. Every operation in a pattern
is followed by ``ROUNDS`` rounds on its two blocks, so the per-operation costs
used by the program model are the excesses over that memory:

    e_remote = b_R - 6 s_mem,  e_local = b_T - 6 s_mem,
    e_tel    = (a_T - a_R) - 6 s_mem       (teleport incl. its Bell-pair blocks),
    e_ret    = (a_Tr - a_T) - 6 s_mem      (the return teleport; should match e_tel).

Uncertainties come from a parametric bootstrap that resamples every simulated
count from its binomial distribution.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

ROUNDS = 3
SETTLE = 4
MEM_BLOCKS = 2


def load_rows(path) -> List[dict]:
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            for key in ("p", "p_ebit", "ratio", "ler", "ci_low", "ci_high", "seconds"):
                r[key] = float(r[key])
            for key in ("d", "n", "code_k", "k", "rounds", "ebit_pairs", "teleports", "time_rounds",
                        "shots", "errors"):
                r[key] = int(float(r[key]))
            rows.append(r)
    return rows


def group(rows) -> Dict[Tuple[str, float, float], List[dict]]:
    out = defaultdict(list)
    for r in rows:
        out[(r["code"], r["p"], r["ratio"])].append(r)
    return out


def _wls(x: np.ndarray, y: np.ndarray, var: np.ndarray) -> Tuple[float, float]:
    w = 1.0 / np.maximum(var, 1e-30)
    X = np.stack([np.ones_like(x), x], axis=1)
    A = X.T @ (X * w[:, None])
    beta = np.linalg.solve(A, X.T @ (w * y))
    return float(beta[0]), float(beta[1])


def _line(points: List[Tuple[float, int, int]], rng=None) -> Tuple[float, float]:
    x = np.array([p[0] for p in points], dtype=float)
    shots = np.array([p[2] for p in points], dtype=float)
    errs = np.array([p[1] for p in points], dtype=float)
    if rng is not None:
        errs = rng.binomial(shots.astype(np.int64), np.clip(errs / shots, 0, 1)).astype(float)
    y = errs / shots
    # Variance from the (pooled-smoothed) rate so zero-error points keep a weight.
    q = np.maximum(y, 0.5 / shots)
    return _wls(x, y, q * (1 - q) / shots)


@dataclass
class Fit:
    key: Tuple[str, float, float]
    n: int
    code_k: int
    d: int
    lines: Dict[str, Tuple[float, float]]
    derived: Dict[str, float]
    ci: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    max_k: Dict[str, int] = field(default_factory=dict)


def _derive(lines: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
    s_mem = lines["MEM"][1] / MEM_BLOCKS
    aR, bR = lines["R"]
    aT, bT = lines["T"]
    out = dict(s_mem=s_mem, b_R=bR, b_T=bT, a_R=aR, a_T=aT,
               e_remote=bR - 2 * ROUNDS * s_mem, e_local=bT - 2 * ROUNDS * s_mem,
               c_tel=aT - aR, e_tel=aT - aR - 2 * ROUNDS * s_mem, delta=bR - bT)
    if "T_rt" in lines:
        aTr, bTr = lines["T_rt"]
        out.update(a_Trt=aTr, b_Trt=bTr, c_ret=aTr - aT, e_ret=aTr - aT - 2 * ROUNDS * s_mem)
    out["k_star_oneway"] = out["c_tel"] / out["delta"] if out["delta"] > 0 else float("inf")
    if "c_ret" in out:
        out["k_star_return"] = ((out["c_tel"] + out["c_ret"]) / out["delta"]
                                if out["delta"] > 0 else float("inf"))
    return out


def fit_point(key, rows: List[dict], n_boot: int = 1000, seed: int = 12345,
              fit_ks: Tuple[int, ...] = (1, 2, 4)) -> Fit:
    """Fit lines on k in ``fit_ks`` (validation points with other k are held out)."""
    pts: Dict[str, List[Tuple[float, int, int]]] = defaultdict(list)
    for r in rows:
        if r["strategy"] == "MEM":
            pts["MEM"].append((r["rounds"], r["errors"], r["shots"]))
        elif r["k"] in fit_ks:
            pts[r["strategy"]].append((r["k"], r["errors"], r["shots"]))
    def lines_for(rng=None):
        out = {s: _line(v, rng) for s, v in pts.items() if len(v) >= 2}
        # A single T_rt point shares the local-CNOT slope of T (checked on the
        # grid points that simulate two k values).
        if len(pts.get("T_rt", [])) == 1 and "T" in out:
            k, e, n = pts["T_rt"][0]
            if rng is not None:
                e = rng.binomial(n, min(e / n, 1.0))
            out["T_rt"] = (e / n - out["T"][1] * k, out["T"][1])
        return out

    lines = lines_for()
    derived = _derive(lines)
    if "T_rt" not in lines:
        # No return-teleport simulation at this point: the return is the same
        # TMCBS protocol, so its cost is taken equal to the outbound teleport.
        derived.update(c_ret=derived["c_tel"], e_ret=derived["e_tel"], assumed_return=1.0)
        derived["k_star_return"] = (2 * derived["c_tel"] / derived["delta"]
                                    if derived["delta"] > 0 else float("inf"))
    rng = np.random.default_rng(seed)
    boots = defaultdict(list)
    for _ in range(n_boot):
        bd = _derive(lines_for(rng))
        if "c_ret" not in bd:
            bd.update(c_ret=bd["c_tel"], e_ret=bd["e_tel"])
            bd["k_star_return"] = 2 * bd["c_tel"] / bd["delta"] if bd["delta"] > 0 else float("inf")
        for k, v in bd.items():
            boots[k].append(v)
    ci = {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for k, v in boots.items()}
    r0 = rows[0]
    return Fit(key, r0["n"], r0["code_k"], r0["d"], lines, derived, ci,
               {s: max(int(p[0]) for p in v) for s, v in pts.items()})


def holdout_check(fit: Fit, rows: List[dict]) -> List[dict]:
    """Compare simulated failure at held-out k with the fitted line."""
    out = []
    for r in rows:
        if r["strategy"] in fit.lines and r["strategy"] != "MEM" and r["k"] not in (1, 2, 4):
            a, b = fit.lines[r["strategy"]]
            pred = a + b * r["k"]
            out.append(dict(strategy=r["strategy"], k=r["k"], simulated=r["ler"], ci_low=r["ci_low"],
                            ci_high=r["ci_high"], predicted=pred,
                            inside_ci=r["ci_low"] <= pred <= r["ci_high"]))
    return out


# --------------------------------------------------------------------------- #
# Clean interaction pattern: one block interacting k times with a remote block.
# --------------------------------------------------------------------------- #
def pattern_metrics(fit: Fit, strategy: str, k: int, rho: float, live_blocks: int = 2) -> dict:
    """Failure, Bell pairs and latency of a strategy under ebit-generation limits.

    Generation runs from time 0 with buffering, so the run lasts
    max(compute rounds, rho * batches); the extra waiting rounds cost memory on
    ``live_blocks`` blocks (A and B in the clean pattern).
    """
    d = fit.derived
    if strategy == "R":
        base = d["a_R"] + d["b_R"] * k
        batches, compute = k, SETTLE + ROUNDS * k
    elif strategy == "T":
        base = d["a_T"] + d["b_T"] * k
        batches, compute = 1, SETTLE + ROUNDS * (k + 1)
    elif strategy == "T_rt":
        base = (d["a_Trt"] + d["b_Trt"] * k) if "a_Trt" in d else (d["a_T"] + d["c_ret"] + d["b_T"] * k)
        batches, compute = 2, SETTLE + ROUNDS * (k + 2)
    else:
        raise ValueError(strategy)
    run = max(compute, rho * batches)
    fail = base + live_blocks * d["s_mem"] * (run - compute)
    return dict(strategy=strategy, k=k, rho=rho, fail=fail, ebit_pairs=batches * fit.n,
                batches=batches, latency_rounds=run, compute_rounds=compute)


def decide(options: List[dict], objective: str) -> dict:
    """Pick by objective; ties go to fewer teleports (the remote-gate default of
    DQC-NAC and memQ), then to the next criterion."""
    order = {"R": 0, "T": 1, "T_rt": 2}
    if objective == "ebits":
        key = lambda o: (o["ebit_pairs"], order[o["strategy"]], o["latency_rounds"])
    elif objective == "latency":
        key = lambda o: (o["latency_rounds"], o["ebit_pairs"], order[o["strategy"]])
    elif objective == "failure":
        key = lambda o: (o["fail"], order[o["strategy"]])
    else:
        raise ValueError(objective)
    return min(options, key=key)
