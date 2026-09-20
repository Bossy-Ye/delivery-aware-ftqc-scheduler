"""Why does the oracle win, when it wins?

Four explanations are separated, using the cheapest discriminating run for
each. The ablations are applied to the cases where the oracle actually beat
the stage-DP, since an explanation is only needed where there is something to
explain.

A  carried inventory      the advantage comes from resource state crossing a
                          stage boundary
B  wide-stage local mix   the advantage is just picking the locally cheaper
                          implementation inside a wide stage
C  one bank starved       the advantage is an artefact of an unbalanced split
                          between the banks
D  buffer artefact        the advantage depends on a particular buffer size
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_marsq import RESULT_DIR, SEED, machine_grid, ratio, read_csv, summarise, write_csv

from ftqc_delivery.mrc.corpus import build_workload
from ftqc_delivery.mrc.execution import execute
from ftqc_delivery.mrc.oracle import stateful_oracle
from ftqc_delivery.mrc.resources import coupled_machine
from ftqc_delivery.mrc.stagedp import (
    _stage_cost_sim,
    pipeline_stages,
    select_stage_dp,
    stage_choices,
    stage_program,
)

FIELDS = [
    "workload", "machine", "model", "tiles", "ccz_share",
    "makespan_stagedp", "makespan_oracle", "residual_headroom_vs_stagedp",
    "reset_stagedp", "reset_oracle", "reset_residual",
    "myopic_stage_exact", "myopic_residual_vs_oracle", "myopic_captures_fraction",
    "buffer_half_residual", "buffer_double_residual",
    "explanation",
]


def execute_with_stage_resets(program, assignment, machine) -> int:
    """Return the makespan if every stage began with an empty machine.

    Running each stage on its own removes exactly one thing: the resource
    state that would otherwise cross the boundary. Everything else, the
    program, the machine and the assignment, is unchanged.
    """

    total = 0
    for stage in pipeline_stages(program):
        sub = stage_program(program, stage)
        total += execute(sub.instantiate(assignment), machine).makespan
    return total


def myopic_stage_exact(program, machine):
    """Return the assignment that optimises each stage from an empty machine.

    This policy sees the whole of a stage, so it can mix implementations
    inside a wide stage as freely as the oracle, but it never learns what the
    previous stage left behind. If it captures the oracle's advantage, that
    advantage was never about carried state.
    """

    assignment = dict(program.default_assignment())
    for stage in pipeline_stages(program):
        sub = stage_program(program, stage)
        best, best_cost = None, None
        for choice in stage_choices(stage, machine):
            cost, _ = _stage_cost_sim(sub, choice, machine, {})
            if best_cost is None or cost < best_cost:
                best_cost, best = cost, choice
        if best:
            assignment.update(best)
    return assignment


def _job(case):
    workload, label = case["workload"], case["machine"]
    program = build_workload(workload).program
    machines = dict(machine_grid())
    machine = machines[label]

    stagedp = select_stage_dp(program, machine, mode="analytic", refine=5, include_uniform=True)
    oracle = stateful_oracle(program, machine, search_budget=20.0, seed=SEED,
                             extra_seeds=(stagedp.assignment,))
    residual = ratio(stagedp.makespan - oracle.makespan, stagedp.makespan)

    reset_dp = execute_with_stage_resets(program, stagedp.assignment, machine)
    reset_or = execute_with_stage_resets(program, oracle.assignment, machine)
    myopic = myopic_stage_exact(program, machine)
    myopic_cost = execute(program.instantiate(myopic), machine).makespan

    parts = label.split("_")
    model, tiles, share = parts[0], int(parts[1]), float(parts[2])
    half = coupled_machine(model, tiles, share, buffer_capacity=16, seed=SEED)
    double = coupled_machine(model, tiles, share, buffer_capacity=64, seed=SEED)
    buffers = {}
    for name, alt in (("buffer_half_residual", half), ("buffer_double_residual", double)):
        dp_alt = select_stage_dp(program, alt, mode="analytic", refine=5, include_uniform=True)
        or_alt = stateful_oracle(program, alt, search_budget=10.0, seed=SEED,
                                 extra_seeds=(dp_alt.assignment,))
        buffers[name] = round(ratio(dp_alt.makespan - or_alt.makespan, dp_alt.makespan), 4)

    captured = (
        ratio(stagedp.makespan - myopic_cost, stagedp.makespan - oracle.makespan)
        if stagedp.makespan > oracle.makespan
        else float("nan")
    )
    reset_residual = ratio(reset_dp - reset_or, reset_dp)

    if residual <= 0.0:
        explanation = "no advantage to explain"
    elif captured == captured and captured >= 0.75:
        explanation = "B: wide-stage local mixing"
    elif reset_residual <= 0.25 * residual:
        explanation = "A: carried inventory"
    else:
        explanation = "mixed or unresolved"

    return {
        "workload": workload,
        "machine": label,
        "model": model,
        "tiles": tiles,
        "ccz_share": share,
        "makespan_stagedp": stagedp.makespan,
        "makespan_oracle": oracle.makespan,
        "residual_headroom_vs_stagedp": round(residual, 4),
        "reset_stagedp": reset_dp,
        "reset_oracle": reset_or,
        "reset_residual": round(reset_residual, 4),
        "myopic_stage_exact": myopic_cost,
        "myopic_residual_vs_oracle": round(ratio(myopic_cost - oracle.makespan, myopic_cost), 4),
        "myopic_captures_fraction": round(captured, 4) if captured == captured else "",
        **buffers,
        "explanation": explanation,
    }


def main() -> None:
    rows_in = read_csv(RESULT_DIR / "RAW_RESULTS.csv")
    interesting = [
        r for r in rows_in
        if float(r["residual_headroom_vs_stagedp"]) > 0.02 and r["regime"] == "standard"
    ]
    interesting.sort(key=lambda r: -float(r["residual_headroom_vs_stagedp"]))
    selected = interesting[:24]
    print(f"{len(interesting)} cases with residual > 2%; ablating the top {len(selected)}")
    rows = []
    with Pool(processes=3) as pool:
        for done, row in enumerate(pool.imap_unordered(_job, selected), 1):
            rows.append(row)
            print(f"  {done}/{len(selected)} {row['workload']} {row['machine']}: "
                  f"residual={row['residual_headroom_vs_stagedp']:+.3f} "
                  f"reset={row['reset_residual']:+.3f} "
                  f"myopic_captures={row['myopic_captures_fraction']} -> {row['explanation']}",
                  flush=True)
    rows.sort(key=lambda r: -r["residual_headroom_vs_stagedp"])
    write_csv(RESULT_DIR / "ABLATIONS.csv", rows, FIELDS)
    print("\n== explanation counts ==")
    for explanation in sorted({r["explanation"] for r in rows}):
        subset = [r for r in rows if r["explanation"] == explanation]
        print(f"  {explanation:30s} {len(subset)}")
    print("\nresidual with state carried :", summarise(r["residual_headroom_vs_stagedp"] for r in rows))
    print("residual with stage resets  :", summarise(r["reset_residual"] for r in rows))
    print("fraction captured by myopic :", summarise(
        float(r["myopic_captures_fraction"]) for r in rows if r["myopic_captures_fraction"] != ""))
    print("residual at half buffer     :", summarise(r["buffer_half_residual"] for r in rows))
    print("residual at double buffer   :", summarise(r["buffer_double_residual"] for r in rows))


if __name__ == "__main__":
    main()
