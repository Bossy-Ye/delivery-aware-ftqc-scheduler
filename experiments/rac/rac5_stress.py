"""Stress tests: does the result survive assumptions we did not choose?

A result that only holds under a convenient model is not worth eight weeks.
Four things are varied here, each of which could plausibly kill the effect:

* space -- the resource-aware choice is charged for the extra ancillas it
  spends, and compared on space-time volume rather than time alone;
* machine width -- the number of logical operations that may start in a cycle
  is capped, removing the free parallelism the wide implementations assume;
* supply randomness -- distillation attempts fail, so the arrival process is
  irregular while the compiler's cost model still assumes the nominal rate;
* factory granularity, phasing, buffer size and production latency -- several
  banks that deliver the *same* average rate in different ways.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import (
    RESULT_DIR,
    program_meta,
    programs,
    ratio,
    summarize,
    write_csv,
)

from ftqc_delivery.rac.execution import execute
from ftqc_delivery.rac.regimes import (
    buffer_regimes,
    factory_configurations,
    main_regimes,
    pipelined_regimes,
)
from ftqc_delivery.rac.select import (
    best_uniform,
    reference_best,
    select_resource_aware,
    select_share_aware_greedy,
    select_static,
)
from ftqc_delivery.rac.supply import StochasticSupplyModel


SPACE_FIELDS = [
    "program",
    "kernel",
    "regime",
    "rate",
    "policy",
    "makespan",
    "ancillas",
    "data_qubits",
    "space_time_volume",
    "volume_ratio_vs_t_depth",
    "time_ratio_vs_t_depth",
]

WIDTH_FIELDS = [
    "program",
    "regime",
    "rate",
    "max_parallel_ops",
    "makespan_min_t_depth",
    "makespan_share_aware",
    "makespan_resource_aware",
    "regret_min_t_depth",
    "regret_resource_aware",
    "reference",
]

STOCHASTIC_FIELDS = [
    "program",
    "regime",
    "nominal_rate",
    "p_accept",
    "seed",
    "makespan_min_t_depth",
    "makespan_min_t_count",
    "makespan_share_aware",
    "makespan_resource_aware",
    "regret_min_t_depth",
    "regret_resource_aware",
    "reference",
]

CONFIG_FIELDS = [
    "program",
    "sweep",
    "regime",
    "rate",
    "buffer",
    "production_latency",
    "makespan_min_t_depth",
    "makespan_min_t_count",
    "makespan_share_aware",
    "makespan_resource_aware",
    "reference",
    "regret_min_t_depth",
    "regret_resource_aware",
]

STRESS_SUBSET = (
    "trotter_t4_l2_b32",
    "qft_q5_t32",
    "reduction_tree_mult_w32_r8",
    "mixed_w32_c16_l2",
    "toffoli_ladder_n3_l2",
    "grover_c16_i2",
)


def _makespan(program, assignment, supply, **kwargs):
    return execute(
        program.instantiate(assignment), supply, record_trace=False, **kwargs
    ).makespan


def _data_qubits(program) -> int:
    """Return a coarse data-register size used to price the space overhead."""

    meta = program_meta(program)
    try:
        return max(8, 2 * int(meta.get("width", "16")))
    except ValueError:
        return 32


def space_sweep(catalogue, subset=STRESS_SUBSET) -> list[dict[str, object]]:
    """Charge each policy for the ancillas it spends and compare volume."""

    rows: list[dict[str, object]] = []
    for name in subset:
        program = catalogue[name]
        meta = program_meta(program)
        data_qubits = _data_qubits(program)
        for regime in main_regimes():
            supply = regime.supply
            assignments = {
                "min_t_depth": select_static(program, "t_depth"),
                "min_t_count": select_static(program, "t_count"),
            }
            assignments["share_aware_greedy"], _ = select_share_aware_greedy(
                program, supply
            )
            assignments["resource_aware"], _ = select_resource_aware(program, supply)

            baseline_time = _makespan(program, assignments["min_t_depth"], supply)
            baseline_volume = baseline_time * (
                data_qubits + program.ancillas(assignments["min_t_depth"])
            )
            for policy, assignment in assignments.items():
                makespan = _makespan(program, assignment, supply)
                ancillas = program.ancillas(assignment)
                volume = makespan * (data_qubits + ancillas)
                rows.append(
                    {
                        "program": name,
                        "kernel": meta.get("kernel", ""),
                        "regime": regime.name,
                        "rate": round(regime.rate, 4),
                        "policy": policy,
                        "makespan": makespan,
                        "ancillas": ancillas,
                        "data_qubits": data_qubits,
                        "space_time_volume": volume,
                        "volume_ratio_vs_t_depth": round(
                            ratio(volume, baseline_volume), 4
                        ),
                        "time_ratio_vs_t_depth": round(
                            ratio(makespan, baseline_time), 4
                        ),
                    }
                )
    return rows


def width_sweep(catalogue, subset=STRESS_SUBSET) -> list[dict[str, object]]:
    """Cap the number of operations that may start per cycle."""

    rows: list[dict[str, object]] = []
    for name in subset:
        program = catalogue[name]
        for regime in main_regimes()[2:6]:
            supply = regime.supply
            for cap in (4, 8, 16, 32, None):
                kwargs = {} if cap is None else {"max_parallel_ops": cap}
                depth_assignment = select_static(program, "t_depth")
                share_assignment, _ = select_share_aware_greedy(program, supply)
                ours_assignment, _ = select_resource_aware(program, supply)
                candidates = {
                    "min_t_depth": depth_assignment,
                    "min_t_count": select_static(program, "t_count"),
                    "share_aware_greedy": share_assignment,
                    "resource_aware": ours_assignment,
                }
                results = {
                    policy: _makespan(program, assignment, supply, **kwargs)
                    for policy, assignment in candidates.items()
                }
                reference = min(results.values())
                _, uniform_best = best_uniform(program, supply)
                reference = min(reference, uniform_best) if cap is None else reference
                rows.append(
                    {
                        "program": name,
                        "regime": regime.name,
                        "rate": round(regime.rate, 4),
                        "max_parallel_ops": cap if cap is not None else "none",
                        "makespan_min_t_depth": results["min_t_depth"],
                        "makespan_share_aware": results["share_aware_greedy"],
                        "makespan_resource_aware": results["resource_aware"],
                        "regret_min_t_depth": round(
                            ratio(results["min_t_depth"], reference), 4
                        ),
                        "regret_resource_aware": round(
                            ratio(results["resource_aware"], reference), 4
                        ),
                        "reference": reference,
                    }
                )
    return rows


def stochastic_sweep(catalogue, subset=STRESS_SUBSET) -> list[dict[str, object]]:
    """Make distillation attempts fail while the cost model assumes they do not."""

    rows: list[dict[str, object]] = []
    for name in subset:
        program = catalogue[name]
        for regime in main_regimes()[2:6]:
            for p_accept in (1.0, 0.8, 0.6):
                for seed in (0, 1, 2):
                    supply = (
                        regime.supply
                        if p_accept == 1.0
                        else StochasticSupplyModel(
                            regime.supply, p_accept=p_accept, seed=seed, horizon=60_000
                        )
                    )
                    assignments = {
                        "min_t_depth": select_static(program, "t_depth"),
                        "min_t_count": select_static(program, "t_count"),
                    }
                    assignments["share_aware_greedy"], _ = select_share_aware_greedy(
                        program, supply
                    )
                    assignments["resource_aware"], _ = select_resource_aware(
                        program, supply
                    )
                    results = {
                        policy: _makespan(program, assignment, supply)
                        for policy, assignment in assignments.items()
                    }
                    _, uniform_best = best_uniform(program, supply)
                    reference = min(min(results.values()), uniform_best)
                    rows.append(
                        {
                            "program": name,
                            "regime": regime.name,
                            "nominal_rate": round(regime.rate, 4),
                            "p_accept": p_accept,
                            "seed": seed,
                            "makespan_min_t_depth": results["min_t_depth"],
                            "makespan_min_t_count": results["min_t_count"],
                            "makespan_share_aware": results["share_aware_greedy"],
                            "makespan_resource_aware": results["resource_aware"],
                            "regret_min_t_depth": round(
                                ratio(results["min_t_depth"], reference), 4
                            ),
                            "regret_resource_aware": round(
                                ratio(results["resource_aware"], reference), 4
                            ),
                            "reference": reference,
                        }
                    )
                    if p_accept == 1.0:
                        break
    return rows


def configuration_sweep(catalogue, subset=STRESS_SUBSET) -> list[dict[str, object]]:
    """Vary factory granularity, phasing, buffer size and production latency."""

    rows: list[dict[str, object]] = []
    sweeps = (
        ("factory_granularity", factory_configurations(rate=1.0)),
        ("buffer", buffer_regimes(rate=1.0)),
        ("production_latency", pipelined_regimes(rate=1.0)),
    )
    for name in subset:
        program = catalogue[name]
        for sweep_name, regimes in sweeps:
            for regime in regimes:
                supply = regime.supply
                assignments = {
                    "min_t_depth": select_static(program, "t_depth"),
                    "min_t_count": select_static(program, "t_count"),
                }
                assignments["share_aware_greedy"], _ = select_share_aware_greedy(
                    program, supply
                )
                assignments["resource_aware"], _ = select_resource_aware(program, supply)
                results = {
                    policy: _makespan(program, assignment, supply)
                    for policy, assignment in assignments.items()
                }
                reference = reference_best(
                    program, supply, extra=list(assignments.values())
                )
                rows.append(
                    {
                        "program": name,
                        "sweep": sweep_name,
                        "regime": regime.name,
                        "rate": round(regime.rate, 4),
                        "buffer": supply.buffer_capacity,
                        "production_latency": supply.production_latency,
                        "makespan_min_t_depth": results["min_t_depth"],
                        "makespan_min_t_count": results["min_t_count"],
                        "makespan_share_aware": results["share_aware_greedy"],
                        "makespan_resource_aware": results["resource_aware"],
                        "reference": reference.makespan,
                        "regret_min_t_depth": round(
                            ratio(results["min_t_depth"], reference.makespan), 4
                        ),
                        "regret_resource_aware": round(
                            ratio(results["resource_aware"], reference.makespan), 4
                        ),
                    }
                )
    return rows


def _sweep_worker(job: tuple[str, str]) -> tuple[str, list[dict[str, object]]]:
    """Run one sweep for one program, so the axes can run in parallel."""

    sweep_name, program_name = job
    catalogue = {program.name: program for program in programs()}
    runner = {
        "space": space_sweep,
        "width": width_sweep,
        "stochastic": stochastic_sweep,
        "configuration": configuration_sweep,
    }[sweep_name]
    return sweep_name, runner(catalogue, subset=(program_name,))


def _run_parallel(sweep_name: str) -> list[dict[str, object]]:
    """Run one sweep across the stress subset in parallel."""

    jobs = [(sweep_name, name) for name in STRESS_SUBSET]
    rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for _, produced in pool.imap_unordered(_sweep_worker, jobs):
            rows.extend(produced)
    rows.sort(key=lambda row: (str(row["program"]), str(row.get("regime", ""))))
    return rows


def main() -> None:
    """Run every stress test and write one table per axis."""

    space_rows = _run_parallel("space")
    write_csv(RESULT_DIR / "rac5_space.csv", space_rows, SPACE_FIELDS)
    print("space sweep done", flush=True)

    width_rows = _run_parallel("width")
    write_csv(RESULT_DIR / "rac5_width.csv", width_rows, WIDTH_FIELDS)
    print("width sweep done", flush=True)

    stochastic_rows = _run_parallel("stochastic")
    write_csv(RESULT_DIR / "rac5_stochastic.csv", stochastic_rows, STOCHASTIC_FIELDS)
    print("stochastic sweep done", flush=True)

    config_rows = _run_parallel("configuration")
    write_csv(RESULT_DIR / "rac5_configurations.csv", config_rows, CONFIG_FIELDS)
    print("configuration sweep done", flush=True)

    print()
    for policy in ("min_t_depth", "min_t_count", "share_aware_greedy", "resource_aware"):
        volumes = [
            row["volume_ratio_vs_t_depth"]
            for row in space_rows
            if row["policy"] == policy
        ]
        times = [
            row["time_ratio_vs_t_depth"] for row in space_rows if row["policy"] == policy
        ]
        print(
            f"space  {policy:20s} median time x{summarize(times)['median']:.3f} "
            f"median volume x{summarize(volumes)['median']:.3f}"
        )
    for label, rows, key in (
        ("width", width_rows, "regret_resource_aware"),
        ("stochastic", stochastic_rows, "regret_resource_aware"),
        ("configuration", config_rows, "regret_resource_aware"),
    ):
        ours = summarize(row[key] for row in rows)
        depth = summarize(row["regret_min_t_depth"] for row in rows)
        print(
            f"{label:14s} ours median regret {ours['median']:.3f} p90 {ours['p90']:.3f} | "
            f"T-depth median regret {depth['median']:.3f} max {depth['max']:.3f}"
        )


if __name__ == "__main__":
    main()
