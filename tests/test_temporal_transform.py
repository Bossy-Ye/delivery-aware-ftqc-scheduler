"""Tests for the semantics-preserving temporal transformations."""

from __future__ import annotations

import pytest

from ftqc_delivery.mrc.extract import GateRecord, extract
from ftqc_delivery.mrc.transform import (
    check_pairwise_commutation,
    commuting_edges,
    consuming_site_ids,
    conventional_edges,
    pace,
    random_linear_extension,
    reads_writes,
    reshape,
)


def test_control_lines_are_reads_and_targets_are_writes():
    reads, writes = reads_writes(GateRecord("Toffoli", (0, 1, 2)))
    assert reads == {0, 1} and writes == {2}
    reads, writes = reads_writes(GateRecord("CNOT", (0, 1)))
    assert reads == {0} and writes == {1}
    # A diagonal gate changes no computational-basis value.
    reads, writes = reads_writes(GateRecord("T", (3,)))
    assert reads == {3} and not writes
    # An unrecognised gate is assumed to write everything it touches.
    reads, writes = reads_writes(GateRecord("H", (4,)))
    assert not reads and writes == {4}


def test_read_after_read_is_not_a_dependency_but_the_others_are():
    # Two Toffolis sharing only controls commute, so no edge.
    shared_controls = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("Toffoli", (0, 1, 3))]
    assert conventional_edges(shared_controls) == [(0, 1)]
    assert commuting_edges(shared_controls) == []

    # Read after write: the second reads what the first wrote.
    raw = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("Toffoli", (2, 3, 4))]
    assert commuting_edges(raw) == [(0, 1)]

    # Write after write on the same target.
    waw = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("Toffoli", (3, 4, 2))]
    assert commuting_edges(waw) == [(0, 1)]

    # Write after read: a line read as a control may not be overwritten first.
    war = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("X", (0,))]
    assert commuting_edges(war) == [(0, 1)]


def test_commutation_check_accepts_the_commuting_graph_and_rejects_a_bad_one():
    gates = [
        GateRecord("Toffoli", (0, 1, 2)),
        GateRecord("Toffoli", (0, 1, 3)),
        GateRecord("CNOT", (2, 5)),
    ]
    ok, offenders = check_pairwise_commutation(gates, commuting_edges(gates))
    assert ok and not offenders

    # Dropping the read-after-write edge leaves a pair that does not commute.
    ok, offenders = check_pairwise_commutation(gates, [])
    assert not ok and (0, 2) in offenders


def test_random_linear_extension_respects_every_edge():
    gates = [GateRecord("Toffoli", (i, i + 1, i + 2)) for i in range(6)]
    edges = commuting_edges(gates)
    for seed in range(4):
        order = random_linear_extension(len(gates), edges, seed)
        position = {node: i for i, node in enumerate(order)}
        assert sorted(order) == list(range(len(gates)))
        for source, target in edges:
            assert position[source] < position[target]


def test_pacing_only_adds_edges_and_bounds_concurrency():
    stream = [GateRecord("Toffoli", (2 * i, 2 * i + 1, 100 + i)) for i in range(6)]
    program = reshape(extract(stream, name="wide").program, commuting_edges(stream))
    assert program.edges == ()  # every gate is independent
    paced = pace(program, 2)
    assert set(program.edges) <= set(paced.edges)
    assert paced.sites == program.sites
    consuming = consuming_site_ids(program)
    expected = {(consuming[i - 2], consuming[i]) for i in range(2, len(consuming))}
    assert expected <= set(paced.edges)


def test_pacing_never_makes_a_schedule_illegal():
    """Pacing restricts orderings, so its extensions are extensions of the base."""

    stream = [GateRecord("Toffoli", (2 * i, 2 * i + 1, 100 + i)) for i in range(5)]
    program = reshape(extract(stream, name="w").program, commuting_edges(stream))
    paced = pace(program, 2)
    index = {site.site_id: i for i, site in enumerate(paced.sites)}
    base_edges = {(index[a], index[b]) for a, b in program.edges}
    paced_edges = [(index[a], index[b]) for a, b in paced.edges]
    for seed in range(3):
        order = random_linear_extension(len(paced.sites), paced_edges, seed)
        position = {node: i for i, node in enumerate(order)}
        for source, target in base_edges:
            assert position[source] < position[target]


def test_reshape_keeps_every_site_and_therefore_every_resource_count():
    from ftqc_delivery.mrc.execution import resource_counts

    stream = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("CNOT", (2, 3)), GateRecord("Toffoli", (0, 1, 4))]
    extraction = extract(stream, name="keep")
    original = extraction.program
    changed = reshape(original, commuting_edges(stream))
    assert changed.sites == original.sites
    assignment = original.default_assignment()
    assert resource_counts(original.instantiate(assignment)) == resource_counts(
        changed.instantiate(assignment)
    )


def test_transformed_order_is_unitarily_equivalent():
    """Confirm the commutation argument numerically on a small circuit."""

    cirq = pytest.importorskip("cirq")
    import numpy as np

    stream = [
        GateRecord("Toffoli", (0, 1, 2)),
        GateRecord("Toffoli", (0, 1, 3)),
        GateRecord("CNOT", (2, 4)),
        GateRecord("T", (3,)),
        GateRecord("Toffoli", (3, 4, 5)),
    ]
    qubits = [cirq.LineQubit(i) for i in range(6)]
    build = {"Toffoli": cirq.TOFFOLI, "CNOT": cirq.CNOT, "T": lambda q: cirq.T(q)}
    ops = [build[g.name](*[qubits[q] for q in g.qubits]) for g in stream]
    reference = cirq.Circuit(ops).unitary(qubit_order=qubits)
    edges = commuting_edges(stream)
    for seed in range(4):
        order = random_linear_extension(len(stream), edges, seed)
        candidate = cirq.Circuit([ops[i] for i in order]).unitary(qubit_order=qubits)
        assert np.allclose(reference, candidate, atol=1e-12)
