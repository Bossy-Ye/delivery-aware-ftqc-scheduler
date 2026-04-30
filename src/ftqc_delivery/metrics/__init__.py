"""Schedule metrics for bounded magic-state delivery."""

from .backlog import backlog_active_length, buffer_adjusted_backlog, max_backlog, mean_backlog
from .backlog_shape import backlog_shape_features
from .buffer_threshold import find_buffer_reference_threshold
from .capacity_threshold import find_capacity_threshold, find_reference_capacity_threshold
from .demand_shape import demand_shape_features
from .delta_max import cumulative_demand, delta_max, t_demand_trace
from .makespan import logical_makespan
from .regime_validation import classify_delivery_regime
from .resource_objective import (
    ResourceWeights,
    budget_feasible,
    near_pareto,
    pareto_dominated,
    resource_penalized_score,
)
from .structural_features import structural_features
from .strategy_gain import backlog_area_gain, relative_gain, strategy_score
from .stalls import stall_fraction

__all__ = [
    "t_demand_trace",
    "cumulative_demand",
    "delta_max",
    "buffer_adjusted_backlog",
    "backlog_active_length",
    "max_backlog",
    "mean_backlog",
    "backlog_shape_features",
    "demand_shape_features",
    "structural_features",
    "logical_makespan",
    "stall_fraction",
    "find_capacity_threshold",
    "find_reference_capacity_threshold",
    "find_buffer_reference_threshold",
    "classify_delivery_regime",
    "relative_gain",
    "backlog_area_gain",
    "strategy_score",
    "ResourceWeights",
    "resource_penalized_score",
    "budget_feasible",
    "pareto_dominated",
    "near_pareto",
]
