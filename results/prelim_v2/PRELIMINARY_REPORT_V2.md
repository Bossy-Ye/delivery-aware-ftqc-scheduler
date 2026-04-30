# Preliminary Report V2

## Summary

Recommendation: **stop/redesign**.

This report is intentionally conservative. The main comparison is DA_v2 versus
`sigma_smooth`, not DA_v2 versus `sigma_static`. The arithmetic, QFT, multiplier,
and phase-estimation-like workloads are still semi-real trace-level
approximations, not full circuit extraction.

## Questions

1. Does DA_v2 beat DA_v1?

   T_exe vs DA_v1: better/equal/worse = 70/403/5.

2. Does DA_v2 beat smooth?

   On nontrivial cases, T_exe vs smooth: better/equal/worse =
   1/377/0.

3. Does DA_v2 reduce absolute T_exe?

   Relative to static, T_exe better/equal/worse =
   199/278/1.

4. Does DA_v2 reduce Delta_max?

   Relative to smooth on nontrivial cases, Delta_max better/equal/worse =
   0/373/5.

5. Does DA_v2 reduce backlog duration?

   Relative to smooth on nontrivial cases, L_backlog better/equal/worse =
   0/375/3.

6. Does DA_v2 reduce corrected C_ref_star?

   Against smooth under T_ref_asap, C_ref_star better/equal/worse/missing =
   0/208/0/0.

7. Does DA_v2 work on real workloads?

   On semi-real approximations, T_exe vs smooth better/equal/worse =
   1/177/0.

8. Is smooth already near-optimal under deterministic delivery?

   Small near-optimal comparison: DA_v2 mean gap 0.010, smooth mean gap 0.014.

9. Should Paper 2 continue as a new scheduler paper, schedule trade-off
   framework paper, robustness/stochastic delivery paper, or stop/redesign?

   Current deterministic V2 signal says: **stop/redesign**. This is not a
   new-scheduler-paper signal. If the project continues, it should be reframed
   around schedule trade-offs, robustness, and limits of delivery-aware
   scheduling, with `sigma_smooth` treated as a strong baseline rather than a
   weak foil.
