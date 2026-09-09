"""Follow-up probe: does the negative result survive a non-fungible resource?

The main study finds no exploitable headroom once a program's magic states all
come from one pool, because constrained execution time is then close to
``max(critical path, states / rate)`` and minimising that needs only two static
counts. This probe asks the obvious next question. Real machines run several
kinds of factory, and one logical operation can often be realised from either
kind. Selecting implementations then means balancing the load across banks,
which is a maximum over resources rather than a sum, so no per-site
minimisation of any single static count can solve it.

The probe is deliberately small and is reported as an open direction, not as a
result: it establishes only that the headroom that vanished in the fungible
model reappears when the resource is split.
"""

from __future__ import annotations

import sys
from itertools import product
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_rac import RESULT_DIR, ratio, summarize, write_csv

from ftqc_delivery.rac.multiresource import (
    and_bank,
    balanced_selection,
    execute_multi,
    factories,
    resource_counts,
)


FIELDS = [
    "program",
    "lanes",
    "stages",
    "t_rate",
    "ccz_rate",
    "makespan_all_t4",
    "makespan_all_ccz1",
    "makespan_min_states",
    "makespan_best_uniform",
    "makespan_balanced_two_term",
    "optimum",
    "exhaustive",
    "regret_best_uniform",
    "regret_balanced_two_term",
    "headroom_beyond_uniform_pct",
    "optimum_heterogeneous",
]

RATE_PAIRS = (
    (1.0, 1.0),
    (1.0, 0.5),
    (2.0, 0.5),
    (0.5, 2.0),
    (1.0, 0.25),
    (4.0, 1.0),
    (0.5, 0.5),
    (3.0, 0.75),
)

SHAPES = ((2, 2), (3, 2), (4, 1), (3, 3))


def _uniform(program, choice):
    return {
        site.site_id: (
            choice if choice in site.variant_names else site.variants[0].name
        )
        for site in program.sites
    }


def _variant_names(program) -> list[str]:
    names: list[str] = []
    for site in program.sites:
        for name in site.variant_names:
            if name != "barrier" and name not in names:
                names.append(name)
    return sorted(names)


def _exhaustive(program, supplies, limit=200_000):
    best = None
    best_assignment = None
    count = 0
    for assignment in program.iter_assignments():
        count += 1
        if count > limit:
            return best, best_assignment, False
        makespan = execute_multi(program.instantiate(assignment), supplies)
        if best is None or makespan < best:
            best, best_assignment = makespan, dict(assignment)
    return best, best_assignment, True


def _job(spec):
    lanes, stages, t_rate, ccz_rate = spec
    program = and_bank(lanes=lanes, stages=stages)
    supplies = factories(t_rate, ccz_rate)

    per_uniform = {
        name: execute_multi(program.instantiate(_uniform(program, name)), supplies)
        for name in _variant_names(program)
    }
    best_uniform_value = min(per_uniform.values())

    # "Minimise total states" is the natural single-metric generalisation of
    # minimising T-count when there is more than one kind of state.
    min_states_name = min(
        _variant_names(program),
        key=lambda name: (
            sum(resource_counts(program.instantiate(_uniform(program, name))).values()),
            name,
        ),
    )
    balanced = execute_multi(
        program.instantiate(balanced_selection(program, supplies)), supplies
    )
    optimum, optimum_assignment, complete = _exhaustive(program, supplies)
    heterogeneous = (
        len({value for value in optimum_assignment.values() if value != "barrier"}) > 1
        if optimum_assignment
        else False
    )

    return {
        "program": program.name,
        "lanes": lanes,
        "stages": stages,
        "t_rate": t_rate,
        "ccz_rate": ccz_rate,
        "makespan_all_t4": per_uniform.get("t4", ""),
        "makespan_all_ccz1": per_uniform.get("ccz1", ""),
        "makespan_min_states": per_uniform[min_states_name],
        "makespan_best_uniform": best_uniform_value,
        "makespan_balanced_two_term": balanced,
        "optimum": optimum,
        "exhaustive": int(complete),
        "regret_best_uniform": round(ratio(best_uniform_value, optimum), 4),
        "regret_balanced_two_term": round(ratio(balanced, optimum), 4),
        "headroom_beyond_uniform_pct": round(
            100.0 * (best_uniform_value - optimum) / best_uniform_value, 2
        ),
        "optimum_heterogeneous": int(heterogeneous),
    }


def main() -> None:
    """Run the probe over a few shapes and rate pairs."""

    specs = [
        (lanes, stages, t_rate, ccz_rate)
        for (lanes, stages), (t_rate, ccz_rate) in product(SHAPES, RATE_PAIRS)
    ]
    with Pool(processes=4) as pool:
        rows = list(pool.imap_unordered(_job, specs))
    rows.sort(key=lambda row: (row["lanes"], row["stages"], row["t_rate"], row["ccz_rate"]))
    write_csv(RESULT_DIR / "rac6_multiresource_probe.csv", rows, FIELDS)

    print(
        f"{'lanes':>5s} {'stg':>3s} {'Trate':>6s} {'CCZrate':>7s} {'allT4':>6s} "
        f"{'allCCZ':>7s} {'bUnif':>6s} {'2-term':>6s} {'opt':>5s} {'gain%':>6s} {'het':>4s} {'exh':>4s}"
    )
    for row in rows:
        print(
            f"{row['lanes']:5d} {row['stages']:3d} {row['t_rate']:6.2f} {row['ccz_rate']:7.2f} "
            f"{row['makespan_all_t4']:6} {row['makespan_all_ccz1']:7} "
            f"{row['makespan_best_uniform']:6d} {row['makespan_balanced_two_term']:6d} "
            f"{row['optimum']:5d} {row['headroom_beyond_uniform_pct']:6.1f} "
            f"{row['optimum_heterogeneous']:4d} {row['exhaustive']:4d}"
        )

    gains = [row["headroom_beyond_uniform_pct"] for row in rows]
    stats = summarize(gains)
    print()
    print(
        f"headroom beyond the best uniform implementation: median {stats['median']:.1f}%, "
        f"p90 {stats['p90']:.1f}%, max {stats['max']:.1f}%"
    )
    het = sum(row["optimum_heterogeneous"] for row in rows)
    print(f"optimum is heterogeneous in {het}/{len(rows)} configurations")
    two_term = summarize(row["regret_balanced_two_term"] for row in rows)
    print(
        f"two-term coordinate descent regret: median {two_term['median']:.3f}, "
        f"max {two_term['max']:.3f}"
    )


if __name__ == "__main__":
    main()
