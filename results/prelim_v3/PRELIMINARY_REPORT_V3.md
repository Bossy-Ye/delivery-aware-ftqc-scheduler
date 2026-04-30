# Preliminary Report V3

## Summary

Recommendation: **regime-aware framework paper**.

V3 does not attempt to make DA look better. It asks whether smooth is near
optimal, when it fails, and whether stochastic or effective-capacity uncertainty
creates a real Paper 2 opening.

## Questions

1. Is smooth near-optimal in deterministic small instances?

   Smooth mean gap to the near-optimal reference is 0.333
   cycles, max gap is 3.000 cycles, and the fraction within
   one cycle is 0.917.

2. What is the average and worst gap between smooth and optimal?

   Mean gap: 0.333. Worst gap: 3.000.

3. Where does smooth fail?

- larger_multiplier_n16 seed=0 C=3 B=0: smooth_stalls;Delta_max_gt_B;positive_L_backlog;positive_BacklogArea;misses_1.05_T_ref score=139.916
- larger_multiplier_n16 seed=0 C=3 B=8: smooth_stalls;Delta_max_gt_B;positive_L_backlog;positive_BacklogArea;misses_1.05_T_ref score=105.491
- larger_multiplier_n16 seed=0 C=2 B=0: smooth_stalls;Delta_max_gt_B;positive_L_backlog;positive_BacklogArea;misses_1.05_T_ref score=69.152
- larger_multiplier_n16 seed=0 C=2 B=8: smooth_stalls;Delta_max_gt_B;positive_L_backlog;positive_BacklogArea;misses_1.05_T_ref score=45.104
- multiplier_n12 seed=0 C=2 B=0: smooth_stalls;Delta_max_gt_B;positive_L_backlog;positive_BacklogArea;misses_1.05_T_ref score=42.850

4. Are failures peak-dominated or persistence-dominated?

   See `exp7_smooth_failure_cases.csv` and Figure 3. The regime counts below
   summarize whether failures are bottleneck-free, peak/buffer limited,
   persistent, low-slack, or uncertainty-sensitive.

5. Does stochastic supply break smooth?

   For p_acc <= 0.95, average smooth p95(T_exe/T_ref) is
   1.187; robust_smooth is 1.375.

6. Does effective capacity degradation break smooth?

   For eta <= 0.75, average smooth degradation is 0.526;
   robust_smooth is 0.393.

7. Does robust_smooth help?

   For p_acc <= 0.95, smooth 5% target violation probability averages
   0.497; robust_smooth averages 0.667.
   Robust_smooth helps only if these tail metrics decrease without large
   deterministic penalties.

8. What regimes can be identified?

- no_delivery_bottleneck: 276
- peak_dominated_buffer_limited: 33
- peak_dominated_smooth_solvable: 141
- persistent_underprovisioning: 24
- uncertainty_sensitive: 4

9. What is the recommended next direction?

   **regime-aware framework paper**. If smooth is near-optimal and robust, stop or merge the
   insight into Paper 1. If uncertainty breaks smooth and robust_smooth helps,
   pivot to robust demand shaping. If failures cluster structurally, pivot to a
   regime-aware compiler-architecture framework.
