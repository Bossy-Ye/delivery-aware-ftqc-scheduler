# Go/No-Go memo: resource-aware compilation for fault-tolerant quantum programs

Scope: a pilot study of whether "a compiler should decide using actual
constrained fault-tolerant resources rather than static proxies such as
T-depth" can be turned into a PLDI 2027 contribution.

Everything below is reproducible from this repository. `rac_report.py` prints
every number quoted here directly from the committed tables.

---

## A. Decision

> **NO-GO — insufficient headroom.**

The premise holds and holds strongly: T-depth selects the wrong implementation
in 135 of 196 constrained cases, and the implementation it picks is up to
**2.0x slower** than the best one available. That part survived every attempt
to break it.

The contribution does not follow from it. Once a compiler is told the
production rate at all, essentially every way of using that information lands
on the optimum. A per-site greedy policy that simulates one site against its
share of the factory bank has mean regret **1.006**; the supply-constrained
cost model and search built for this study has mean regret **1.007**. The
proposed mechanism is not better than the most obvious thing one would try
first.

This is stop condition **C** ("a trivial greedy policy captures essentially all
available improvement"), reached through stop condition **E**: after the
strongest simple baselines are in place, what is left of the idea is the
observation that T-depth is inaccurate.

Novelty is *not* the reason. The literature check (Section F) found no prior
work doing supply-rate-driven selection among semantically equivalent
implementations. The idea appears to be new. It is simply not worth doing,
because the problem it solves is solved by two lines of arithmetic.

---

## B. One-sentence contribution

What the study set out to claim, and what it can actually support, differ, so
both are stated.

Intended:

> A resource-aware compiler representation and selection algorithm that models
> magic-state supply against program demand over time, and thereby chooses
> better implementations than T-depth-oriented compilation.

Supported by the data:

> Constrained fault-tolerant execution time is, to within a few percent,
> `max(dependency critical path, T-count / supply rate)`; T-depth optimises
> only the first term, which is why it misleads, and adding the second term is
> the entire fix.

The second sentence is true, useful, and far too small for PLDI.

---

## C. Evidence

Five results, in the order in which they mattered to the decision.

**C1. The reversal is real, large, and structured.** Across 28 pilot programs
and 7 supply regimes (196 cases), the T-depth-optimal implementation is not
the fastest one in **135 cases (69%)**. Median penalty by regime:

| states / logical cycle | 0.1 | 0.2 | 0.5 | 1.0 | 2.0 | 4.0 | 8.0 | unconstrained |
|---|---|---|---|---|---|---|---|---|
| selection reversal rate | 0.89 | 0.89 | 0.89 | 0.89 | 0.64 | 0.25 | 0.36 | **0.00** |
| median regret of T-depth | 1.93 | 1.93 | 1.92 | 1.58 | 1.11 | 1.00 | 1.00 | **1.00** |
| 95th percentile | 2.00 | 2.00 | 1.98 | 1.96 | 1.87 | 1.46 | 1.22 | **1.00** |

Two controls were run to try to explain the effect away, and both failed to.
Removing the supply constraint removes every reversal (0 of 28, regret exactly
1.000), so the effect is about magic states. Making Clifford operations free —
the exact semantics under which T-depth *is* the runtime — leaves the
reversals intact and slightly stronger (0.89 selection reversal rate and
median regret 1.85 at 2 states/cycle), so the effect is not T-depth quietly
ignoring Clifford cost.

The effect also survives every stress axis: a cap on how many logical
operations may start per cycle (T-depth median regret 1.53), distillation
attempts that fail (1.61), and factory banks that deliver the same average
rate through different granularity, phasing, buffer size and production
latency (1.69). It is not bought with qubits either: at the median the
resource-aware choice takes 0.63x the time *and* 0.33x the space-time volume
of the T-depth choice, because the T-depth-minimal implementations are the
ancilla-hungry ones. Stop condition G does not fire.

**C2. But the fix is two static numbers and a division.** Ranking the
realistic candidate implementations by `max(critical path, T-count / rate)`
picks the fastest one in **89.3%** of the 196 cases, with worst-case regret
**1.25x**. For comparison, minimum T-depth picks it in 31.1% of cases and
minimum T-count in 65.3%.

**C3. Every resource-aware policy converges on the optimum.** Regret relative
to the reference optimum, over all 196 cases (133 of which have an
exhaustively proven optimum):

| policy | median | mean | p90 | p95 | max | cases > 5% off |
|---|---|---|---|---|---|---|
| A: minimise T-count | 1.000 | 1.324 | 2.254 | 2.534 | 4.451 | 74 |
| B: minimise T-depth | 1.479 | 1.470 | 1.982 | 1.989 | 2.000 | 131 |
| B+: best of the two, timed | 1.000 | 1.033 | 1.115 | 1.238 | 1.484 | 31 |
| C: prior study's flow | 1.479 | 1.474 | 1.982 | 1.989 | 2.000 | 134 |
| D: greedy per site | 1.000 | 1.056 | 1.243 | 1.368 | 1.643 | 37 |
| D+: greedy, share-aware | 1.000 | **1.006** | 1.000 | 1.035 | 1.158 | 8 |
| D++: simulate every library choice | 1.000 | 1.014 | 1.016 | 1.115 | 1.267 | 17 |
| **ours: supply-constrained selection** | 1.000 | **1.007** | 1.010 | 1.037 | 1.316 | 10 |

Our method beats the strongest baseline in **5 of 196** cases, ties in 162 and
**loses in 29**. The largest win is 1.10x, on a 33-cycle toy program.

**C4. The demand *shape* does not matter, which is why there is nothing to
optimise.** A dedicated probe varied concurrency from 1 to 16 lanes and buffer
capacity from 2 states to unbounded, at a fixed rate. From 4 concurrent sites
upward every policy returns the identical makespan, and buffer capacity makes
no difference at any concurrency above 1. Once the program is supply-bound,
implementations with equal T-count take equal time regardless of how their
demand is distributed, because a burst simply queues. Committing to a static
schedule does not create headroom either: the prior study's smoothed static
schedule and dynamic greedy execution differ by a median of 1.000 and a
maximum of 1.067.

**C5. The ablation confirms where the value is, and how little of it is
left.** Selection quality and prediction accuracy by cost-model information:

| model | median regret | p90 regret | mean prediction error | ranks the best candidate |
|---|---|---|---|---|
| dependencies only (what T-depth sees) | 1.479 | 1.982 | 61.7% | 31.1% |
| T-count and average rate | 1.000 | 2.254 | 11.7% | 62.2% |
| dependencies + T-count | 1.000 | 1.122 | 3.0% | 86.7% |
| + factory arrival timing | 1.000 | 1.071 | 0.41% | 91.8% |
| + buffer capacity (full model) | 1.000 | 1.010 | 0.40% | 91.8% |

The full model is a genuinely better predictor than the two-term rule — p90
regret 1.122 to 1.010, prediction error 3.0% to 0.4%. It is not a better
*compiler*, because a compiler has only a handful of library implementations
to choose between and can simply time them (row D++ above).

**C6. And the cost model is not even cheaper than the thing it replaces.** A
static cost model earns its place by costing less than running the circuit.
Measured across all 196 program/regime pairs, evaluating the supply-constrained
bound is **slower than simulating the circuit outright in 196 of 196 cases**,
by a median factor of 2.1x. The bound is `O(thresholds^2)` in the number of
distinct release and tail values, while the simulator is dominated by graph
setup and barely grows with makespan, so the gap does not close even at the
lowest supply rate, where the simulated makespan reaches 17,643 cycles. A
faster implementation is certainly possible, but the burden was on the cost
model to be cheap, and at pilot scale it is not.

---

## D. Killer figure

Two figures carry the memo, and they point in opposite directions. Both are in
`figures/rac_pilot/`.

**The phenomenon:** `fig1_t_depth_vs_constrained_runtime`. Four panels of
T-depth against constrained runtime, each normalised to the best candidate for
that program. In the unconstrained panel every point sits exactly on the
diagonal — T-depth *is* the runtime. In the constrained panels the
relationship inverts: the implementations with 4-8x the minimum T-depth are
the fastest ones, and the T-depth-minimal ones are twice as slow.

**The decision:** `fig3_runtime_vs_supply`, which is the figure that closed the
project. The two static metrics each fail across half of the regime space and
cross over near 1 state per cycle. Every resource-aware policy — including the
simplest per-site greedy — lies on the optimum line at both the median and the
90th percentile, indistinguishable from the method built for this study. There
is no visible gap for a new mechanism to occupy.

`fig4_headroom_captured` makes the same point as a census and adds the one
counterpoint: on the left, the strongest simple baseline is already optimal for
almost every program at every rate; on the right, headroom reappears once there
are two kinds of magic state and their production rates are imbalanced. That
right-hand panel is the entire case for the follow-up in "What to do instead".

---

## E. Compiler mechanism

What was built, so the record is concrete. All of it works and is tested.

*Supply-constrained critical path (SCCP).* A static cost model. The classical
critical-path bound says a program cannot finish before its longest dependency
chain. SCCP adds the dual statement for a rate-limited consumable: for every
pair of thresholds `(a, b)`, the T gates that cannot start before cycle `a` and
that carry at least `b` cycles of work behind them must all be supplied at or
after `a`, so the factories fix the earliest cycle at which the last of them
can start, and `b` more cycles must follow. Maximising over all such windows
gives a bound that is simultaneously aware of dependency structure, T-count,
factory throughput, production latency and buffer capacity. It is a certified
lower bound (`test_rac_cost_and_select.py` checks this), and it never runs the
circuit — a test asserts the selection policy makes zero calls to the
simulator, so this is a compiler cost model and not an offline evaluator. What
it is not is cheap: as implemented it costs about 2.1x more than simulating the
circuit (Section C6).

*Supply-constrained selection.* Coordinate descent over per-site
implementation choices, scored only by SCCP, restarted from several cheap
seeds. It can produce assignments that no static metric can express: giving
concurrent sites *different* implementations so their demand bursts interleave.
It did so in 79 of 196 cases.

The relation to the previous paper is clean, which is why Gate 3 would have
passed. The T-depth paper ranks *schedules of one fixed circuit* and predicts
slowdown; `Delta_max` is a bound for a fixed schedule and therefore cannot
compare two different circuits. SCCP is schedule-independent, so it can, and
that is the capability that did not exist before: the compiler can compare
different realisations of the same program under a rate-limited resource, and
can deliberately mix them across concurrent sites.

The problem is that this capability is worth 0.1% on average.

Stated without quantum vocabulary, the framing was going to be: a compiler that
minimises a dependency-only metric is minimising a program's recurrence bound
while ignoring the resource bound imposed by a rate-limited consumable — the
mistake classical compilers stopped making when modulo scheduling started
taking `max(RecMII, ResMII)`. That framing is correct, and it is also the
reason the project fails: taking the maximum of the two bounds is the whole
fix, and it has been standard practice elsewhere for thirty years.

---

## F. Novelty table

The exact contribution is not in the literature. Access to arXiv full text was
blocked from this environment, so entries are built from abstracts, indexed
summaries and search results; each should be re-read in full before any claim
is published.

| Work | Problem | Resource model | Compiler decision | Optimisation target | What remains open |
|---|---|---|---|---|---|
| When T-Depth Misleads (arXiv 2604.11409) — our paper 1 | predict slowdown of a fixed schedule under bounded delivery | delivery capacity `C`, buffer `B`, deterministic and stochastic | none; it is a diagnostic | predict `T_exe`; slack ratio and `Delta_max` | how to *choose* between different circuits, not orderings |
| Harvest (arXiv 2608.03315) | lattice-surgery placement, routing and scheduling under magic-state contention | protocol-agnostic factories, ports, routes, terminals | placement + routing + schedule for a **fixed** circuit | schedule length, layout footprint | which implementation to emit in the first place |
| PureMagic (arXiv 2512.06484) | scheduling lattice surgery with stochastic cultivation | cultivation latency distribution, ancilla patches | runtime scheduling of a **fixed** circuit | efficiency, logical qubit count | compile-time implementation choice |
| Ding, Holmes, Javadi-Abhari, Franklin, Martonosi, Chong, MICRO-51 (2018) | magic-state functional units | multi-level distillation circuits, braids | mapping and scheduling **inside the factory** | factory area and throughput | the demand side of the same problem |
| Molavi, Xu, Tannu, Albarghouthi, OOPSLA (2025) | dependency-aware surface-code compilation | patches, routing channels | routing order by dependency criticality | schedule length | magic-state production rate as a constraint |
| Litinski, *A Game of Surface Codes* (2019) | space/time trade-offs in surface-code architectures | factories, tiles, fast/compact/intermediate blocks | architecture provisioning, by hand | space-time volume | automated per-site implementation choice |
| Optimizing Multi-level Magic State Factories (arXiv 2411.04270) | factory provisioning as a supply chain | multi-level distillation, zones | how many factories and at which levels | space-time volume | demand-side choice given a fixed supply |
| Towards Deploying Optimistic QFTs (arXiv 2605.15297) | which adder to use under cultivation-era rates | neutral atoms, cultivation, parallelism budget | manual, per-algorithm | space-time volume, peak parallelism | automation; arbitrary programs; a cost model |
| Quartz, PLDI (2022) | superoptimisation over equivalence circuit classes | none — the cost function is static | **select among semantically equivalent circuits** | gate count, depth | a resource-rate-aware cost function |
| Accuracy-aware compilation / Azure RE (arXiv 2003.08408, 2311.05801) | choose decomposition accuracy under an error budget | error budget; the estimator does model T-factory throughput | choose accuracy parameters per decomposition | T-count subject to total error | selection driven by *throughput*, not by error |

Reading of the table. The closest work on the *decision* (Quartz) uses a static
cost function. The closest work on the *resource* (Harvest, PureMagic, Ding,
Litinski) takes the circuit as given. The closest work on the *phenomenon*
(the QFT co-design study, and Gidney's observation that cheap magic states
make T-hungrier adders worth it) reports it by hand for one algorithm. Nobody
has automated it. Stop condition D does not fire.

---

## G. Remaining risks

If the project were continued anyway, these are the three reasons it would
still fail, ordered by how likely each is to be fatal.

1. **The baselines do not get weaker at scale, they get stronger.** The
   share-aware greedy policy needs one simulation per variant per site, and
   sites are small. Real programs have more sites, not bigger ones, so the
   policy stays cheap while the assignment space our search must explore grows.
   Nothing in the data suggests the gap opens up with size: the concurrency
   probe closed it completely by 4 lanes.

2. **The reviewer's first question has a one-line answer.** "Why not just try
   the ripple version and the lookahead version and time them?" is answered by
   row D++ of the table in Section C3: doing exactly that is optimal in 175 of
   196 cases. The usual rebuttal — that a compiler cannot afford to simulate
   every candidate — is not available here, both because there are only a
   handful of library implementations and because our own cost model turned out
   to be slower than the simulation it was meant to replace (Section C6).

3. **The residual accuracy advantage is in the wrong place.** SCCP is a
   materially better predictor than the two-term rule, but only on
   heterogeneous assignments — and those are exactly the assignments that turn
   out not to be worth choosing. Worse, the one place the model is genuinely
   loose is heterogeneous demand with a bounded buffer, where it under-predicts
   by up to 6% because it cannot see production lost at a full buffer once the
   constraint itself has spread the demand out. Fixing that without simulating
   is an open problem, and it is an open problem in service of a 0.1% win.

---

## H. Eight-week feasibility

Engineering is not the constraint and never was. This pilot took a working
resource model, variant library, cycle-accurate simulator, analytic cost
model, five baselines, an exhaustive optimality reference, six experiments and
a test suite. Extending it to a PLDI-scale evaluation — more circuit families,
real transpiler front ends, larger instances — would fit comfortably in eight
weeks.

The result is the constraint. There is no version of the next eight weeks that
turns a 0.1% mean improvement over a greedy baseline into a PLDI paper, and
spending them trying would mean optimising the evaluation until the baseline
looks worse, which is the failure mode this study was designed to prevent.

---

## What to do instead

Three options, in the order we would recommend them.

**1. Fold C2 into the existing paper (about a week).** The result
"constrained execution time is `max(critical path, T-count / rate)`, so use
both terms" is correct, cheap to state, and directly actionable for anyone
using T-depth as a compilation objective. It belongs as a section in the
journal version of the T-depth paper, or as a short QCE-style paper. It also
sharpens paper 1: the reason T-depth misleads is that it ignores T-count and
the rate, not that it ignores demand shape, and Figure 5 shows this plainly —
the T-depth-selected circuit stalls for 255 of its 267 cycles simply because
it needs twice as many states.

**2. Probe the non-fungible-resource question (two to three weeks, bounded).**
The one place where the headroom came back. Real machines run several kinds of
factory, and one logical operation can often be realised from either — a
Toffoli from four T states through a measurement-based AND, or directly from a
CCZ factory. Selecting implementations then means *balancing* several
independent supplies, and the objective becomes a maximum over resources
rather than a sum, which no per-site minimisation of any single static count
can solve. A small probe (`rac6_multiresource_probe.py`, 32 configurations)
found:

* headroom beyond the best uniform library implementation of **15.8% at the
  90th percentile and 23.1% at the maximum**, concentrated where the two
  production rates are imbalanced;
* the optimum is a **mixed** assignment in 19 of 32 configurations;
* the two-term rule lifted to several resources, which was sufficient in the
  single-resource setting, has worst-case regret **1.348** here.

That is the signature the main study lacked: a decision problem that the
trivial policies genuinely do not solve. It is a toy — one kernel, four
variants, twelve to twenty-one sites — and it must not be quoted as a result.
The right next step is a bounded probe with a hard kill date: if realistic
mixed-factory architectures do not reproduce 15%+ headroom on real kernels,
stop there too.

**3. Accept that the interesting problems are the ones we excluded.** The
study deliberately isolated supply against demand, leaving out routing,
locality, magic-state ports, code distance and error budget. Those are where
the remaining difficulty lives — and they are also where Harvest, PureMagic
and the factory-provisioning line of work already are. Entering that space
means competing with architecture groups on their own ground, which is a
different decision from this one and should be made on its own merits.
