"""Strategy gain and score helpers for V4 validation."""

from __future__ import annotations


def relative_gain(baseline: float, candidate: float) -> float:
    """Return `(baseline-candidate)/baseline`, guarding zero baselines."""

    if baseline == 0:
        return 0.0
    return (baseline - candidate) / baseline


def backlog_area_gain(baseline_area: float, candidate_area: float) -> float:
    """Return backlog-area gain with max(1, baseline) normalization."""

    return (baseline_area - candidate_area) / max(1.0, baseline_area)


def strategy_score(
    ratio_to_t_ref: float,
    backlog_area: float,
    backlog_weight: float = 0.01,
    resource_penalty: float = 0.0,
) -> float:
    """Score a candidate strategy for strategy-match analysis."""

    return ratio_to_t_ref + backlog_weight * backlog_area + resource_penalty
