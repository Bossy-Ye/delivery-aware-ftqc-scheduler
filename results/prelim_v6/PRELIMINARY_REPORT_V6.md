# Preliminary Report V6

## Summary

Recommendation: **resource-aware framework useful, but not dominant**.

V6 fixes the V5 caveat by charging for extra delivery capacity and buffer.

## Questions

1. Does always_increase_C dominate only when capacity is free?

   With zero resource penalties, always_increase_C mean regret is
   0.0000. Under lambda_A=0.01,
   lambda_C=0.05, lambda_B=0.01, always_increase_C mean regret becomes
   0.0002. This means the V5 caveat is reduced but
   not eliminated at the default resource prices: capacity expansion is still
   near-oracle for this workload/parameter set. At a stronger capacity penalty
   (lambda_C=0.20, lambda_B=0.01), regime-aware mean regret is
   0.0027 versus always_increase_C
   0.0040.

2. Under positive capacity and buffer penalties, does regime_aware keep lower
   regret than naive policies?

   Regime-aware mean regret is 0.0045;
   always_smooth is 0.0420;
   always_increase_C is 0.0002. Regime-aware clearly
   improves over always_smooth and capacity-aware style fixed policies, but it
   does not beat always_increase_C under the default cost setting.

3. How sensitive are conclusions to lambda_C, lambda_B, and lambda_A?

   See `exp22_resource_penalty_sweep_summary.csv` and Figures 1-2. The
   lambda_C=0 slice intentionally reproduces the V5 caveat.

4. Under budget constraints, does regime_aware remain close to budget oracle?

   At C_budget=1, B_budget=8, regime-aware mean regret is
   0.0058 with infeasibility rate
   0.0549.

5. Does regime-aware selection choose Pareto-optimal or near-Pareto strategies?

   Regime-aware Pareto optimal rate is
   0.998; near-Pareto rate is
   1.000. Always-increase-C Pareto
   optimal rate is 0.998.

6. Does the result still hold on nontrivial cases only?

   Regime-aware nontrivial mean regret is
   0.0132; always_smooth nontrivial mean
   regret is 0.1240; always-increase-C
   nontrivial mean regret is 0.0004.

7. What scoring settings should be used in the paper?

   Use lambda_A=0.01, lambda_C=0.05, lambda_B=0.01 as a transparent default,
   but do not claim it fully resolves the capacity-free caveat. The paper
   should show the full lambda_C/lambda_B sensitivity, and capacity-free scores
   should be shown only as a caveat/reproduction of V5.

8. Is Paper 2 ready to write as a regime-aware, resource-aware framework paper?

   Current answer: **resource-aware framework useful, but not dominant**. If always_increase_C remains best under
   positive capacity penalties, the framework should be presented as diagnostic
   rather than prescriptive.
