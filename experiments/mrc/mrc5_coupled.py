"""Phase 2: does the effect survive realistic coupled provisioning?

The earlier matrix treated T and CCZ banks as independently dialable. Real CCZ
factories are built on top of level-1 T production, so the two products draw
on one upstream stream. Three provisioning models are compared at a *fixed
factory area*, so no model is quietly given more hardware:

* ``A`` independent banks (the earlier reference);
* ``B`` one raw level-1 stream feeding 15-to-1 T distillers and 8-to-1 CCZ
  distillers, the raw bank's area taken from the same budget;
* ``C`` model B plus catalyzed CCZ-to-2T units, one per CCZ distiller.

Only the decisive kernels from the main matrix are run, plus two null cases
that showed no headroom there. The kill condition is that coupling removes
practically meaningful headroom except at extreme settings.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, SIMPLE_BASELINES, kernels, ratio, summarize, write_csv

from ftqc_delivery.mrc.policies import (
    best_oracle,
    heterogeneity,
    mixture,
    run_policy,
)
from ftqc_delivery.mrc.resources import CCZ, RAW, T, coupled_machine


DECISIVE = (
    "mixed_w32_c16_l2",
    "modexp_w32_s2",
    "modexp_w16_s2",
    "phase_est_w32_r1",
    "grover_c16_i2",
    "and_ladder_s2_l3",
    "multiplier_w32_r4",
    "trotter_t3_l2_b10",
)
NULL_CONTROLS = ("oracle_bank_c16_l4", "heterostage_l3")

MODELS = ("A", "B", "C")
TILES = (200, 400, 800)
SHARES = (0.25, 0.5, 0.75)
#: Raw-stream sensitivity for models B and C at the middle area: (period,
#: scale relative to distiller demand, tiles per raw unit). ``scale 0.5`` makes
#: the distillers compete for a stream that covers half their appetite;
#: ``tiles 0`` is the literature-faithful reading where level-1 production is
#: inside each factory's published footprint.
RAW_SETTINGS = (
    ("default", 2, 1.0, 2),
    ("scarce", 2, 0.5, 2),
    ("cheap", 1, 1.0, 2),
    ("expensive", 4, 1.0, 2),
    ("free_area", 2, 1.0, 0),
    ("free_scarce", 2, 0.5, 0),
)

FIELDS = [
    "kernel",
    "role",
    "model",
    "tiles",
    "ccz_share",
    "raw_setting",
    "raw_period",
    "raw_scale",
    "raw_tiles",
    "factory_tiles",
    "t_rate",
    "ccz_rate",
    "raw_rate",
    "capacity_teq",
    "t_units",
    "ccz_units",
    *[f"makespan_{policy}" for policy in SIMPLE_BASELINES],
    "makespan_sim_descent",
    "makespan_global_oracle",
    "oracle_exhaustive",
    "best_simple_baseline",
    "makespan_best_simple",
    "headroom_over_uniform_oracle",
    "headroom_over_best_simple",
    "oracle_heterogeneity",
    "oracle_ccz_share_of_demand",
    "regret_sim_descent",
]


def _row(program, role, model, tiles, share, raw_setting=("default", 2, 1.0, 2)):
    label, raw_period, raw_scale, raw_tiles = raw_setting
    machine = coupled_machine(
        model, tiles=tiles, ccz_share=share,
        raw_period=raw_period, raw_scale=raw_scale, raw_tiles=raw_tiles,
    )
    outcomes = {policy: run_policy(policy, program, machine) for policy in SIMPLE_BASELINES}
    descent = run_policy("sim_descent", program, machine)
    oracle = best_oracle(
        program,
        machine,
        extra_seeds=[o.assignment for o in outcomes.values()] + [descent.assignment],
    )
    best_simple = min(SIMPLE_BASELINES, key=lambda name: outcomes[name].makespan)
    uniform = outcomes["uniform_oracle"].makespan
    units = machine.distiller_counts
    if model == "A":
        units = {T: machine.bank(T).count if machine.bank(T) else 0,
                 CCZ: machine.bank(CCZ).count if machine.bank(CCZ) else 0}
    row = {
        "kernel": program.name,
        "role": role,
        "model": model,
        "tiles": tiles,
        "ccz_share": share,
        "raw_setting": label if model != "A" else "",
        "raw_period": raw_period if model != "A" else "",
        "raw_scale": raw_scale if model != "A" else "",
        "raw_tiles": raw_tiles if model != "A" else "",
        "factory_tiles": machine.factory_tiles,
        "t_rate": round(machine.rate(T), 4),
        "ccz_rate": round(machine.rate(CCZ), 4),
        "raw_rate": round(machine.rate(RAW), 4),
        "capacity_teq": round(machine.rate(T) + 2 * machine.rate(CCZ), 4),
        "t_units": units.get(T, 0),
        "ccz_units": units.get(CCZ, 0),
        "makespan_sim_descent": descent.makespan,
        "makespan_global_oracle": oracle.makespan,
        "oracle_exhaustive": int(oracle.exhaustive),
        "best_simple_baseline": best_simple,
        "makespan_best_simple": outcomes[best_simple].makespan,
        "headroom_over_uniform_oracle": round(ratio(uniform - oracle.makespan, uniform), 4),
        "headroom_over_best_simple": round(
            ratio(outcomes[best_simple].makespan - oracle.makespan, outcomes[best_simple].makespan), 4
        ),
        "oracle_heterogeneity": round(heterogeneity(program, oracle.assignment), 4),
        "oracle_ccz_share_of_demand": round(mixture(oracle.counts), 4),
        "regret_sim_descent": round(ratio(descent.makespan, oracle.makespan), 4),
    }
    for policy in SIMPLE_BASELINES:
        row[f"makespan_{policy}"] = outcomes[policy].makespan
    return row


def _job(spec):
    name, role = spec
    program = {k.name: k for k in kernels()}[name]
    rows = []
    for model in MODELS:
        for tiles in TILES:
            for share in SHARES:
                rows.append(_row(program, role, model, tiles, share))
    for model in ("B", "C"):
        for setting in RAW_SETTINGS[1:]:
            for share in SHARES:
                rows.append(_row(program, role, model, 400, share, setting))
    return rows


def main() -> None:
    """Run the coupled-provisioning comparison and write the table."""

    specs = [(name, "decisive") for name in DECISIVE] + [(name, "null") for name in NULL_CONTROLS]
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        rows = []
        program = {k.name: k for k in kernels()}["and_ladder_s2_l3"]
        for model in MODELS:
            rows.append(_row(program, "decisive", model, 400, 0.5))
        for setting in RAW_SETTINGS[1:]:
            rows.append(_row(program, "decisive", "B", 400, 0.5, setting))
        for row in rows:
            print(
                f"model {row['model']}/{row['raw_setting'] or '-':11s}: tiles={row['factory_tiles']} T={row['t_rate']:.3f} "
                f"CCZ={row['ccz_rate']:.3f} raw={row['raw_rate']:.3f} units={row['t_units']}/{row['ccz_units']} "
                f"uniform={row['makespan_uniform_oracle']} simple={row['makespan_best_simple']} "
                f"opt={row['makespan_global_oracle']} exact={row['oracle_exhaustive']} "
                f"head={100*row['headroom_over_best_simple']:.1f}% mix={row['oracle_ccz_share_of_demand']}"
            )
        return

    rows = []
    with Pool(processes=4) as pool:
        for done, produced in enumerate(pool.imap_unordered(_job, specs), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(specs)}", flush=True)
    rows.sort(key=lambda r: (r["role"], r["kernel"], r["model"], r["tiles"], r["ccz_share"], str(r["raw_setting"])))
    write_csv(RESULT_DIR / "mrc5_coupled.csv", rows, FIELDS)

    print()
    print(f"{'role':9s} {'model':5s} {'tiles':>5s} {'n':>3s} {'vsUnif_med':>10s} {'vsUnif_p90':>10s} {'vsSimple_med':>12s} {'vsSimple_p90':>12s} {'vsSimple_max':>12s} {'>5%':>4s} {'mix':>5s} {'exact':>5s}")
    for role in ("decisive", "null"):
        for model in MODELS:
            for tiles in TILES:
                sub = [r for r in rows if r["role"] == role and r["model"] == model and r["tiles"] == tiles and r["raw_setting"] in ("default", "")]
                if not sub:
                    continue
                u = summarize(r["headroom_over_uniform_oracle"] for r in sub)
                s = summarize(r["headroom_over_best_simple"] for r in sub)
                het = summarize(r["oracle_heterogeneity"] for r in sub)
                print(
                    f"{role:9s} {model:5s} {tiles:5d} {len(sub):3d} {u['median']:10.3f} {u['p90']:10.3f} "
                    f"{s['median']:12.3f} {s['p90']:12.3f} {s['max']:12.3f} "
                    f"{sum(1 for r in sub if r['headroom_over_best_simple'] > 0.05):4d} {het['mean']:5.2f} "
                    f"{sum(r['oracle_exhaustive'] for r in sub):5d}"
                )


if __name__ == "__main__":
    main()
