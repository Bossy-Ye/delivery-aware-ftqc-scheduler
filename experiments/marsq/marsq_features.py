"""Measure every corpus workload's structure, before any policy is run.

Nothing here touches a machine, a policy or the simulator, so the table it
writes cannot have been influenced by an outcome. The role each workload
plays in the study (target or control) is decided here, from structure alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_marsq import RESULT_DIR, write_csv

from ftqc_delivery.mrc.corpus import CORPUS, build_workload
from ftqc_delivery.mrc.features import classify_role, structural_features

FIELDS = [
    "workload", "source", "family", "declared_role", "role", "note",
    "gates", "decision_sites", "consuming_sites", "choosing_sites", "stages",
    "max_stage_width", "mean_stage_width", "wide_stage_fraction", "longest_serial_chain",
    "total_parallelism", "families", "consuming_families", "family_names",
    "mean_variants_per_site", "t_demand", "ccz_demand", "mean_stage_teq",
    "mix_variance", "mix_drift", "mix_entropy", "alternation_rate", "load_variance",
    "rotation_sites", "t_gate_sites", "and_pairs",
]


def main() -> None:
    rows = []
    for workload in CORPUS:
        extraction = build_workload(workload.name)
        features = structural_features(extraction.program)
        summary = extraction.summary()
        role = classify_role(features)
        row = {
            "workload": workload.name,
            "source": workload.source,
            "family": workload.family,
            "declared_role": workload.role,
            "role": role,
            "note": workload.note,
            "gates": summary["gates"],
            "rotation_sites": summary["rotation_sites"],
            "t_gate_sites": summary["t_gate_sites"],
            "and_pairs": summary["paired_sites"] // 2,
        }
        row.update({key: (round(value, 4) if isinstance(value, float) else value)
                    for key, value in features.items()})
        rows.append(row)
    write_csv(RESULT_DIR / "WORKLOAD_FEATURES.csv", rows, FIELDS)

    targets = [r for r in rows if r["role"] == "target"]
    controls = [r for r in rows if r["role"] == "control"]
    print(f"{len(rows)} workloads: {len(targets)} target, {len(controls)} control")
    print(f"sources: {sorted({r['source'] for r in rows})}")
    print(f"target families: {sorted({r['family'] for r in targets})}")
    print(f"reclassified from declared: {[r['workload'] for r in rows if r['role'] != r['declared_role']]}")
    print(f"\n{'workload':18s} {'role':8s} {'src':10s} {'sites':>5s} {'stages':>6s} {'maxw':>5s} {'wide%':>6s} {'fam':>4s} {'drift':>6s} {'alt':>5s}")
    for row in rows:
        print(f"{row['workload']:18s} {row['role']:8s} {row['source']:10s} {row['decision_sites']:5.0f} "
              f"{row['stages']:6.0f} {row['max_stage_width']:5.0f} {row['wide_stage_fraction']:6.2f} "
              f"{row['consuming_families']:4.0f} {row['mix_drift']:6.3f} {row['alternation_rate']:5.2f}")


if __name__ == "__main__":
    main()
