"""How expensive is the analytic cost model compared with simply simulating?

A static cost model earns its place by being cheaper than running the thing it
predicts. This script measures both on the pilot programs across the supply
sweep, so the claim can be checked rather than assumed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import RESULT_DIR, programs, ratio, summarize, write_csv

from ftqc_delivery.rac.cost import SupplyProfile, default_horizon, sccp_bound
from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.regimes import main_regimes


FIELDS = [
    "program",
    "nodes",
    "t_count",
    "regime",
    "rate",
    "makespan",
    "cost_model_ms",
    "simulation_ms",
    "simulation_over_cost_model",
]

REPEATS = 5


def main() -> None:
    """Time the cost model against the simulator and write the comparison."""

    rows: list[dict[str, object]] = []
    for program in programs():
        dag = program.instantiate(program.default_assignment())
        for regime in main_regimes():
            supply = regime.supply
            profile = SupplyProfile.build(supply, default_horizon(dag, supply))
            makespan = execute(dag, supply, record_trace=False).makespan

            start = time.perf_counter()
            for _ in range(REPEATS):
                sccp_bound(dag, supply, profile=profile)
            cost_ms = 1000 * (time.perf_counter() - start) / REPEATS

            start = time.perf_counter()
            for _ in range(REPEATS):
                execute(dag, supply, record_trace=False)
            simulation_ms = 1000 * (time.perf_counter() - start) / REPEATS

            rows.append(
                {
                    "program": program.name,
                    "nodes": len(dag.nodes),
                    "t_count": dag.num_t_gates(),
                    "regime": regime.name,
                    "rate": round(regime.rate, 4),
                    "makespan": makespan,
                    "cost_model_ms": round(cost_ms, 3),
                    "simulation_ms": round(simulation_ms, 3),
                    "simulation_over_cost_model": round(
                        ratio(simulation_ms, cost_ms), 3
                    ),
                }
            )
        print(f"  done {program.name}", flush=True)

    write_csv(RESULT_DIR / "rac7_cost_model_timing.csv", rows, FIELDS)
    stats = summarize(row["simulation_over_cost_model"] for row in rows)
    print()
    print(
        f"simulation time / cost-model time: median {stats['median']:.2f}, "
        f"min {min(row['simulation_over_cost_model'] for row in rows):.2f}, "
        f"max {stats['max']:.2f}"
    )
    cheaper = sum(1 for row in rows if row["simulation_over_cost_model"] < 1.0)
    print(
        f"the cost model is slower than simulating in {cheaper}/{len(rows)} "
        "program/regime pairs"
    )


if __name__ == "__main__":
    main()
