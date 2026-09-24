"""Static versus branch-aware placement on real dynamic programs and controls.

For every program, network and branch probability, four compilers choose a
placement and every placement is scored under the same true probabilities:

* ``blind``    what the audited compilers do (branch interactions ignored);
* ``flat``     Case 1, the strongest control-flow-insensitive compiler;
* ``likely``   the trivial heuristic "optimise for the most probable branch";
* ``expected`` Case 2, the branch-aware objective, one placement;
* ``case3``    branch-dependent placement with teleportation charged,
               computed exactly where the placements can be enumerated.

Ties among a static compiler's optima are broken in that compiler's favour:
the tied placement that is best under the true probabilities is the one it is
credited with, so no baseline loses to bad luck.
"""

from __future__ import annotations

import json
import math
import sys
import time
import warnings
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from ftqc_delivery.ddqc.placement import (
    DynamicProgram,
    Segment,
    build_network,
    evaluate,
    exhaustive_optimum,
    local_search,
    reconfiguration_oracle,
    weights,
)
from ftqc_delivery.ddqc.programs import from_qasm2, from_qiskit, qualtran_program
from ftqc_delivery.utils.io import write_csv_rows

SCRATCH = Path("/tmp/claude-0/-home-user/e20503e7-ec17-5c34-979d-e2d3051d15b7/scratchpad")
RESULT_DIR = ROOT / "results" / "ddqc_go_nogo"
SEED = 20260924
PROBABILITIES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
REPO = {
    "qualtran": ("quantumlib/Qualtran (PyPI)", "0.7.0"),
    "qasmbench": ("pnnl/QASMBench", "357b942396d5c2b7cbc1c229c585a6ef5ccaebac"),
    "veriqbench": ("Veri-Q/Benchmark", "1c03e45371e5701f62c123943dec1cace4d46767"),
    "mqtbench": ("mqt.bench (PyPI)", "2.3.0"),
    "control": ("this study", "constructed"),
}


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


def _qualtran_builders():
    from qualtran import QUInt
    from qualtran.bloqs import arithmetic, data_loading, mod_arithmetic

    return {
        # census widths
        "qt_add8": lambda: arithmetic.Add(QUInt(8)),
        "qt_sub8": lambda: arithmetic.Subtract(QUInt(8)),
        "qt_cadd8": lambda: arithmetic.CAdd(QUInt(8)),
        "qt_addk8": lambda: arithmetic.AddK(QUInt(8), k=93),
        "qt_ltc8": lambda: arithmetic.LessThanConstant(8, 101),
        "qt_gt8": lambda: arithmetic.GreaterThan(8, 8),
        "qt_equals8": lambda: arithmetic.Equals(QUInt(8)),
        "qt_modadd8": lambda: mod_arithmetic.ModAdd(8, mod=251),
        "qt_modneg8": lambda: mod_arithmetic.ModNeg(QUInt(8), mod=251),
        "qt_qrom16": lambda: data_loading.QROM.build_from_data(list(range(16)), target_bitsizes=(5,)),
        # small widths of the same algorithms, for exact Case 3
        "qt_add3": lambda: arithmetic.Add(QUInt(3)),
        "qt_add4": lambda: arithmetic.Add(QUInt(4)),
        "qt_equals3": lambda: arithmetic.Equals(QUInt(3)),
        "qt_qrom8": lambda: data_loading.QROM.build_from_data(list(range(8)), target_bitsizes=(3,)),
    }


def divergent_control(p: float, m: int = 4) -> DynamicProgram:
    tight = [(2, 3), (3, 4), (2, 4), (5, 6), (6, 7), (5, 7)] * 10
    return DynamicProgram(
        "ctl_divergent", 8,
        [Segment(pairs=tight), Segment(branches=[(p, [(1, 2)] * m), (1 - p, [(1, 5)] * (2 * m))])],
        source="control",
    )


def identical_control(p: float, m: int = 4) -> DynamicProgram:
    tight = [(2, 3), (3, 4), (2, 4), (5, 6), (6, 7), (5, 7)] * 10
    return DynamicProgram(
        "ctl_identical", 8,
        [Segment(pairs=tight), Segment(branches=[(p, [(1, 2)] * m), (1 - p, [(1, 2)] * m)])],
        source="control",
    )


def build_program(name: str, p: float) -> DynamicProgram:
    if name == "ctl_divergent":
        return divergent_control(p)
    if name == "ctl_identical":
        return identical_control(p)
    if name.startswith("qt_"):
        return qualtran_program(name, _qualtran_builders()[name], probability=p)
    if name.startswith("qb_"):
        group, folder = LOCAL_QASM2[name]
        path = sorted(p_ for p_ in (SCRATCH / "qasmbench" / group / folder).glob("*.qasm") if "transpiled" not in p_.name)[0]
        return from_qasm2(path, name, "qasmbench", probability=p)
    if name.startswith("vq_"):
        return from_qasm2(SCRATCH / "veriqbench" / "dynamic" / VERIQ[name], name, "veriqbench", probability=p)
    if name.startswith("mq_"):
        from mqt.bench import BenchmarkLevel, get_benchmark

        bench, size = name[3:].rsplit("_", 1)
        return from_qiskit(get_benchmark(bench, BenchmarkLevel.INDEP, int(size)), name, "mqtbench", probability=p)
    raise KeyError(name)


LOCAL_QASM2 = {
    "qb_cc_n12": ("medium", "cc_n12"),
    "qb_ipea_n2": ("small", "ipea_n2"),
    "qb_inverseqft_n4": ("small", "inverseqft_n4"),
    "qb_qec_sm_n5": ("small", "qec_sm_n5"),
    "qb_shor_n5": ("small", "shor_n5"),
}
VERIQ = {
    "vq_teleportation": "dqc_teleportation.qasm",
    "vq_bitflip": "dqc_bitflip_code.qasm",
    "vq_phaseflip": "dqc_phaseflip_code.qasm",
    "vq_state_injection_T": "dqc_state_injection_T.qasm",
}
MQT = ["mq_ghz_dynamic_6", "mq_iqpe_6", "mq_dynamic_qft_6"]

#: Real programs whose branches contain any multi-qubit interaction.
WITH_CONDITIONAL_PAIRS = [n for n in _qualtran_builders.__code__.co_consts if False]  # filled in main
LOCAL_ONLY = ["qb_ipea_n2", "qb_inverseqft_n4", "qb_qec_sm_n5", "qb_shor_n5",
              "vq_teleportation", "vq_bitflip", "vq_phaseflip", "vq_state_injection_T"] + MQT


def networks_for(n: int) -> list[tuple[int, int, str, int]]:
    """Return (qpus, capacity, topology, slack) configurations for n qubits."""

    out = []
    for k, topologies in ((2, ("line",)), (3, ("line", "full")), (4, ("line", "ring", "grid", "full"))):
        for slack in (0, 2):
            cap = math.ceil(n / k) + slack
            for topology in topologies:
                out.append((k, cap, topology, slack))
    return out


# ---------------------------------------------------------------------------
# One case
# ---------------------------------------------------------------------------


def _optimum(w, program, network, restarts=24):
    exact = exhaustive_optimum(w, program.n_qubits, network)
    if exact is not None:
        return exact[1], "exhaustive"
    # Collect the distinct best placements across seeds, so ties can be broken
    # in the compiler's favour even when the optimum is not enumerable.
    found = []
    best = math.inf
    for s in range(4):
        cost, placement = local_search(w, program.n_qubits, network, seed=SEED + s, restarts=restarts // 4 or 1)
        if cost < best - 1e-9:
            best, found = cost, [placement]
        elif abs(cost - best) <= 1e-9:
            found.append(placement)
    return np.array(found), "local_search"


def _likely_weights(program: DynamicProgram):
    """Weights of the heuristic that optimises for the most probable branch."""

    out = {}
    for segment in program.segments:
        if not segment.conditional:
            for a, b in segment.pairs:
                k = (min(a, b), max(a, b))
                out[k] = out.get(k, 0.0) + 1.0
            continue
        _, pairs = max(segment.branches, key=lambda item: item[0])
        for a, b in pairs:
            k = (min(a, b), max(a, b))
            out[k] = out.get(k, 0.0) + 1.0
    return out


def _score(program, placements, network):
    scored = [evaluate(program, placement, network) for placement in placements]
    best = int(np.argmin([x["expected_epr"] for x in scored]))
    return scored[best], placements[best]


def run_config(args) -> list[dict]:
    """Run every probability for one program on one network.

    ``flat`` and ``blind`` weights do not depend on the branch probability, so
    they are optimised once; ``likely`` depends only on which branch is more
    probable; ``expected`` is optimised per probability. Every chosen
    placement is then scored under each probability's true expected cost,
    with ties among a compiler's optima broken in that compiler's favour.
    """

    name, probabilities, k, cap, topology, slack, with_case3 = args
    network = build_network(k, cap, topology)
    t0 = time.perf_counter()
    reference = build_program(name, probabilities[0])
    restarts = 24 if reference.n_qubits <= 25 else 12

    cache: dict = {}

    def optimum_for(key, w):
        if key not in cache:
            cache[key] = _optimum(w, reference, network, restarts=restarts)
        return cache[key]

    flat_placements, flat_method = optimum_for("flat", weights(reference, "flat"))
    blind_w = weights(reference, "blind") or weights(reference, "flat")
    blind_placements, blind_method = optimum_for("blind", blind_w)

    rows = []
    for p in probabilities:
        program = build_program(name, p)
        likely_key = ("likely", p > 0.5)
        likely_placements, likely_method = optimum_for(likely_key, _likely_weights(program) or weights(program, "flat"))
        expected_placements, expected_method = _optimum(weights(program, "expected") or weights(program, "flat"), program, network, restarts=restarts)
        row = {
            "program": name,
            "source": program.source,
            "repository": REPO[program.source][0],
            "commit": REPO[program.source][1],
            "n_qubits": program.n_qubits,
            "conditional_regions": sum(1 for s in program.segments if s.conditional),
            "conditional_pairs": sum(len(b[1]) for s in program.segments if s.conditional for b in s.branches),
            "unconditional_pairs": sum(len(s.pairs) for s in program.segments if not s.conditional),
            "qpus": k, "capacity": cap, "slack": slack, "topology": topology,
            "probability": p, "seed": SEED,
        }
        chosen = {}
        for model, (placements, method) in (
            ("blind", (blind_placements, blind_method)),
            ("flat", (flat_placements, flat_method)),
            ("likely", (likely_placements, likely_method)),
            ("expected", (expected_placements, expected_method)),
        ):
            score, placement = _score(program, placements, network)
            chosen[model] = score
            for metric, value in score.items():
                row[f"{model}_{metric}"] = round(value, 4)
            row[f"{model}_placement"] = "".join(str(int(x)) for x in placement)
            row[f"{model}_method"] = method
        if with_case3:
            oracle = reconfiguration_oracle(program, network)
            row["case3_expected_epr"] = round(oracle["expected_epr"], 4) if oracle else ""
            row["case3_reconfiguration_epr"] = round(oracle["reconfiguration_epr"], 4) if oracle else ""
        else:
            row["case3_expected_epr"] = ""
            row["case3_reconfiguration_epr"] = ""
        flat_e = chosen["flat"]["expected_epr"]
        aware_e = chosen["expected"]["expected_epr"]
        blind_e = chosen["blind"]["expected_epr"]
        row["headroom_expected_vs_flat"] = round((flat_e - aware_e) / flat_e, 4) if flat_e > 0 else 0.0
        row["headroom_likely_vs_flat"] = round((flat_e - chosen["likely"]["expected_epr"]) / flat_e, 4) if flat_e > 0 else 0.0
        row["headroom_expected_vs_blind"] = round((blind_e - aware_e) / blind_e, 4) if blind_e > 0 else 0.0
        row["headroom_case3_vs_flat"] = (
            round((flat_e - row["case3_expected_epr"]) / flat_e, 4)
            if row["case3_expected_epr"] != "" and flat_e > 0 else ""
        )
        row["placement_changed"] = int(flat_e > aware_e + 1e-9)
        rows.append(row)
    elapsed = round(time.perf_counter() - t0, 3)
    for row in rows:
        row["runtime_s"] = round(elapsed / len(rows), 3)
    return rows


def main() -> None:
    warnings.simplefilter("ignore")
    real_conditional = [n for n in _qualtran_builders()] + ["qb_cc_n12"]
    small = {"qt_add3", "qt_add4", "qt_equals3", "qt_qrom8", "ctl_divergent", "ctl_identical"}
    jobs = []
    sizes = {}
    for name in real_conditional + LOCAL_ONLY + ["ctl_divergent", "ctl_identical"]:
        sizes[name] = build_program(name, 0.5).n_qubits
    for name in real_conditional + ["ctl_divergent", "ctl_identical"]:
        for k, cap, topology, slack in networks_for(sizes[name]):
            jobs.append((name, PROBABILITIES, k, cap, topology, slack, name in small))
    for name in LOCAL_ONLY:
        # No branch of these programs contains a multi-qubit interaction, so
        # the probability cannot enter any objective; one value suffices.
        for k, cap, topology, slack in networks_for(sizes[name]):
            jobs.append((name, (0.5,), k, cap, topology, slack, False))
    # Largest programs first, so the pool is not left waiting on one straggler.
    jobs.sort(key=lambda job: -sizes[job[0]])
    print(f"{len(jobs)} configurations", flush=True)
    rows = []
    with Pool(processes=3) as pool:
        for done, produced in enumerate(pool.imap_unordered(run_config, jobs), 1):
            rows.extend(produced)
            if done % 20 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} configurations, {len(rows)} rows", flush=True)
    rows.sort(key=lambda r: (r["program"], r["qpus"], r["topology"], r["slack"], r["probability"]))
    fields = list(rows[0].keys())
    for r in rows:
        for f in fields:
            r.setdefault(f, "")
    write_csv_rows(RESULT_DIR / "RAW_RESULTS.csv", rows, fields)
    (RESULT_DIR / "RAW_RESULTS.json").write_text(json.dumps(rows, indent=1, default=str))
    print(f"wrote {len(rows)} rows")


if __name__ == "__main__":
    main()
