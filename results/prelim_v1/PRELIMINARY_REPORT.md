# Preliminary Report

## Summary

Recommendation: **continue**.

This report is generated from deterministic preliminary scans only. The
arithmetic and QFT workloads are semi-real trace-level approximations, not full
circuit extraction.

## Questions

1. Does `sigma_DA` reduce `Delta_max`?

   Yes in 242 of 460 deterministic schedule scans relative
   to `sigma_static`.

2. Does it reduce actual `T_exe`?

   Yes in 184 of 460 scans relative to `sigma_static`.

3. Does it reduce stall cycles?

   Stall reductions track executable-makespan reductions in 184 of
   460 scans.

4. Does it outperform `sigma_smooth` or `sigma_ca`?

   It improves `T_exe` over `sigma_smooth` in 5 of
   460 scans and over `sigma_ca` in 252 of 460
   scans.

5. Does it reduce required capacity `C_star`?

   `sigma_DA` has a lower finite `C_star` in 76 of
   546 direct baseline comparisons.

6. Does it work on real workloads, not only constructed DAGs?

   On the semi-real workload approximations, it reduces `T_exe` relative to
   `sigma_static` in 50 of 160 scans.

7. Should Paper 2 continue, stop, or redesign?

   Current deterministic signal says: **continue**. If this is not a
   clear continue, the next step is to refine `sigma_DA` and replace the
   semi-real workload approximations with actual extracted circuits before
   scaling stochastic or architecture-proxy experiments.
