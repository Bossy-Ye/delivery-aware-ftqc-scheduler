"""Independently authored logical programs as remote-interaction sequences.

A program is lowered to CX plus single-qubit gates (the logical Clifford+T
basis; CZ and multi-qubit gates become CX sequences), and only the CX
interactions are kept, with their ASAP layer among CX gates. Single-qubit gates
are local on every QPU and do not change where a qubit sits.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

BASIS = ["cx", "rz", "sx", "x", "h", "s", "sdg", "t", "tdg"]
SCRATCH = Path("/tmp/claude-0/-home-user/e20503e7-ec17-5c34-979d-e2d3051d15b7/scratchpad")

# Excluded for oracle tractability (exact CP-SAT over qubits x layers):
# QASMBench factor247_n15 (294,691 CX after lowering), vqe_n24 (1,509,904 CX) and
# hhl_n14 (3.7M-line source), hhl_n10 (59,345 CX over 58,935 layers).
# name, category, source, locator. QASMBench "large" files ship with DQC-NAC's
# examples (qslab-unipr/dqcnac @ 564ae1b); "medium" files with QASMBench @ 357b942.
WORKLOADS = [
    ("qft_n29", "qft", "QASMBench (via DQC-NAC examples)", ("qasm", "ftp/dqcnac/examples/benchmark_circuits/qft_n29.qasm")),
    ("qft_n32", "qft", "MQT Bench 2.3.0", ("mqt", "qft", 32)),
    ("qpeexact_n24", "qft", "MQT Bench 2.3.0", ("mqt", "qpeexact", 24)),
    ("ae_n24", "qft", "MQT Bench 2.3.0", ("mqt", "ae", 24)),
    ("adder_n28", "arithmetic", "QASMBench (via DQC-NAC examples)", ("qasm", "ftp/dqcnac/examples/benchmark_circuits/adder_n28.qasm")),
    ("bigadder_n18", "arithmetic", "QASMBench 357b942", ("qasm", "qasmbench/medium/bigadder_n18/bigadder_n18.qasm")),
    ("cdkm_adder_n24", "arithmetic", "MQT Bench 2.3.0", ("mqt", "cdkm_ripple_carry_adder", 24)),
    ("vbe_adder_n22", "arithmetic", "MQT Bench 2.3.0", ("mqt", "vbe_ripple_carry_adder", 22)),
    ("draper_adder_n24", "arithmetic", "MQT Bench 2.3.0", ("mqt", "draper_qft_adder", 24)),
    ("modular_adder_n16", "modular-arithmetic", "MQT Bench 2.3.0", ("mqt", "modular_adder", 16)),
    ("rg_qft_multiplier_n16", "modular-arithmetic", "MQT Bench 2.3.0", ("mqt", "rg_qft_multiplier", 16)),
    ("multiplier_n15", "arithmetic", "QASMBench 357b942", ("qasm", "qasmbench/medium/multiplier_n15/multiplier_n15.qasm")),
    ("square_root_n18", "arithmetic", "QASMBench 357b942", ("qasm", "qasmbench/medium/square_root_n18/square_root_n18.qasm")),
    ("ising_n34", "pauli-rotations", "QASMBench (via DQC-NAC examples)", ("qasm", "ftp/dqcnac/examples/benchmark_circuits/ising_n34.qasm")),
    ("ising_n26", "pauli-rotations", "QASMBench 357b942", ("qasm", "qasmbench/medium/ising_n26/ising_n26.qasm")),
    ("vqe_uccsd_n8", "chemistry", "QASMBench 357b942", ("qasm", "qasmbench/small/vqe_uccsd_n8/vqe_uccsd_n8.qasm")),
    ("qaoa_n24", "qaoa", "MQT Bench 2.3.0", ("mqt", "qaoa", 24)),
    ("qec9xz_n17", "qec", "QASMBench 357b942", ("qasm", "qasmbench/medium/qec9xz_n17/qec9xz_n17.qasm")),
    ("steane_code_n26", "qec", "MQT Bench 2.3.0", ("mqt", "seven_qubit_steane_code", 26)),
    ("swap_test_n25", "other", "QASMBench (via DQC-NAC examples)", ("qasm", "ftp/dqcnac/examples/benchmark_circuits/swap_test_n25.qasm")),
    ("knn_n25", "other", "QASMBench 357b942", ("qasm", "qasmbench/medium/knn_n25/knn_n25.qasm")),
]


@dataclass
class Workload:
    name: str
    category: str
    source: str
    nq: int
    gates: List[Tuple[int, int]]          # CX (control, target) in program order
    layer: List[int]                      # ASAP CX layer of each gate (0-based)
    n_layers: int
    single_qubit_gates: int
    t_gates: int
    notes: str = ""
    per_qubit: List[List[int]] = field(default_factory=list)  # gate indices per qubit


def _load_circuit(locator):
    from qiskit import QuantumCircuit
    kind = locator[0]
    if kind == "qasm":
        from qiskit import qasm2
        path = SCRATCH / locator[1]
        # Measurements are dropped before lowering anyway; removing them first also
        # sidesteps sources whose trailing measurements name undeclared registers
        # (QASMBench vqe_uccsd_n8 measures q[]/c[] but declares only reg[]).
        text = "\n".join(line for line in path.read_text().splitlines()
                         if not line.lstrip().startswith("measure"))
        return qasm2.loads(text, include_path=[str(path.parent), str(SCRATCH / "qasmbench")],
                           custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS, strict=False)
    if kind == "mqt":
        from mqt.bench import BenchmarkLevel, get_benchmark
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return get_benchmark(locator[1], level=BenchmarkLevel.INDEP, circuit_size=locator[2])
    raise ValueError(kind)


def lower(circuit, name: str, category: str, source: str) -> Workload:
    from qiskit import transpile
    from qiskit.transpiler.passes import RemoveBarriers
    stripped = RemoveBarriers()(circuit.remove_final_measurements(inplace=False))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = transpile(stripped, basis_gates=BASIS + ["measure", "reset"],
                      optimization_level=1, seed_transpiler=1)
    index = {q: i for i, q in enumerate(t.qubits)}
    free = [0] * t.num_qubits
    gates, layers = [], []
    one_q = t_count = 0
    for inst in t.data:
        op = inst.operation
        qs = [index[q] for q in inst.qubits]
        if op.name == "cx":
            lvl = max(free[qs[0]], free[qs[1]])
            gates.append((qs[0], qs[1]))
            layers.append(lvl)
            free[qs[0]] = free[qs[1]] = lvl + 1
        elif op.name in ("barrier", "measure", "reset"):
            continue
        elif len(qs) == 1:
            one_q += 1
            t_count += op.name in ("t", "tdg")
        else:
            raise ValueError(f"{name}: unexpected {op.name}")
    used = sorted({q for g in gates for q in g})
    remap = {q: i for i, q in enumerate(used)}
    gates = [(remap[a], remap[b]) for a, b in gates]
    per_qubit = [[] for _ in used]
    for gi, (a, b) in enumerate(gates):
        per_qubit[a].append(gi)
        per_qubit[b].append(gi)
    note = "" if len(used) == t.num_qubits else f"{t.num_qubits - len(used)} qubits without CX dropped"
    return Workload(name, category, source, len(used), gates, layers,
                    (max(layers) + 1) if layers else 0, one_q, t_count, note, per_qubit)


def load(entry) -> Workload:
    name, category, source, locator = entry
    return lower(_load_circuit(locator), name, category, source)


def initial_partition(w: Workload, seed: int = 0) -> List[int]:
    """Balanced two-way min-cut of the weighted interaction graph (Kernighan-Lin).

    This is the resource-oriented static placement every policy starts from.
    """
    import networkx as nx
    from networkx.algorithms.community import kernighan_lin_bisection
    g = nx.Graph()
    g.add_nodes_from(range(w.nq))
    for a, b in w.gates:
        if g.has_edge(a, b):
            g[a][b]["weight"] += 1
        else:
            g.add_edge(a, b, weight=1)
    best = None
    for s in range(seed, seed + 8):
        part0, part1 = kernighan_lin_bisection(g, weight="weight", seed=s)
        cut = sum(d["weight"] for a, b, d in g.edges(data=True) if (a in part0) != (b in part0))
        if best is None or cut < best[0]:
            best = (cut, part0)
    homes = [0 if q in best[1] else 1 for q in range(w.nq)]
    return homes
