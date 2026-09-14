"""Decision-site extraction from a real gate-level program.

The kernels used so far declare their decision sites by hand. A compiler
cannot: it receives a program and must find the operations whose
implementation is free to vary. This module does that for gate-level programs
expressed as a stream of named gates over integer qubit lines, which is what
arithmetic libraries such as qmpa emit.

Every Toffoli occurrence becomes a decision site. Which realisations are legal
at a site depends on its context, and the extractor records the argument:

* A standalone Toffoli may be realised as one CCZ state consumed directly
  (Gidney & Fowler 2019), as 7 T states at T-depth 3 (Amy, Maslov, Mosca &
  Roetteler 2013) or T-depth 1 (Selinger 2013), or as 4 T states with one
  ancilla and a measurement-based erasure (Jones 2013; Gidney 2018 Fig. 3:
  temporary AND, CNOT into the target, uncompute the AND by measurement). The
  4-T form needs classical feed-forward, which the record states.
* A compute/uncompute pair -- a later Toffoli with the same controls and target
  where no gate in between writes either control -- is the temporary-AND
  structure of a ripple-carry adder (the MAJ/UMA halves of Cuccaro et al.
  2004; Gidney 2018 computes the same carries into fresh ancillas). The
  compute may be done into a fresh ancilla with one CCZ state or 4 T states
  and the uncompute is then a measurement costing no magic states at all
  (Gidney 2018). Because the two Toffolis share the AND value, this is exact
  whenever the controls are unchanged between them; the target line may be
  read or written freely, since XOR-ing it with a stored copy of the AND is
  the same operation as XOR-ing it with the AND recomputed. In-place 7-T
  realisations are not offered at the compute half of a pair: they force a
  magic-state-consuming uncompute, so the pair would cost at least 7 T plus
  another Toffoli against 1 CCZ or 4 T with the same number of sequential
  resource layers, and no selector can prefer them. (This assumes ancilla
  qubits are not the scarce resource, which is the standing assumption of the
  whole pilot.)

The pairing rule is conservative: a write to a control between the halves
breaks the pair even if a later gate would restore the value.

Dependencies follow qubit-line order: a gate depends on the most recent
earlier gate touching any of its lines. Every non-Toffoli gate becomes a
single-variant site of one Clifford operation, so the extracted program is an
ordinary :class:`ProgramSpace` and every policy applies unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ftqc_delivery.rac.variants import FragmentBuilder, ProgramSpace, Site, Variant

from .library import AND_CCZ, AND_T4, TOF_T7_D1, TOF_T7_D3, Realisation, _emit_and


@dataclass(frozen=True)
class GateRecord:
    """One gate of the input program.

    ``role`` carries an explicit compute/uncompute marker when the source IR
    has one (qualtran's ``And`` and ``And†``); it is ``None`` for plain gate
    streams, where the pairing must be inferred from structure.
    """

    name: str
    qubits: tuple[int, ...]
    role: str | None = None


@dataclass
class ExtractedSite:
    """What the extractor knows about one decision site, for the record."""

    site_id: str
    family: str
    index: int
    qubits: tuple[int, ...]
    depth: int
    variants: tuple[str, ...]
    sources: tuple[str, ...]
    ancillas: tuple[int, ...]
    paired_with: str | None = None
    equivalence: str = ""


@dataclass
class Extraction:
    """The result of extracting decision sites from a gate stream."""

    program: ProgramSpace
    sites: list[ExtractedSite] = field(default_factory=list)
    gate_count: int = 0
    toffoli_count: int = 0
    paired_count: int = 0
    pairing: str = "structural"
    explicit_pairs: int = 0
    structural_pairs: int = 0
    structural_matches: int = 0

    def summary(self) -> dict[str, object]:
        """Return a compact description for tables."""

        deciding = [site for site in self.sites if len(site.variants) > 1]
        return {
            "gates": self.gate_count,
            "toffolis": self.toffoli_count,
            "decision_sites": len(deciding),
            "paired_sites": self.paired_count,
            "standalone_sites": sum(1 for site in self.sites if site.family == "toffoli"),
            "variants_per_site": round(
                sum(len(site.variants) for site in deciding) / max(1, len(deciding)), 2
            ),
            "pairing": self.pairing,
            "explicit_pairs": self.explicit_pairs,
            "structural_pairs": self.structural_pairs,
            "structural_matches": self.structural_matches,
        }


TOF_T4_MEAS = Realisation(
    name="t4",
    layers=AND_T4.layers,
    ancillas=1,
    source=(
        "Jones 2013 / Gidney 2018 Fig. 3: AND into a fresh ancilla (4 T), CNOT to the "
        "target, measurement-based uncompute; needs classical feed-forward"
    ),
)

#: Realisations of a Toffoli with no recognised partner.
STANDALONE = (AND_CCZ, TOF_T4_MEAS, TOF_T7_D3, TOF_T7_D1)
#: Realisations of the compute half of a recognised compute/uncompute pair.
PAIR_COMPUTE = (AND_CCZ, AND_T4)
UNCOMPUTE_SOURCE = (
    "Gidney 2018: measurement-based uncomputation of a temporary AND, no magic states; "
    "legal because the paired compute writes a fresh ancilla and no control is written in between"
)

#: Gates whose action on the computational basis leaves every line unchanged.
DIAGONAL_GATES = {"z", "s", "sdg", "t", "tdg", "cz", "ccz", "rz", "phase", "p", "cphase", "cp"}
#: Gates that flip exactly their last line.
FLIP_LAST_GATES = {"x", "cx", "cnot", "ccx", "toffoli", "ccnot", "mcx"}
#: Spellings used by cirq and qualtran for the gates the analysis models.
GATE_ALIASES = {
    "_paulix": "x", "xgate": "x", "xpowgate": "x",
    "_pauliz": "z", "zgate": "z", "zpowgate": "z", "spowgate": "s", "tpowgate": "t",
    "cxpowgate": "cnot", "cxgate": "cnot", "cx": "cnot",
    "czpowgate": "cz", "czgate": "cz",
    "ccxpowgate": "toffoli", "ccx": "toffoli", "ccnot": "toffoli", "ccxgate": "toffoli",
    "cczpowgate": "ccz", "cczgate": "ccz",
}


def canonical_name(name: str) -> str:
    """Return the analysis's spelling of a gate name."""

    lowered = name.lower()
    return GATE_ALIASES.get(lowered, lowered)


def written_lines(gate: GateRecord) -> tuple[int, ...]:
    """Return the lines whose computational-basis value ``gate`` may change.

    Unknown gates are assumed to write every line they touch.
    """

    name = canonical_name(gate.name)
    if name in DIAGONAL_GATES:
        return ()
    if name in FLIP_LAST_GATES:
        return gate.qubits[-1:]
    return gate.qubits


def _toffoli_variants(prefix: str, realisations: Sequence[Realisation]) -> tuple[Variant, ...]:
    variants = []
    for realisation in realisations:
        builder = FragmentBuilder(prefix=f"{prefix}_{realisation.name}_")
        source = builder.add("Clifford")
        result = _emit_and(builder, realisation, [source])
        builder.add("Clifford", [result])
        variants.append(
            Variant(
                name=realisation.name,
                family="and",
                fragment=builder.finish(ancillas=realisation.ancillas, notes=realisation.source),
                notes=realisation.source,
            )
        )
    return tuple(variants)


def _clifford_site(site_id: str, name: str) -> Site:
    builder = FragmentBuilder(prefix=f"{site_id}_")
    builder.add("Clifford")
    return Site(
        site_id=site_id,
        family="clifford",
        variants=(Variant(name=name, family="clifford", fragment=builder.finish()),),
    )


TOFFOLI_NAMES = ("toffoli",)


def is_toffoli(gate: GateRecord) -> bool:
    """Return whether ``gate`` is a Toffoli under any accepted spelling."""

    return canonical_name(gate.name) in TOFFOLI_NAMES


def _toffoli_key(gate: GateRecord) -> tuple[tuple[int, ...], int]:
    return (tuple(sorted(gate.qubits[:2])), gate.qubits[2])


class _Values:
    """Symbolic computational-basis values of every line, as XOR-sets of atoms.

    An atom is an initial line value, the constant one, the AND of two
    expressions (hash-consed on its operands, so the same AND recomputed on the
    same operand expressions is the same atom and cancels under XOR), or a
    fresh unknown introduced by a gate the analysis does not model. Equality
    of two expressions therefore implies equality of the values they denote,
    while the converse can fail; the pairing rule built on it is sound but
    conservative.
    """

    ONE = ("one",)

    def __init__(self) -> None:
        self.values: dict[int, frozenset] = {}
        self.fresh = 0

    def get(self, line: int) -> frozenset:
        if line not in self.values:
            self.values[line] = frozenset({("var", line)})
        return self.values[line]

    def xor(self, line: int, other: frozenset) -> None:
        self.values[line] = self.get(line) ^ other

    def unknown(self, line: int) -> None:
        self.fresh += 1
        self.values[line] = frozenset({("fresh", self.fresh)})

    @staticmethod
    def conj(left: frozenset, right: frozenset) -> frozenset:
        key = tuple(sorted((tuple(sorted(left)), tuple(sorted(right)))))
        return frozenset({("and", key)})

    def apply(self, gate: GateRecord) -> None:
        name = canonical_name(gate.name)
        if name in DIAGONAL_GATES:
            return
        if name == "x":
            self.xor(gate.qubits[0], frozenset({self.ONE}))
        elif name in ("cx", "cnot"):
            self.xor(gate.qubits[1], self.get(gate.qubits[0]))
        elif name in TOFFOLI_NAMES:
            a, b, t = gate.qubits
            self.xor(t, self.conj(self.get(a), self.get(b)))
        else:
            for line in gate.qubits:
                self.unknown(line)


def find_uncompute_pairs(gates: Sequence[GateRecord]) -> dict[int, int]:
    """Return {compute index: uncompute index} for Toffoli pairs, by structure.

    A later Toffoli with the same controls and target uncomputes an earlier
    one when both controls provably hold the same values as at the compute,
    which is exactly when the earlier AND could have been computed into a
    fresh ancilla and erased by measurement (Gidney 2018). Values are tracked
    symbolically (see :class:`_Values`), so X and CNOT writes to a control
    that are undone before the uncompute do not break a pair, while writes the
    analysis cannot see through do. The target line may be read or written
    freely: XOR-ing it with a stored copy of the AND is the same operation as
    XOR-ing it with the AND recomputed. Explicit role markers are ignored here
    so that the rule can be checked against them.
    """

    pairs: dict[int, int] = {}
    open_by_key: dict[tuple[tuple[int, ...], int], list[tuple[int, frozenset, frozenset]]] = {}
    values = _Values()
    for index, gate in enumerate(gates):
        if is_toffoli(gate):
            key = _toffoli_key(gate)
            a, b = key[0]
            now_a, now_b = values.get(a), values.get(b)
            stack = open_by_key.setdefault(key, [])
            match = next(
                (pos for pos in range(len(stack) - 1, -1, -1)
                 if stack[pos][1] == now_a and stack[pos][2] == now_b),
                None,
            )
            if match is not None:
                pairs[stack[match][0]] = index
                del stack[match:]
            else:
                stack.append((index, now_a, now_b))
        values.apply(gate)
    return pairs


def explicit_uncompute_pairs(gates: Sequence[GateRecord]) -> dict[int, int]:
    """Return the pairs declared by the source IR's compute/uncompute markers.

    An uncompute marker is matched to the most recent unmatched compute marker
    on the same controls and target. Unmatched markers are left alone.
    """

    pairs: dict[int, int] = {}
    open_by_key: dict[tuple[tuple[int, ...], int], list[int]] = {}
    for index, gate in enumerate(gates):
        if not is_toffoli(gate) or gate.role is None:
            continue
        key = _toffoli_key(gate)
        if gate.role == "compute":
            open_by_key.setdefault(key, []).append(index)
        elif gate.role == "uncompute" and open_by_key.get(key):
            pairs[open_by_key[key].pop()] = index
    return pairs


def has_markers(gates: Sequence[GateRecord]) -> bool:
    """Return whether any gate carries an explicit compute/uncompute role."""

    return any(gate.role is not None for gate in gates)


def extract(gates: Iterable[GateRecord], name: str = "program", drop_cliffords: bool = False) -> Extraction:
    """Turn a gate stream into a program whose Toffolis are decision sites.

    ``drop_cliffords`` removes single-qubit and CNOT gates from the dependency
    graph entirely; dependencies then run Toffoli to Toffoli through the qubit
    lines. This keeps the extracted program small enough for the exact
    reference on modest circuits, at the cost of the Clifford critical path.
    """

    records = list(gates)
    structural = find_uncompute_pairs(records)
    if has_markers(records):
        pairs = explicit_uncompute_pairs(records)
        pairing = "explicit"
    else:
        pairs = structural
        pairing = "structural"
    matches = sum(1 for k, v in structural.items() if pairs.get(k) == v)
    reverse = {v: k for k, v in pairs.items()}
    uncompute_indices = set(reverse)

    sites: list[Site] = []
    edges: list[tuple[str, str]] = []
    extracted: list[ExtractedSite] = []
    last_on_line: dict[int, set[str]] = {}
    depth_of: dict[str, int] = {}
    toffolis = 0

    for index, gate in enumerate(records):
        toffoli = is_toffoli(gate)
        if not toffoli and drop_cliffords:
            # The gate is not a site, but dependencies still flow through it:
            # every line it touches now depends on everything any of its lines
            # depended on, so a Toffoli reached through a chain of CNOTs keeps
            # its ordering after the Cliffords are gone.
            merged: set[str] = set()
            for q in gate.qubits:
                merged |= last_on_line.get(q, set())
            for q in gate.qubits:
                last_on_line[q] = set(merged)
            continue
        site_id = f"g{index:05d}"
        role = "clifford"
        if toffoli:
            toffolis += 1
            if index in pairs:
                role = "and"
                site = Site(site_id=site_id, family="and", variants=_toffoli_variants(site_id, PAIR_COMPUTE))
            elif index in uncompute_indices:
                role = "and_uncompute"
                site = _clifford_site(site_id, "uncompute_and_meas")
            else:
                role = "toffoli"
                site = Site(site_id=site_id, family="toffoli", variants=_toffoli_variants(site_id, STANDALONE))
        else:
            site = _clifford_site(site_id, gate.name)
        sites.append(site)

        preds: set[str] = set()
        for q in gate.qubits:
            preds |= last_on_line.get(q, set())
        depth = 1 + max((depth_of[p] for p in preds), default=0)
        depth_of[site_id] = depth
        for pred in sorted(preds):
            edges.append((pred, site_id))
        for q in gate.qubits:
            last_on_line[q] = {site_id}

        if toffoli:
            partner = pairs.get(index)
            if role == "and_uncompute":
                partner = reverse[index]
                sources: tuple[str, ...] = (UNCOMPUTE_SOURCE,)
                ancillas: tuple[int, ...] = (0,)
                equivalence = (
                    "Erasing the ancilla that holds the AND reproduces the second Toffoli exactly "
                    "because both controls are unchanged since the compute"
                )
            else:
                sources = tuple(v.notes for v in site.variants)
                ancillas = tuple(v.fragment.ancillas for v in site.variants)
                equivalence = (
                    "Toffoli = CCZ up to Clifford conjugation; 7-T forms are exact Clifford+T "
                    "decompositions; 4-T form is exact given one clean ancilla and feed-forward"
                    + ("; compute half of a temporary AND, uncompute is free" if role == "and" else "")
                )
            extracted.append(
                ExtractedSite(
                    site_id=site_id,
                    family=role,
                    index=index,
                    qubits=gate.qubits,
                    depth=depth,
                    variants=tuple(v.name for v in site.variants),
                    sources=sources,
                    ancillas=ancillas,
                    paired_with=f"g{partner:05d}" if partner is not None else None,
                    equivalence=equivalence,
                )
            )

    program = ProgramSpace(
        name=name,
        sites=tuple(sites),
        edges=tuple(edges),
        meta=(("kernel", name), ("concurrency", "?"), ("width", "0")),
    )
    return Extraction(
        program=program,
        sites=extracted,
        gate_count=len(records),
        toffoli_count=toffolis,
        paired_count=2 * len(pairs),
        pairing=pairing,
        explicit_pairs=len(pairs) if pairing == "explicit" else 0,
        structural_pairs=len(structural),
        structural_matches=matches,
    )


# ---------------------------------------------------------------------------
# qmpa adapter and external workloads
# ---------------------------------------------------------------------------


def qmpa_gate_stream(circuit) -> list[GateRecord]:
    """Return a qmpa circuit as a gate stream."""

    stream: list[GateRecord] = []
    for gate in circuit.circuit:
        kind = type(gate).__name__
        if kind in ("Alloc", "Free", "Space"):
            continue
        qubits = tuple(int(q) for q in gate.qargs())
        stream.append(GateRecord(name=kind, qubits=qubits))
    return stream


def qmpa_adder(bits: int):
    """Return a qmpa Cuccaro ripple-carry adder circuit of the given width."""

    from qmpa.circuit import Circuit

    circuit = Circuit()
    a = circuit.register(bits, name="a", initial_value=0)
    b = circuit.register(bits + 1, name="b", initial_value=0)
    circuit.add_cuccaro(a, b)
    return circuit


def qmpa_multiplier(bits: int):
    """Return a qmpa shift-and-add multiplier circuit."""

    from qmpa.circuit import Circuit

    circuit = Circuit()
    a = circuit.register(bits, name="a", initial_value=0)
    b = circuit.register(bits, name="b", initial_value=0)
    circuit.multiply(a, b)
    return circuit


def qmpa_divider(bits: int):
    """Return a qmpa trial-subtraction divider circuit."""

    from qmpa.circuit import Circuit

    circuit = Circuit()
    a = circuit.register(bits, name="a", initial_value=0)
    b = circuit.register(bits, name="b", initial_value=0)
    circuit.divide(a, b)
    return circuit


def qualtran_gate_stream(bloq) -> list[GateRecord]:
    """Return a qualtran bloq, flattened to leaf gates, as a gate stream.

    ``And`` and ``And†`` become Toffolis on (control, control, ancilla) with
    explicit compute/uncompute roles. A two-bit controlled swap is expanded
    exactly into CNOT, Toffoli, CNOT. State preparations and effects on an
    ancilla line are kept as single-line operations that write their line.
    """

    circuit = bloq.decompose_bloq().flatten().to_cirq_circuit()
    qubits = sorted(circuit.all_qubits(), key=str)
    index = {q: i for i, q in enumerate(qubits)}
    stream: list[GateRecord] = []
    for op in circuit.all_operations():
        gate = op.gate
        kind = type(gate).__name__
        lines = tuple(index[q] for q in op.qubits)
        if kind == "And":
            role = "uncompute" if getattr(gate, "uncompute", False) else "compute"
            stream.append(GateRecord("Toffoli", lines, role=role))
        elif kind == "TwoBitCSwap":
            ctrl, x, y = lines
            stream.append(GateRecord("CNOT", (y, x)))
            stream.append(GateRecord("Toffoli", (ctrl, x, y)))
            stream.append(GateRecord("CNOT", (y, x)))
        else:
            stream.append(GateRecord(canonical_name(kind).upper() if canonical_name(kind) != kind.lower() else kind, lines))
    return stream


def _qualtran_builders() -> dict[str, object]:
    from qualtran import QUInt
    from qualtran.bloqs import arithmetic, mod_arithmetic

    return {
        "qt_add8": lambda: arithmetic.Add(QUInt(8)),
        "qt_add16": lambda: arithmetic.Add(QUInt(16)),
        "qt_sub8": lambda: arithmetic.Subtract(QUInt(8)),
        "qt_cadd8": lambda: arithmetic.CAdd(QUInt(8)),
        "qt_addk8": lambda: arithmetic.AddK(QUInt(8), k=93),
        "qt_ltc8": lambda: arithmetic.LessThanConstant(8, 101),
        "qt_gt8": lambda: arithmetic.GreaterThan(8, 8),
        "qt_modadd8": lambda: mod_arithmetic.ModAdd(8, mod=251),
        "qt_cmodadd8": lambda: mod_arithmetic.CModAdd(QUInt(8), mod=251),
        "qt_modsub8": lambda: mod_arithmetic.ModSub(QUInt(8), mod=251),
        "qt_modneg8": lambda: mod_arithmetic.ModNeg(QUInt(8), mod=251),
    }


QMPA_BUILDERS = {
    "qmpa_add8": lambda: qmpa_adder(8),
    "qmpa_add16": lambda: qmpa_adder(16),
    "qmpa_add32": lambda: qmpa_adder(32),
    "qmpa_mul4": lambda: qmpa_multiplier(4),
    "qmpa_mul6": lambda: qmpa_multiplier(6),
    "qmpa_mul8": lambda: qmpa_multiplier(8),
    "qmpa_div4": lambda: qmpa_divider(4),
    "qmpa_div6": lambda: qmpa_divider(6),
}


def external_names() -> list[str]:
    """Return the names of every external workload, qmpa first."""

    return list(QMPA_BUILDERS) + list(_qualtran_builders())


def build_external(name: str, drop_cliffords: bool = True) -> Extraction:
    """Build and extract one external workload by name."""

    if name in QMPA_BUILDERS:
        stream = qmpa_gate_stream(QMPA_BUILDERS[name]())
    else:
        stream = qualtran_gate_stream(_qualtran_builders()[name]())
    return extract(stream, name=name, drop_cliffords=drop_cliffords)


def qualtran_workloads(drop_cliffords: bool = True) -> list[Extraction]:
    """Return independently authored qualtran arithmetic bloqs with extracted sites.

    qualtran (Google Quantum AI) expresses its adders and modular arithmetic
    with explicit ``And``/``And†`` pairs, so these programs also serve as
    ground truth for the structural pairing rule.
    """

    out = []
    for name in _qualtran_builders():
        try:
            out.append(build_external(name, drop_cliffords))
        except Exception as error:  # a library quirk should not hide the others
            print(f"  skipped {name}: {error!r}")
    return out


def external_workloads(drop_cliffords: bool = True) -> list[Extraction]:
    """Return independently authored arithmetic programs with extracted sites.

    The qmpa circuits (Alan Robertson, UTS) come from a reversible
    multi-precision arithmetic library written for other purposes; nothing in
    them was arranged to favour heterogeneous selection.
    """

    out = []
    for name in QMPA_BUILDERS:
        try:
            out.append(build_external(name, drop_cliffords))
        except Exception as error:  # a library quirk should not hide the others
            print(f"  skipped {name}: {error!r}")
    return out
