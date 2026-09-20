# GO/NO-GO: is there enough state-dependent optimisation headroom to justify MARS-Q?

**Decision: NO_GO** for MARS-Q as the next flagship compiler project.

Run under `EXPERIMENT_CONTRACT.md`, frozen at commit `efd5fd3` before any
decisive result existed. 330 cases (22 workloads x 15 machines), 79 with a
proven optimum, plus 24 ablation cases. Raw rows in `RAW_RESULTS.csv`,
`ABLATIONS.csv`, `SCREENING_RESULTS.csv`, structure in
`WORKLOAD_FEATURES.csv`. Baseline commit `345b94fd`, 141 tests passing, is
unchanged and still reproducible.

## The one number that decides it

Against `sim_descent`, a coordinate descent on the simulator that **already
exists in this repository and predates this experiment**, the stateful oracle
gains a mean of **0.13%** and a median of **0.0%** across all 240 target
cases. It gains anything at all in **6 of 330** cases.

Every one of the 8 target cases where the oracle beats the stage-DP by more
than 10% is a case where that existing search finds **exactly the same
assignment as the oracle**. The headroom over the stage-DP is real, and it is
already reachable today, by code that is already written.

A new stateful selector would therefore be competing for a median of zero
against a method we already have.

## The nine questions

**1. Does exploitable oracle headroom exist on independent real wide workloads?**
Yes, but rarely and in a thin tail. Over 240 target cases: median 0.0%, mean
1.7%, p75 2.1%, p90 5.9%, max 20.0%. 63 cases exceed 2%, 26 exceed 5%, 8
exceed 10%, none exceed 20%. The workloads are 16 programs from three
independently authored sources; none was written for this project and none
was hand-edited.

**2. How large is it relative to the current stage-DP?**
Median zero. Three quarters of target cases are at or below 2.1%. This is the
contract's NO-GO condition, "oracle improvement versus stage-DP is at most 2%
almost everywhere", met on its own terms.

**3. Which workload structures produce it?**

| structure | n | median | mean | cases >5% |
|---|---|---|---|---|
| one site per stage | 45 | 1.1% | 1.5% | 1 |
| two or more sites in a stage | 195 | 0.0% | 1.7% | 25 |
| one consuming family | 135 | 0.0% | 2.0% | 20 |
| two consuming families | 75 | 0.0% | 0.9% | 5 |
| three consuming families | 30 | 2.0% | 2.2% | 1 |

The two arms of the hypothesis behave differently. Width produces rare large
gains; temporal heterogeneity (the QFT programs, which mix AND pairs, bare T
gates and synthesised rotations) produces a small but consistent gain, and is
the only structural class with a non-zero median. Neither reaches the gate.

**4. Does it disappear on the frozen negative controls?**
Essentially yes: 90 control cases, median 0.0%, mean 0.1%. Two controls show
anything at all. The largest, a serial AND ladder at 7.0%, is the stage-DP
being weak on a serial chain, not the oracle being strong: the existing search
ties the oracle there exactly. Reported as a gate failure rather than argued
away, because the contract's wording was "near zero" and 7.0% is not.

**5. Does it survive machine and resource parameter changes?**
Only in the constrained, unbalanced corner.

| regime | n | median | max |
|---|---|---|---|
| 400 tiles | 176 | 0.0% | 20.0% |
| 800 tiles | 48 | 0.0% | 4.2% |
| 3200 tiles (abundance control) | 16 | 0.0% | **0.0%** |
| CCZ share 0.25 | 48 | 3.9% | 15.2% |
| CCZ share 0.50 | 144 | 0.0% | 20.0% |
| CCZ share 0.75 | 48 | 0.0% | 10.3% |

The abundance control is exactly zero in all 16 cases, and no case above 5%
survives past 800 tiles. This matches the mechanism prediction, and it also
bounds the opportunity: the effect needs a machine that is both tight and
badly balanced.

**6. Does it survive beyond a single Toffoli resource family?**
Evaluated, not skipped. Rotations were added as a genuine second family:
qualtran's QFT and uniform-superposition preparation contain atomic
z-rotations, classified by exponent so that Clifford phases are free, quarter
turns cost exactly one T state, and only genuine rotations are synthesised,
using the five already-cited variants (Ross-Selinger T synthesis,
Toffoli-count synthesis, phase-gradient addition, the latter two drawn from
either bank). On those 45 cases the residual is median 1.2%, max 7.4%. The
family works and the effect is present, but at a twelfth of the gate.

**7. Is the mechanism actually caused by cross-stage resource state?**
Partly, and less than the hypothesis assumed. On the 24 largest cases:

| explanation | cases | how it was separated |
|---|---|---|
| A, carried inventory | 9 | forcing every stage to start empty removes the advantage |
| B, wide-stage local mixing | 3 | a stage-local exact optimiser captures 80-100% of it |
| mixed or unresolved | 12 | neither test was decisive |
| D, buffer artefact | 0 | halving and doubling the buffer leaves the residual at 8.6% and 7.8% against a baseline of 7.8% |

Explanation C has real force: the effect concentrates at the unbalanced
0.25 split (median 3.9%) and vanishes at 0.5 and 0.75 (median 0.0%).

The decisive observation is about the largest cases, not the average: the
biggest residuals in the whole study, the 20.0% and 18.2% `qmpa_draper`
cases, are **single-stage programs**. Nothing can cross a stage boundary
because there is no second stage. Whatever the stage-DP loses there, it does
not lose by failing to carry state; it loses because its analytic stage cost
misprices a stage of 8 or 16 parallel sites contending for a 2-unit CCZ
distiller bank. On the 18.2% case the stage-DP sends all 8 sites to CCZ and
stalls 25 cycles while 80 raw states overflow; the oracle moves 2 sites to
the T route and wastes nothing. Across the 63 cases with more than 2% gain,
the oracle removes on average 11.7 CCZ stall cycles and 12.0 wasted T states.
The phenomenon is real and is about turning wasted production into progress.
It is not mainly about statefulness.

**8. Is the capability still novel relative to closest 2026 work?**
Unresolved, and the risk grew. Details in `NOVELTY_MATRIX.md`. The capability
is code-verified absent from the one compiler whose source could be read
(arXiv:2506.04620: a single fixed 7-T Toffoli, no CCZ in 64 files, first-fit
binding). Harvest (arXiv:2608.03315) varies the supply protocol, not the
implementation, as far as its abstract shows. FT-Weave (arXiv:2609.20573,
September 2026) is a nearer neighbour than anything in the previous audit: it
is described as reacting to resource-preparation outcomes rather than to
nominal throughput, which is half the capability. arxiv.org and every mirror
are blocked by this environment's network policy, so none of these could be
read in full, and no novelty claim should be made in public until they are.

**9. Final decision.**

**NO_GO.** Not because the phenomenon is fake: it is real, it is traced to a
concrete mechanism, it behaves exactly as predicted on the controls and under
abundance, and it survives coupled provisioning. NO_GO because the
opportunity a new algorithm could capture is a median of zero over the
stage-DP, and what tail exists is already captured by a search that exists in
this repository today. Building a more sophisticated stateful selector would
be building a second way to reach an answer we can already reach.

## Gate table

| Gate | Required | Observed | Pass/Fail |
| ---- | -------: | -------: | --------- |
| Wide-workload oracle gain vs best non-stateful | >=10% median | +0.0% median (mean +2.4%, max +22.8%) | **FAIL** |
| Residual oracle gain vs stage-DP | >=5% median | +0.0% median (mean +1.7%, p90 +5.9%) | **FAIL** |
| Independent workload families | >=3 | 7 families with a case above 5%; 1 with a median above 2% | PASS |
| Independent workload sources | >=2 | 3 (qmpa, qualtran, QASMBench) | PASS |
| Multiple >10% external cases | yes | 8 of 240 target cases | PASS |
| Negative controls near zero | yes | max +7.0% over 90 cases (median 0.0%) | **FAIL** |
| Robust to machine variation | yes | present in models A, B and C; zero under abundance | PASS |
| Second resource family | supported | rotations modelled and measured: median +1.2%, max +7.4% | **FAIL** |
| Novelty survives audit | yes | unresolved; full texts unreadable from this environment | **UNRESOLVED** |

Four of eight quantitative gates pass; both primary gates fail by a wide
margin, and the strong-GO condition requires all seven of its clauses.

## What is worth keeping

The negative result is clean and the machinery is reusable:

* the three-source corpus with an OpenQASM front end that refuses to drop an
  unmodelled gate, and structural role assignment made before any policy runs;
* the rotation family, extracted and classified by angle so that Clifford
  phases stay free;
* the provable lower bound on what any assignment can achieve, which is what
  lets an unproven case still bound its own headroom;
* the ablation harness that separates carried inventory from wide-stage
  mixing from buffer artefacts.

## What would reopen the question

Not a better selector. Only evidence that the opportunity is larger than
measured:

1. A workload class where the existing search fails and the oracle does not.
   The whole study found six such cases, two of them meaningful, and both
   were single-stage programs where a 16-wide stage defeated coordinate
   descent. If wide stages are common in a real algorithm at scale, the
   target is stage-cost modelling for wide stages, not statefulness.
2. A machine model where the abundance control stops being zero.
3. A resource family whose variants differ by much more than the roughly
   2:1 T-equivalent ratio that T and CCZ happen to have here.

## Honest limitations

* 79 of 330 cases reached a proven optimum. Elsewhere the oracle is an
  iterated search, so the measured residual is a **lower bound** on the true
  one. The lower bound on the optimum is loose (it permits a median of 6.3%
  more than the stage-DP achieves), so this study cannot prove that no
  larger opportunity exists on the unproven cases; it can only show that
  neither an exact search, where affordable, nor a 20-second iterated search
  elsewhere, found one.
* The corpus is small programs. The largest is 164 decision sites. Behaviour
  at algorithmic scale is not measured here.
* `qmpa_draper8` and `qmpa_draper16`, which produce the largest single
  numbers, come from an upstream function whose prefix rounds are
  unimplemented. They are used as wide gate streams, not as verified adders,
  and the memo's conclusions do not rest on them.
* Clifford operations are charged one cycle each, identically across
  variants. A machine where Clifford cost is far lower would be more
  supply-bound and could show more headroom; the previous study measured that
  direction and found it grows the effect.
