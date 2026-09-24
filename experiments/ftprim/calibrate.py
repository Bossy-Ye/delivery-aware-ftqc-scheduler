"""Measure logical failure of the composed patterns with TMCBS circuits + Tesseract.

Usage (TMCBS venv):
    python experiments/ftprim/calibrate.py GRID.json OUT.csv [--workers 4]

GRID.json lists points {code, p, ratio, strategy, k|rounds, target_errors,
max_shots}. Rows are appended as points finish, so an interrupted run resumes
by skipping keys already present in OUT.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

TMCBS_COMMIT = "c0490fa63965d8984cca89deb8826c19c46e8a3c"
FIELDS = ["key", "code", "d", "n", "code_k", "p", "p_ebit", "ratio", "strategy", "k", "rounds",
          "ebit_pairs", "teleports", "time_rounds", "detectors", "shots", "errors", "ler",
          "ci_low", "ci_high", "batches", "hit_shot_limit", "seconds", "decoder", "tmcbs_commit"]


def point_key(pt: dict) -> str:
    return (f"{pt['code']}|p={pt['p']:g}|r={pt['ratio']:g}|{pt['strategy']}|"
            f"k={pt.get('k', 0)}|rounds={pt.get('rounds', 0)}")


def run_point(pt: dict) -> dict:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    from ftqc_delivery.ftprim import patterns as pat
    from ftqc_delivery.ftprim.sampling import estimate
    code = pat.code_by_name(pt["code"])
    p, ratio = pt["p"], pt["ratio"]
    key = point_key(pt)
    if pt["strategy"] == "MEM":
        circuit = pat.memory_pair(code, p, pt["rounds"])
        meta = dict(ebit_pairs=0, teleports=0, time_rounds=pat.SETTLE_ROUNDS + pt["rounds"], k=0)
    elif pt["strategy"].startswith("T_q"):
        pattern = pat.teleport_ablation(code, p, ratio * p, pt["k"],
                                        quiet_bell_blocks="qbell" in pt["strategy"],
                                        quiet_bsm="qbsm" in pt["strategy"])
        circuit = pattern.circuit
        meta = dict(ebit_pairs=pattern.ebit_pairs, teleports=pattern.teleports,
                    time_rounds=pattern.time_rounds, k=pt["k"])
    else:
        pattern = pat.build(code, pt["strategy"], p, ratio * p, pt["k"])
        circuit = pattern.circuit
        meta = dict(ebit_pairs=pattern.ebit_pairs, teleports=pattern.teleports,
                    time_rounds=pattern.time_rounds, k=pt["k"])
    est = estimate(circuit, key, pt["target_errors"], pt["max_shots"])
    return dict(key=key, code=pt["code"], d=code.d, n=code.n, code_k=code.k, p=p, p_ebit=ratio * p,
                ratio=ratio, strategy=pt["strategy"], rounds=pt.get("rounds", 0),
                detectors=circuit.num_detectors, decoder="tesseract", tmcbs_commit=TMCBS_COMMIT,
                **meta, **est)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("grid")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    points = json.load(open(args.grid))
    out = Path(args.out)
    done = set()
    if out.exists():
        with open(out) as f:
            done = {row["key"] for row in csv.DictReader(f)}
    todo = [pt for pt in points if point_key(pt) not in done]
    # Longest jobs first keeps the pool busy at the end.
    todo.sort(key=lambda pt: -(pt.get("cost_hint", 1.0)))
    print(f"{len(points)} points, {len(done)} done, {len(todo)} to run", flush=True)
    new_file = not out.exists()
    with open(out, "a", newline="") as f, ProcessPoolExecutor(max_workers=args.workers) as pool:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        futures = {pool.submit(run_point, pt): pt for pt in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            writer.writerow({k: row.get(k) for k in FIELDS})
            f.flush()
            print(f"[{i}/{len(todo)}] {row['key']} ler={row['ler']:.3e} "
                  f"({row['errors']}/{row['shots']}) {row['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
