"""Delivery-aware scheduling heuristic."""

from __future__ import annotations

from dataclasses import dataclass

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.dag.slack import alap_times, longest_paths_to_sink, normalize_scores

from .common import Schedule, planning_horizon, ready_nodes, split_t_nodes


@dataclass(frozen=True)
class DeliveryAwareWeights:
    """Weights used by the delivery-aware T-gate score."""

    urgency: float = 1.0
    downstream: float = 0.5
    pressure: float = 1.0


def schedule_delivery_aware(
    dag: CircuitDAG,
    capacity: int,
    buffer: int = 0,
    weights: DeliveryAwareWeights = DeliveryAwareWeights(),
) -> Schedule:
    """Schedule with slack, downstream criticality, and delivery pressure.

    `sigma_DA` differs from slack smoothing by making the per-layer T target
    explicitly capacity and buffer aware. It also scores ready T gates using
    current slack, downstream criticality, and the pressure risk of admitting
    another T gate into the current layer.
    """

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if buffer < 0:
        raise ValueError("buffer must be nonnegative")

    horizon = planning_horizon(dag, capacity)
    latest = alap_times(dag, horizon=horizon)
    downstream = normalize_scores(longest_paths_to_sink(dag))
    topo_order = dag.topological_order()
    scheduled: set[str] = set()
    cumulative_t = 0
    schedule: Schedule = {}
    time_step = 1

    while len(scheduled) < len(dag.nodes):
        ready = ready_nodes(dag, scheduled, topo_order)
        if not ready:
            raise ValueError(f"No ready nodes while scheduling {dag.name!r}")

        non_t, t_nodes = split_t_nodes(dag, ready)
        layer = sorted(non_t)

        supply_headroom = max(0, capacity * time_step + buffer - cumulative_t)
        q_extra = min(max(0, buffer // 4), 2, supply_headroom)
        target = capacity + q_extra

        selected_t: list[str] = []

        def score(node_id: str, demand_if_scheduled: int) -> tuple[float, str]:
            slack = latest[node_id] - time_step
            urgency = 1.0 / (1.0 + max(slack, 0))
            pressure_risk = max(0, demand_if_scheduled - target)
            value = (
                weights.urgency * urgency
                + weights.downstream * downstream.get(node_id, 0.0)
                - weights.pressure * pressure_risk
            )
            return (value, node_id)

        mandatory = [node_id for node_id in t_nodes if latest[node_id] <= time_step]
        mandatory = sorted(
            mandatory,
            key=lambda node_id: (
                latest[node_id] - time_step,
                -downstream.get(node_id, 0.0),
                node_id,
            ),
        )
        selected_t.extend(mandatory)

        flexible = [node_id for node_id in t_nodes if node_id not in selected_t]
        while len(selected_t) < target and flexible:
            demand_if = len(selected_t) + 1
            flexible.sort(key=lambda node_id: score(node_id, demand_if), reverse=True)
            selected_t.append(flexible.pop(0))

        if not layer and not selected_t and t_nodes:
            t_nodes.sort(key=lambda node_id: score(node_id, 1), reverse=True)
            selected_t = [t_nodes[0]]

        layer.extend(selected_t)
        schedule[time_step] = layer
        scheduled.update(layer)
        cumulative_t += len(selected_t)
        time_step += 1

    dag.assert_valid_schedule(schedule)
    return schedule
