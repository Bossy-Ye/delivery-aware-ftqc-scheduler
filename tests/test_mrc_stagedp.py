"""Tests for the stage-wise dynamic-programming selector."""

from __future__ import annotations

from ftqc_delivery.mrc.execution import execute
from ftqc_delivery.mrc.kernels import modular_exponentiation, oracle_bank, trotter_layers
from ftqc_delivery.mrc.policies import best_oracle, select_uniform_oracle
from ftqc_delivery.mrc.resources import machine_for_capacity
from ftqc_delivery.mrc.stagedp import pipeline_stages, select_stage_dp


def test_pipeline_stages_recover_the_staged_structure():
    program = modular_exponentiation(width=16, steps=2)
    stages = pipeline_stages(program)
    assert len(stages) == 4
    assert all(sum(len(group) for group in stage) == 1 for stage in stages)
    wide = oracle_bank(controls=8, lanes=4)
    assert len(pipeline_stages(wide)) == 1


def test_initial_stock_is_honoured_by_the_executor():
    program = trotter_layers(terms=1, layers=1, bits=6)
    machine = machine_for_capacity(0.5, 0.5)
    assignment = program.default_assignment()
    dag = program.instantiate(assignment)
    cold = execute(dag, machine).makespan
    warm = execute(dag, machine.with_initial_stock({"T": 32, "CCZ": 32})).makespan
    assert warm <= cold


def test_stage_dp_returns_a_complete_assignment_in_every_mode():
    program = modular_exponentiation(width=16, steps=2)
    machine = machine_for_capacity(0.5, 0.5)
    for mode, refine in (("analytic", 0), ("sim", 0), ("analytic", 4)):
        outcome = select_stage_dp(program, machine, mode=mode, refine=refine)
        assert set(outcome.assignment) == {site.site_id for site in program.sites}
        assert outcome.makespan > 0


def test_stage_dp_is_never_worse_than_uniform_on_a_serial_kernel():
    """On the kernel where alternation pays, the DP must find it."""

    program = modular_exponentiation(width=16, steps=2)
    machine = machine_for_capacity(0.5, 0.5)
    uniform = select_uniform_oracle(program, machine).makespan
    dp = select_stage_dp(program, machine, mode="sim").makespan
    optimum = best_oracle(program, machine).makespan
    assert dp <= uniform
    assert dp <= 1.05 * optimum
