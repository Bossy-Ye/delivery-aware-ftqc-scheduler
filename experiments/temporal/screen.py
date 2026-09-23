"""Cheap screening: two structured programs, one dependent control, two regimes.

The contract stops the study here unless some valid transformation reaches 5%
makespan improvement under constrained supply *while remaining near zero under
abundant supply*. The second half of that condition is what separates
temporal smoothing from ordinary depth reduction.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_temporal import ASSIGNMENTS, TRANSFORMS, run_case

from ftqc_delivery.utils.io import write_csv_rows

RESULT_DIR = Path(__file__).resolve().parents[2] / "results" / "temporal_transform_go_nogo"

PROMISING = ("qt_qft6", "qt_aliassamp16")
CONTROL = ("qt_multiand10",)
MACHINES = ("A_400_0.5", "A_3200_0.5")


def main() -> None:
    rows = []
    for workload in PROMISING + CONTROL:
        for assignment in ASSIGNMENTS:
            for machine in MACHINES:
                base = None
                for transformation in TRANSFORMS:
                    row = run_case(workload, transformation, machine, assignment)
                    if transformation == "conventional":
                        base = row["makespan"]
                    row["baseline_makespan"] = base
                    row["improvement"] = round((base - row["makespan"]) / base, 4) if base else 0.0
                    rows.append(row)
    write_csv_rows(
        RESULT_DIR / "SCREENING_RESULTS.csv",
        rows,
        list(rows[0].keys()),
    )

    print(f"{'workload':16s} {'asgn':5s} {'machine':12s} {'transformation':20s} "
          f"{'makespan':>9s} {'depth':>7s} {'improv':>8s} {'stalls':>7s} {'waste':>7s} {'burst':>6s}")
    for row in rows:
        print(f"{row['workload']:16s} {row['assignment']:5s} {row['machine']:12s} "
              f"{row['transformation']:20s} {row['makespan']:9d} {row['depth']:7d} "
              f"{row['improvement']:+8.3f} {row['total_stalls']:7d} "
              f"{row['t_waste'] + row['ccz_waste']:7d} {row['burstiness']:6.2f}")

    print("\n== screening gate ==")
    for transformation in TRANSFORMS:
        if transformation == "conventional":
            continue
        constrained = [r["improvement"] for r in rows
                       if r["transformation"] == transformation and r["regime"] == "constrained"
                       and r["role"] == "target"]
        abundant = [r["improvement"] for r in rows
                    if r["transformation"] == transformation and r["regime"] == "abundant"
                    and r["role"] == "target"]
        controls = [r["improvement"] for r in rows
                    if r["transformation"] == transformation and r["role"] == "control"]
        best_c = max(constrained, default=0.0)
        best_a = max(abundant, default=0.0)
        verdict = "passes screen" if best_c >= 0.05 and best_a < 0.05 else (
            "gain is not supply-driven" if best_c >= 0.05 else "no constrained gain")
        print(f"  {transformation:20s} constrained max={best_c:+.3f} abundant max={best_a:+.3f} "
              f"control max={max(controls, default=0.0):+.3f}  -> {verdict}")


if __name__ == "__main__":
    main()
