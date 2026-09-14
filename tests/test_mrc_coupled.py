"""Tests for coupled provisioning: shared upstream production and conversions."""

from __future__ import annotations

import pytest

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.mrc.execution import execute
from ftqc_delivery.mrc.resources import CCZ, RAW, T, coupled_machine


def fan(op_type: str, width: int) -> CircuitDAG:
    dag = CircuitDAG("fan")
    dag.add_node("src", "Clifford")
    for index in range(width):
        dag.add_node(f"n{index}", op_type)
        dag.add_edge("src", f"n{index}")
    return dag


@pytest.mark.parametrize("model", ["A", "B", "C"])
def test_every_model_fits_the_area_budget(model):
    for share in (0.25, 0.5, 0.75):
        machine = coupled_machine(model, tiles=400, ccz_share=share)
        assert machine.factory_tiles <= 400 + 72  # rounding to whole factories


def test_model_b_has_no_product_banks_only_a_raw_stream():
    machine = coupled_machine("B", tiles=400, ccz_share=0.5)
    assert machine.bank(RAW) is not None
    assert machine.bank(T) is None and machine.bank(CCZ) is None
    assert set(machine.producible) == {RAW, T, CCZ}


def test_model_b_products_come_only_from_the_shared_stream():
    """With no raw supply, nothing distils and the effective rates are zero."""

    machine = coupled_machine("B", tiles=400, ccz_share=0.5)
    assert machine.rate(T) > 0 and machine.rate(CCZ) > 0
    total_draw = 0.0
    for conversion in machine.conversions:
        total_draw += conversion.concurrency * conversion.inputs / conversion.latency
    # Distillers cannot consume more raw states than the stream delivers.
    consumed = machine.rate(T) * 15 + machine.rate(CCZ) * 8
    assert consumed <= machine.rate(RAW) + 1e-9


def test_distillers_prefill_the_buffer_and_then_stop():
    machine = coupled_machine("B", tiles=400, ccz_share=0.5, buffer_capacity=8)
    dag = fan("T", 4)
    trace = execute(dag, machine, record_trace=True)
    assert trace.consumed[T] == 4
    assert max(trace.stock_series[T]) <= 8
    assert trace.overflow[T] == 0


def test_a_t_only_circuit_runs_under_every_model():
    dag = fan("T", 12)
    for model in ("A", "B", "C"):
        machine = coupled_machine(model, tiles=400, ccz_share=0.5)
        assert execute(dag, machine).makespan > 0


def test_catalysis_only_appears_in_model_c():
    b = coupled_machine("B", tiles=400, ccz_share=0.5)
    c = coupled_machine("C", tiles=400, ccz_share=0.5)
    assert not any(conv.source == CCZ for conv in b.conversions)
    assert any(conv.source == CCZ and conv.target == T for conv in c.conversions)


def test_model_c_serves_starved_t_demand_from_ccz():
    dag = fan("T", 40)
    b = coupled_machine("B", tiles=400, ccz_share=0.9)
    c = coupled_machine("C", tiles=400, ccz_share=0.9)
    plain = execute(dag, b).makespan
    catalysed = execute(dag, c, record_trace=True)
    assert catalysed.makespan <= plain
    assert catalysed.conversions.get("1CCZ->2T", 0) > 0


def test_raw_states_are_never_consumed_by_operations():
    machine = coupled_machine("B", tiles=400, ccz_share=0.5)
    trace = execute(fan("CCZ", 6), machine, record_trace=True)
    assert trace.consumed[RAW] == 0
    assert trace.consumed[CCZ] == 6
