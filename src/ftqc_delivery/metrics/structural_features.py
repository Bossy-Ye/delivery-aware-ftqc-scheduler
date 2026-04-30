"""Circuit structural features used for regime analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median

from ftqc_delivery.dag.graph import CircuitDAG
from ftqc_delivery.dag.slack import alap_times, asap_times
from ftqc_delivery.schedulers.common import ready_nodes, split_t_nodes


@dataclass(frozen=True)
class StructuralFeatures:
    """DAG-level structural features relevant to demand shaping."""

    T_count: int
    critical_path_length: int
    T_static_static: int
    slack_ratio: float
    mean_slack: float
    median_slack: float
    p90_slack: float
    max_slack: int
    slack_std: float
    fraction_zero_slack: float
    fraction_slack_ge_1: float
    fraction_slack_ge_2: float
    fraction_slack_ge_5: float
    ready_T_width_peak: int
    ready_T_width_mean: float
    ready_T_width_std: float


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5


def _ready_t_widths(dag: CircuitDAG) -> list[int]:
    topo_order = dag.topological_order()
    scheduled: set[str] = set()
    widths: list[int] = []
    while len(scheduled) < len(dag.nodes):
        ready = ready_nodes(dag, scheduled, topo_order)
        if not ready:
            raise ValueError(f"No ready nodes while computing widths for {dag.name!r}")
        _, t_nodes = split_t_nodes(dag, ready)
        widths.append(len(t_nodes))
        scheduled.update(ready)
    return widths


def structural_features(dag: CircuitDAG) -> StructuralFeatures:
    """Compute static structural features of a workload DAG."""

    asap = asap_times(dag)
    horizon = max(asap.values(), default=0)
    alap = alap_times(dag, horizon=horizon)
    t_nodes = dag.t_nodes()
    slack_values = [max(0, alap[node_id] - asap[node_id]) for node_id in t_nodes]
    t_count = len(t_nodes)
    widths = _ready_t_widths(dag)
    mean_slack = sum(slack_values) / t_count if t_count else 0.0
    return StructuralFeatures(
        T_count=t_count,
        critical_path_length=horizon,
        T_static_static=horizon,
        slack_ratio=sum(1 for value in slack_values if value > 0) / t_count if t_count else 0.0,
        mean_slack=mean_slack,
        median_slack=median(slack_values) if slack_values else 0.0,
        p90_slack=_percentile([float(value) for value in slack_values], 0.9),
        max_slack=max(slack_values, default=0),
        slack_std=_std([float(value) for value in slack_values]),
        fraction_zero_slack=sum(1 for value in slack_values if value == 0) / t_count
        if t_count
        else 0.0,
        fraction_slack_ge_1=sum(1 for value in slack_values if value >= 1) / t_count
        if t_count
        else 0.0,
        fraction_slack_ge_2=sum(1 for value in slack_values if value >= 2) / t_count
        if t_count
        else 0.0,
        fraction_slack_ge_5=sum(1 for value in slack_values if value >= 5) / t_count
        if t_count
        else 0.0,
        ready_T_width_peak=max(widths, default=0),
        ready_T_width_mean=sum(widths) / len(widths) if widths else 0.0,
        ready_T_width_std=_std([float(value) for value in widths]),
    )


def structural_features_dict(dag: CircuitDAG) -> dict[str, float]:
    """Return structural features as a dictionary."""

    return asdict(structural_features(dag))
