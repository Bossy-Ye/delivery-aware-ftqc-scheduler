# Mechanism: why the transformation helps, and why it is not temporal smoothing

The commutation-aware transformation does reduce FT makespan, substantially
on several programs. This note establishes what causes that, against the four
explanations fixed in the contract. Raw rows: `RAW_RESULTS.csv` (2464 runs),
`MECHANISM_ABLATIONS.csv`.

## H3, work reduction: excluded by construction and by measurement

Both transformations keep the gate list untouched, so the T-count and the
CCZ-count cannot move. Measured: **0 of 2464 runs** differ from their baseline
in T-count or CCZ-count. T-count change is exactly 0%, not merely under the
2% bar.

## H4, model artefact: excluded

The gain is unchanged across buffer capacities, which is the parameter most
likely to manufacture a queueing effect:

| workload | buffer 16 | buffer 32 | buffer 64 |
|---|---:|---:|---:|
| qt_qft6 | +68.9% | +68.9% | +68.9% |
| qt_aliassamp16 | +32.6% | +35.2% | +35.4% |
| qmpa_div6 | +5.2% | +5.2% | +5.2% |
| qb_multiplier_n15 | 0.0% | 0.0% | 0.0% |
| qt_multiand10 (control) | 0.0% | 0.0% | 0.0% |

It is also unchanged across factory area and split: the frozen grid varies
tiles over 200, 400, 800 and 3200 and the CCZ share over 0.25, 0.5 and 0.75,
and the median gain moves only between +8.7% and +10.8%.

## H2, depth reduction: confirmed

| evidence | value |
|---|---|
| correlation(makespan improvement, depth reduction), 256 target runs | **0.795** |
| correlation(makespan improvement, baseline stall fraction) | 0.392 |
| median improvement on cases above 10% | +30.5% |
| median depth reduction on the same cases | +38.7% |

Per workload the two track each other closely: `qt_add16` +7.7% gain against
+8.0% depth reduction, `qt_modadd8` +9.0% against +9.2%, `qt_qrom16x5` +11.3%
against +11.7%, `qmpa_mul6` +1.6% against +1.8%. Every negative control is
0.0% on both.

The regime breakdown is the decisive part. If the mechanism were magic-state
smoothing, the gain would grow as supply tightened and vanish when supply was
free. It does the opposite:

| regime | median improvement | median depth reduction |
|---|---:|---:|
| constrained | +8.7% | +11.7% |
| moderate | +10.8% | +11.7% |
| abundant | **+10.8%** | +11.7% |

The gain is *smallest* where supply is tightest, because there the freed
parallelism runs into the factories instead. Under abundant supply the
makespan simply follows the shortened dependency chain.

## H1, temporal smoothing: not supported

On the cases with at least 10% improvement:

| quantity | median |
|---|---:|
| cycles saved | 29.0 |
| stall cycles present in the baseline | 6.0 |
| change in stall cycles | **−7.0**, i.e. stalls went up |
| share of the saving that stall reduction could account for | **−0.167** |
| burstiness before → after | 0.333 → **0.787** |

There were never 29 cycles of stalling available to remove. The transformation
makes demand *burstier*, not smoother, and stalls slightly worse; the makespan
falls anyway because the chain is shorter.

The pacing transformation was built to test H1 in isolation: it increases
depth and holds work constant, so any win could only be temporal. Across the
whole matrix it never wins. `conventional_pace4` is exactly 0.0% everywhere,
since conventional lowering had already imposed at least that much order.
Applied to the commuting graph, every pacing width scores *below* the
commuting graph it was applied to (median +8.3% at k=2 and +8.7% at k=8
against +8.7% for no pacing at all), and k=1 is negative (mean −7.2%). Pacing
only claws back part of what it gives away.

## Why these programs are not supply bound in the first place

Across the whole matrix the median ratio of makespan to critical-path depth is
**1.042** under constrained supply, 1.021 under moderate and abundant. Median
stall time is 7 cycles out of makespans in the hundreds. Only 74 of 264
constrained baseline runs are even marginally supply bound. There is very
little magic-state waiting to reshape.

## Is that an artefact of charging one cycle per Clifford?

This was the obvious way the negative result could have been unfair, so it was
tested directly, outside the frozen grid and reported as a limitation rather
than as evidence. With Clifford operations made free, the same programs do
become genuinely supply bound, and in that regime the transformations do
*less*, not more:

| workload | Clifford cost | baseline | stalls | bound by | commuting gain | best pacing gain |
|---|---:|---:|---:|---|---:|---:|
| qt_aliassamp16 | 1 | 347 | 6 | depth | +35.2% | −7.1% |
| qt_aliassamp16 | 0 | 105 | 81 | **supply** | **0.0%** | 0.0% |
| qb_multiplier_n15 | 0 | 54 | 49 | **supply** | 0.0% | 0.0% |
| qmpa_div6 | 0 | 54 | 37 | **supply** | 0.0% | 0.0% |
| qt_multiand10 | 0 | 32 | 14 | **supply** | 0.0% | 0.0% |
| qt_qft6 | 0 | 286 | 12 | depth | +31.5% | 0.0% |

Exactly in the regime the hypothesis is about, reshaping temporal demand buys
nothing at all.

## The reason, stated generally

When a program is supply bound its makespan is set by total demand divided by
production rate. That quantity does not depend on *when* the demand arrives,
so rearranging demand in time cannot beat it. Demand shape can only matter
through waste: production discarded because a buffer was full. But a buffer
fills during *idle* periods, not during bursts, so spreading demand out
increases waste rather than reducing it. That is why pacing loses, and it is
why the whole class of smoothing transformations has little to work with in
this model.

Smoothing would pay only where bursts destroy capacity rather than merely
queue behind it, for example where a factory must be reconfigured, where
states expire, or where a burst forces a spatial reallocation. None of those
are in this machine model, and adding them would be modelling a machine to fit
the hypothesis rather than testing it.
