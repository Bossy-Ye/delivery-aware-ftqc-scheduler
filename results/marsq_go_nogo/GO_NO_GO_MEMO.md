# GO/NO-GO: is there enough state-dependent optimisation headroom to justify MARS-Q?

**Decision: NO_GO** for MARS-Q as the next flagship compiler project.

Run under `EXPERIMENT_CONTRACT.md`, frozen at commit `efd5fd3` before any
decisive result existed. 330 cases (22 workloads x 15 machines), 79 with a
proven optimum, plus 40 screening cases and 24 ablation cases. Raw rows in
`RAW_RESULTS.csv`, `ABLATIONS.csv`, `SCREENING_RESULTS.csv`; structure in
`WORKLOAD_FEATURES.csv`.

## A simulator bug was found and fixed before these numbers were taken

While checking that the repository's published results still reproduced, every
re-run came out exactly one cycle longer than the stored value. The cause was
mine, from the previous sprint: the executor's stall guard reused
`last_finish`, the variable that defines the makespan, as a last-progress
timestamp, and assigned it at node completion rather than at dispatch. Every
makespan from that commit onward was one cycle too long.

The guard now keeps its own clock (commit `9bd9bba`). 30 stored cases from
`results/mrc_pilot/mrc1_cases.csv` re-run across six policies now reproduce
180 of 180 values exactly, where before every one differed. The entire study
below was re-run on the fixed simulator; the numbers from the buggy run were
discarded rather than reported. The error had been conservative, inflating
both sides of every ratio, and correcting it did not change any gate outcome.

## The one number that decides it

Against `sim_descent`, a coordinate descent on the simulator that **already
exists in this repository and predates this experiment**, the stateful oracle
gains a mean of **0.14%** and a median of **0.0%** across all 240 target
cases. It gains anything at all in **6 of 330** cases.

Every one of the 8 target cases where the oracle beats the stage-DP by more
than 10% is a case where that existing search finds **exactly the same
assignment as the oracle**. The headroom over the stage-DP is real, and it is
already reachable today by code that is already written.

A new stateful selector would be competing for a median of zero against a
method we already have.

## The nine questions

**1. Does exploitable oracle headroom exist on independent real wide workloads?**
Yes, but rarely and in a thin tail. Over 240 target cases: median 0.0%, mean
1.7%, p75 2.1%, p90 6.0%, max 20.4%. 63 cases exceed 2%, 26 exceed 5%, 8
exceed 10%, 1 exceeds 20%. The workloads are 16 programs from three
independently authored sources; none was written for this project and none was
hand-edited.

**2. How large is it relative to the current stage-DP?**
Median zero. Three quarters of target cases are at or below 2.1%. This is the
contract's NO-GO condition, "oracle improvement versus stage-DP is at most 2%
almost everywhere", met on its own terms.

**3. Which workload structures produce it?**

| structure | n | median | mean | cases >5% |
|---|---|---|---|---|
| one site per stage | 45 | 1.1% | 1.5% | 1 |
| two or more sites in a stage | 195 | 0.0% | 1.8% | 25 |
| one consuming family | 135 | 0.0% | 2.1% | 20 |
| two consuming families | 75 | 0.0% | 0.9% | 5 |
| three consuming families | 30 | 2.0% | 2.2% | 1 |

The two arms of the hypothesis behave differently. Width produces rare large
gains; temporal heterogeneity (the QFT programs, which mix AND pairs, bare T
gates and synthesised rotations) produces a small but consistent gain and is
the only structural class with a non-zero median. Neither reaches the gate.

By family, the effect is concentrated: parallel adders (mean 3.9%, five cases
above 10%), state preparation (mean 1.8%) and multipliers (mean 1.5%) carry
it; phase estimation is exactly zero across all 15 cases.

**4. Does it disappear on the frozen negative controls?**
Essentially yes: 90 control cases, median 0.0%, mean 0.1%. Only two control
programs move at all, and only at the most unbalanced split. The largest, a
serial AND ladder at 7.1%, is the stage-DP being weak on a serial chain, not
the oracle being strong: the existing search ties the oracle there exactly.
Reported as a gate failure rather than argued away, because the contract said
"near zero" and 7.1% is not.

**5. Does it survive machine and resource parameter changes?**
Only in the constrained, unbalanced corner.

| regime | n | median | max | cases >5% |
|---|---|---|---|---|
| 400 tiles | 176 | 0.0% | 20.4% | 26 |
| 800 tiles | 48 | 0.0% | 4.2% | 0 |
| 3200 tiles (abundance control) | 16 | 0.0% | **0.0%** | 0 |
| CCZ share 0.25 | 48 | 3.9% | 15.6% | 15 |
| CCZ share 0.50 | 144 | 0.0% | 20.4% | 8 |
| CCZ share 0.75 | 48 | 0.0% | 10.7% | 3 |

The abundance control is exactly zero in all 16 cases, and no case above 5%
survives past 800 tiles. This matches the mechanism prediction, and it also
bounds the opportunity: the effect needs a machine that is both tight and
badly balanced.

**6. Does it survive beyond a single Toffoli resource family?**
Evaluated, not skipped. Rotations were added as a genuine second family:
qualtran's QFT and uniform-superposition preparation contain atomic
z-rotations, classified by exponent so that Clifford phases stay free, a
quarter turn costs exactly one T state, and only genuine rotations are
synthesised, using the five already-cited variants (Ross-Selinger T
synthesis, Toffoli-count synthesis, phase-gradient addition, the latter two
drawn from either bank). On those 45 cases the residual is median 1.2%, max
7.4%. The family works and the effect is present, at a quarter of the gate.

**7. Is the mechanism actually caused by cross-stage resource state?**
Partly, and less than the hypothesis assumed. On the 24 largest cases:

| explanation | cases | how it was separated |
|---|---|---|
| A, carried inventory | 9 | forcing every stage to start empty removes the advantage |
| B, wide-stage local mixing | 3 | a stage-local exact optimiser captures 80-100% of it |
| mixed or unresolved | 12 | neither test was decisive |
| D, buffer artefact | 0 | halving and doubling the buffer leaves the residual at 8.6% and 7.8% against a baseline of 7.8% |

Explanation C has real force: the effect concentrates at the unbalanced 0.25
split (median 3.9%) and vanishes at 0.5 and 0.75 (median 0.0%).

The decisive observation is about the largest cases, not the average. The
biggest residuals in the study, the 20.4% and 18.8% `qmpa_draper` cases, are
**single-stage programs**. Nothing can cross a stage boundary because there
is no second stage. Whatever the stage-DP loses there, it does not lose by
failing to carry state; it loses because its analytic stage cost misprices a
stage of 8 or 16 parallel sites contending for a 2-unit CCZ distiller bank.
On the 18.8% case the stage-DP sends all 8 sites to CCZ and stalls 25 cycles
while 80 raw states overflow; the oracle moves 2 sites to the T route and
wastes nothing. Across the 63 cases with more than 2% gain, the oracle
removes on average 11.7 CCZ stall cycles and 12.0 wasted T states. The
phenomenon is real and is about turning wasted production into progress. It
is not mainly about statefulness.

**8. Is the capability still novel relative to closest 2026 work?**
Unresolved, and the risk grew. Details in `NOVELTY_MATRIX.md`. The capability
is code-verified absent from the one compiler whose source could be read
(arXiv:2506.04620: a single fixed 7-T Toffoli, no CCZ in 64 files, first-fit
binding). Harvest (arXiv:2608.03315) varies the supply protocol, not the
implementation, as far as its abstract shows. FT-Weave (arXiv:2609.20573,
September 2026) is a nearer neighbour than anything in the previous audit: it
is described as reacting to resource-preparation outcomes rather than to
nominal throughput, which is half the capability. arxiv.org and every mirror
are blocked by this environment's network policy, so none could be read in
full, and no novelty claim should be made in public until they are.

**9. Final decision.**

**NO_GO.** Not because the phenomenon is fake: it is real, traced to a
concrete mechanism, behaves exactly as predicted on the controls and under
abundance, and survives coupled provisioning. NO_GO because the opportunity a
new algorithm could capture is a median of zero over the stage-DP, and what
tail exists is already captured by a search that exists in this repository
today. Building a more sophisticated stateful selector would be building a
second way to reach an answer we can already reach.

## Gate table

| Gate | Required | Observed | Pass/Fail |
| ---- | -------: | -------: | --------- |
| Wide-workload oracle gain vs best non-stateful | >=10% median | +0.0% median (mean +2.4%, max +23.2%) | **FAIL** |
| Residual oracle gain vs stage-DP | >=5% median | +0.0% median (mean +1.7%, p90 +6.0%) | **FAIL** |
| Independent workload families | >=3 | 7 families with a case above 5%; 1 with a median above 2% | PASS |
| Independent workload sources | >=2 | 3 (qmpa, qualtran, QASMBench) | PASS |
| Multiple >10% external cases | yes | 8 of 240 target cases | PASS |
| Negative controls near zero | yes | max +7.1% over 90 cases (median 0.0%) | **FAIL** |
| Robust to machine variation | yes | present in models A, B and C; exactly zero under abundance | PASS |
| Second resource family | supported | rotations modelled and measured: median +1.2%, max +7.4% | **FAIL** |
| Novelty survives audit | yes | unresolved; full texts unreadable from this environment | **UNRESOLVED** |

Four of eight quantitative gates pass; both primary gates fail by a wide
margin, and the strong-GO condition requires all seven of its clauses.

## Cost, for completeness

The oracle costs a median of 21.1 seconds per case against the stage-DP's
0.22 seconds, roughly ninety times more, to deliver a median of zero.

## What is worth keeping

The negative result is clean and the machinery is reusable:

* the three-source corpus with an OpenQASM front end that refuses to drop an
  unmodelled gate, and structural role assignment made before any policy runs;
* the rotation family, extracted and classified by angle so Clifford phases
  stay free;
* the provable lower bound on what any assignment can achieve, which lets an
  unproven case still bound its own headroom;
* the ablation harness that separates carried inventory from wide-stage
  mixing from buffer artefacts;
* the reproduction check against stored results, which is what caught the
  makespan bug.

## What would reopen the question

Not a better selector. Only evidence that the opportunity is larger than
measured:

1. A workload class where the existing search fails and the oracle does not.
   This study found six such cases, two of them meaningful, and both were
   single-stage programs where a 16-wide stage defeated coordinate descent.
   If wide stages are common in real algorithms at scale, the target is
   stage-cost modelling for wide stages, not statefulness.
2. A machine model where the abundance control stops being zero.
3. A resource family whose variants differ by much more than the roughly 2:1
   T-equivalent ratio that T and CCZ happen to have here.

## Honest limitations

* 79 of 330 cases reached a proven optimum. Elsewhere the oracle is an
  iterated search, so the measured residual is a **lower bound** on the true
  one. The lower bound on the optimum is loose, permitting a median of 5.9%
  more than the stage-DP achieves, so this study cannot prove that no larger
  opportunity exists on the unproven cases. It shows only that neither an
  exact search, where affordable, nor a 20-second iterated search elsewhere,
  found one.
* The corpus is small programs; the largest has 164 decision sites. Behaviour
  at algorithmic scale is not measured here.
* `qmpa_draper8` and `qmpa_draper16`, which produce the largest single
  numbers, come from an upstream function whose prefix rounds are
  unimplemented. They are used as wide gate streams, not as verified adders,
  and no conclusion here rests on them.
* Clifford operations are charged one cycle each, identically across
  variants. A machine with much cheaper Cliffords would be more supply-bound;
  the previous study measured that direction and found it grows the effect.
