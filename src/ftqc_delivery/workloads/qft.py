"""Semi-real QFT workload approximations."""

from __future__ import annotations

from ftqc_delivery.dag.generators import add_burst, add_linear_chain
from ftqc_delivery.dag.graph import CircuitDAG


def make_exact_qft(n: int = 8, seed: int = 0) -> CircuitDAG:
    """Return an exact-QFT-style approximation with diagonal rotation bursts."""

    del seed
    dag = CircuitDAG(name=f"exact_qft_n{n}")
    dag.add_node("qft_src", "Other")
    spine = add_linear_chain(
        dag,
        f"qft_n{n}_phase_tcritical",
        max(18, 3 * n),
        start="qft_src",
        op_type="Clifford",
        t_every=10,
    )
    for distance in range(1, n):
        release_index = min(2 * distance - 1, len(spine) - 2)
        deadline_index = min(release_index + max(4, n // 2), len(spine) - 1)
        count = n - distance
        add_burst(
            dag,
            f"qft_n{n}_rot_d{distance}",
            count,
            "qft_src" if release_index == 0 else spine[release_index],
            spine[deadline_index],
            op_type="T" if distance % 2 else "Tdg",
        )
    dag.add_node("qft_sink", "Other")
    dag.add_edge(spine[-1], "qft_sink")
    return dag


def make_approx_qft(n: int = 12, seed: int = 0, max_distance: int = 4) -> CircuitDAG:
    """Return an approximate-QFT-style workload with truncated rotation distances."""

    del seed
    dag = CircuitDAG(name=f"approx_qft_n{n}")
    dag.add_node("aqft_src", "Other")
    spine = add_linear_chain(
        dag,
        f"aqft_n{n}_phase_tcritical",
        max(20, 3 * n),
        start="aqft_src",
        op_type="Clifford",
        t_every=11,
    )
    for distance in range(1, min(n, max_distance + 1)):
        release_index = min(2 * distance - 1, len(spine) - 2)
        deadline_index = min(release_index + max(5, n // 2), len(spine) - 1)
        add_burst(
            dag,
            f"aqft_n{n}_rot_d{distance}",
            n - distance,
            "aqft_src" if release_index == 0 else spine[release_index],
            spine[deadline_index],
            op_type="T" if distance % 2 else "Tdg",
        )
    dag.add_node("aqft_sink", "Other")
    dag.add_edge(spine[-1], "aqft_sink")
    return dag


def make_phase_estimation_like(n: int = 10, seed: int = 0) -> CircuitDAG:
    """Return a phase-estimation-like approximation with repeated QFT bursts."""

    del seed
    dag = CircuitDAG(name=f"phase_estimation_like_n{n}")
    dag.add_node("pe_src", "Other")
    spine = add_linear_chain(
        dag,
        f"pe_n{n}_control_spine",
        max(30, 4 * n),
        start="pe_src",
        op_type="Clifford",
        t_every=13,
    )
    rounds = max(3, n // 2)
    for round_id in range(rounds):
        release_index = min(round_id * 4, len(spine) - 2)
        deadline_index = min(release_index + max(8, n), len(spine) - 1)
        count = max(4, n - round_id // 2)
        add_burst(
            dag,
            f"pe_n{n}_phase_round{round_id}",
            count,
            "pe_src" if release_index == 0 else spine[release_index],
            spine[deadline_index],
            op_type="T" if round_id % 2 == 0 else "Tdg",
        )
    dag.add_node("pe_sink", "Other")
    dag.add_edge(spine[-1], "pe_sink")
    return dag


def make_hamiltonian_simulation_synthetic(n: int = 10, layers: int = 4, seed: int = 0) -> CircuitDAG:
    """Return a synthetic Trotterized Pauli-evolution-style workload."""

    del seed
    dag = CircuitDAG(name=f"hamiltonian_simulation_synthetic_n{n}_l{layers}")
    dag.add_node("ham_src", "Other")
    previous = "ham_src"
    for layer in range(layers):
        spine = add_linear_chain(
            dag,
            f"ham_l{layer}_basis_spine",
            max(12, 2 * n),
            start=previous,
            op_type="Clifford",
            t_every=9,
        )
        for term in range(max(3, n // 2)):
            release = spine[min(term * 2, len(spine) - 2)]
            deadline = spine[min(term * 2 + max(4, n // 3), len(spine) - 1)]
            add_burst(
                dag,
                f"ham_l{layer}_pauli_term{term}",
                max(2, n // 3),
                release,
                deadline,
                op_type="T" if term % 2 == 0 else "Tdg",
            )
        previous = spine[-1]
    dag.add_node("ham_sink", "Other")
    dag.add_edge(previous, "ham_sink")
    return dag
