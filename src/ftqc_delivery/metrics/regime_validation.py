"""Rule-based regime classification for bounded-delivery schedules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeDecision:
    """A regime label plus recommended response."""

    regime_label: str
    regime_reason: str
    recommended_strategy: str


def classify_delivery_regime(
    *,
    static_stall_cycles: int,
    static_delta_max: float,
    static_backlog_area: float,
    smooth_stall_cycles: int,
    smooth_delta_max: float,
    smooth_backlog_area: float,
    smooth_l_backlog: float,
    buffer: int,
    slack_ratio: float,
    fraction_zero_slack: float,
    supply_tightness: float,
    peak_demand_over_c: float,
    mean_demand_over_c: float,
    smooth_t_exe: float,
    static_t_exe: float,
    uncertainty_sensitive: bool = False,
) -> RegimeDecision:
    """Classify a bounded-delivery setting using V3/V4 rule heuristics."""

    if uncertainty_sensitive:
        return RegimeDecision(
            "uncertainty_sensitive",
            "deterministic schedule is fragile under stochastic or effective-capacity loss",
            "robust_scheduling",
        )
    if static_stall_cycles == 0 and static_delta_max <= buffer and static_backlog_area == 0:
        return RegimeDecision(
            "no_delivery_bottleneck",
            "static execution already meets delivery constraints",
            "none",
        )
    if (
        static_delta_max > buffer
        and smooth_stall_cycles == 0
        and smooth_backlog_area == 0
        and slack_ratio >= 0.5
    ):
        return RegimeDecision(
            "peak_dominated_smooth_solvable",
            "slack smoothing removes burst-induced backlog",
            "smooth",
        )
    if mean_demand_over_c >= 1.0 or (supply_tightness >= 0.95 and smooth_l_backlog > 0):
        return RegimeDecision(
            "persistent_underprovisioning",
            "average T demand is too close to available delivery supply",
            "increase_capacity",
        )
    smooth_gain = (static_t_exe - smooth_t_exe) / static_t_exe if static_t_exe else 0.0
    if slack_ratio <= 0.1 and fraction_zero_slack >= 0.8 and static_stall_cycles > 0 and smooth_gain < 0.05:
        return RegimeDecision(
            "low_slack_structure_limited",
            "circuit structure leaves too little slack for demand reshaping",
            "architecture_provisioning",
        )
    if peak_demand_over_c >= 2.0 and smooth_delta_max < static_delta_max and smooth_l_backlog > 0:
        return RegimeDecision(
            "peak_dominated_buffer_limited",
            "smoothing reduces peaks but available buffer remains too small",
            "increase_buffer",
        )
    if smooth_l_backlog > 0 or smooth_delta_max > buffer:
        return RegimeDecision(
            "peak_dominated_buffer_limited",
            "residual backlog remains after smoothing",
            "increase_buffer",
        )
    return RegimeDecision(
        "peak_dominated_smooth_solvable",
        "smooth is sufficient in this setting",
        "smooth",
    )
