"""Constructed DAG families for demand-shaping smoke tests."""

from __future__ import annotations

import random

from ftqc_delivery.dag.generators import add_burst, add_linear_chain, add_sink_join
from ftqc_delivery.dag.graph import CircuitDAG


def make_high_compressibility(seed: int = 0, n: int = 24) -> CircuitDAG:
    """Return a bursty DAG with many flexible T gates and a long critical spine."""

    rng = random.Random(seed)
    dag = CircuitDAG(name=f"constructed_high_seed{seed}_n{n}")
    dag.add_node("high_src", "Other")
    chain_length = 3 * n + rng.randint(0, max(1, n // 3))
    spine = add_linear_chain(
        dag,
        "high_spine_tcritical",
        chain_length,
        start="high_src",
        op_type="Clifford",
        t_every=7,
    )
    sink = "high_sink"
    add_sink_join(dag, sink, [spine[-1]])
    burst_size = 2 * n + rng.randint(0, max(1, n // 2))
    add_burst(dag, "high_flex_t", burst_size, "high_src", sink)
    return dag


def make_medium_compressibility(seed: int = 0, n: int = 24) -> CircuitDAG:
    """Return staged bursts with moderate local slack windows."""

    rng = random.Random(seed)
    dag = CircuitDAG(name=f"constructed_medium_seed{seed}_n{n}")
    dag.add_node("med_src", "Other")
    chain_length = 3 * n
    spine = add_linear_chain(
        dag,
        "med_spine_tcritical",
        chain_length,
        start="med_src",
        op_type="Clifford",
        t_every=9,
    )
    stages = 6
    window = max(5, n // 3)
    burst_base = max(3, n // 4)
    for stage in range(stages):
        anchor = min(stage * max(2, n // stages), len(spine) - 2)
        release = "med_src" if anchor == 0 else spine[anchor]
        deadline_index = min(anchor + window + rng.randint(0, 2), len(spine) - 1)
        deadline = spine[deadline_index]
        count = burst_base + rng.randint(0, 2)
        add_burst(dag, f"med_flex_t_s{stage}", count, release, deadline)
    return dag


def make_low_compressibility(seed: int = 0, n: int = 24) -> CircuitDAG:
    """Return a negative-control DAG where T gates lie on the critical path."""

    rng = random.Random(seed)
    dag = CircuitDAG(name=f"constructed_low_seed{seed}_n{n}")
    previous = "low_src"
    dag.add_node(previous, "Other")
    total = 2 * n + rng.randint(0, max(1, n // 4))
    for index in range(total):
        clifford = f"low_c_{index:04d}"
        t_gate = f"low_tcritical_{index:04d}"
        dag.add_node(clifford, "Clifford")
        dag.add_node(t_gate, "T" if index % 2 == 0 else "Tdg")
        dag.add_edge(previous, clifford)
        dag.add_edge(clifford, t_gate)
        previous = t_gate
    dag.add_node("low_sink", "Other")
    dag.add_edge(previous, "low_sink")
    return dag
