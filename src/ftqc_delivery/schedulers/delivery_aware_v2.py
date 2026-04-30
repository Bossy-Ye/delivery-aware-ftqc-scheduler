"""Projected-cost delivery-aware scheduling heuristic."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from ftqc_delivery.dag.graph import CircuitDAG, is_t_gate
from ftqc_delivery.dag.slack import alap_times, longest_paths_to_sink, normalize_scores

from .common import Schedule, planning_horizon, ready_nodes, split_t_nodes


@dataclass(frozen=True)
class DeliveryAwareV2Weights:
    """Weights for the projected V2 objective."""

    lambda_exe: float = 2.0
    lambda_delta: float = 1.0
    lambda_backlog: float = 1.0
    lambda_static: float = 0.5
    lambda_critical: float = 0.5


@dataclass(frozen=True)
class DeliveryAwareV2Config:
    """Configuration for `sigma_DA_v2`."""

    lookahead_horizon: int = 5
    weights: DeliveryAwareV2Weights = DeliveryAwareV2Weights()


def generate_candidate_subsets(
    ready_t: list[str],
    latest: dict[str, int],
    downstream: dict[str, float],
    time_step: int,
    capacity: int,
    buffer: int,
) -> list[list[str]]:
    """Generate bounded T-gate candidate subsets for one logical step."""

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if buffer < 0:
        raise ValueError("buffer must be nonnegative")

    ready_t = sorted(ready_t)
    if not ready_t:
        return [[]]

    extra_margin = min(buffer, 2)
    max_size = min(len(ready_t), capacity + extra_margin)
    mandatory = sorted(node_id for node_id in ready_t if latest[node_id] <= time_step)
    max_size = max(max_size, len(mandatory))

    def urgency(node_id: str) -> float:
        slack = latest[node_id] - time_step
        return 1.0 / (1.0 + max(slack, 0))

    urgent_order = sorted(
        ready_t,
        key=lambda node_id: (-urgency(node_id), -downstream.get(node_id, 0.0), node_id),
    )
    downstream_order = sorted(
        ready_t,
        key=lambda node_id: (-downstream.get(node_id, 0.0), -urgency(node_id), node_id),
    )
    mixed_order = sorted(
        ready_t,
        key=lambda node_id: (
            -(urgency(node_id) + downstream.get(node_id, 0.0)),
            node_id,
        ),
    )
    smooth_order = sorted(ready_t, key=lambda node_id: (latest[node_id] - time_step, node_id))

    candidates: dict[tuple[str, ...], list[str]] = {}

    def add(nodes: list[str]) -> None:
        selected = set(mandatory)
        selected.update(nodes)
        ordered = tuple(sorted(selected))
        candidates[ordered] = list(ordered)

    if not mandatory:
        candidates[()] = []

    for size in range(0, max_size + 1):
        add(urgent_order[:size])
        add(downstream_order[:size])
        add(mixed_order[:size])
        add(smooth_order[:size])
        urgent_count = (size + 1) // 2
        mixed_nodes = urgent_order[:urgent_count] + downstream_order[: max(0, size - urgent_count)]
        add(mixed_nodes)

    return sorted(candidates.values(), key=lambda nodes: (len(nodes), nodes))


def schedule_delivery_aware_v2(
    dag: CircuitDAG,
    capacity: int,
    buffer: int = 0,
    config: DeliveryAwareV2Config = DeliveryAwareV2Config(),
) -> Schedule:
    """Schedule with bounded candidate search and projected delivery cost.

    At each logical step, the scheduler evaluates a small set of candidate
    ready-T subsets. Each candidate is scored using a short greedy lookahead
    that estimates extra stalls, Delta_max, backlog duration, deadline pressure,
    and scheduled downstream criticality.
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
        non_t = sorted(non_t)
        candidates = generate_candidate_subsets(
            t_nodes,
            latest,
            downstream,
            time_step,
            capacity,
            buffer,
        )
        candidate_costs = [
            (
                _projected_candidate_cost(
                    dag=dag,
                    scheduled=scheduled,
                    current_non_t=non_t,
                    candidate_t=candidate,
                    topo_order=topo_order,
                    latest=latest,
                    downstream=downstream,
                    time_step=time_step,
                    cumulative_t=cumulative_t,
                    capacity=capacity,
                    buffer=buffer,
                    config=config,
                ),
                candidate,
            )
            for candidate in candidates
        ]
        _, selected_t = min(candidate_costs, key=lambda item: (item[0], len(item[1]), item[1]))

        layer = non_t + selected_t
        if not layer and t_nodes:
            selected_t = max(
                candidates,
                key=lambda nodes: (
                    sum(downstream.get(node_id, 0.0) for node_id in nodes),
                    len(nodes),
                ),
            )
            layer = selected_t if selected_t else [sorted(t_nodes)[0]]

        schedule[time_step] = layer
        scheduled.update(layer)
        cumulative_t += sum(1 for node_id in selected_t if is_t_gate(dag.op_type(node_id)))
        time_step += 1

    dag.assert_valid_schedule(schedule)
    return schedule


def _projected_candidate_cost(
    dag: CircuitDAG,
    scheduled: set[str],
    current_non_t: list[str],
    candidate_t: list[str],
    topo_order: list[str],
    latest: dict[str, int],
    downstream: dict[str, float],
    time_step: int,
    cumulative_t: int,
    capacity: int,
    buffer: int,
    config: DeliveryAwareV2Config,
) -> float:
    projected_scheduled = set(scheduled)
    demand_by_time: dict[int, int] = {}
    static_delay = 0.0
    criticality = sum(downstream.get(node_id, 0.0) for node_id in candidate_t)

    current_layer = current_non_t + list(candidate_t)
    projected_scheduled.update(current_layer)
    demand_by_time[time_step] = len(candidate_t)
    ready_now = ready_nodes(dag, scheduled, topo_order)
    ready_t_now = [node_id for node_id in ready_now if is_t_gate(dag.op_type(node_id))]
    deferred_now = set(ready_t_now) - set(candidate_t)
    static_delay += sum(max(0, time_step - latest[node_id]) for node_id in deferred_now)

    for future_time in range(time_step + 1, time_step + config.lookahead_horizon):
        ready = ready_nodes(dag, projected_scheduled, topo_order)
        if not ready:
            break
        non_t, t_nodes = split_t_nodes(dag, ready)
        future_target = capacity + min(buffer, 1)
        mandatory = [node_id for node_id in t_nodes if latest[node_id] <= future_time]
        flexible = [node_id for node_id in t_nodes if node_id not in mandatory]
        flexible.sort(
            key=lambda node_id: (
                latest[node_id] - future_time,
                -downstream.get(node_id, 0.0),
                node_id,
            )
        )
        selected_t = sorted(mandatory) + flexible[: max(0, future_target - len(mandatory))]
        layer = sorted(non_t) + selected_t
        if not layer and t_nodes:
            selected_t = [flexible[0] if flexible else sorted(t_nodes)[0]]
            layer = selected_t
        projected_scheduled.update(layer)
        demand_by_time[future_time] = len(selected_t)
        deferred = set(t_nodes) - set(selected_t)
        static_delay += sum(max(0, future_time - latest[node_id]) for node_id in deferred)
        criticality += 0.15 * sum(downstream.get(node_id, 0.0) for node_id in selected_t)

    projected_delta = 0
    projected_backlog_length = 0
    projected_extra_stall = 0
    running = cumulative_t
    last_time = time_step + config.lookahead_horizon - 1
    for tau in range(time_step, last_time + 1):
        running += demand_by_time.get(tau, 0)
        surplus = running - capacity * tau
        projected_delta = max(projected_delta, surplus)
        backlog = max(0, running - (capacity * tau + buffer))
        if backlog > 0:
            projected_backlog_length += 1
            projected_extra_stall += ceil(backlog / capacity)

    w = config.weights
    return (
        w.lambda_exe * projected_extra_stall
        + w.lambda_delta * max(0, projected_delta)
        + w.lambda_backlog * projected_backlog_length
        + w.lambda_static * static_delay
        - w.lambda_critical * criticality
    )
