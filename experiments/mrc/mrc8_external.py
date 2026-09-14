"""Phase 7: independently authored external workloads.

Arithmetic programs from qmpa (Alan Robertson, UTS) and qualtran (Google
Quantum AI) are run through the decision-site extractor and then through
every simple policy, the stage-DP selector, the global search and the
strongest affordable optimality reference, under the independent-bank model
and the coupled models. Nothing here was arranged to favour heterogeneous
selection: the programs were written for other purposes and the decision
sites are found by the extractor, not declared.

Clifford gates are kept in the primary run so that the Clifford critical path
counts; ``--drop-cliffords`` runs the resource-layer-only variant as a
sensitivity check. Results are reported separately from the synthetic
kernels and never pooled with them.
"""

from __future__ import annotations

import argparse
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_mrc import RESULT_DIR, SIMPLE_BASELINES, ratio, summarize, supply_pressure, write_csv

from ftqc_delivery.mrc.execution import resource_counts
from ftqc_delivery.mrc.extract import build_external, external_names
from ftqc_delivery.mrc.kernels import decision_sites
from ftqc_delivery.mrc.policies import best_oracle, heterogeneity, run_policy
from ftqc_delivery.mrc.resources import CCZ, T, coupled_machine, machine_for_capacity
from ftqc_delivery.mrc.stagedp import pipeline_stages, select_stage_dp


#: The independent-bank grid, identical to the synthetic study's.
CAPACITIES = (0.25, 0.5, 1.0, 2.0)
SHARES = (0.1, 0.25, 0.5, 0.75, 0.9)
#: Coupled provisioning at fixed area (model, tiles, ccz share of distiller area).
COUPLED = (
    ("B", 400, 0.25), ("B", 400, 0.5), ("B", 400, 0.75),
    ("C", 400, 0.25), ("C", 400, 0.5), ("C", 400, 0.75),
    ("C", 200, 0.5), ("C", 800, 0.5),
)
POLICIES = tuple(SIMPLE_BASELINES) + ("sim_descent",)
ORACLE_LIMIT = 40_000
ORACLE_BUDGET = 15.0

FIELDS = [
    "program", "source", "cliffords", "gates", "decision_sites", "stages", "max_stage_width",
    "model", "capacity_or_tiles", "ccz_share", "t_rate", "ccz_rate", "supply_pressure",
    *[f"makespan_{policy}" for policy in POLICIES],
    "makespan_stage_dp_r5", "seconds_stage_dp_r5", "makespan_stage_dp_sim", "seconds_stage_dp_sim", "seconds_sim_descent",
    "makespan_reference", "reference_exhaustive", "reference_heterogeneity", "reference_ccz_fraction",
    "best_simple", "makespan_best_simple",
    "headroom_over_best_simple", "headroom_over_uniform",
    "regret_stage_dp_r5", "regret_stage_dp_sim", "regret_sim_descent", "regret_best_simple",
]


def machine_list(quick: bool = False):
    """Yield (model, capacity_or_tiles, share, machine)."""

    caps = (0.5, 2.0) if quick else CAPACITIES
    shares = (0.25, 0.75) if quick else SHARES
    for cap in caps:
        for share in shares:
            yield ("A", cap, share, machine_for_capacity(cap, share))
    coupled = COUPLED[3:6] if quick else COUPLED
    for model, tiles, share in coupled:
        yield (model, tiles, share, coupled_machine(model, tiles, share))


def _ccz_fraction(program, assignment) -> float:
    sites = decision_sites(program)
    if not sites:
        return float("nan")
    ccz = 0
    for site in sites:
        counts = resource_counts(site.variant(assignment[site.site_id]).fragment.to_dag("x"))
        if counts.get(CCZ, 0) > 0:
            ccz += 1
    return ccz / len(sites)


def _job(args) -> list[dict[str, object]]:
    name, drop_cliffords, quick = args
    extraction = build_external(name, drop_cliffords=drop_cliffords)
    program = extraction.program
    stages = pipeline_stages(program)
    source = "qmpa" if name.startswith("qmpa") else "qualtran"
    rows: list[dict[str, object]] = []
    for model, size, share, machine in machine_list(quick):
        outcomes = {policy: run_policy(policy, program, machine) for policy in POLICIES}
        start = time.perf_counter()
        dp = select_stage_dp(program, machine, mode="analytic", refine=5)
        dp_seconds = time.perf_counter() - start
        start = time.perf_counter()
        dp_sim = select_stage_dp(program, machine, mode="sim", refine=0)
        dp_sim_seconds = time.perf_counter() - start
        reference = best_oracle(
            program, machine, limit=ORACLE_LIMIT, time_budget=ORACLE_BUDGET,
            extra_seeds=[o.assignment for o in outcomes.values()] + [dp.assignment, dp_sim.assignment],
        )
        # The reference is the best assignment anyone found; never worse than a seed.
        best_seed = min(list(outcomes.values()) + [dp, dp_sim], key=lambda o: o.makespan)
        if best_seed.makespan < reference.makespan:
            reference = best_seed
        best_simple = min(SIMPLE_BASELINES, key=lambda p: outcomes[p].makespan)
        best_simple_makespan = outcomes[best_simple].makespan
        uniform = outcomes["uniform_oracle"].makespan
        row: dict[str, object] = {
            "program": name, "source": source, "cliffords": "dropped" if drop_cliffords else "kept",
            "gates": extraction.gate_count, "decision_sites": len(decision_sites(program)),
            "stages": len(stages), "max_stage_width": max(len(group) for group in stages) if stages else 0,
            "model": model, "capacity_or_tiles": size, "ccz_share": share,
            "t_rate": round(machine.rate(T), 4), "ccz_rate": round(machine.rate(CCZ), 4),
            "supply_pressure": round(supply_pressure(program, reference.assignment, machine), 4),
            "makespan_stage_dp_r5": dp.makespan, "seconds_stage_dp_r5": round(dp_seconds, 3),
            "makespan_stage_dp_sim": dp_sim.makespan, "seconds_stage_dp_sim": round(dp_sim_seconds, 3),
            "regret_stage_dp_sim": round(ratio(dp_sim.makespan, reference.makespan), 4),
            "seconds_sim_descent": round(outcomes["sim_descent"].seconds, 3),
            "makespan_reference": reference.makespan, "reference_exhaustive": int(reference.exhaustive),
            "reference_heterogeneity": round(heterogeneity(program, reference.assignment), 4),
            "reference_ccz_fraction": round(_ccz_fraction(program, reference.assignment), 4),
            "best_simple": best_simple, "makespan_best_simple": best_simple_makespan,
            "headroom_over_best_simple": round(ratio(best_simple_makespan - reference.makespan, best_simple_makespan), 4),
            "headroom_over_uniform": round(ratio(uniform - reference.makespan, uniform), 4),
            "regret_stage_dp_r5": round(ratio(dp.makespan, reference.makespan), 4),
            "regret_sim_descent": round(ratio(outcomes["sim_descent"].makespan, reference.makespan), 4),
            "regret_best_simple": round(ratio(best_simple_makespan, reference.makespan), 4),
        }
        for policy in POLICIES:
            row[f"makespan_{policy}"] = outcomes[policy].makespan
        rows.append(row)
    return rows


def export_sites(names: list[str], path: Path) -> None:
    """Write the extracted decision-site records (Phase 6 deliverable)."""

    fields = ["program", "site_id", "role", "gate_index", "qubits", "depth", "paired_with",
              "variants", "signatures", "ancillas", "sources", "equivalence"]
    rows = []
    for name in names:
        extraction = build_external(name, drop_cliffords=False)
        by_id = {site.site_id: site for site in extraction.program.sites}
        for record in extraction.sites:
            site = by_id[record.site_id]
            signatures = []
            for variant in site.variants:
                counts = resource_counts(variant.fragment.to_dag("x"))
                signatures.append(variant.name + ":" + ",".join(f"{k}={v}" for k, v in sorted(counts.items())) if counts else variant.name + ":clifford")
            rows.append({
                "program": name, "site_id": record.site_id, "role": record.family,
                "gate_index": record.index, "qubits": " ".join(map(str, record.qubits)),
                "depth": record.depth, "paired_with": record.paired_with or "",
                "variants": " ".join(record.variants), "signatures": " ".join(signatures),
                "ancillas": " ".join(map(str, record.ancillas)),
                "sources": " | ".join(record.sources), "equivalence": record.equivalence,
            })
    write_csv(path, rows, fields)
    print(f"  wrote {len(rows)} site records to {path.name}")


def report(rows: list[dict[str, object]]) -> None:
    """Print the summary, external only, never pooled with synthetic kernels."""

    def block(label: str, subset: list[dict[str, object]]) -> None:
        if not subset:
            return
        head = [float(r["headroom_over_best_simple"]) for r in subset]
        uni = [float(r["headroom_over_uniform"]) for r in subset]
        dp = [float(r["regret_stage_dp_r5"]) for r in subset]
        dps = [float(r["regret_stage_dp_sim"]) for r in subset]
        sd = [float(r["regret_sim_descent"]) for r in subset]
        het = sum(1 for r in subset if float(r["reference_heterogeneity"]) > 0)
        exact = sum(int(r["reference_exhaustive"]) for r in subset)
        print(f"  {label:34s} n={len(subset):3d} exact={exact:3d} | headroom/best-simple mean={summarize(head)['mean']:.3f} "
              f"med={summarize(head)['median']:.3f} p90={summarize(head)['p90']:.3f} max={summarize(head)['max']:.3f} "
              f">5%={sum(h > 0.05 for h in head):3d} >10%={sum(h > 0.10 for h in head):3d} | /uniform mean={summarize(uni)['mean']:.3f} "
              f"| hetero ref={het:3d} | dp_r5 regret mean={summarize(dp)['mean']:.3f} max={summarize(dp)['max']:.3f} "
              f"| dp_sim mean={summarize(dps)['mean']:.3f} max={summarize(dps)['max']:.3f} | search regret mean={summarize(sd)['mean']:.3f}")

    for cliffords in sorted({r["cliffords"] for r in rows}):
        sub = [r for r in rows if r["cliffords"] == cliffords]
        print(f"\n== Cliffords {cliffords} ==")
        block("all external", sub)
        for source in ("qmpa", "qualtran"):
            block(f"source={source}", [r for r in sub if r["source"] == source])
        for model in ("A", "B", "C"):
            block(f"model={model}", [r for r in sub if r["model"] == model])
        for source in ("qmpa", "qualtran"):
            for model in ("A", "B", "C"):
                block(f"source={source} model={model}", [r for r in sub if r["source"] == source and r["model"] == model])
        print("  per program (model A):")
        for name in sorted({r["program"] for r in sub}):
            block(f"    {name}", [r for r in sub if r["program"] == name and r["model"] == "A"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="small grid for a smoke test")
    parser.add_argument("--drop-cliffords", action="store_true", help="resource layers only")
    parser.add_argument("--names", nargs="*", default=None)
    parser.add_argument("--processes", type=int, default=2)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    names = args.names or external_names()
    suffix = "_dropped" if args.drop_cliffords else ""
    out = Path(args.out) if args.out else RESULT_DIR / f"mrc8_external{suffix}.csv"
    if not args.drop_cliffords and not args.names:
        export_sites(names, RESULT_DIR / "mrc8_sites.csv")

    jobs = [(name, args.drop_cliffords, args.quick) for name in names]
    rows: list[dict[str, object]] = []
    with Pool(processes=args.processes) as pool:
        for done, produced in enumerate(pool.imap_unordered(_job, jobs), 1):
            rows.extend(produced)
            print(f"  done {done}/{len(jobs)} ({produced[0]['program']})", flush=True)
    rows.sort(key=lambda r: (r["program"], r["model"], float(r["capacity_or_tiles"]), float(r["ccz_share"])))
    write_csv(out, rows, FIELDS)
    print(f"wrote {len(rows)} rows to {out}")
    report(rows)


if __name__ == "__main__":
    main()
