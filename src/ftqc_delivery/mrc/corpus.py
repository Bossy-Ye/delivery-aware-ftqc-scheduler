"""The frozen external workload corpus for the stateful-oracle study.

Three independently authored sources, none of them written for this project:

qmpa
    Alan Robertson (UTS), a reversible multi-precision arithmetic library,
    commit 47e27d38a55f5161baac7805f9cc06a8146aa064.
qualtran
    Google Quantum AI, version 0.7.0, a fault-tolerant algorithm library whose
    bloqs carry explicit ``And``/``And†`` compute-uncompute markers.
QASMBench
    Pacific Northwest National Laboratory, commit
    357b942396d5c2b7cbc1c229c585a6ef5ccaebac, a benchmark suite of OpenQASM 2
    programs.

Workloads are labelled ``target`` when their extracted structure has parallel
decision sites or changing resource demand, and ``control`` when it does not.
The labels are assigned from structure measured before any policy is run, and
are frozen in the experiment contract.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from math import pi
from pathlib import Path
from typing import Callable

from .extract import Extraction, GateRecord, extract, qmpa_gate_stream, qualtran_gate_stream

#: Where the QASMBench checkout lives. Overridable for reproduction elsewhere.
QASMBENCH_ROOT = Path(
    os.environ.get(
        "QASMBENCH_ROOT",
        "/tmp/claude-0/-home-user/e20503e7-ec17-5c34-979d-e2d3051d15b7/scratchpad/qasmbench",
    )
)
QASMBENCH_COMMIT = "357b942396d5c2b7cbc1c229c585a6ef5ccaebac"
QMPA_COMMIT = "47e27d38a55f5161baac7805f9cc06a8146aa064"
QUALTRAN_VERSION = "0.7.0"

#: Precision used for every extracted rotation site, in bits.
ROTATION_BITS = 10

# ---------------------------------------------------------------------------
# OpenQASM 2 front end
# ---------------------------------------------------------------------------

_CLIFFORD_1Q = {"x", "y", "z", "h", "s", "sdg", "sx", "sxdg", "id"}
_CLIFFORD_2Q = {"cx", "cz", "cy", "ch"}


def _angle(text: str) -> float:
    """Evaluate a QASM angle expression."""

    expression = text.strip().replace("pi", str(pi))
    if not re.fullmatch(r"[0-9eE piE.+\-*/()]*", expression.replace(str(pi), " ")):
        raise ValueError(f"unsupported angle expression {text!r}")
    return float(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 - numeric only


def _z_rotation_gate(theta: float) -> str | None:
    """Return the gate name a z-rotation of ``theta`` really costs.

    Multiples of a half turn are Clifford, a quarter turn is exactly a T gate,
    and anything else is a genuine rotation that must be synthesised.
    """

    # Angles are measured in quarter turns: 0 is the identity, 2 and 6 are S
    # and its inverse, 4 is Z, and the odd quarter turns are exactly T gates.
    turns = (theta / (pi / 4)) % 8
    for value, name in ((0.0, None), (2.0, "S"), (4.0, "Z"), (6.0, "S")):
        if abs(turns - value) < 1e-9:
            return name
    if any(abs(turns - v) < 1e-9 for v in (1.0, 3.0, 5.0, 7.0)):
        return "T"
    return "ZPowGate"


def qasm_gate_stream(path: Path) -> list[GateRecord]:
    """Return an OpenQASM 2 program as a gate stream over integer lines.

    Only the qelib1 gates the study models are accepted, and a gate outside
    that set raises rather than being silently dropped: a missed non-Clifford
    would understate the program's magic-state demand. ``u1``/``u2``/``u3``
    are expanded into the z-rotations they contain (one, two and three
    respectively), each classified by its own angle, which is the standard
    Euler decomposition and errs towards counting rotations rather than
    hiding them.
    """

    text = path.read_text()
    registers: dict[str, tuple[int, int]] = {}
    next_line = 0
    stream: list[GateRecord] = []

    for raw in text.splitlines():
        line = raw.split("//")[0].strip().rstrip(";").strip()
        if not line or line.startswith(("OPENQASM", "include", "creg")):
            continue
        if line.startswith("qreg"):
            name, size = re.fullmatch(r"qreg\s+(\w+)\s*\[(\d+)\]", line).groups()
            registers[name] = (next_line, int(size))
            next_line += int(size)
            continue
        if line.startswith(("measure", "barrier", "reset", "if", "gate", "opaque", "}")):
            continue

        head, _, rest = line.partition(" ")
        name = head.split("(")[0].lower()
        params = re.findall(r"\(([^)]*)\)", head)
        args = [a.strip() for a in rest.split(",") if a.strip()]

        lines_used = []
        for arg in args:
            match = re.fullmatch(r"(\w+)\s*\[(\d+)\]", arg)
            if match is None:
                raise ValueError(f"whole-register operand {arg!r} in {path.name}")
            base, index = match.groups()
            start, size = registers[base]
            if int(index) >= size:
                raise ValueError(f"index {arg!r} out of range in {path.name}")
            lines_used.append(start + int(index))
        qubits = tuple(lines_used)

        if name == "ccx":
            stream.append(GateRecord("Toffoli", qubits))
        elif name in ("cswap", "fredkin"):
            control, first, second = qubits
            stream.append(GateRecord("CNOT", (second, first)))
            stream.append(GateRecord("Toffoli", (control, first, second)))
            stream.append(GateRecord("CNOT", (second, first)))
        elif name in _CLIFFORD_2Q:
            stream.append(GateRecord("CNOT" if name == "cx" else name.upper(), qubits))
        elif name == "swap":
            a, b = qubits
            for pair in ((a, b), (b, a), (a, b)):
                stream.append(GateRecord("CNOT", pair))
        elif name in _CLIFFORD_1Q:
            stream.append(GateRecord(name.upper(), qubits))
        elif name in ("t", "tdg"):
            stream.append(GateRecord("T", qubits))
        elif name in ("rz", "u1", "p", "phase"):
            gate = _z_rotation_gate(_angle(params[0]))
            if gate is not None:
                stream.append(GateRecord(gate, qubits))
        elif name in ("rx", "ry"):
            # A bare x- or y-rotation is a z-rotation conjugated by Cliffords.
            gate = _z_rotation_gate(_angle(params[0]))
            if gate is not None:
                stream.append(GateRecord(gate, qubits))
        elif name in ("u", "u3", "u2"):
            angles = [a.strip() for a in params[0].split(",")] if params else []
            for value in angles:
                gate = _z_rotation_gate(_angle(value))
                if gate is not None:
                    stream.append(GateRecord(gate, qubits))
        elif name in ("crz", "cu1", "cp"):
            # Controlled phase: half the angle on each line, two CNOTs between.
            gate = _z_rotation_gate(_angle(params[0]) / 2.0)
            control, target = qubits
            if gate is not None:
                stream.append(GateRecord(gate, (control,)))
                stream.append(GateRecord("CNOT", (control, target)))
                stream.append(GateRecord(gate, (target,)))
                stream.append(GateRecord("CNOT", (control, target)))
        else:
            raise ValueError(f"unmodelled gate {name!r} in {path.name}")
    return stream


def qasm_path(group: str, program: str) -> Path:
    """Return the path of a QASMBench program."""

    folder = QASMBENCH_ROOT / group / program
    candidates = sorted(p for p in folder.glob("*.qasm") if "transpiled" not in p.name)
    if not candidates:
        raise FileNotFoundError(f"no QASM file for {group}/{program} under {QASMBENCH_ROOT}")
    return candidates[0]


# ---------------------------------------------------------------------------
# qmpa builders
# ---------------------------------------------------------------------------


def _qmpa_circuit(method: str, bits: int, extra: int = 0):
    from qmpa.circuit import Circuit

    circuit = Circuit()
    a = circuit.register(bits, name="a", initial_value=0)
    b = circuit.register(bits + extra, name="b", initial_value=0)
    getattr(circuit, method)(a, b)
    return circuit


def qmpa_stream(method: str, bits: int, extra: int = 0) -> list[GateRecord]:
    return qmpa_gate_stream(_qmpa_circuit(method, bits, extra))


# ---------------------------------------------------------------------------
# qualtran builders
# ---------------------------------------------------------------------------


def _qualtran(name: str):
    from qualtran import QUInt
    import qualtran.bloqs.arithmetic as arith
    import qualtran.bloqs.data_loading as dl
    import qualtran.bloqs.mcmt as mcmt
    import qualtran.bloqs.mod_arithmetic as moda
    import qualtran.bloqs.phase_estimation as pe
    import qualtran.bloqs.basic_gates as bg
    import qualtran.bloqs.qft as qftm
    import qualtran.bloqs.state_preparation as sp

    table: dict[str, Callable[[], object]] = {
        "aliassamp8": lambda: sp.StatePreparationAliasSampling.from_probabilities(
            [0.25, 0.25, 0.125, 0.125, 0.125, 0.0625, 0.0625, 0.0]
        ),
        "aliassamp16": lambda: sp.StatePreparationAliasSampling.from_probabilities(
            [0.2, 0.15, 0.12, 0.1, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.02, 0.01, 0.005, 0.005, 0.0, 0.0]
        ),
        "qft6": lambda: qftm.QFTTextBook(6),
        "qft8": lambda: qftm.QFTTextBook(8),
        "qpe3": lambda: pe.TextbookQPE(
            bg.ZPowGate(0.25), pe.qpe_window_state.RectangularWindowState(3)
        ),
        "prepunif6": lambda: sp.PrepareUniformSuperposition(6),
        "qrom16x5": lambda: dl.QROM.build_from_data(list(range(16)), target_bitsizes=(5,)),
        "multiand10": lambda: mcmt.MultiAnd(cvs=(1,) * 10),
        "modadd8": lambda: moda.ModAdd(8, mod=251),
        "add16": lambda: arith.Add(QUInt(16)),
        "halfgt8": lambda: arith.comparison.LinearDepthHalfGreaterThan(QUInt(8)),
    }
    return table[name]()


# ---------------------------------------------------------------------------
# The frozen corpus
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Workload:
    """One frozen corpus entry."""

    name: str
    source: str
    family: str
    role: str
    builder: Callable[[], list[GateRecord]]
    rotation_bits: int | None = ROTATION_BITS
    note: str = ""


CORPUS: tuple[Workload, ...] = (
    # --- qmpa: wide by construction -------------------------------------
    Workload(
        "qmpa_draper8", "qmpa", "parallel_adder", "target",
        lambda: qmpa_stream("add_draper", 8),
        note=(
            "qmpa's Draper-style adder. Upstream leaves the prefix rounds "
            "(P/G/C) unimplemented, so this is used only as an independently "
            "authored wide gate stream, not as a verified adder."
        ),
    ),
    Workload(
        "qmpa_draper16", "qmpa", "parallel_adder", "target",
        lambda: qmpa_stream("add_draper", 16),
        note="as qmpa_draper8, 16 bits",
    ),
    Workload("qmpa_mul6", "qmpa", "multiplier", "target", lambda: qmpa_stream("multiply", 6)),
    Workload("qmpa_mul8", "qmpa", "multiplier", "target", lambda: qmpa_stream("multiply", 8)),
    Workload("qmpa_div6", "qmpa", "divider", "target", lambda: qmpa_stream("divide", 6)),
    # --- qualtran --------------------------------------------------------
    Workload("qt_aliassamp8", "qualtran", "state_preparation", "target", lambda: qualtran_gate_stream(_qualtran("aliassamp8"))),
    Workload("qt_aliassamp16", "qualtran", "state_preparation", "target", lambda: qualtran_gate_stream(_qualtran("aliassamp16"))),
    Workload("qt_qft6", "qualtran", "qft", "target", lambda: qualtran_gate_stream(_qualtran("qft6"))),
    Workload("qt_qft8", "qualtran", "qft", "target", lambda: qualtran_gate_stream(_qualtran("qft8"))),
    Workload("qt_qpe3", "qualtran", "phase_estimation", "target", lambda: qualtran_gate_stream(_qualtran("qpe3"))),
    Workload("qt_prepunif6", "qualtran", "state_preparation", "target", lambda: qualtran_gate_stream(_qualtran("prepunif6"))),
    # --- QASMBench -------------------------------------------------------
    Workload("qb_qram_n20", "qasmbench", "lookup", "target", lambda: qasm_gate_stream(qasm_path("medium", "qram_n20"))),
    Workload("qb_sat_n11", "qasmbench", "oracle", "target", lambda: qasm_gate_stream(qasm_path("medium", "sat_n11"))),
    Workload("qb_sat_n7", "qasmbench", "oracle", "target", lambda: qasm_gate_stream(qasm_path("small", "sat_n7"))),
    Workload("qb_multiplier_n15", "qasmbench", "multiplier", "target", lambda: qasm_gate_stream(qasm_path("medium", "multiplier_n15"))),
    Workload("qb_multiply_n13", "qasmbench", "multiplier", "target", lambda: qasm_gate_stream(qasm_path("medium", "multiply_n13"))),
    Workload("qb_sqrt_n18", "qasmbench", "arithmetic", "target", lambda: qasm_gate_stream(qasm_path("medium", "square_root_n18"))),
    # --- frozen negative controls ---------------------------------------
    Workload("qt_add16", "qualtran", "serial_adder", "control", lambda: qualtran_gate_stream(_qualtran("add16")),
             note="ripple-carry: one site per stage, homogeneous demand"),
    Workload("qt_modadd8", "qualtran", "serial_adder", "control", lambda: qualtran_gate_stream(_qualtran("modadd8")),
             note="serial chain"),
    Workload("qt_multiand10", "qualtran", "and_ladder", "control", lambda: qualtran_gate_stream(_qualtran("multiand10")),
             note="single serial AND ladder, no uncompute"),
    Workload("qt_qrom16x5", "qualtran", "lookup", "control", lambda: qualtran_gate_stream(_qualtran("qrom16x5")),
             note="unary iteration is genuinely sequential"),
    Workload("qt_halfgt8", "qualtran", "comparator", "control", lambda: qualtran_gate_stream(_qualtran("halfgt8")),
             note="serial comparison chain"),
)

BY_NAME = {workload.name: workload for workload in CORPUS}


def build_workload(name: str, drop_cliffords: bool = False) -> Extraction:
    """Build and extract one corpus workload."""

    workload = BY_NAME[name]
    return extract(
        workload.builder(),
        name=name,
        drop_cliffords=drop_cliffords,
        rotation_bits=workload.rotation_bits,
    )


def target_names() -> list[str]:
    return [w.name for w in CORPUS if w.role == "target"]


def control_names() -> list[str]:
    return [w.name for w in CORPUS if w.role == "control"]
