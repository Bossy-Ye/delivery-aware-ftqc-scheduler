# Preliminary Report V4

## Summary

Recommendation: **green light: regime-aware framework paper**.

V4 validates the regime-aware compiler-architecture framing. It does not claim
a new scheduler contribution.

## Questions

1. Are V3 regimes stable under larger sweeps?

   Regime counts over smooth rows in the expanded sweep:

- no_delivery_bottleneck: 970
- peak_dominated_buffer_limited: 57
- peak_dominated_smooth_solvable: 377
- persistent_underprovisioning: 52

2. Which workloads fall into which regimes?

   See `exp11_regime_distribution_summary.csv` and Figure 1. The distribution
   remains multi-regime rather than collapsing to a single scheduler story.

3. Does each regime have a distinct best response?

   Empirical strategy match rate is 0.985 with mean regret
   0.009. Match treats exact score ties as success, because many
   no-bottleneck cases genuinely require no distinct intervention.

4. Does increasing buffer help buffer-limited cases more than changing scheduler?

   In buffer-limited rows, mean T_exe gain for increase_B is
   0.178; mean
   BacklogArea gain is 1.000.

5. Does increasing capacity help persistent-underprovisioning cases more than smoothing?

   In persistent-underprovisioning rows, mean T_exe gain for increase_C is
   0.460; mean
   BacklogArea gain is 1.000.

6. Do larger / more realistic workloads preserve the same regimes?

   Expanded workload smooth-regime counts:

- no_delivery_bottleneck: 53
- peak_dominated_buffer_limited: 17
- peak_dominated_smooth_solvable: 28
- persistent_underprovisioning: 42

7. Do Qiskit/tket-optimized circuits still show delivery-pressure regimes?

   Transpiler sanity regime counts:

- no_delivery_bottleneck: 16

   If Qiskit is unavailable, the script marks rows as proxy synthetic sanity
   checks instead of claiming real transpiler evidence.

8. Are representative case-study plots visually consistent with regime labels?

   See `case1_smooth_solvable.pdf`, `case2_buffer_limited.pdf`,
   `case3_persistent_underprovisioning.pdf`, and
   `case4_effective_capacity_sensitive.pdf`.

9. What is the empirical strategy match rate?

   Strategy match rate is 0.985; mean regret is 0.009.

10. Is Paper 2 viable as a regime-aware framework paper?

   Current V4 answer: **green light: regime-aware framework paper**. The strongest framing is that
   bounded magic-state delivery creates distinct execution regimes with
   different appropriate responses: no action, smoothing, buffer, capacity, or
   robustness/provisioning margin.
