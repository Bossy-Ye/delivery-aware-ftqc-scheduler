"""What do the branches of real dynamic quantum programs actually do?

The hypothesis under test needs branches whose *multi-qubit* interactions
depend on the measurement outcome, because only multi-qubit interactions
generate inter-QPU communication. A branch that applies single-qubit
corrections costs the same under every placement, so no placement decision
can depend on it.

Every measurement-conditioned region of a program is classified by what its
branches contain:

``local``
    Only single-qubit operations (or measurements) in every branch. No
    communication depends on the outcome. Cannot change a placement.
``present_absent``
    One branch contains multi-qubit interactions and the other contains none.
    The expected weight of those interactions depends on the branch
    probability, so a branch-aware objective can reweight them.
``divergent``
    Two or more branches contain multi-qubit interactions with *different*
    partner sets. This is the case in the motivating example, where one
    branch couples q1 to q2 and the other couples q1 to q8.
``identical``
    Every branch has the same multi-qubit interactions.
``loop``
    A loop whose continuation depends on a measurement. Each iteration
    repeats the same body, so the interaction pattern does not diverge; only
    the expected repetition count depends on outcomes.

For ``present_absent`` and ``divergent`` regions the census also records
whether each conditional interaction pair already occurs unconditionally
elsewhere in the program. An edge that is paid for anyway can only be
reweighted, which is a weaker lever than an edge that exists only
conditionally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

Pair = tuple[int, int]


@dataclass
class Region:
    """One measurement-conditioned region and what its branches do."""

    kind: str  # "if" or "loop"
    branches: list[list[tuple[str, tuple[int, ...]]]]

    def pairs(self, branch: list[tuple[str, tuple[int, ...]]]) -> set[Pair]:
        out: set[Pair] = set()
        for _name, qubits in branch:
            distinct = sorted(set(qubits))
            for i in range(len(distinct)):
                for j in range(i + 1, len(distinct)):
                    out.add((distinct[i], distinct[j]))
        return out

    def classify(self) -> str:
        if self.kind == "loop":
            return "loop"
        pair_sets = [self.pairs(b) for b in self.branches]
        with_pairs = [p for p in pair_sets if p]
        if not with_pairs:
            return "local"
        if len(with_pairs) < len(pair_sets):
            return "present_absent"
        if all(p == with_pairs[0] for p in with_pairs):
            return "identical"
        return "divergent"

    def conditional_pairs(self) -> set[Pair]:
        out: set[Pair] = set()
        for branch in self.branches:
            out |= self.pairs(branch)
        return out


@dataclass
class ProgramCensus:
    """Every conditional region of one program, and its unconditional pairs."""

    name: str
    source: str
    regions: list[Region] = field(default_factory=list)
    unconditional_pairs: set[Pair] = field(default_factory=set)
    unconditional_multi_qubit_ops: int = 0
    note: str = ""

    def counts(self) -> dict[str, int]:
        out = {"local": 0, "present_absent": 0, "divergent": 0, "identical": 0, "loop": 0}
        for region in self.regions:
            out[region.classify()] += 1
        return out

    def novel_conditional_pairs(self) -> int:
        """Return conditional pairs that never occur unconditionally."""

        pairs: set[Pair] = set()
        for region in self.regions:
            if region.classify() in ("present_absent", "divergent"):
                pairs |= region.conditional_pairs()
        return len(pairs - self.unconditional_pairs)


# ---------------------------------------------------------------------------
# OpenQASM 2: ``if (creg == n) gate args;``
# ---------------------------------------------------------------------------

_QASM2_IF = re.compile(r"^\s*if\s*\(([^)]*)\)\s*(.+?);\s*$")
_QASM2_GATE = re.compile(r"^\s*([a-zA-Z_][\w]*)\s*(\([^)]*\))?\s+(.+?);\s*$")
_ARG = re.compile(r"(\w+)\s*\[\s*(\d+)\s*\]")
_SKIP = {"qreg", "creg", "include", "openqasm", "barrier", "measure", "reset", "gate", "opaque"}


def census_qasm2(path: Path, name: str, source: str) -> ProgramCensus:
    """Census of an OpenQASM 2 program, whose conditionals are single statements.

    In OpenQASM 2 a conditional applies one gate when a classical register
    equals a value; there is no else branch. Each is therefore a region with
    one populated branch and one empty one.
    """

    text = path.read_text()
    offsets: dict[str, int] = {}
    total = 0
    for match in re.finditer(r"qreg\s+(\w+)\s*\[\s*(\d+)\s*\]", text):
        offsets[match.group(1)] = total
        total += int(match.group(2))

    def operands(args: str) -> tuple[int, ...]:
        return tuple(offsets[reg] + int(idx) for reg, idx in _ARG.findall(args) if reg in offsets)

    census = ProgramCensus(name=name, source=source)
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line:
            continue
        conditional = _QASM2_IF.match(line)
        if conditional:
            body = conditional.group(2).strip() + ";"
            gate = _QASM2_GATE.match(body)
            if gate is None:
                continue
            op = (gate.group(1).lower(), operands(gate.group(3)))
            census.regions.append(Region(kind="if", branches=[[op], []]))
            continue
        gate = _QASM2_GATE.match(line)
        if gate is None or gate.group(1).lower() in _SKIP:
            continue
        qubits = operands(gate.group(3))
        if len(set(qubits)) >= 2:
            census.unconditional_multi_qubit_ops += 1
            distinct = sorted(set(qubits))
            for i in range(len(distinct)):
                for j in range(i + 1, len(distinct)):
                    census.unconditional_pairs.add((distinct[i], distinct[j]))
    return census


# ---------------------------------------------------------------------------
# OpenQASM 3, through the reference parser
# ---------------------------------------------------------------------------


def census_qasm3(path: Path, name: str, source: str) -> ProgramCensus:
    """Census of an OpenQASM 3 program, walking the reference parser's AST.

    Qubit operands are resolved to integers per register. Gates inside
    subroutines and gate definitions are counted where they are *called*
    only when the call is inlined by the program itself; calls to a
    subroutine inside a branch are recorded with the subroutine's qubit
    arguments as one multi-qubit operation, which is the conservative
    choice for this study (it can only make a branch look more
    communication-heavy, never less).
    """

    import openqasm3
    from openqasm3 import ast

    program = openqasm3.parse(path.read_text())
    offsets: dict[str, int] = {}
    total = 0

    def declare(statement) -> None:
        nonlocal total
        if isinstance(statement, ast.QubitDeclaration):
            size = statement.size.value if statement.size is not None and hasattr(statement.size, "value") else 1
            offsets[statement.qubit.name] = total
            total += int(size)

    synthetic: dict[str, int] = {}

    def placeholder(key: str) -> int:
        """Return a stable id for an operand the declarations cannot resolve.

        Operands inside subroutines are parameters, and indices may be loop
        variables, so they have no global position. A stable negative id per
        textual operand keeps the operation's arity and the distinctness of its
        operands, which is all the local/multi-qubit classification needs.
        """

        if key not in synthetic:
            synthetic[key] = -(len(synthetic) + 1)
        return synthetic[key]

    def resolve(operand) -> list[int]:
        if isinstance(operand, ast.IndexedIdentifier):
            base = operand.name.name
            out = []
            for index_group in operand.indices:
                for index in (index_group if isinstance(index_group, list) else [index_group]):
                    if hasattr(index, "value") and base in offsets:
                        out.append(offsets[base] + int(index.value))
                    else:
                        out.append(placeholder(f"{base}[{openqasm3.dumps(index) if hasattr(openqasm3, 'dumps') else id(index)}]"))
            return out
        if isinstance(operand, ast.Identifier):
            if operand.name in offsets:
                return [offsets[operand.name]]
            return [placeholder(operand.name)]
        return []

    def ops_in(statements) -> list[tuple[str, tuple[int, ...]]]:
        out: list[tuple[str, tuple[int, ...]]] = []
        for statement in statements or []:
            if isinstance(statement, ast.QuantumGate):
                qubits: list[int] = []
                for operand in statement.qubits:
                    qubits.extend(resolve(operand))
                out.append((statement.name.name, tuple(qubits)))
            elif isinstance(statement, ast.ExpressionStatement) and isinstance(
                statement.expression, ast.FunctionCall
            ):
                qubits = []
                for argument in statement.expression.arguments:
                    qubits.extend(resolve(argument))
                if qubits:
                    out.append((statement.expression.name.name, tuple(qubits)))
            elif isinstance(statement, (ast.ClassicalAssignment,)) and isinstance(
                getattr(statement, "rvalue", None), ast.FunctionCall
            ):
                qubits = []
                for argument in statement.rvalue.arguments:
                    qubits.extend(resolve(argument))
                if qubits:
                    out.append((statement.rvalue.name.name, tuple(qubits)))
            elif isinstance(statement, ast.Box):
                out.extend(ops_in(statement.body))
        return out

    census = ProgramCensus(name=name, source=source)

    def walk(statements, conditional_depth: int) -> None:
        for statement in statements or []:
            declare(statement)
            if isinstance(statement, ast.BranchingStatement):
                census.regions.append(
                    Region(kind="if", branches=[ops_in(statement.if_block), ops_in(statement.else_block)])
                )
                walk(statement.if_block, conditional_depth + 1)
                walk(statement.else_block, conditional_depth + 1)
            elif isinstance(statement, ast.WhileLoop):
                census.regions.append(Region(kind="loop", branches=[ops_in(statement.block)]))
                walk(statement.block, conditional_depth + 1)
            elif isinstance(statement, ast.ForInLoop):
                # A counted loop is not measurement-conditioned; its body is
                # unconditional work repeated a fixed number of times.
                walk(statement.block, conditional_depth)
            elif isinstance(statement, ast.SubroutineDefinition):
                # Conditionals written inside a subroutine are real program
                # conditionals; they run wherever the subroutine is called.
                walk(statement.body, conditional_depth)
            elif conditional_depth == 0:
                for name_, qubits in ops_in([statement]):
                    distinct = sorted(set(qubits))
                    if len(distinct) >= 2:
                        census.unconditional_multi_qubit_ops += 1
                        for i in range(len(distinct)):
                            for j in range(i + 1, len(distinct)):
                                census.unconditional_pairs.add((distinct[i], distinct[j]))

    walk(program.statements, 0)
    return census


# ---------------------------------------------------------------------------
# Qiskit circuits with IfElseOp / WhileLoopOp
# ---------------------------------------------------------------------------


def census_qiskit(circuit, name: str, source: str) -> ProgramCensus:
    """Census of a Qiskit circuit with native control-flow operations."""

    census = ProgramCensus(name=name, source=source)
    index = {q: i for i, q in enumerate(circuit.qubits)}

    def block_ops(block, outer_qubits) -> list[tuple[str, tuple[int, ...]]]:
        mapping = {inner: outer_qubits[k] for k, inner in enumerate(block.qubits)}
        out = []
        for instruction in block.data:
            qubits = tuple(index[mapping[q]] for q in instruction.qubits)
            if instruction.operation.name in ("barrier",):
                continue
            out.append((instruction.operation.name, qubits))
        return out

    for instruction in circuit.data:
        op = instruction.operation
        name_ = op.name
        if name_ == "if_else":
            branches = [block_ops(b, instruction.qubits) if b is not None else [] for b in op.blocks]
            if len(branches) == 1:
                branches.append([])
            census.regions.append(Region(kind="if", branches=branches))
        elif name_ in ("while_loop",):
            census.regions.append(Region(kind="loop", branches=[block_ops(op.blocks[0], instruction.qubits)]))
        elif name_ in ("barrier", "measure", "reset"):
            continue
        else:
            qubits = sorted({index[q] for q in instruction.qubits})
            if len(qubits) >= 2:
                census.unconditional_multi_qubit_ops += 1
                for i in range(len(qubits)):
                    for j in range(i + 1, len(qubits)):
                        census.unconditional_pairs.add((qubits[i], qubits[j]))
    return census


# ---------------------------------------------------------------------------
# Cirq circuits with classically controlled operations (qualtran lowering)
# ---------------------------------------------------------------------------


def census_cirq(circuit, name: str, source: str) -> ProgramCensus:
    """Census of a cirq circuit whose conditionals are classically controlled ops.

    A classically controlled operation applies its gate only when its
    control keys are set, with no else branch, so each becomes a region with
    one populated branch and one empty one.
    """

    import cirq

    census = ProgramCensus(name=name, source=source)
    qubits = sorted(circuit.all_qubits(), key=str)
    index = {q: i for i, q in enumerate(qubits)}
    for op in circuit.all_operations():
        if isinstance(op, cirq.ClassicallyControlledOperation):
            inner = op.without_classical_controls()
            census.regions.append(
                Region(kind="if", branches=[[(str(inner.gate), tuple(index[q] for q in inner.qubits))], []])
            )
            continue
        if cirq.is_measurement(op):
            continue
        distinct = sorted({index[q] for q in op.qubits})
        if len(distinct) >= 2:
            census.unconditional_multi_qubit_ops += 1
            for i in range(len(distinct)):
                for j in range(i + 1, len(distinct)):
                    census.unconditional_pairs.add((distinct[i], distinct[j]))
    return census
