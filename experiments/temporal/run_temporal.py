"""One run of the temporal-transform study: workload x transformation x machine."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ftqc_delivery.mrc.corpus import BY_NAME, build_workload
from ftqc_delivery.mrc.execution import critical_path, execute, resource_counts
from ftqc_delivery.mrc.policies import _fixed_preference
from ftqc_delivery.mrc.resources import CCZ, T, Machine, coupled_machine
from ftqc_delivery.mrc.stagedp import pipeline_stages
from ftqc_delivery.mrc.transform import (
    commuting_edges,
    conventional_edges,
    pace,
    reshape,
)

SEED = 20260923

#: The frozen machine grid. The 3200-tile entry is the abundance control.
MACHINES = (
    ("A_200_0.5", "A", 200, 0.5, "constrained"),
    ("A_400_0.25", "A", 400, 0.25, "constrained"),
    ("A_400_0.5", "A", 400, 0.5, "constrained"),
    ("A_400_0.75", "A", 400, 0.75, "constrained"),
    ("B_400_0.5", "B", 400, 0.5, "constrained"),
    ("C_400_0.5", "C", 400, 0.5, "constrained"),
    ("A_800_0.5", "A", 800, 0.5, "moderate"),
    ("A_3200_0.5", "A", 3200, 0.5, "abundant"),
)

#: The frozen transformation set.
TRANSFORMS = (
    "conventional",
    "commuting",
    "conventional_pace4",
    "commuting_pace1",
    "commuting_pace2",
    "commuting_pace4",
    "commuting_pace8",
)

ASSIGNMENTS = ("ccz", "t")

FIELDS = [
    "workload", "source", "family", "role", "assignment", "transformation",
    "machine", "model", "tiles", "ccz_share", "regime",
    "makespan", "depth", "t_count", "ccz_count", "teq_demand",
    "t_stalls", "ccz_stalls", "total_stalls", "t_waste", "ccz_waste",
    "peak_stage_demand", "mean_stage_demand", "burstiness", "stages",
    "parallelism", "space_time", "factory_tiles", "utilisation",
]


def machine_for(label: str) -> Machine:
    for name, model, tiles, share, _ in MACHINES:
        if name == label:
            return coupled_machine(model, tiles, share, seed=SEED)
    raise KeyError(label)


def build_program(workload: str, transformation: str):
    """Return the program under one transformation, with its gate stream."""

    extraction = build_workload(workload)
    gates = BY_NAME[workload].builder()
    base = (
        conventional_edges(gates)
        if transformation.startswith("conventional")
        else commuting_edges(gates)
    )
    program = reshape(extraction.program, base)
    if "pace" in transformation:
        width = int(transformation.split("pace")[1])
        program = pace(program, width)
    return program


def _assignment_for(program, machine: Machine, kind: str):
    return _fixed_preference(program, machine, CCZ if kind == "ccz" else T)


def _demand_trace(program, assignment) -> tuple[float, float, float, int]:
    """Return peak, mean, burstiness of per-stage demand and the stage count."""

    loads = []
    for stage in pipeline_stages(program):
        total = 0.0
        for group in stage:
            for site in group:
                counts = resource_counts(
                    site.variant(assignment[site.site_id]).fragment.to_dag("x")
                )
                total += counts.get(T, 0) + 2.0 * counts.get(CCZ, 0)
        loads.append(total)
    if not loads:
        return 0.0, 0.0, 0.0, 0
    mean = sum(loads) / len(loads)
    variance = sum((x - mean) ** 2 for x in loads) / len(loads)
    burst = (variance**0.5 / mean) if mean > 0 else 0.0
    return max(loads), mean, burst, len(loads)


def run_case(workload: str, transformation: str, machine_label: str, assignment_kind: str) -> dict:
    entry = BY_NAME[workload]
    machine = machine_for(machine_label)
    program = build_program(workload, transformation)
    assignment = _assignment_for(program, machine, assignment_kind)

    dag = program.instantiate(assignment)
    trace = execute(dag, machine)
    counts = resource_counts(dag)
    peak, mean, burst, stages = _demand_trace(program, assignment)
    depth = critical_path(dag)
    teq = counts.get(T, 0) + 2.0 * counts.get(CCZ, 0)
    model, tiles, share, regime = next(
        (m, t, s, r) for n, m, t, s, r in MACHINES if n == machine_label
    )
    return {
        "workload": workload,
        "source": entry.source,
        "family": entry.family,
        "role": "control" if workload in CONTROLS else "target",
        "assignment": assignment_kind,
        "transformation": transformation,
        "machine": machine_label,
        "model": model,
        "tiles": tiles,
        "ccz_share": share,
        "regime": regime,
        "makespan": trace.makespan,
        "depth": depth,
        "t_count": counts.get(T, 0),
        "ccz_count": counts.get(CCZ, 0),
        "teq_demand": teq,
        "t_stalls": trace.stalls.get(T, 0),
        "ccz_stalls": trace.stalls.get(CCZ, 0),
        "total_stalls": trace.total_stalls,
        "t_waste": trace.overflow.get(T, 0),
        "ccz_waste": trace.overflow.get(CCZ, 0),
        "peak_stage_demand": round(peak, 2),
        "mean_stage_demand": round(mean, 2),
        "burstiness": round(burst, 4),
        "stages": stages,
        "parallelism": round(len(program.sites) / max(1, depth), 3),
        "space_time": trace.makespan * machine.factory_tiles,
        "factory_tiles": machine.factory_tiles,
        "utilisation": round(teq / max(1e-9, trace.makespan * (machine.rate(T) + 2 * machine.rate(CCZ))), 4),
    }


#: Frozen by structure before the decisive run: the commuting graph leaves
#: their critical path unchanged, so they expose no freedom to exploit.
CONTROLS = {
    "qmpa_draper8",
    "qmpa_draper16",
    "qt_multiand10",
    "qb_sat_n7",
    "qb_sat_n11",
    "qb_sqrt_n18",
}
