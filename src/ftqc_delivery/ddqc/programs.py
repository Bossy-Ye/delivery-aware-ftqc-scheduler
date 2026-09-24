"""Turn real dynamic programs into the placement model's segment form.

Only two-qubit interactions matter for placement, so each program becomes a
sequence of unconditional interaction lists and measurement-conditioned
regions. A region's branch probabilities are not stored in the source
programs; they are supplied by the experiment, either as the physically
determined value (1/2 for measurement-based uncomputation, whose outcome comes
from an X-basis measurement) or swept.

Interactions among three or more qubits are expanded into their pairs, which
is the standard clique model of a multi-qubit gate's communication.
"""

from __future__ import annotations

import re
from pathlib import Path

from .placement import DynamicProgram, Segment

Pair = tuple[int, int]


def _pairs(qubits: tuple[int, ...]) -> list[Pair]:
    distinct = sorted(set(qubits))
    return [(distinct[i], distinct[j]) for i in range(len(distinct)) for j in range(i + 1, len(distinct))]


class _Builder:
    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.pending: list[Pair] = []

    def unconditional(self, qubits: tuple[int, ...]) -> None:
        self.pending.extend(_pairs(qubits))

    def region(self, branches: list[list[tuple[int, ...]]], probability: float) -> None:
        if self.pending:
            self.segments.append(Segment(pairs=self.pending))
            self.pending = []
        branch_pairs = [[pair for qubits in branch for pair in _pairs(qubits)] for branch in branches]
        if len(branch_pairs) == 1:
            branch_pairs.append([])
        # Two-way regions carry (p, 1 - p); wider ones share the rest equally.
        probabilities = [probability] + [(1 - probability) / (len(branch_pairs) - 1)] * (len(branch_pairs) - 1)
        self.segments.append(Segment(branches=list(zip(probabilities, branch_pairs))))

    def finish(self, name: str, n: int, source: str, note: str = "") -> DynamicProgram:
        if self.pending:
            self.segments.append(Segment(pairs=self.pending))
        return DynamicProgram(name, n, self.segments, source, note)


def from_cirq(circuit, name: str, source: str, probability: float = 0.5) -> DynamicProgram:
    """Return a cirq circuit with classically controlled operations as a program."""

    import cirq

    qubits = sorted(circuit.all_qubits(), key=str)
    index = {q: i for i, q in enumerate(qubits)}
    builder = _Builder()
    for op in circuit.all_operations():
        if isinstance(op, cirq.ClassicallyControlledOperation):
            inner = op.without_classical_controls()
            builder.region([[tuple(index[q] for q in inner.qubits)]], probability)
        elif cirq.is_measurement(op):
            continue
        elif len(op.qubits) >= 2:
            builder.unconditional(tuple(index[q] for q in op.qubits))
    return builder.finish(name, len(qubits), source)


def from_qiskit(circuit, name: str, source: str, probability: float = 0.5) -> DynamicProgram:
    """Return a Qiskit circuit with native control flow as a program."""

    index = {q: i for i, q in enumerate(circuit.qubits)}
    builder = _Builder()

    def block_ops(block, outer) -> list[tuple[int, ...]]:
        mapping = {inner: outer[k] for k, inner in enumerate(block.qubits)}
        out = []
        for instruction in block.data:
            if instruction.operation.name in ("barrier", "measure", "reset"):
                continue
            qs = tuple(index[mapping[q]] for q in instruction.qubits)
            if len(set(qs)) >= 2:
                out.append(qs)
        return out

    for instruction in circuit.data:
        op = instruction.operation
        if op.name == "if_else":
            branches = [block_ops(b, instruction.qubits) if b is not None else [] for b in op.blocks]
            builder.region(branches, probability)
        elif op.name in ("barrier", "measure", "reset"):
            continue
        else:
            qs = tuple(index[q] for q in instruction.qubits)
            if len(set(qs)) >= 2:
                builder.unconditional(qs)
    return builder.finish(name, len(circuit.qubits), source)


_IF = re.compile(r"^\s*if\s*\(([^)]*)\)\s*(.+?);\s*$")
_GATE = re.compile(r"^\s*([a-zA-Z_]\w*)\s*(\([^)]*\))?\s+(.+?);\s*$")
_ARG = re.compile(r"(\w+)\s*\[\s*(\d+)\s*\]")
_SKIP = {"qreg", "creg", "include", "openqasm", "barrier", "measure", "reset", "gate", "opaque"}


def from_qasm2(path: Path, name: str, source: str, probability: float = 0.5) -> DynamicProgram:
    """Return an OpenQASM 2 program as a program; each ``if`` is a two-way region."""

    text = path.read_text()
    offsets: dict[str, int] = {}
    total = 0
    for match in re.finditer(r"qreg\s+(\w+)\s*\[\s*(\d+)\s*\]", text):
        offsets[match.group(1)] = total
        total += int(match.group(2))

    def operands(args: str) -> tuple[int, ...]:
        return tuple(offsets[r] + int(i) for r, i in _ARG.findall(args) if r in offsets)

    builder = _Builder()
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line:
            continue
        conditional = _IF.match(line)
        if conditional:
            gate = _GATE.match(conditional.group(2).strip() + ";")
            if gate is not None:
                builder.region([[operands(gate.group(3))]], probability)
            continue
        gate = _GATE.match(line)
        if gate is None or gate.group(1).lower() in _SKIP:
            continue
        qs = operands(gate.group(3))
        if len(set(qs)) >= 2:
            builder.unconditional(qs)
    return builder.finish(name, total, source)


def qualtran_program(name: str, build, probability: float = 0.5) -> DynamicProgram:
    """Lower a qualtran bloq so that AND uncomputation becomes measure + conditional CZ."""

    import cirq

    def keep(op) -> bool:
        return (
            isinstance(op, cirq.ClassicallyControlledOperation)
            or cirq.is_measurement(op)
            or (len(op.qubits) <= 2 and not str(op.gate).startswith("And"))
        )

    circuit = build().decompose_bloq().flatten().to_cirq_circuit()
    lowered = cirq.Circuit(cirq.decompose(circuit, keep=keep))
    return from_cirq(lowered, name, "qualtran", probability)
