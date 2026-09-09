"""Mechanism: what does the resource-aware choice actually do to the machine?

For a few representative cases this script records the full cycle-by-cycle
picture of the T-depth-selected implementation and the resource-aware one:
magic states requested, states delivered, buffer occupancy, and the cycles in
which the machine was stalled waiting for a state. It also reports whether the
resource-aware assignment is heterogeneous, that is, whether it deliberately
gives concurrent sites different implementations so their demand bursts do not
land on the same cycles.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import (
    RESULT_DIR,
    circuit_metrics,
    heterogeneous,
    programs,
    ratio,
    variant_profile,
    write_csv,
)

from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.regimes import main_regimes
from ftqc_delivery.rac.select import (
    reference_best,
    select_resource_aware,
    select_static,
)


CASES = (
    ("trotter_t4_l2_b32", "rate2"),
    ("qft_q5_t32", "rate2"),
    ("reduction_tree_mult_w32_r8", "rate4"),
)

TRACE_FIELDS = [
    "program",
    "regime",
    "policy",
    "cycle",
    "demand",
    "arrivals",
    "stock",
    "stalled",
]

CASE_FIELDS = [
    "program",
    "regime",
    "rate",
    "buffer",
    "policy",
    "profile",
    "heterogeneous",
    "t_count",
    "t_depth",
    "logical_depth",
    "peak_demand",
    "burstiness",
    "ancilla_width",
    "makespan",
    "supply_stall_cycles",
    "overflow",
    "speedup_over_t_depth",
]


def main() -> None:
    """Write per-cycle traces and a summary for the representative cases."""

    catalogue = {program.name: program for program in programs()}
    regimes = {regime.name: regime for regime in main_regimes()}

    trace_rows: list[dict[str, object]] = []
    case_rows: list[dict[str, object]] = []

    for program_name, regime_name in CASES:
        program = catalogue[program_name]
        regime = regimes[regime_name]
        supply = regime.supply

        assignments = {
            "min_t_depth": select_static(program, "t_depth"),
            "min_t_count": select_static(program, "t_count"),
        }
        assignments["resource_aware"], _ = select_resource_aware(program, supply)
        reference = reference_best(program, supply)
        assignments["reference"] = reference.assignment

        baseline = execute(
            program.instantiate(assignments["min_t_depth"]), supply, record_trace=False
        ).makespan

        for policy, assignment in assignments.items():
            dag = program.instantiate(assignment)
            trace = execute(dag, supply, record_trace=True)
            metrics = circuit_metrics(dag)
            case_rows.append(
                {
                    "program": program_name,
                    "regime": regime_name,
                    "rate": round(regime.rate, 4),
                    "buffer": supply.buffer_capacity,
                    "policy": policy,
                    "profile": variant_profile(assignment),
                    "heterogeneous": int(heterogeneous(assignment)),
                    "makespan": trace.makespan,
                    "supply_stall_cycles": trace.supply_stall_cycles,
                    "overflow": trace.overflow,
                    "speedup_over_t_depth": round(ratio(baseline, trace.makespan), 4),
                    **metrics,
                }
            )
            if policy in ("min_t_depth", "resource_aware"):
                for index in range(trace.makespan):
                    trace_rows.append(
                        {
                            "program": program_name,
                            "regime": regime_name,
                            "policy": policy,
                            "cycle": index + 1,
                            "demand": trace.demand[index],
                            "arrivals": trace.arrivals[index],
                            "stock": trace.stock[index],
                            "stalled": int(
                                trace.demand[index] == 0 and trace.stock[index] == 0
                            ),
                        }
                    )
        print(f"  done {program_name} @ {regime_name}", flush=True)

    write_csv(RESULT_DIR / "rac4_mechanism_traces.csv", trace_rows, TRACE_FIELDS)
    write_csv(RESULT_DIR / "rac4_mechanism_cases.csv", case_rows, CASE_FIELDS)

    print()
    print(f"{'program':28s} {'policy':16s} {'Tc':>6s} {'Td':>5s} {'peak':>5s} {'make':>6s} {'stall':>6s} {'ovf':>5s} {'het':>4s}")
    for row in case_rows:
        print(
            f"{row['program']:28s} {row['policy']:16s} {row['t_count']:6.0f} "
            f"{row['t_depth']:5.0f} {row['peak_demand']:5.0f} {row['makespan']:6d} "
            f"{row['supply_stall_cycles']:6d} {row['overflow']:5d} {row['heterogeneous']:4d}"
        )


if __name__ == "__main__":
    main()
