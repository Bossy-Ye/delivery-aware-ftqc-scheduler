# Experiment contract: is there stateful-selection headroom worth a new compiler project?

Frozen on 2026-09-20, before the decisive run. Baseline repository commit
`345b94fdb2188d8d8d67b3cc779f60dcbea00875`, 141 tests passing at that commit.
Thresholds in section 8 are not to be changed after results exist.

## 1. Research question

On workloads with temporally heterogeneous non-Clifford demand, how much
execution-cost headroom exists between the strongest existing static and
stage-local policies and an oracle allowed to carry resource state across
decision boundaries and choose different semantically equivalent
implementations over time?

## 2. Primary hypothesis

A stateful oracle shows substantial residual headroom over the current
stage-DP specifically when (1) there is sufficient parallelism, (2) resource
demand changes over time, and (3) several non-Clifford resource families
compete for finite production, storage and area. The effect should be weak or
absent on serial chains and on unconstrained machines.

## 3. What "stateful" means here, and what is already stateful

Every candidate assignment is scored by running the whole program on the
machine with the existing simulator, which carries stock, factory phase,
buffer occupancy, in-flight conversions and outstanding demand from the first
cycle to the last and never resets them at a stage boundary. The action space
is one implementation choice per decision site, ordered in time, so the state
evolves as `S_{t+1} = g(S_t, a_t)` with `g` the simulator's own transition and
no imposed abstraction.

This means the existing exact optimiser is already the stateful oracle: it is
a joint search over all site choices, scored by a fully state-carrying
execution. The new work in this experiment is therefore not a new notion of
statefulness but (a) workloads chosen for width and temporal heterogeneity,
(b) a provable lower bound so unproven cases still bound the headroom, and
(c) ablations that test why any advantage appears. The stage-DP is the
contrasting stage-local method: it carries stock across stage boundaries but
not factory phase, and optimises stage by stage over a pruned frontier.

## 4. Workloads

The corpus is frozen in `src/ftqc_delivery/mrc/corpus.py`: 22 programs from
three independently authored sources, none written for this project.

| source | version | programs |
|---|---|---|
| qmpa (Alan Robertson, UTS) | commit `47e27d38a55f5161baac7805f9cc06a8146aa064` | 5 |
| qualtran (Google Quantum AI) | 0.7.0 | 11 |
| QASMBench (PNNL) | commit `357b942396d5c2b7cbc1c229c585a6ef5ccaebac` | 6 |

Inclusion rule: the program must be extractable by the existing decision-site
extractor without hand editing, and every gate it contains must be modelled
(the OpenQASM front end raises on an unmodelled gate rather than dropping it,
so no non-Clifford demand can go uncounted).

Exclusion: programs whose upstream decomposition is unavailable
(`Product`, `Square`, `PlusEqualProduct`, `AddIntoPhaseGrad` do not declare
one) and `bwt_n21` (25,600 Toffolis, outside the simulation budget).

Role assignment is by measured structure only, computed with no machine and
no policy, by `ftqc_delivery.mrc.features.classify_role`:

> **target** if the program has a stage with at least two eligible sites and
> at least 5% of its stages are wide, **or** it has at least two distinct
> consuming site families; **control** otherwise.

The frozen split is 16 targets over 8 families (parallel_adder, multiplier,
divider, state_preparation, qft, phase_estimation, lookup, oracle) and 6
controls (serial adders, a serial AND ladder, unary-iteration lookup, a serial
comparator, and a 65-site serial square root). The full table with every
measured feature is `WORKLOAD_FEATURES.csv`. One workload, `qb_sqrt_n18`, was
declared a target by expectation and reclassified as a control by measurement
before any policy was run.

## 5. Machine configurations

Seventeen configurations from the existing coupled models, at fixed factory
area so no model is given more hardware:

* `A_400_{0.25,0.5,0.75}`, `B_400_{...}`, `C_400_{...}` — constrained;
* `A_800_0.5`, `B_800_0.5`, `C_800_0.5` — larger;
* `B_400_0.5_scarce`, `C_400_0.5_scarce` — raw stream at half the distillers'
  appetite;
* `A_3200_0.5_abundant` — the weakly constrained control.

Model A is independent T and CCZ banks; B distils both from one raw stream; C
adds the catalysed CCZ-to-2T conversion.

## 6. Policies

| label | policy | description |
|---|---|---|
| P0 | `fixed_t` | every site built from T states |
| P1 | `fixed_ccz` | every eligible site consumes a CCZ state directly |
| P2 | `uniform_oracle` | best whole-program uniform choice, chosen by simulation |
| P3 | best of six | fewest T-equivalents, weighted count, two-term descent, local simulated greedy, share-aware greedy, proportional split |
| P4 | stage-DP | `select_stage_dp(mode="analytic", refine=5, include_uniform=True)` |
| P5 | stateful oracle | exact where affordable, else iterated search plus a provable lower bound |

`best_non_stateful` is the minimum makespan over P0, P1, P2 and P3.

## 7. Metrics

Primary: **execution makespan in logical cycles**.

* `headroom_vs_best_non_stateful = (best_non_stateful - P5) / best_non_stateful`
* `residual_headroom_vs_stagedp = (P4 - P5) / P4`
* `max_possible_headroom_vs_stagedp = (P4 - lower_bound) / P4`

When P5 is proven, the first two are exact. When P5 is bounded, they are lower
bounds on the true headroom and the third is an upper bound on it, so a case
whose third value falls below a threshold provably fails that gate.

Secondary, recorded per case: T and CCZ stall cycles, T and CCZ waste
(overflow), final stock, conversions run, factory tiles, space-time volume
(makespan times factory tiles), compiler search time per policy, number of
simulations, and the fraction of sites whose chosen implementation differs
from the whole-program uniform choice.

## 8. Decision thresholds

### Strong GO — all of:

1. On the target subset, P5 improves makespan by at least **10% median**
   versus `best_non_stateful`.
2. Residual headroom of P5 over P4 is at least **5% median** on the target
   subset.
3. The effect appears in at least **three distinct workload families** and at
   least **two independently authored sources**.
4. Multiple external cases exceed 10% improvement; not one outlier.
5. Negative controls show little or no advantage.
6. The phenomenon survives the coupled-machine parameter variation in §5.
7. A second implementation/resource family is supported, or is shown
   independently promising enough to justify immediate follow-up.

### HOLD

Mechanism real but one decisive gate open: median target gain 5-10%; residual
headroom over P4 2-5%; effect confined to one narrow but real family; second
resource family `NOT_EVALUATED`; or exact oracle coverage too thin on
important real workloads.

### NO-GO

Any of: residual headroom over P4 at most 2% almost everywhere; gains only in
synthetic or constructed workloads; wide external workloads show negligible
practical headroom; the effect depends on one Toffoli-specific modelling
choice and disappears under reasonable alternatives; unconstrained and serial
controls behave like the target cases; or prior work already implements the
same stateful capability.

## 9. Screening gate

Before the full matrix: unit tests, then 3 controls and 5 wide targets on the
400- and 800-tile machines with the exact oracle where feasible. If every
credible wide workload shows at most 2% residual headroom over P4 **and** the
lower bound proves no more is available, stop and report likely NO-GO.

## 10. Determinism and seeds

One seed, `20260920`, is used for the machine arrival series, for the
iterated search's random restarts, and for any workload builder that draws
random values. Distillation succeeds deterministically (`p_success = 1.0`) in
every configuration here, so a case is reproducible by re-running it.

## 11. Resource-cost assumptions and their sources

| quantity | value | source |
|---|---|---|
| CCZ factory | 12d x 6d tiles, one state per 5.5d | Gidney & Fowler 2019, arXiv:1812.01238 |
| 15-to-1 T factory | 11 tiles, 11 cycles | Litinski 2019, arXiv:1808.02892 |
| Toffoli from one CCZ state | 1 CCZ | Gidney & Fowler 2019 |
| temporary AND | 4 T to compute, 0 to uncompute | Gidney 2018, arXiv:1709.06648 |
| Toffoli, T-depth 3 | 7 T, no ancilla | Amy, Maslov, Mosca & Roetteler 2013 |
| Toffoli, T-depth 1 | 7 T, four ancillas | Selinger 2013 |
| catalysed conversion | 1 CCZ -> 2 T | Gidney & Fowler 2019 |
| 8T -> CCZ distillation | 8 T -> 1 CCZ | Gidney & Fowler 2019 |
| rotation, Clifford+T | 4 log2(1/eps) T, sequential | Ross & Selinger 2016 |
| rotation, Toffoli-count | 4 ceil(log2(1/eps)) + 6 Toffoli, depth log2(1/eps)+3 | arXiv:2404.05618 |
| rotation, phase gradient | about 2b Toffoli for b bits | phase-gradient addition; qualtran's own `RzViaPhaseGradient` decomposes this way |
| bare T gate | exactly 1 T state | definition |

Rotation precision is frozen at **b = 10 bits** for every extracted rotation
site, matching the existing kernels. A z-rotation is classified by its angle:
multiples of a half turn are Clifford and free, a quarter turn is exactly one
T state, anything else is a synthesised rotation. Clifford glue is charged one
cycle per operation, identically for every variant, so it cannot bias a
comparison.

Two workload caveats are recorded rather than hidden: qmpa's `add_draper`
leaves its prefix rounds unimplemented upstream, so it is used only as an
independently authored wide gate stream and not as a verified adder; and
OpenQASM `u2`/`u3` are expanded into the two or three z-rotations of the Euler
decomposition, which counts rotations rather than hiding them.

## 12. Second resource family

Rotations are included as a second family wherever a workload contains them
(qualtran's QFT, phase estimation and uniform-superposition preparation), with
the five cited variants above. The family gate is judged on whether the
phenomenon appears in those workloads, and is reported `NOT_EVALUATED` if no
corpus workload exercises it.

## 13. Outputs

`WORKLOAD_FEATURES.csv`, `SCREENING_RESULTS.md`, `RAW_RESULTS.csv`,
`ABLATIONS.csv`, `NOVELTY_MATRIX.md`, `GO_NO_GO_MEMO.md`. Existing result
files elsewhere in the repository are not modified.
