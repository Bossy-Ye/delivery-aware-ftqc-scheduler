# Screening results: is there enough oracle opportunity to justify the full matrix?

Run before the full matrix, under the frozen contract. Five wide or
heterogeneous targets and three controls on five machines: 40 cases, of which
7 reached a proven optimum. Raw rows: `SCREENING_RESULTS.csv`.

## Gate

The contract stops the study here if every credible wide workload shows at
most 2% residual headroom over the stage-DP and the lower bound proves no more
is available. That did not happen: 7 of 25 target cases exceed 2%. The full
matrix was therefore warranted, and was run.

## What the screen measured

| subset | n | proven | residual vs stage-DP (median / mean / p90 / max) | vs best non-stateful (median / max) |
|---|---|---|---|---|
| targets | 25 | 5 | 0.000 / 0.018 / 0.042 / 0.182 | 0.010 / 0.182 |
| controls | 15 | 2 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 |

Every case with a measured advantage:

| workload | machine | stage-DP | oracle | status | residual | vs non-stateful |
|---|---|---|---|---|---|---|
| qmpa_draper8 | C_400_0.5 | 33 | 27 | proven | +18.2% | +18.2% |
| qt_qft6 | A_400_0.5 | 481 | 459 | bounded | +4.6% | +6.1% |
| qt_qft6 | C_800_0.5 | 452 | 433 | bounded | +4.2% | +3.4% |
| qmpa_draper8 | B_400_0.5 | 28 | 27 | proven | +3.6% | 0.0% |
| qmpa_draper16 | C_800_0.5 | 29 | 28 | bounded | +3.5% | +12.5% |
| qt_aliassamp8 | B_400_0.5 | 143 | 140 | bounded | +2.1% | +11.9% |
| qt_aliassamp8 | C_400_0.5 | 143 | 140 | bounded | +2.1% | +11.9% |
| qt_aliassamp8 | A_400_0.5 | 138 | 136 | bounded | +1.5% | +2.2% |
| qt_qft6 | B_400_0.5 | 492 | 486 | bounded | +1.2% | +1.2% |
| qt_qft6 | C_400_0.5 | 492 | 486 | bounded | +1.2% | +1.2% |
| qb_multiplier_n15 | B_400_0.5 | 96 | 95 | bounded | +1.0% | +1.0% |
| qb_multiplier_n15 | C_400_0.5 | 96 | 95 | bounded | +1.0% | +1.0% |

## Three observations recorded before the full matrix

1. **The controls are exactly zero.** All 15 control cases show 0.000 residual
   and 0.000 against the best non-stateful policy, on every machine. A
   mechanism that improved serial chains too would have been evidence that
   something was wrong with the measurement.

2. **The largest case cannot be explained by carried state.** The single
   >10% case, `qmpa_draper8` at 18.2%, is a program with exactly one stage.
   Nothing crosses a stage boundary because there is no second stage, so
   whatever the stage-DP loses there, it does not lose it by failing to carry
   resource state. The plausible explanation is that its analytic stage cost
   misprices a wide stage of eight parallel sites. The ablations test this
   directly.

3. **The bound is too loose to prove a negative on most cases.** Across the
   target cases the lower bound allows a median of 13.9% more than the
   stage-DP achieves, so only 2 of 25 cases are provably within 2% of
   optimal. Where the oracle is `bounded` rather than `proven`, the measured
   residual is a lower bound on the true one; the study must say so rather
   than treat a small measured residual as proof of no opportunity.
