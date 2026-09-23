# GO/NO-GO: can a semantics-preserving transformation reshape temporal magic-state demand?

**Decision: NO_GO** for the temporal-demand-reshaping compiler direction.

Run under `EXPERIMENT_CONTRACT.md`, frozen at commit `885743d` before any
decisive result existed. 2464 matrix runs (22 workloads x 7 transformations x
8 machines x 2 implementation assignments), 84 screening runs, 45 ablation
runs. Baseline commit `7b75206`, 153 tests passing; 161 now, all additive.

## The short version

Two semantics-preserving transformations were built and verified. One of them
produces large makespan reductions, up to 87% and a median of 11% on the
programs that have any freedom at all. It fails the hypothesis anyway, for two
independent reasons:

1. **The mechanism is depth reduction, not demand smoothing.** The gain
   correlates 0.795 with depth reduction and only 0.392 with baseline stall
   fraction, and it is *larger* under abundant magic-state supply (+10.8%
   median) than under constrained supply (+8.7%). Stalls go up, not down.
2. **The transformation is standard practice.** It is commutation-aware
   dependency analysis, which Qiskit ships as `DAGDependency` and
   `CommutationAnalysis`.

The transformation that would have tested the hypothesis properly, pacing
magic-state consumers to smooth demand, never helps anywhere.

## The nine questions

**1. Do real structured programs contain legal transformations that reshape
temporal magic-state demand?**
Yes, and they are common. Conventional lowering makes a gate depend on the
previous gate touching any of its lines, which is stricter than the physics:
control lines are read, not written, and gates that only read a line commute
exactly. Sixteen of 22 programs have such false edges; removing them cuts the
critical path by up to 87% (QFT-8: 93 to 30). Six programs have genuinely
serial chains and no freedom at all. So the opportunity to *rearrange* is
real and measurable.

**2. Do those transformations materially reduce FT makespan?**
Yes. Under constrained supply the commuting transformation gives a median
+8.7% and reaches +79.5%; 81 of 192 constrained target runs exceed 10%. Nine
distinct programs from two independent sources exceed 10%.

**3. Does the effect occur without materially changing T-count?**
Yes, exactly. Both transformations keep the gate list untouched; 0 of 2464
runs differ from their baseline in T-count or CCZ-count. The change is 0%, not
merely inside the 2% bar.

**4. Is reduced magic-state backlog or stalling actually the cause?**
**No.** On the cases above 10%, the median saving is 29 cycles while the
baseline contains only 6 stall cycles in total, so the saving cannot be
stall removal. Stalls in fact rise by a median of 7 cycles, and demand becomes
burstier (coefficient of variation 0.333 to 0.787). The share of the saving
attributable to stall reduction is negative. The cause is depth: median
improvement +30.5% against median depth reduction +38.7%, correlation 0.795.

**5. Does the result survive multiple realistic resource configurations?**
The *improvement* survives everything, which is precisely the problem. It is
unchanged across buffer capacities 16, 32 and 64, across factory areas 200 to
3200 tiles, across CCZ shares 0.25 to 0.75, and across all three coupled
provisioning models. An effect that is indifferent to the magic-state supply
is not an effect of the magic-state supply.

**6. Does it occur across at least two independent workload sources?**
Yes: qualtran and QASMBench both contribute programs above 10% (qmpa's
programs gain 1.1% to 5.2%). Six workload families are represented.

**7. Is there a recurring transformation pattern an automatic compiler could
exploit?**
Yes, and that is the difficulty. The pattern is a purely local dataflow rule,
classify each line of each gate as read or written and drop read-after-read
edges, which needs no program-specific insight. It is exactly the kind of
thing that is already a compiler pass.

**8. Is that capability not already provided by the closest existing work?**
**It is already provided.** Qiskit's `DAGDependency` is documented as a DAG
whose edges "correspond to non-commutation between two operations", alongside
`CommutationAnalysis`, `CommutativeCancellation` and commutation-aware
routing. The novel half of this study, source-level pacing of magic-state
consumers, appears not to exist elsewhere, and produces no benefit.

**9. Final decision.**
**NO_GO.** The measured gains are real but are ordinary depth reduction
delivered by a standard analysis. The hypothesis specific to this project,
that reshaping *when* magic states are demanded buys FT time, is not supported
in any configuration tested, including the one deliberately constructed to
favour it.

## Gate table

| Gate | Required | Observed | Result |
| ---- | -------: | -------: | ------ |
| Real programs with >=10% improvement | >=3 | 9 programs | PASS |
| Independent workload sources | >=2 | 2 (qualtran, QASMBench) | PASS |
| Semantic equivalence | verified | 3 by exact unitary, 8 by statevector, 11 structural; 0 failures | PASS |
| T-count change | <=2% | 0.0%, on 0 of 2464 runs | PASS |
| Improvement explained by reduced stalls | yes | stalls *rise* by 7 cycles median; correlation with depth 0.795 vs 0.392 with stalls | **FAIL** |
| Survives multiple constrained configurations | yes | unchanged across buffers, areas, splits, models | PASS |
| Disappears or weakens under abundant supply | yes | **larger** under abundance: +10.8% vs +8.7% | **FAIL** |
| Generalizable compiler transformation | yes | a local read/write dataflow rule | PASS |
| Novelty survives audit | yes | Qiskit ships `DAGDependency` / `CommutationAnalysis` | **FAIL** |

Six of nine pass. The three that fail are the three that define the
hypothesis.

## The fairness check that closes the loophole

The obvious objection is that these programs are depth bound only because the
model charges one cycle per Clifford operation, so the hypothesis was never
given a supply-bound regime to prove itself in. That was tested directly,
outside the frozen grid and reported as a limitation rather than as evidence.
With Cliffords free, the same programs do become supply bound: alias sampling
stalls 81 cycles out of 105, the QASMBench multiplier 49 out of 54, the qmpa
divider 37 out of 54. In that regime the commuting transformation gains
**0.0%** on four of five probes, and pacing gains **0.0%** on all five.

Exactly where magic-state delivery is the binding constraint, reshaping
temporal demand buys nothing. The negative result is stronger there, not
weaker.

## Why, in one sentence

A supply-bound program's makespan is total demand divided by production rate,
which does not depend on when the demand arrives; demand shape matters only
through production discarded from a full buffer, and buffers fill during idle
periods rather than during bursts, so spreading demand out makes that worse
rather than better.

## What would reopen the question

Not a cleverer transformation. Only a machine model in which bursts destroy
capacity instead of merely queueing behind it: factories that must be
reconfigured between products, magic states that expire, or bursts that force
a spatial reallocation of the layout. None of those are in this model, and
adding one to make the hypothesis work would be fitting the machine to the
answer.

## What is worth keeping

* `src/ftqc_delivery/mrc/transform.py`: commutation-aware lowering, pacing,
  the pairwise-commutation soundness check and random linear extensions,
  with tests.
* The verification harness, which establishes equivalence at the strongest
  level each program size allows and found no failures.
* The finding itself, which is useful to the repository: the extractor's
  line-contact lowering overstates the critical path of real programs by up to
  87%, so every earlier result computed on it was measured against an
  unnecessarily serial baseline. That does not change any earlier conclusion,
  because those studies compared policies on the same graph, but the corrected
  lowering is the better default for future work.

## Limitations

* Eleven of 22 workloads are verified structurally rather than numerically,
  because their state spaces are too large to simulate. The structural check
  is the premise of the commutation argument, not a weaker substitute, but it
  is not an end-to-end numerical confirmation.
* The corpus is small programs, the largest 736 gates. Programs whose
  magic-state demand dwarfs their Clifford structure, which is the regime real
  algorithms are expected to reach at scale, are represented here only through
  the Clifford-free probe.
* Pacing was tested at four widths on a single ordering of the consuming
  sites. A smarter pacing policy might do better, but since pacing gains
  nothing even where programs are supply bound, the ordering is unlikely to be
  what is holding it back.
