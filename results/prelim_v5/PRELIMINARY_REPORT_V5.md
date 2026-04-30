# Preliminary Report V5

## Summary

V5 audits whether the V4 regime-aware framework is circular or
self-fulfilling. The primary `regime_aware` policy uses outcome-blind labels
assigned only from pre-intervention structural, static-demand, and delivery
features.

## Policy Baselines

- always_smooth: match=0.910, mean=0.182, median=0.000, p95=0.961, nontrivial_mean=0.543, excluding_ties_match=0.000
- always_increase_B: match=0.947, mean=0.052, median=0.000, p95=0.158, nontrivial_mean=0.154, excluding_ties_match=0.000
- always_increase_C: match=1.000, mean=0.000, median=0.000, p95=0.000, nontrivial_mean=0.000, excluding_ties_match=1.000
- random: match=0.843, mean=0.551, median=0.000, p95=1.324, nontrivial_mean=1.649, excluding_ties_match=0.203
- regime_aware: match=0.989, mean=0.004, median=0.000, p95=0.000, nontrivial_mean=0.011, excluding_ties_match=1.000
- oracle: match=1.000, mean=0.000, median=0.000, p95=0.000, nontrivial_mean=0.000, excluding_ties_match=1.000

Best naive policy by mean regret: **always_increase_C** with mean regret
0.000. Outcome-blind regime-aware mean regret
is 0.004; oracle is 0.000.


Important caveat: the best naive baseline is at least as good as outcome-blind regime-aware under the current unpenalized score. In this run that usually means `always_increase_C`, because the score does not charge for extra delivery capacity. The non-circularity claim is therefore supported against shuffled labels and most naive scheduling policies, but the decision-tool claim needs a resource-penalized score or explicit capacity budget.


## Permutation Test

Label permutation trials: 1000.

- p-value by match rate: 0.0010
- p-value by mean regret: 0.0010
- p-value by nontrivial mean regret: 0.0010

## Feature Ablation

Full outcome-blind rules: match=0.989,
mean regret=0.004. Worst ablation:
buffer_only with mean regret
0.806.

## Train/Test Validation

- seed train: match=0.996, mean_regret=0.001, n=1120
- seed test: match=0.991, mean_regret=0.001, n=336
- workload train: match=0.994, mean_regret=0.001, n=1232
- workload test: match=1.000, mean_regret=0.000, n=224
- cb train: match=1.000, mean_regret=0.000, n=416
- cb test: match=0.993, mean_regret=0.001, n=1040

## Outcome-Blind Audit

Forbidden empirical outcome features used by primary labeler:
0.

The primary labeler does not use empirical strategy outcomes such as
candidate_T_exe, strategy_gain, oracle strategy, stall cycles, Delta_max,
BacklogArea, or L_backlog.

## Interpretation

If outcome-blind regime-aware regret is lower than naive policies, the
permutation p-value is small, and train/test performance remains stable, the
framework is not merely a post-hoc relabeling of the empirical best strategy.
If it underperforms the best naive policy, the regime labels may still be useful
descriptively, but the decision-tool claim should be weakened.
