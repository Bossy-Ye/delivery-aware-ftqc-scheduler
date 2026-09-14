"""Tests for decision-site extraction from gate streams."""

from __future__ import annotations

import pytest

from ftqc_delivery.mrc.execution import execute, resource_counts
from ftqc_delivery.mrc.extract import (
    GateRecord,
    extract,
    find_uncompute_pairs,
    qmpa_adder,
    qmpa_gate_stream,
)
from ftqc_delivery.mrc.kernels import decision_sites
from ftqc_delivery.mrc.resources import machine_for_capacity
from ftqc_delivery.mrc.stagedp import pipeline_stages


def test_every_toffoli_becomes_a_site_and_cliffords_do_not():
    stream = [GateRecord("CNOT", (0, 1)), GateRecord("Toffoli", (0, 1, 2)), GateRecord("X", (2,))]
    result = extract(stream, name="tiny")
    assert result.toffoli_count == 1
    assert len(decision_sites(result.program)) == 1
    assert len(result.program.sites) == 3


def test_dependencies_follow_qubit_lines():
    stream = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("Toffoli", (3, 4, 5)), GateRecord("Toffoli", (2, 5, 6))]
    result = extract(stream, name="lines")
    edges = set(result.program.edges)
    assert ("g00000", "g00002") in edges and ("g00001", "g00002") in edges
    assert ("g00000", "g00001") not in edges


def test_uncompute_pairs_survive_target_writes_but_not_control_writes():
    paired = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("CNOT", (0, 3)), GateRecord("Toffoli", (1, 0, 2))]
    assert find_uncompute_pairs(paired) == {0: 2}
    target_written = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("X", (2,)), GateRecord("Toffoli", (0, 1, 2))]
    assert find_uncompute_pairs(target_written) == {0: 2}
    control_written = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("CNOT", (3, 0)), GateRecord("Toffoli", (0, 1, 2))]
    assert find_uncompute_pairs(control_written) == {}
    unknown_gate = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("H", (1,)), GateRecord("Toffoli", (0, 1, 2))]
    assert find_uncompute_pairs(unknown_gate) == {}


def test_dropping_cliffords_keeps_dependencies_that_flow_through_them():
    stream = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("CNOT", (2, 3)), GateRecord("Toffoli", (3, 4, 5))]
    kept = extract(stream, name="k", drop_cliffords=False)
    dropped = extract(stream, name="d", drop_cliffords=True)
    assert len(dropped.program.sites) == 2
    assert ("g00000", "g00002") in set(dropped.program.edges)
    assert [len(stage) for stage in pipeline_stages(kept.program)] == [len(stage) for stage in pipeline_stages(dropped.program)]


def test_pair_halves_and_standalone_toffolis_get_the_right_variants():
    paired = extract([GateRecord("Toffoli", (0, 1, 2)), GateRecord("Toffoli", (0, 1, 2))], name="p")
    standalone = extract([GateRecord("Toffoli", (0, 1, 2))], name="s")
    compute, uncompute = paired.program.sites
    assert compute.family == "and" and compute.variant_names == ("ccz", "t4")
    assert uncompute.family == "clifford" and len(uncompute.variant_names) == 1
    assert len(decision_sites(paired.program)) == 1
    assert standalone.program.sites[0].family == "toffoli"
    assert standalone.program.sites[0].variant_names == ("ccz", "t4", "t7d3", "t7d1")
    records = {site.family: site for site in paired.sites}
    assert records["and"].paired_with == "g00001" and records["and_uncompute"].paired_with == "g00000"
    assert records["and_uncompute"].variants == ("uncompute_and_meas",)


def test_extracted_program_instantiates_and_runs():
    result = extract([GateRecord("Toffoli", (0, 1, 2)), GateRecord("CNOT", (2, 3)), GateRecord("Toffoli", (3, 4, 5))], name="run")
    assignment = result.program.default_assignment()
    dag = result.program.instantiate(assignment)
    assert resource_counts(dag).get("CCZ", 0) == 2
    machine = machine_for_capacity(1.0, 0.5)
    assert execute(dag, machine).makespan > 0


def test_qmpa_adder_extracts_paired_sites():
    pytest.importorskip("qmpa")
    result = extract(qmpa_gate_stream(qmpa_adder(8)), name="add8")
    assert result.toffoli_count == 16
    assert result.paired_count == 16
    summary = result.summary()
    assert summary["decision_sites"] == 8 and summary["standalone_sites"] == 0
    computes = [site for site in result.sites if site.family == "and"]
    assert len(computes) == 8 and all(site.variants == ("ccz", "t4") for site in computes)
    assert all(site.paired_with is not None for site in result.sites)
