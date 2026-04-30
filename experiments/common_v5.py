"""Shared utilities for V5 non-circularity validation."""

from __future__ import annotations

import csv
import os
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import median
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPLCONFIGDIR = Path("/private/tmp/delivery_aware_ftqc_scheduler_mpl")
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))


RESULT_DIR_V5 = ROOT / "results" / "prelim_v5"
FIGURE_DIR_V5 = ROOT / "figures" / "prelim_v5"
RESULT_DIR_V4 = ROOT / "results" / "prelim_v4"
POLICIES = [
    "always_smooth",
    "always_increase_B",
    "always_increase_C",
    "random",
    "regime_aware",
    "oracle",
]
REGIME_TO_STRATEGY = {
    "no_delivery_bottleneck": "none/static",
    "peak_dominated_smooth_solvable": "smooth",
    "peak_dominated_buffer_limited": "increase_B",
    "persistent_underprovisioning": "increase_C",
    "low_slack_structure_limited": "increase_C",
    "uncertainty_sensitive": "robust_smooth",
}
OUTCOME_BLIND_FEATURES = [
    "C",
    "B",
    "B_over_C",
    "T_count",
    "critical_path_length",
    "slack_ratio",
    "mean_slack",
    "median_slack",
    "p90_slack",
    "fraction_zero_slack",
    "fraction_slack_ge_2",
    "fraction_slack_ge_5",
    "ready_T_width_peak",
    "D_peak",
    "D_mean",
    "D_cv",
    "D_peak_to_mean",
    "num_demand_peaks",
    "mean_demand_over_C",
    "peak_demand_over_C",
    "supply_tightness",
]
FORBIDDEN_OUTCOME_FEATURES = [
    "T_exe",
    "ratio_to_T_ref",
    "stall_cycles",
    "Delta_max",
    "BacklogArea",
    "L_backlog",
    "candidate_T_exe",
    "candidate_BacklogArea",
    "strategy_gain_Texe",
    "strategy_success",
    "empirical_best_strategy",
]


@dataclass(frozen=True)
class RuleParams:
    """Thresholds for outcome-blind regime assignment."""

    peak_threshold: float = 2.0
    persistent_threshold: float = 0.95
    high_slack_threshold: float = 0.5
    low_slack_threshold: float = 0.1
    small_buffer_over_c: float = 4.0
    no_bottleneck_peak_threshold: float = 1.1
    no_bottleneck_supply_threshold: float = 0.55


@dataclass
class Setting:
    """One workload/C/B setting with candidate strategy outcomes."""

    key: tuple[str, str, str, str, str, str]
    workload: str
    family: str
    seed: int
    n: int
    C: int
    B: int
    v4_regime_label: str
    v4_recommended_strategy: str
    features: dict[str, float]
    strategy_scores: dict[str, float]
    strategy_rows: dict[str, dict[str, str]]

    @property
    def nontrivial(self) -> bool:
        static = self.strategy_rows["none/static"]
        _, best_score = self.oracle()
        static_score = self.strategy_scores["none/static"]
        return (
            static_score > best_score + 1e-9
            or float(static["candidate_T_exe"]) > 1.05 * float(static["T_ref_asap"])
            or float(static["candidate_BacklogArea"]) > 0
        )

    def oracle(self) -> tuple[str, float]:
        return min(self.strategy_scores.items(), key=lambda item: (item[1], item[0]))

    def best_strategies(self, eps: float = 1e-9) -> list[str]:
        best = self.oracle()[1]
        return [name for name, score in self.strategy_scores.items() if score <= best + eps]


def ensure_output_dirs() -> None:
    RESULT_DIR_V5.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR_V5.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_output_dirs()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def strategy_score_from_row(row: dict[str, str]) -> float:
    return float(row["candidate_T_exe"]) / float(row["T_ref_asap"]) + 0.01 * float(
        row["candidate_BacklogArea"]
    )


def load_settings() -> list[Setting]:
    exp12 = read_csv(RESULT_DIR_V4 / "exp12_strategy_validation.csv")
    exp11 = read_csv(RESULT_DIR_V4 / "exp11_regime_stability.csv")
    static_features = {
        (row["workload"], row["family"], row["seed"], row["n"], row["C"], row["B"]): row
        for row in exp11
        if row["schedule"] == "static"
    }
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in exp12:
        key = (row["workload"], row["family"], row["seed"], row["n"], row["C"], row["B"])
        grouped[key].append(row)

    settings: list[Setting] = []
    for key, rows in grouped.items():
        feature_row = static_features[key]
        first = rows[0]
        strategy_rows = {row["candidate_strategy"]: row for row in rows}
        strategy_scores = {name: strategy_score_from_row(row) for name, row in strategy_rows.items()}
        c = int(key[4])
        b = int(key[5])
        features = {
            name: float(feature_row[name])
            for name in OUTCOME_BLIND_FEATURES
            if name not in {"B_over_C"}
        }
        features["B_over_C"] = b / c if c else 0.0
        settings.append(
            Setting(
                key=key,
                workload=key[0],
                family=key[1],
                seed=int(key[2]),
                n=int(key[3]),
                C=c,
                B=b,
                v4_regime_label=first["regime_label"],
                v4_recommended_strategy=first["recommended_strategy"],
                features=features,
                strategy_scores=strategy_scores,
                strategy_rows=strategy_rows,
            )
        )
    return settings


def outcome_blind_label(
    features: dict[str, float],
    params: RuleParams = RuleParams(),
    variant: str = "full",
) -> str:
    """Assign a regime using pre-intervention features only."""

    slack = features["slack_ratio"] if variant not in {"no_slack", "supply_only", "peak_only"} else 0.5
    zero = features["fraction_zero_slack"] if variant != "no_slack" else 0.0
    peak = features["peak_demand_over_C"] if variant not in {"no_demand", "supply_only", "slack_only"} else 1.5
    mean = features["mean_demand_over_C"] if variant not in {"no_demand", "peak_only", "slack_only"} else 0.5
    supply = features["supply_tightness"] if variant not in {"no_delivery", "peak_only", "slack_only"} else 0.5
    b_over_c = features["B_over_C"] if variant not in {"no_delivery", "peak_only", "slack_only"} else 4.0

    if variant == "slack_only":
        if slack <= params.low_slack_threshold and zero >= 0.8:
            return "low_slack_structure_limited"
        if slack >= params.high_slack_threshold:
            return "peak_dominated_smooth_solvable"
        return "peak_dominated_buffer_limited"
    if variant == "supply_only":
        if supply >= params.persistent_threshold or mean >= 0.95:
            return "persistent_underprovisioning"
        if supply <= params.no_bottleneck_supply_threshold:
            return "no_delivery_bottleneck"
        return "peak_dominated_buffer_limited"
    if variant == "peak_only":
        if peak <= params.no_bottleneck_peak_threshold:
            return "no_delivery_bottleneck"
        if peak >= params.peak_threshold:
            return "peak_dominated_buffer_limited"
        return "peak_dominated_smooth_solvable"
    if variant == "buffer_only":
        if b_over_c >= 8:
            return "no_delivery_bottleneck"
        if b_over_c <= params.small_buffer_over_c:
            return "peak_dominated_buffer_limited"
        return "peak_dominated_smooth_solvable"

    if supply <= params.no_bottleneck_supply_threshold and peak <= params.no_bottleneck_peak_threshold:
        return "no_delivery_bottleneck"
    if mean >= 1.0 or supply >= params.persistent_threshold:
        return "persistent_underprovisioning"
    if slack <= params.low_slack_threshold and zero >= 0.8 and peak > params.no_bottleneck_peak_threshold:
        return "low_slack_structure_limited"
    if peak >= params.peak_threshold and b_over_c <= params.small_buffer_over_c:
        return "peak_dominated_buffer_limited"
    if slack >= params.high_slack_threshold and peak > params.no_bottleneck_peak_threshold:
        return "peak_dominated_smooth_solvable"
    if peak > params.no_bottleneck_peak_threshold:
        return "peak_dominated_buffer_limited"
    return "no_delivery_bottleneck"


def strategy_for_label(label: str) -> str:
    return REGIME_TO_STRATEGY.get(label, "smooth")


def policy_choice(setting: Setting, policy: str, rng: random.Random | None = None) -> str:
    if policy == "always_smooth":
        return "smooth"
    if policy == "always_increase_B":
        return "increase_B"
    if policy == "always_increase_C":
        return "increase_C"
    if policy == "oracle":
        return setting.oracle()[0]
    if policy == "random":
        if rng is None:
            rng = random.Random(0)
        return rng.choice(sorted(setting.strategy_scores))
    if policy == "regime_aware":
        return strategy_for_label(outcome_blind_label(setting.features))
    raise ValueError(f"Unknown policy {policy}")


def evaluate_policy_choices(
    settings: list[Setting],
    choices: dict[tuple[str, str, str, str, str, str], str],
) -> dict[str, float]:
    regrets: list[float] = []
    matches = 0
    nontrivial_regrets: list[float] = []
    nontrivial_matches = 0
    unique_regrets: list[float] = []
    unique_matches = 0
    for setting in settings:
        choice = choices[setting.key]
        chosen_score = setting.strategy_scores[choice]
        best_strategy, best_score = setting.oracle()
        regret = chosen_score - best_score
        regrets.append(regret)
        best_ties = setting.best_strategies()
        matches += int(choice in best_ties)
        if setting.nontrivial:
            nontrivial_regrets.append(regret)
            nontrivial_matches += int(choice in best_ties)
        if len(best_ties) == 1:
            unique_regrets.append(regret)
            unique_matches += int(choice == best_strategy)
    return summarize_regrets(regrets, matches, nontrivial_regrets, nontrivial_matches, unique_regrets, unique_matches)


def summarize_regrets(
    regrets: list[float],
    matches: int,
    nontrivial_regrets: list[float],
    nontrivial_matches: int,
    unique_regrets: list[float],
    unique_matches: int,
) -> dict[str, float]:
    def p95(values: list[float]) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        index = min(len(values) - 1, int(0.95 * (len(values) - 1)))
        return values[index]

    return {
        "match_rate": matches / len(regrets) if regrets else 0.0,
        "mean_regret": sum(regrets) / len(regrets) if regrets else 0.0,
        "median_regret": median(regrets) if regrets else 0.0,
        "p95_regret": p95(regrets),
        "nontrivial_match_rate": nontrivial_matches / len(nontrivial_regrets)
        if nontrivial_regrets
        else 0.0,
        "nontrivial_mean_regret": sum(nontrivial_regrets) / len(nontrivial_regrets)
        if nontrivial_regrets
        else 0.0,
        "nontrivial_median_regret": median(nontrivial_regrets) if nontrivial_regrets else 0.0,
        "nontrivial_p95_regret": p95(nontrivial_regrets),
        "excluding_ties_match_rate": unique_matches / len(unique_regrets) if unique_regrets else 0.0,
        "excluding_ties_mean_regret": sum(unique_regrets) / len(unique_regrets) if unique_regrets else 0.0,
        "excluding_ties_median_regret": median(unique_regrets) if unique_regrets else 0.0,
        "excluding_ties_p95_regret": p95(unique_regrets),
        "num_cases": len(regrets),
        "num_nontrivial_cases": len(nontrivial_regrets),
        "num_unique_best_cases": len(unique_regrets),
    }


def policy_metrics(settings: list[Setting]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(2026)
    rows: list[dict[str, Any]] = []
    per_case: list[dict[str, Any]] = []
    for policy in POLICIES:
        choices = {setting.key: policy_choice(setting, policy, rng) for setting in settings}
        metrics = evaluate_policy_choices(settings, choices)
        rows.append({"policy": policy, **metrics})
        for setting in settings:
            choice = choices[setting.key]
            best_strategy, best_score = setting.oracle()
            per_case.append(
                {
                    "policy": policy,
                    "workload": setting.workload,
                    "family": setting.family,
                    "seed": setting.seed,
                    "n": setting.n,
                    "C": setting.C,
                    "B": setting.B,
                    "outcome_blind_regime_label": outcome_blind_label(setting.features),
                    "v4_regime_label": setting.v4_regime_label,
                    "chosen_strategy": choice,
                    "oracle_strategy": best_strategy,
                    "match": int(choice in setting.best_strategies()),
                    "unique_best": int(len(setting.best_strategies()) == 1),
                    "nontrivial": int(setting.nontrivial),
                    "chosen_score": setting.strategy_scores[choice],
                    "oracle_score": best_score,
                    "regret": setting.strategy_scores[choice] - best_score,
                }
            )
    return rows, per_case


def permutation_test(settings: list[Setting], trials: int = 1000, seed: int = 2026) -> tuple[list[dict[str, Any]], dict[str, float]]:
    labels = [outcome_blind_label(setting.features) for setting in settings]
    observed_choices = {
        setting.key: strategy_for_label(label) for setting, label in zip(settings, labels, strict=True)
    }
    observed = evaluate_policy_choices(settings, observed_choices)
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for trial in range(trials):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        choices = {
            setting.key: strategy_for_label(label)
            for setting, label in zip(settings, shuffled, strict=True)
        }
        metrics = evaluate_policy_choices(settings, choices)
        rows.append({"trial": trial, **metrics})
    p_match = (1 + sum(1 for row in rows if row["match_rate"] >= observed["match_rate"])) / (trials + 1)
    p_regret = (1 + sum(1 for row in rows if row["mean_regret"] <= observed["mean_regret"])) / (trials + 1)
    p_nontrivial = (
        1
        + sum(
            1
            for row in rows
            if row["nontrivial_mean_regret"] <= observed["nontrivial_mean_regret"]
        )
    ) / (trials + 1)
    summary = {
        "observed_match_rate": observed["match_rate"],
        "observed_mean_regret": observed["mean_regret"],
        "observed_nontrivial_mean_regret": observed["nontrivial_mean_regret"],
        "p_value_match_rate": p_match,
        "p_value_mean_regret": p_regret,
        "p_value_nontrivial_mean_regret": p_nontrivial,
        "num_trials": trials,
    }
    return rows, summary


def feature_ablation_metrics(settings: list[Setting], params: RuleParams = RuleParams()) -> list[dict[str, Any]]:
    variants = [
        "full",
        "no_slack",
        "no_demand",
        "no_delivery",
        "no_backlog",
        "slack_only",
        "supply_only",
        "peak_only",
        "buffer_only",
    ]
    rows = []
    for variant in variants:
        label_variant = "full" if variant == "no_backlog" else variant
        choices = {
            setting.key: strategy_for_label(
                outcome_blind_label(setting.features, params=params, variant=label_variant)
            )
            for setting in settings
        }
        rows.append({"feature_variant": variant, **evaluate_policy_choices(settings, choices)})
    return rows


def grid_params() -> list[RuleParams]:
    return [
        RuleParams(peak, supply, slack, 0.1, b_over_c)
        for peak, supply, slack, b_over_c in product(
            [1.5, 2.0, 2.5, 3.0],
            [0.85, 0.9, 0.95, 1.0],
            [0.3, 0.5, 0.7],
            [2.0, 4.0, 8.0],
        )
    ]


def train_params(train: list[Setting]) -> RuleParams:
    best_params = RuleParams()
    best_score = -10**9
    for params in grid_params():
        choices = {
            setting.key: strategy_for_label(outcome_blind_label(setting.features, params=params))
            for setting in train
        }
        metrics = evaluate_policy_choices(train, choices)
        score = metrics["match_rate"] - metrics["mean_regret"] - 0.5 * metrics["nontrivial_mean_regret"]
        if score > best_score:
            best_score = score
            best_params = params
    return best_params


def split_settings(settings: list[Setting], split_name: str) -> tuple[list[Setting], list[Setting]]:
    if split_name == "seed":
        train = [setting for setting in settings if setting.seed in {0, 2, 4}]
        test = [setting for setting in settings if setting.seed in {1, 3}]
    elif split_name == "workload":
        held_out = {"multiplier_n8", "multiplier_n12", "exact_qft_n8", "approx_qft_n12"}
        train = [setting for setting in settings if setting.workload not in held_out]
        test = [setting for setting in settings if setting.workload in held_out]
    elif split_name == "cb":
        train = [setting for setting in settings if setting.C <= 4 and setting.B <= 8]
        test = [setting for setting in settings if setting.C > 4 or setting.B > 8]
    else:
        raise ValueError(f"Unknown split {split_name}")
    return train, test


def train_test_validation(settings: list[Setting]) -> list[dict[str, Any]]:
    rows = []
    for split_name in ["seed", "workload", "cb"]:
        train, test = split_settings(settings, split_name)
        params = train_params(train)
        for partition, subset in [("train", train), ("test", test)]:
            choices = {
                setting.key: strategy_for_label(outcome_blind_label(setting.features, params=params))
                for setting in subset
            }
            metrics = evaluate_policy_choices(subset, choices) if subset else {}
            rows.append(
                {
                    "split": split_name,
                    "partition": partition,
                    "num_cases": len(subset),
                    "peak_threshold": params.peak_threshold,
                    "persistent_threshold": params.persistent_threshold,
                    "high_slack_threshold": params.high_slack_threshold,
                    "small_buffer_over_c": params.small_buffer_over_c,
                    **metrics,
                }
            )
    return rows


def outcome_blind_audit_rows() -> list[dict[str, Any]]:
    used = set(OUTCOME_BLIND_FEATURES)
    forbidden = set(FORBIDDEN_OUTCOME_FEATURES)
    rows = [
        {"feature": feature, "role": "used_outcome_blind", "allowed": int(feature not in forbidden)}
        for feature in OUTCOME_BLIND_FEATURES
    ]
    rows.extend(
        {"feature": feature, "role": "forbidden_outcome", "allowed": int(feature not in used)}
        for feature in FORBIDDEN_OUTCOME_FEATURES
    )
    return rows
