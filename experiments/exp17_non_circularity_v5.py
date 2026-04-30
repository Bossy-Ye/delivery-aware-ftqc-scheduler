"""V5: non-circularity tests for the regime-aware framework."""

from __future__ import annotations

from common_v5 import (
    FIGURE_DIR_V5,
    RESULT_DIR_V5,
    feature_ablation_metrics,
    load_settings,
    outcome_blind_audit_rows,
    permutation_test,
    policy_metrics,
    read_csv,
    train_test_validation,
    write_csv,
)


POLICY_FIELDNAMES = [
    "policy",
    "match_rate",
    "mean_regret",
    "median_regret",
    "p95_regret",
    "nontrivial_match_rate",
    "nontrivial_mean_regret",
    "nontrivial_median_regret",
    "nontrivial_p95_regret",
    "excluding_ties_match_rate",
    "excluding_ties_mean_regret",
    "excluding_ties_median_regret",
    "excluding_ties_p95_regret",
    "num_cases",
    "num_nontrivial_cases",
    "num_unique_best_cases",
]

PER_CASE_FIELDNAMES = [
    "policy",
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "outcome_blind_regime_label",
    "v4_regime_label",
    "chosen_strategy",
    "oracle_strategy",
    "match",
    "unique_best",
    "nontrivial",
    "chosen_score",
    "oracle_score",
    "regret",
]

PERMUTATION_FIELDNAMES = ["trial"] + POLICY_FIELDNAMES[1:]

PERMUTATION_SUMMARY_FIELDNAMES = [
    "observed_match_rate",
    "observed_mean_regret",
    "observed_nontrivial_mean_regret",
    "p_value_match_rate",
    "p_value_mean_regret",
    "p_value_nontrivial_mean_regret",
    "num_trials",
]

ABLATION_FIELDNAMES = ["feature_variant"] + POLICY_FIELDNAMES[1:]

TRAIN_TEST_FIELDNAMES = [
    "split",
    "partition",
    "num_cases",
    "peak_threshold",
    "persistent_threshold",
    "high_slack_threshold",
    "small_buffer_over_c",
] + POLICY_FIELDNAMES[1:]

AUDIT_FIELDNAMES = ["feature", "role", "allowed"]


def main() -> None:
    settings = load_settings()
    policy_rows, per_case_rows = policy_metrics(settings)
    write_csv(RESULT_DIR_V5 / "exp17_policy_baseline_comparison.csv", policy_rows, POLICY_FIELDNAMES)
    write_csv(RESULT_DIR_V5 / "exp17_policy_per_case.csv", per_case_rows, PER_CASE_FIELDNAMES)

    permutation_rows, permutation_summary = permutation_test(settings, trials=1000)
    write_csv(
        RESULT_DIR_V5 / "exp18_label_permutation_trials.csv",
        permutation_rows,
        PERMUTATION_FIELDNAMES,
    )
    write_csv(
        RESULT_DIR_V5 / "exp18_label_permutation_summary.csv",
        [permutation_summary],
        PERMUTATION_SUMMARY_FIELDNAMES,
    )

    ablation_rows = feature_ablation_metrics(settings)
    write_csv(RESULT_DIR_V5 / "exp19_feature_ablation.csv", ablation_rows, ABLATION_FIELDNAMES)

    train_test_rows = train_test_validation(settings)
    write_csv(RESULT_DIR_V5 / "exp20_train_test_validation.csv", train_test_rows, TRAIN_TEST_FIELDNAMES)

    audit_rows = outcome_blind_audit_rows()
    write_csv(RESULT_DIR_V5 / "exp21_outcome_blind_feature_audit.csv", audit_rows, AUDIT_FIELDNAMES)

    _write_audit_markdown(audit_rows)
    _generate_figures()
    _write_report()
    print(f"Wrote V5 outputs to {RESULT_DIR_V5}")


def _write_audit_markdown(audit_rows: list[dict[str, object]]) -> None:
    bad = [row for row in audit_rows if int(row["allowed"]) == 0 and row["role"] == "used_outcome_blind"]
    text = [
        "# Outcome-Blind Regime Assignment Audit",
        "",
        "Primary V5 regime-aware labels are assigned from pre-intervention features only.",
        "The used feature list excludes empirical strategy outcomes such as T_exe, stall cycles, BacklogArea, strategy gains, and oracle/best-strategy labels.",
        "",
        f"Forbidden outcome features used by primary labeler: {len(bad)}",
    ]
    if bad:
        text.extend(f"- {row['feature']}" for row in bad)
    (RESULT_DIR_V5 / "exp21_outcome_blind_feature_audit.md").write_text("\n".join(text) + "\n")


def _generate_figures() -> None:
    import matplotlib.pyplot as plt

    policy_rows = read_csv(RESULT_DIR_V5 / "exp17_policy_baseline_comparison.csv")
    permutation = read_csv(RESULT_DIR_V5 / "exp18_label_permutation_trials.csv")
    ablation = read_csv(RESULT_DIR_V5 / "exp19_feature_ablation.csv")
    train_test = read_csv(RESULT_DIR_V5 / "exp20_train_test_validation.csv")

    fig, ax = plt.subplots(figsize=(9, 4.8))
    policies = [row["policy"] for row in policy_rows]
    ax.bar(policies, [float(row["mean_regret"]) for row in policy_rows], color="#4c78a8")
    ax.set_ylabel("mean regret")
    ax.set_title("Policy baseline comparison")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V5 / "fig1_policy_mean_regret.pdf")
    plt.close(fig)

    observed = next(row for row in policy_rows if row["policy"] == "regime_aware")
    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.hist([float(row["mean_regret"]) for row in permutation], bins=40, color="#bab0ab")
    ax.axvline(float(observed["mean_regret"]), color="#e45756", label="observed")
    ax.set_xlabel("shuffled-label mean regret")
    ax.set_ylabel("count")
    ax.set_title("Label permutation test")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V5 / "fig2_label_permutation_mean_regret.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    variants = [row["feature_variant"] for row in ablation]
    ax.bar(variants, [float(row["mean_regret"]) for row in ablation], color="#f58518")
    ax.set_ylabel("mean regret")
    ax.set_title("Feature ablation")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V5 / "fig3_feature_ablation_mean_regret.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    labels = [f"{row['split']}-{row['partition']}" for row in train_test]
    ax.bar(labels, [float(row["mean_regret"]) for row in train_test], color="#54a24b")
    ax.set_ylabel("mean regret")
    ax.set_title("Train/test validation")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR_V5 / "fig4_train_test_mean_regret.pdf")
    plt.close(fig)


def _write_report() -> None:
    policy_rows = read_csv(RESULT_DIR_V5 / "exp17_policy_baseline_comparison.csv")
    permutation = read_csv(RESULT_DIR_V5 / "exp18_label_permutation_summary.csv")[0]
    ablation = read_csv(RESULT_DIR_V5 / "exp19_feature_ablation.csv")
    train_test = read_csv(RESULT_DIR_V5 / "exp20_train_test_validation.csv")
    audit = read_csv(RESULT_DIR_V5 / "exp21_outcome_blind_feature_audit.csv")

    by_policy = {row["policy"]: row for row in policy_rows}
    regime = by_policy["regime_aware"]
    oracle = by_policy["oracle"]
    best_naive = min(
        [row for row in policy_rows if row["policy"] not in {"regime_aware", "oracle"}],
        key=lambda row: float(row["mean_regret"]),
    )
    naive_caveat = ""
    if float(best_naive["mean_regret"]) <= float(regime["mean_regret"]):
        naive_caveat = (
            "\n\nImportant caveat: the best naive baseline is at least as good as "
            "outcome-blind regime-aware under the current unpenalized score. In "
            "this run that usually means `always_increase_C`, because the score "
            "does not charge for extra delivery capacity. The non-circularity "
            "claim is therefore supported against shuffled labels and most "
            "naive scheduling policies, but the decision-tool claim needs a "
            "resource-penalized score or explicit capacity budget.\n"
        )
    full_ablation = next(row for row in ablation if row["feature_variant"] == "full")
    worst_ablation = max(ablation, key=lambda row: float(row["mean_regret"]))
    forbidden_used = [
        row
        for row in audit
        if row["role"] == "used_outcome_blind" and int(row["allowed"]) == 0
    ]

    train_lines = "\n".join(
        f"- {row['split']} {row['partition']}: match={float(row['match_rate']):.3f}, "
        f"mean_regret={float(row['mean_regret']):.3f}, n={row['num_cases']}"
        for row in train_test
    )
    policy_lines = "\n".join(
        f"- {row['policy']}: match={float(row['match_rate']):.3f}, "
        f"mean={float(row['mean_regret']):.3f}, median={float(row['median_regret']):.3f}, "
        f"p95={float(row['p95_regret']):.3f}, nontrivial_mean={float(row['nontrivial_mean_regret']):.3f}, "
        f"excluding_ties_match={float(row['excluding_ties_match_rate']):.3f}"
        for row in policy_rows
    )

    report = f"""# Preliminary Report V5

## Summary

V5 audits whether the V4 regime-aware framework is circular or
self-fulfilling. The primary `regime_aware` policy uses outcome-blind labels
assigned only from pre-intervention structural, static-demand, and delivery
features.

## Policy Baselines

{policy_lines}

Best naive policy by mean regret: **{best_naive['policy']}** with mean regret
{float(best_naive['mean_regret']):.3f}. Outcome-blind regime-aware mean regret
is {float(regime['mean_regret']):.3f}; oracle is {float(oracle['mean_regret']):.3f}.
{naive_caveat}

## Permutation Test

Label permutation trials: {permutation['num_trials']}.

- p-value by match rate: {float(permutation['p_value_match_rate']):.4f}
- p-value by mean regret: {float(permutation['p_value_mean_regret']):.4f}
- p-value by nontrivial mean regret: {float(permutation['p_value_nontrivial_mean_regret']):.4f}

## Feature Ablation

Full outcome-blind rules: match={float(full_ablation['match_rate']):.3f},
mean regret={float(full_ablation['mean_regret']):.3f}. Worst ablation:
{worst_ablation['feature_variant']} with mean regret
{float(worst_ablation['mean_regret']):.3f}.

## Train/Test Validation

{train_lines}

## Outcome-Blind Audit

Forbidden empirical outcome features used by primary labeler:
{len(forbidden_used)}.

The primary labeler does not use empirical strategy outcomes such as
candidate_T_exe, strategy_gain, oracle strategy, stall cycles, Delta_max,
BacklogArea, or L_backlog.

## Interpretation

If outcome-blind regime-aware regret is lower than naive policies, the
permutation p-value is small, and train/test performance remains stable, the
framework is not merely a post-hoc relabeling of the empirical best strategy.
If it underperforms the best naive policy, the regime labels may still be useful
descriptively, but the decision-tool claim should be weakened.
"""
    (RESULT_DIR_V5 / "PRELIMINARY_REPORT_V5.md").write_text(report)


if __name__ == "__main__":
    main()
