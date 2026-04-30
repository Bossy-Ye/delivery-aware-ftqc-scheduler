"""Semi-real arithmetic workload approximations.

These generators intentionally create trace-level DAG approximations rather
than claiming full circuit extraction. They are sufficient for preliminary
go/no-go tests of delivery-aware demand shaping.
"""

from __future__ import annotations

from ftqc_delivery.dag.generators import add_burst, add_linear_chain
from ftqc_delivery.dag.graph import CircuitDAG


def make_adder(n: int = 8, seed: int = 0) -> CircuitDAG:
    """Return a ripple-carry adder approximation with low T flexibility."""

    del seed
    dag = CircuitDAG(name=f"adder_n{n}")
    previous = "adder_src"
    dag.add_node(previous, "Other")
    for bit in range(n):
        for phase in range(4):
            op_type = "T" if phase in {1, 2} else "Clifford"
            node_id = f"adder_b{bit:03d}_p{phase}"
            dag.add_node(node_id, op_type)
            dag.add_edge(previous, node_id)
            previous = node_id
    dag.add_node("adder_sink", "Other")
    dag.add_edge(previous, "adder_sink")
    return dag


def make_multiplier(n: int = 4, seed: int = 0) -> CircuitDAG:
    """Return a schoolbook-multiplier approximation with bursty partial products."""

    del seed
    dag = CircuitDAG(name=f"multiplier_n{n}")
    dag.add_node("mul_src", "Other")
    spine_length = max(20, 5 * n)
    spine = add_linear_chain(
        dag,
        f"mul_n{n}_accum_tcritical",
        spine_length,
        start="mul_src",
        op_type="Clifford",
        t_every=8,
    )
    for row in range(n):
        anchor = min(row * 3, len(spine) - 2)
        release = "mul_src" if anchor == 0 else spine[anchor]
        deadline = spine[min(anchor + max(6, n // 2 + 4), len(spine) - 1)]
        add_burst(dag, f"mul_n{n}_partial_row{row}", n, release, deadline)
    dag.add_node("mul_sink", "Other")
    dag.add_edge(spine[-1], "mul_sink")
    return dag


def make_modular_arithmetic_block(n: int = 8, repeats: int = 3, seed: int = 0) -> CircuitDAG:
    """Return a synthetic modular-arithmetic block with repeated carry pressure."""

    del seed
    dag = CircuitDAG(name=f"modular_arithmetic_block_n{n}_r{repeats}")
    dag.add_node("mod_src", "Other")
    previous = "mod_src"
    for repeat in range(repeats):
        spine = add_linear_chain(
            dag,
            f"mod_r{repeat}_carry_spine",
            max(14, 3 * n),
            start=previous,
            op_type="Clifford",
            t_every=7,
        )
        for block in range(max(2, n // 2)):
            release = spine[min(block * 2, len(spine) - 2)]
            deadline = spine[min(block * 2 + max(5, n // 2), len(spine) - 1)]
            add_burst(dag, f"mod_r{repeat}_block{block}", max(3, n // 2), release, deadline)
        previous = spine[-1]
    dag.add_node("mod_sink", "Other")
    dag.add_edge(previous, "mod_sink")
    return dag
