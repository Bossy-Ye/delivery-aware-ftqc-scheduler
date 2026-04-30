"""Tests for V5 non-circularity helpers."""

from __future__ import annotations

import sys
from pathlib import Path

EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from common_v5 import (
    FORBIDDEN_OUTCOME_FEATURES,
    OUTCOME_BLIND_FEATURES,
    RuleParams,
    outcome_blind_label,
    strategy_for_label,
)


def test_outcome_blind_feature_list_excludes_forbidden_outcomes() -> None:
    assert not (set(OUTCOME_BLIND_FEATURES) & set(FORBIDDEN_OUTCOME_FEATURES))


def test_outcome_blind_label_maps_persistent_case_to_capacity() -> None:
    features = {
        "slack_ratio": 0.8,
        "fraction_zero_slack": 0.1,
        "peak_demand_over_C": 3.0,
        "mean_demand_over_C": 1.1,
        "supply_tightness": 1.05,
        "B_over_C": 0.0,
    }
    label = outcome_blind_label(features, RuleParams())

    assert label == "persistent_underprovisioning"
    assert strategy_for_label(label) == "increase_C"
