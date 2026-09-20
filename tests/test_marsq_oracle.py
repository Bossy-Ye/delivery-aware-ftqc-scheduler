"""Tests for the stateful oracle, its lower bound and the frozen corpus."""

from __future__ import annotations

import pytest

from ftqc_delivery.mrc.execution import execute
from ftqc_delivery.mrc.extract import GateRecord, extract
from ftqc_delivery.mrc.kernels import decision_sites, pilot_kernels
from ftqc_delivery.mrc.oracle import assignment_lower_bound, bounded_search, stateful_oracle
from ftqc_delivery.mrc.policies import run_policy
from ftqc_delivery.mrc.resources import CCZ, T, build_machine, machine_for_capacity


def _one_and():
    return extract([GateRecord("Toffoli", (0, 1, 2))], name="one_and").program


def _two_serial_ands():
    stream = [GateRecord("Toffoli", (0, 1, 2)), GateRecord("Toffoli", (2, 3, 4))]
    return extract(stream, name="two_ands").program


def test_tiny_case_optimum_is_the_only_feasible_choice_and_respects_arrival_time():
    """A single AND on a CCZ-only machine: one choice, and it cannot beat the factory.

    The CCZ bank has one factory of period 6, so its first state exists at
    cycle 6 and no execution consuming a CCZ can finish earlier. With no T
    bank the T-consuming variants are infeasible, so the optimum is the CCZ
    variant and its makespan is whatever that single execution takes.
    """

    program = _one_and()
    machine = build_machine(t_factories=0, ccz_factories=1)
    site = decision_sites(program)[0]

    result = stateful_oracle(program, machine)
    assert result.status == "proven"
    assert result.assignment[site.site_id] == "ccz"

    only = dict(program.default_assignment())
    only[site.site_id] = "ccz"
    assert result.makespan == execute(program.instantiate(only), machine).makespan
    assert result.makespan >= 6
    assert result.lower_bound <= result.makespan


def test_optimum_flips_with_which_bank_exists():
    """With no CCZ bank the same site must be built from T states instead."""

    program = _one_and()
    site = decision_sites(program)[0]
    ccz_only = stateful_oracle(program, build_machine(t_factories=0, ccz_factories=1))
    t_only = stateful_oracle(program, build_machine(t_factories=4, ccz_factories=0))
    assert ccz_only.assignment[site.site_id] == "ccz"
    assert t_only.assignment[site.site_id] != "ccz"
    assert t_only.status == "proven"


def test_carried_resource_state_changes_the_chosen_implementation():
    """The same program on the same factories decides differently once stock exists.

    This is the property the whole study rests on: the action taken at a site
    is a function of the resource state carried into it, not of the site alone.
    """

    program = _one_and()
    site = decision_sites(program)[0]
    empty = build_machine(t_factories=1, ccz_factories=1)
    stocked = empty.with_initial_stock({T: 8})

    on_empty = stateful_oracle(program, empty)
    on_stocked = stateful_oracle(program, stocked)

    assert on_empty.assignment[site.site_id] == "ccz"
    # With T states already banked the site switches to a T-consuming variant
    # and finishes sooner; which T variant wins is the simulator's business.
    assert on_stocked.assignment[site.site_id].startswith("t")
    assert on_stocked.makespan < on_empty.makespan


def test_lower_bound_never_exceeds_any_real_execution():
    """No policy may ever beat the bound, on any kernel or machine."""

    policies = ("uniform_min_teq", "uniform_oracle", "share_aware_greedy", "sim_descent")
    for program in pilot_kernels()[:6]:
        for capacity, share in ((0.25, 0.25), (1.0, 0.5), (2.0, 0.9)):
            machine = machine_for_capacity(capacity, share)
            bound = assignment_lower_bound(program, machine)
            for policy in policies:
                outcome = run_policy(policy, program, machine)
                assert bound <= outcome.makespan + 1e-9, (
                    f"bound {bound} exceeded {policy} makespan {outcome.makespan} "
                    f"on {program.name} cap={capacity} share={share}"
                )


def test_lower_bound_never_exceeds_the_proven_optimum():
    program = _two_serial_ands()
    for capacity, share in ((0.25, 0.1), (1.0, 0.5), (2.0, 0.75)):
        machine = machine_for_capacity(capacity, share)
        result = stateful_oracle(program, machine)
        assert result.status == "proven"
        assert result.lower_bound <= result.makespan + 1e-9
        assert result.gap() == 0.0


def test_bounded_search_is_deterministic():
    program = pilot_kernels()[0]
    machine = machine_for_capacity(0.5, 0.5)
    seeds = [program.default_assignment()]
    first = bounded_search(program, machine, seeds, time_budget=1.0, seed=7)
    second = bounded_search(program, machine, seeds, time_budget=1.0, seed=7)
    assert first[0] == second[0] and first[1] == second[1]


def test_proven_optimum_matches_independent_brute_force():
    """Enumerate by hand and check the oracle agrees."""

    from itertools import product

    program = _two_serial_ands()
    machine = machine_for_capacity(0.5, 0.5)
    sites = decision_sites(program)
    best = None
    for combination in product(*[site.variant_names for site in sites]):
        assignment = dict(program.default_assignment())
        assignment.update(dict(zip([s.site_id for s in sites], combination)))
        cost = execute(program.instantiate(assignment), machine).makespan
        best = cost if best is None else min(best, cost)
    result = stateful_oracle(program, machine)
    assert result.status == "proven"
    assert result.makespan == best


def test_corpus_workloads_build_and_are_classified_from_structure():
    corpus = pytest.importorskip("ftqc_delivery.mrc.corpus")
    features = pytest.importorskip("ftqc_delivery.mrc.features")
    pytest.importorskip("qmpa")
    pytest.importorskip("qualtran")
    names = ["qmpa_draper8", "qt_qft6", "qt_add16"]
    roles = {}
    for name in names:
        extraction = corpus.build_workload(name)
        assert extraction.gate_count > 0
        roles[name] = features.classify_role(features.structural_features(extraction.program))
    assert roles["qmpa_draper8"] == "target"
    assert roles["qt_qft6"] == "target"
    assert roles["qt_add16"] == "control"


def test_qasm_front_end_rejects_unmodelled_gates():
    corpus = pytest.importorskip("ftqc_delivery.mrc.corpus")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "bad.qasm"
        path.write_text("OPENQASM 2.0;\nqreg q[2];\nrxx(0.3) q[0],q[1];\n")
        with pytest.raises(ValueError, match="unmodelled gate"):
            corpus.qasm_gate_stream(path)


def test_qasm_angles_are_classified_by_cost():
    corpus = pytest.importorskip("ftqc_delivery.mrc.corpus")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "angles.qasm"
        path.write_text(
            "OPENQASM 2.0;\nqreg q[1];\n"
            "rz(pi) q[0];\nrz(pi/2) q[0];\nrz(pi/4) q[0];\nrz(pi/8) q[0];\nrz(0) q[0];\n"
        )
        names = [gate.name for gate in corpus.qasm_gate_stream(path)]
    assert names == ["Z", "S", "T", "ZPowGate"]


def test_stage_resets_remove_exactly_the_carried_state():
    """With resets each stage restarts empty, so the total can only grow."""

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "marsq"))
    from marsq_ablate import execute_with_stage_resets, myopic_stage_exact

    from ftqc_delivery.mrc.execution import execute as run

    program = extract(
        [
            GateRecord("Toffoli", (0, 1, 2)),
            GateRecord("Toffoli", (0, 1, 2)),
            GateRecord("Toffoli", (2, 3, 4)),
            GateRecord("Toffoli", (2, 3, 4)),
        ],
        name="two_stage",
    ).program
    machine = machine_for_capacity(0.5, 0.5)
    assignment = program.default_assignment()
    carried = run(program.instantiate(assignment), machine).makespan
    reset = execute_with_stage_resets(program, assignment, machine)
    assert reset >= carried

    myopic = myopic_stage_exact(program, machine)
    assert set(myopic) >= {site.site_id for site in decision_sites(program)}
    assert run(program.instantiate(myopic), machine).makespan > 0


def test_executor_reports_a_stall_instead_of_spinning():
    """A machine that can never deliver must fail loudly, not hang."""

    from ftqc_delivery.mrc.resources import Conversion, FactoryBank, Machine

    program = _one_and()
    starved = Machine(
        banks=(FactoryBank(resource="RAW", count=1, period=1, buffer_capacity=1),),
        conversions=(Conversion(source="RAW", target=CCZ, inputs=8, outputs=1, latency=1),),
    )
    with pytest.raises(RuntimeError, match="stalled|exceeded"):
        execute(program.instantiate({**program.default_assignment(), **{
            decision_sites(program)[0].site_id: "ccz"}}), starved)
