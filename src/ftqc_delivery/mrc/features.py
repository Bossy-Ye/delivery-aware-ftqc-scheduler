"""Structural measurement of a program, independent of any policy outcome.

Everything here is computed from the program's decision sites and their
variants. No machine, no policy and no simulation is involved, so a workload
can be classified as a target or a control before any performance number
exists. The temporal-heterogeneity measures are deliberately several: the
study fixes the candidates first and reports all of them, rather than keeping
whichever one correlates best with the gains.
"""

from __future__ import annotations

from math import log2
from statistics import fmean, pvariance

from ftqc_delivery.rac.variants import ProgramSpace, Site

from .execution import resource_counts
from .kernels import decision_sites
from .policies import t_equivalents
from .resources import CCZ, T
from .stagedp import pipeline_stages


def _cheapest_counts(site: Site) -> dict[str, int]:
    """Return the resource counts of the site's fewest-T-equivalent variant.

    This is a fixed, policy-independent reference: it does not depend on a
    machine, so it cannot smuggle an outcome into a structural feature.
    """

    best: dict[str, int] | None = None
    best_cost = None
    for variant in site.variants:
        counts = resource_counts(variant.fragment.to_dag(variant.name))
        cost = t_equivalents(counts)
        if best_cost is None or cost < best_cost:
            best_cost, best = cost, counts
    return best or {}


def _ccz_share(counts: dict[str, int]) -> float:
    """Return the CCZ fraction of a demand vector, in T-equivalents."""

    total = t_equivalents(counts)
    if total <= 0:
        return 0.0
    return 2.0 * counts.get(CCZ, 0) / total


def _preferred_resource(site: Site) -> str | None:
    """Return the resource a site would draw on if left to itself."""

    counts = _cheapest_counts(site)
    if not counts:
        return None
    return max(counts, key=lambda resource: t_equivalents({resource: counts[resource]}))


def consuming_sites(program: ProgramSpace) -> list[Site]:
    """Return every site that consumes magic states, choice or not.

    A bare T gate has one implementation, so it is not a decision site, but it
    still competes for the T bank and still makes a stage's demand differ from
    its neighbours. Leaving such sites out of the demand measures would hide
    exactly the competition this study is about.
    """

    return [
        site for site in program.sites if t_equivalents(_cheapest_counts(site)) > 0
    ]


def stage_demand(program: ProgramSpace) -> list[dict[str, int]]:
    """Return the per-stage demand of the fewest-T-equivalent assignment.

    Stages are the decision-site levels; every consuming site is charged to the
    stage of the deepest decision level at or before it, so fixed T demand
    sitting between two decision stages is counted where it actually runs.
    """

    stages = pipeline_stages(program)
    depth = _site_depth(program)
    stage_of = {}
    for index, stage in enumerate(stages):
        for group in stage:
            for site in group:
                stage_of[site.site_id] = index
    demand: list[dict[str, int]] = [{} for _ in stages] or [{}]
    for site in consuming_sites(program):
        index = stage_of.get(site.site_id)
        if index is None:
            # Not a decision site: charge it to the last decision stage that
            # cannot run after it.
            index = min(
                len(demand) - 1,
                max(0, sum(1 for s in stages if _stage_depth(s, depth) <= depth[site.site_id]) - 1),
            )
        for resource, count in _cheapest_counts(site).items():
            demand[index][resource] = demand[index].get(resource, 0) + count
    return demand


def _site_depth(program: ProgramSpace) -> dict[str, int]:
    """Return each site's depth in the site graph."""

    predecessors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    successors: dict[str, set[str]] = {site.site_id: set() for site in program.sites}
    for source, target in program.edges:
        predecessors[target].add(source)
        successors[source].add(target)
    remaining = {sid: len(preds) for sid, preds in predecessors.items()}
    queue = [sid for sid, count in remaining.items() if count == 0]
    order: list[str] = []
    while queue:
        current = queue.pop()
        order.append(current)
        for nxt in successors[current]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                queue.append(nxt)
    depth: dict[str, int] = {}
    for sid in order:
        depth[sid] = 1 + max((depth[p] for p in predecessors[sid]), default=-1)
    for site in program.sites:
        depth.setdefault(site.site_id, 0)
    return depth


def _stage_depth(stage, depth: dict[str, int]) -> int:
    return min(depth[site.site_id] for group in stage for site in group)


def structural_features(program: ProgramSpace) -> dict[str, float]:
    """Return the structural description of one program."""

    sites = decision_sites(program)
    consuming = consuming_sites(program)
    stages = pipeline_stages(program)
    widths = [sum(len(group) for group in stage) for stage in stages]
    demand = stage_demand(program)

    families = sorted({site.family for site in sites})
    consuming_families = sorted({site.family for site in consuming})

    shares = [_ccz_share(counts) for counts in demand if t_equivalents(counts) > 0]
    per_stage_teq = [t_equivalents(counts) for counts in demand]

    # Candidate temporal-heterogeneity measures, all fixed in advance.
    mix_variance = pvariance(shares) if len(shares) > 1 else 0.0
    mix_drift = (
        fmean(abs(b - a) for a, b in zip(shares, shares[1:])) if len(shares) > 1 else 0.0
    )
    totals: dict[str, float] = {}
    for counts in demand:
        for resource, count in counts.items():
            totals[resource] = totals.get(resource, 0.0) + t_equivalents({resource: count})
    grand = sum(totals.values())
    mix_entropy = (
        max(0.0, -sum((v / grand) * log2(v / grand) for v in totals.values() if v > 0))
        if grand > 0
        else 0.0
    )
    preferred = [
        max(counts, key=lambda r: t_equivalents({r: counts[r]}))
        for counts in demand
        if t_equivalents(counts) > 0
    ]
    alternation_rate = (
        sum(1 for a, b in zip(preferred, preferred[1:]) if a != b) / max(1, len(preferred) - 1)
        if len(preferred) > 1
        else 0.0
    )
    load_variance = (
        pvariance(per_stage_teq) / max(1e-9, fmean(per_stage_teq) ** 2)
        if len(per_stage_teq) > 1 and fmean(per_stage_teq) > 0
        else 0.0
    )

    choosing = [site for site in sites if len(site.variants) > 1]
    return {
        "decision_sites": len(sites),
        "choosing_sites": len(choosing),
        "stages": len(stages),
        "max_stage_width": max(widths) if widths else 0,
        "mean_stage_width": fmean(widths) if widths else 0.0,
        "wide_stage_fraction": (
            sum(1 for w in widths if w > 1) / len(widths) if widths else 0.0
        ),
        "longest_serial_chain": len(stages),
        "total_parallelism": len(sites) / max(1, len(stages)),
        "consuming_sites": len(consuming),
        "families": len(families),
        "consuming_families": len(consuming_families),
        "family_names": "|".join(families),
        "mean_variants_per_site": (
            fmean([len(site.variants) for site in choosing]) if choosing else 0.0
        ),
        "t_demand": totals.get(T, 0.0),
        "ccz_demand": totals.get(CCZ, 0.0),
        "mean_stage_teq": fmean(per_stage_teq) if per_stage_teq else 0.0,
        "mix_variance": mix_variance,
        "mix_drift": mix_drift,
        "mix_entropy": mix_entropy,
        "alternation_rate": alternation_rate,
        "load_variance": load_variance,
    }


#: A workload is a target when its structure can express the hypothesised
#: mechanism: either several sites compete inside one stage, or the demand
#: changes character over time because more than one consuming family is
#: present. Both tests are structural and fixed before any policy is run.
def classify_role(features: dict[str, float]) -> str:
    """Return ``target`` or ``control`` from structure alone."""

    wide = features["max_stage_width"] >= 2 and features["wide_stage_fraction"] >= 0.05
    heterogeneous = features["consuming_families"] >= 2
    return "target" if (wide or heterogeneous) else "control"
