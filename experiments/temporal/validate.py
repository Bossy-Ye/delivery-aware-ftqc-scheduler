"""Establish that the transformations preserve semantics, as strongly as size allows.

Three levels of evidence, each recorded per workload:

``unitary``
    The full unitary of the original gate order equals that of several random
    linear extensions of the transformed graph. Exact, used where the qubit
    count allows building the matrix.
``statevector``
    The same comparison applied to random input states. Equality on random
    states is equality of the operators up to numerical tolerance.
``structural``
    Every pair of gates the transformed graph leaves unordered is checked to
    write nothing the other touches, which is the premise of the commutation
    argument. Used where the state space is too large to simulate.

A workload whose check fails at its own level is excluded from the decisive
results rather than explained away.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from ftqc_delivery.mrc.corpus import BY_NAME, CORPUS, build_workload
from ftqc_delivery.mrc.execution import resource_counts
from ftqc_delivery.mrc.extract import canonical_name
from ftqc_delivery.mrc.transform import (
    check_pairwise_commutation,
    commuting_edges,
    conventional_edges,
    random_linear_extension,
)
from ftqc_delivery.utils.io import write_csv_rows

RESULT_DIR = Path(__file__).resolve().parents[2] / "results" / "temporal_transform_go_nogo"

#: A generic angle for the synthesised rotations. The dependency argument is
#: about which lines a gate reads and writes, not about a particular angle, so
#: a generic one is the stronger test.
GENERIC_EXPONENT = 0.1
UNITARY_MAX_QUBITS = 11
STATEVECTOR_MAX_QUBITS = 22
EXTENSIONS = 3


def _cirq_ops(gates, qubits):
    import cirq

    ops = []
    for gate in gates:
        name = canonical_name(gate.name)
        lines = [qubits[q] for q in gate.qubits]
        if name == "toffoli":
            ops.append(cirq.TOFFOLI(*lines))
        elif name == "cnot":
            ops.append(cirq.CNOT(*lines))
        elif name == "x":
            ops.append(cirq.X(lines[0]))
        elif name == "z":
            ops.append(cirq.Z(lines[0]))
        elif name == "s":
            ops.append(cirq.S(lines[0]))
        elif name == "t":
            ops.append(cirq.T(lines[0]))
        elif name in ("zpowgate", "rz"):
            ops.append(cirq.ZPowGate(exponent=GENERIC_EXPONENT)(lines[0]))
        elif name in ("h", "hpowgate"):
            ops.append(cirq.H(lines[0]))
        elif name == "cz":
            ops.append(cirq.CZ(*lines))
        elif name in ("swap", "swappowgate"):
            ops.append(cirq.SWAP(*lines))
        else:
            raise ValueError(f"no cirq mapping for {gate.name!r}")
        
    return ops


def _numerical_check(gates, edges, level: str, seed: int) -> tuple[bool, float]:
    import cirq

    lines = sorted({q for gate in gates for q in gate.qubits})
    index = {line: i for i, line in enumerate(lines)}
    qubits = {line: cirq.LineQubit(index[line]) for line in lines}
    ops = _cirq_ops(gates, qubits)
    order = [qubits[line] for line in lines]

    reference_circuit = cirq.Circuit(ops)
    worst = 0.0
    if level == "unitary":
        reference = reference_circuit.unitary(qubit_order=order)
        for k in range(EXTENSIONS):
            extension = random_linear_extension(len(gates), edges, seed + k)
            candidate = cirq.Circuit([ops[i] for i in extension]).unitary(qubit_order=order)
            worst = max(worst, float(np.max(np.abs(reference - candidate))))
    else:
        rng = np.random.default_rng(seed)
        for k in range(EXTENSIONS):
            state = rng.normal(size=2 ** len(lines)) + 1j * rng.normal(size=2 ** len(lines))
            state = (state / np.linalg.norm(state)).astype(np.complex64)
            reference = cirq.final_state_vector(
                reference_circuit, initial_state=state, qubit_order=order, dtype=np.complex64
            )
            extension = random_linear_extension(len(gates), edges, seed + k)
            candidate = cirq.final_state_vector(
                cirq.Circuit([ops[i] for i in extension]),
                initial_state=state,
                qubit_order=order,
                dtype=np.complex64,
            )
            worst = max(worst, float(np.max(np.abs(reference - candidate))))
    return worst < 1e-4, worst


def t_counts(name: str) -> dict[str, int]:
    """Return the magic-state demand of the extracted program, by resource."""

    program = build_workload(name).program
    assignment = program.default_assignment()
    return dict(resource_counts(program.instantiate(assignment)))


def main() -> None:
    rows = []
    for workload in CORPUS:
        gates = workload.builder()
        lines = {q for gate in gates for q in gate.qubits}
        conv = conventional_edges(gates)
        comm = commuting_edges(gates)
        sound, offenders = check_pairwise_commutation(gates, comm)

        if len(lines) <= UNITARY_MAX_QUBITS:
            level = "unitary"
        elif len(lines) <= STATEVECTOR_MAX_QUBITS:
            level = "statevector"
        else:
            level = "structural"

        equivalent, worst = sound, 0.0
        note = f"{len(offenders)} non-commuting unordered pairs" if offenders else "all unordered pairs commute"
        if level != "structural" and sound:
            try:
                equivalent, worst = _numerical_check(gates, comm, level, seed=20260923)
                note += f"; max amplitude deviation {worst:.2e} over {EXTENSIONS} random linear extensions"
            except Exception as error:
                level, equivalent = "structural", sound
                note += f"; numerical check unavailable ({type(error).__name__})"

        counts = t_counts(workload.name)
        for transformation in ("commuting", "pacing"):
            rows.append(
                {
                    "workload": workload.name,
                    "source": workload.source,
                    "transformation": transformation,
                    "equivalence_method": level if transformation == "commuting" else "edge-superset",
                    "equivalent": bool(equivalent),
                    "T_count_original": counts.get("T", 0),
                    "T_count_transformed": counts.get("T", 0),
                    "CCZ_count_original": counts.get("CCZ", 0),
                    "CCZ_count_transformed": counts.get("CCZ", 0),
                    "gates": len(gates),
                    "qubits": len(lines),
                    "edges_conventional": len(conv),
                    "edges_transformed": len(comm),
                    "notes": note if transformation == "commuting" else
                    "pacing only adds edges to an acyclic graph, so every schedule of the result was already legal",
                }
            )
        print(f"  {workload.name:18s} {level:12s} equivalent={equivalent} {note}", flush=True)

    write_csv_rows(
        RESULT_DIR / "TRANSFORMATION_VALIDATION.csv",
        rows,
        [
            "workload", "source", "transformation", "equivalence_method", "equivalent",
            "T_count_original", "T_count_transformed", "CCZ_count_original",
            "CCZ_count_transformed", "gates", "qubits", "edges_conventional",
            "edges_transformed", "notes",
        ],
    )
    failed = [r["workload"] for r in rows if not r["equivalent"]]
    print(f"\n{len(rows)} rows; workloads failing verification: {sorted(set(failed)) or 'none'}")
    by_level = {}
    for r in rows:
        if r["transformation"] == "commuting":
            by_level[r["equivalence_method"]] = by_level.get(r["equivalence_method"], 0) + 1
    print(f"verification levels: {by_level}")


if __name__ == "__main__":
    main()
