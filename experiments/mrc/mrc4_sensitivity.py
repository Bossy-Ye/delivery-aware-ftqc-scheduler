"""Is the headroom an artefact of the two rotation routes costing the same?

At the published counts, Ross-Selinger synthesis (4b T states) and
phase-gradient synthesis (2b Toffolis, hence 2b CCZ states) cost exactly the
same in T-equivalents. That makes the choice between them a pure question of
which factory to load, which is the most favourable possible setting for the
mechanism under study. If the result only survives at that exact ratio it is a
coincidence, not a finding.

This script scales the Toffoli count of the Toffoli-based routes by a factor
and re-measures the headroom, so the sensitivity to the coincidence is
reported rather than assumed.
"""

from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, SIMPLE_BASELINES, ratio, summarize, write_csv

from ftqc_delivery.mrc.kernels import staged
from ftqc_delivery.mrc.library import rotation_variants
from ftqc_delivery.mrc.policies import best_oracle, heterogeneity, mixture, run_policy
from ftqc_delivery.mrc.resources import machine_for_capacity
from ftqc_delivery.rac.variants import Site


SCALES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
CAPACITIES = (0.25, 0.5, 1.0)
SHARES = (0.25, 0.5, 0.75)
LANES = (2, 3, 4)

FIELDS = [
    "toffoli_scale",
    "lanes",
    "capacity_target",
    "ccz_share",
    "cheaper_route",
    "makespan_uniform_oracle",
    "makespan_best_simple",
    "best_simple_baseline",
    "makespan_global_oracle",
    "oracle_exhaustive",
    "headroom_over_uniform_oracle",
    "headroom_over_best_simple",
    "oracle_heterogeneity",
    "oracle_ccz_share_of_demand",
]


def _kernel(lanes: int, scale: float):
    """Return a Trotter-shaped kernel whose rotations use the scaled counts."""

    stage = [
        Site(
            site_id=f"sens_l{lane:02d}",
            family="rotation",
            variants=rotation_variants(f"sens_l{lane:02d}", 10, toffoli_scale=scale),
        )
        for lane in range(lanes)
    ]
    return staged(
        f"sensitivity_l{lanes}_g{scale:g}",
        [stage, [Site(site_id=f"sens2_l{lane:02d}", family="rotation",
                      variants=rotation_variants(f"sens2_l{lane:02d}", 10, toffoli_scale=scale))
                 for lane in range(lanes)]],
        {"kernel": "sensitivity", "concurrency": str(lanes), "width": "10"},
    )


def _job(spec):
    scale, lanes = spec
    program = _kernel(lanes, scale)
    rows = []
    for capacity in CAPACITIES:
        for share in SHARES:
            machine = machine_for_capacity(capacity, share)
            simple = {
                policy: run_policy(policy, program, machine).makespan
                for policy in SIMPLE_BASELINES
            }
            best_simple = min(simple, key=lambda name: simple[name])
            uniform = simple["uniform_oracle"]
            oracle = best_oracle(program, machine)
            # 2b*scale CCZ is 4b*scale T-equivalents against 4b T for Ross-Selinger.
            cheaper = "equal" if scale == 1.0 else ("ccz" if scale < 1.0 else "t")
            rows.append(
                {
                    "toffoli_scale": scale,
                    "lanes": lanes,
                    "capacity_target": capacity,
                    "ccz_share": share,
                    "cheaper_route": cheaper,
                    "makespan_uniform_oracle": uniform,
                    "makespan_best_simple": simple[best_simple],
                    "best_simple_baseline": best_simple,
                    "makespan_global_oracle": oracle.makespan,
                    "oracle_exhaustive": int(oracle.exhaustive),
                    "headroom_over_uniform_oracle": round(
                        ratio(uniform - oracle.makespan, uniform), 4
                    ),
                    "headroom_over_best_simple": round(
                        ratio(simple[best_simple] - oracle.makespan, simple[best_simple]), 4
                    ),
                    "oracle_heterogeneity": round(
                        heterogeneity(program, oracle.assignment), 4
                    ),
                    "oracle_ccz_share_of_demand": round(mixture(oracle.counts), 4),
                }
            )
    return rows


def main() -> None:
    """Sweep the cost ratio and write the sensitivity table."""

    specs = [(scale, lanes) for scale in SCALES for lanes in LANES]
    rows: list[dict[str, object]] = []
    with Pool(processes=4) as pool:
        for done, produced in enumerate(pool.imap_unordered(_job, specs), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(specs)}", flush=True)
    rows.sort(key=lambda row: (row["toffoli_scale"], row["lanes"]))
    write_csv(RESULT_DIR / "mrc4_sensitivity.csv", rows, FIELDS)

    print()
    print(
        f"{'scale':>6s} {'n':>4s} {'vsUnif_med':>10s} {'vsUnif_p90':>10s} "
        f"{'vsSimple_med':>12s} {'vsSimple_p90':>12s} {'vsSimple_max':>12s} {'het':>5s}"
    )
    for scale in SCALES:
        subset = [row for row in rows if row["toffoli_scale"] == scale]
        uniform = summarize(row["headroom_over_uniform_oracle"] for row in subset)
        simple = summarize(row["headroom_over_best_simple"] for row in subset)
        het = summarize(row["oracle_heterogeneity"] for row in subset)
        print(
            f"{scale:6.2f} {len(subset):4d} {uniform['median']:10.3f} {uniform['p90']:10.3f} "
            f"{simple['median']:12.3f} {simple['p90']:12.3f} {simple['max']:12.3f} "
            f"{het['mean']:5.2f}"
        )


if __name__ == "__main__":
    main()
