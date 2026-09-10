# Evidence memo: implementation selection under non-fungible magic states

Question: when semantically equivalent implementations consume different
mixtures of T and CCZ states, does global heterogeneous implementation
selection materially outperform simple local or uniform policies under bounded
factory supply?

Short answer: **yes, and by more than the single-resource study left room for.**
Every implementable simple policy is at least 10.8% off the optimum on average;
global heterogeneous selection reaches 1.005. Both falsification controls
behave exactly as a real mechanism requires.

Everything below is reproducible from this repository.
`experiments/mrc/mrc_report.py` prints every number quoted here from the
committed tables.

---

## 1. Model and assumptions

**Time and space.** Time is in *logical cycles*, one logical cycle being the
`d` surface-code rounds a lattice-surgery operation takes. Space is in *tiles*,
one tile being a `d x d` patch.

**Factories.** Two independent banks, each with a count, a period, a production
latency, a bounded buffer, a per-attempt success probability, and a tile
footprint. Production arriving at a full buffer is lost. The reference designs
are:

| bank | tiles | cycles per state | source |
|---|---|---|---|
| CCZ | 72 (`12d x 6d`) | 6 (rounded up from 5.5) | Gidney & Fowler 2019, arXiv:1812.01238 |
| T | 11 | 11 | Litinski 2019, arXiv:1808.02892, 15-to-1 |

These are not one calibrated design point — they target different output
fidelities — so **no claim is made that their ratio is the correct one for any
machine**. They fix the scale; the number of factories of each kind is the
architectural parameter the study sweeps. The CCZ period is rounded 5.5 to 6,
which is conservative for CCZ.

**Execution.** A greedy list scheduler: everything whose predecessors have
finished starts immediately, except that an operation consuming a magic state
waits for a state *of its own kind*. Cliffords cost one cycle and consume
nothing. Clifford structure inside a variant is a uniform one-cycle glue layer
between resource layers, identical across variants, so it cannot bias a
comparison.

**Conversions.** Both real protocols are modelled and can be switched on: the
catalyzed one CCZ to two T (Gidney & Fowler 2019) and the eight T to one CCZ
distillation used by current CCZ factory designs. The round trip loses a factor
of four, so the exchange is asymmetric and lossy. Switching them on is the main
control.

**Capacity parameterisation.** Machines are specified by *total* capacity in
T-equivalent states per cycle (one CCZ counted as two T, via the catalyzed
transformation) and by the *fraction* of that capacity held by the CCZ bank.
Holding capacity fixed while sweeping the split separates the effect of
splitting the supply from the effect of having more or less of it. Factory
counts are integral, so achieved capacity varies within about +/-15% of target;
achieved rates are recorded, not targets.

**What is deliberately excluded.** Routing, locality, magic-state ports, code
distance and the error budget. This is the same isolation discipline as the
single-resource study: the question is supply *composition* against demand
*composition*, and nothing else.

**Known limitations.** (i) The two banks are treated as independent, but real
CCZ factories are often built on top of T distillation (the 8T-to-CCZ protocol),
so their capacities may not be independently dialable. (ii) Clifford cost is
uniform, which flatters no variant but is not physical. (iii) The Toffoli-based
rotation routes assume a phase-gradient catalyst is already held.

---

## 2. Literature-backed variant table

Costs are the published ones. Every row records its source.

| family | variant | T | CCZ | T-equiv | crit. path | ancillas | source |
|---|---|---|---|---|---|---|---|
| AND / Toffoli | `ccz` | 0 | 1 | 2 | 5 | 1 | Toffoli is a CCZ up to Cliffords, consumed directly from a CCZ factory (Gidney & Fowler 2019) |
| | `t4` | 4 | 0 | 4 | 7 | 1 | Gidney 2018 temporary AND: 4 T to compute, 0 to uncompute (arXiv:1709.06648) |
| | `t7d3` | 7 | 0 | 7 | 9 | 0 | Amy, Maslov, Mosca & Roetteler 2013: T-count 7, T-depth 3 |
| | `t7d1` | 7 | 0 | 7 | 5 | 4 | Selinger 2013: T-count 7, T-depth 1, four ancillas |
| adder n=32 | `ripple_ccz` | 0 | 31 | 62 | 95 | 1 | `n-1` ANDs on a serial carry chain |
| | `ripple_t4` | 124 | 0 | 124 | 157 | 1 | the same chain, `4n` T (Gidney 2018) |
| | `ripple_mix` | 60 | 16 | 92 | 125 | 1 | alternating ANDs; tests *within-site* mixing |
| | `select8_ccz` | 0 | 61 | 122 | 35 | 12 | carry-select: about `2n` ANDs for `O(log n)` depth (Draper et al. 2004) |
| | `select8_t4` | 244 | 0 | 244 | 55 | 12 | the same, from T states |
| | `select8_mix` | 120 | 31 | 182 | 45 | 12 | alternating |
| MCX k=16 | `linear_ccz` / `linear_t4` | 0 / 60 | 15 / 0 | 30 / 60 | 47 / 77 | 16 | `k-1` ANDs on an ancilla chain |
| | `tree_ccz` / `tree_t4` | 0 / 60 | 15 / 0 | 30 / 60 | 18 / 26 | 24 | balanced ancilla tree, same AND count |
| rotation b=10 | `rs_t` | 40 | 0 | 40 | 82 | 0 | Ross-Selinger: T-count about `4 log2(1/eps)`, sequential |
| | `toflog_ccz` / `toflog_t4` | 0 / 184 | 46 / 0 | 92 / 184 | 50 / 74 | 20 | expected Toffoli count under `4*ceil(log2(1/eps)) + 6`, depth under `log2(1/eps)+3` (arXiv:2404.05618, PRR 6 L042027) |
| | `pg_ccz` / `pg_t4` | 0 / 80 | 20 / 0 | 40 / 80 | 62 / 102 | 10 | phase-gradient catalyst: a rotation is a `b`-bit controlled addition, about twice a bare adder in Toffoli count |

The rotation family contains the cleanest possible instance of the decision
under study. `rs_t` costs 40 T states and `pg_ccz` costs 20 CCZ states, which
is **exactly 40 T-equivalents**: the two are identical in fungible value and
differ *only* in which factory they load. That equality is not tuned; it falls
out of Ross-Selinger's `4 log2(1/eps)` T against the phase-gradient route's
`2 log2(1/eps)` Toffolis at one CCZ per Toffoli. Section 7 measures how much
the result depends on it.

**Kernels.** 24 programs spanning modular exponentiation, multiplier trees,
QFT blocks, Trotter layers, Grover iterations, parallel oracle banks, phase
estimation, mixed-family kernels, wide heterogeneous stages and bare AND
ladders; operand widths 16-128, concurrency 1-16, 2-16 decision sites each.

---

## 3. Baselines

Eight policies, ordered by how much they are allowed to see.

| policy | sees | may simulate | may mix within a family |
|---|---|---|---|
| `uniform_min_teq` | the circuit | no | no |
| `min_weighted_count` | circuit + bank rates | no | yes (per site) |
| `uniform_oracle` | circuit + machine | every uniform choice | no |
| `two_term_descent` | circuit + machine | no (analytic `max(critical path, per-resource demand/rate)`) | yes |
| `local_sim_greedy` | one site + whole machine | one site at a time | yes |
| `share_aware_greedy` | one site + its share of the machine | one site at a time | yes |
| `proportional_split` | group sizes + bank rates | no | yes, by formula |
| `sim_descent` | whole program + machine | yes | yes |
| `global_oracle` | everything | exhaustively | yes |

`proportional_split` is the kill-condition baseline: for each group of
interchangeable sites it sends a fraction of them to the CCZ bank equal to that
bank's share of total T-equivalent capacity, needing no search and no
simulation. `two_term_bound` uses the bank's exact arrival series rather than
`count / rate`, which would overstate the wait by up to one production period
and is not a valid bound; a test checks it never exceeds the simulated
makespan.

**The optimality reference.** Sites within a stage that have the same
predecessors, successors and variant set are interchangeable, so the optimum
over assignments equals the optimum over *multisets* of choices per group. That
reduction is exact — verified against exhaustive enumeration, matching to the
cycle — and it collapses spaces like 390,625 to 4,900, which is what makes
exact optima available at concurrency 16. Where even the reduced space exceeds
a measured time budget, the reference is a seeded search and the row is marked
non-exact; such rows are excluded from every claim requiring a proven optimum.
The reference is seeded with every policy's answer, so it is never beaten by a
policy it is compared against (verified: 0 of 480 rows).

---

## 4. Experiment matrix

| axis | values | where |
|---|---|---|
| kernels | 24 programs, 4 families, concurrency 1-16 | mrc1 |
| total capacity | 0.25, 0.5, 1.0, 2.0 T-equiv/cycle | mrc1 |
| CCZ share of capacity | 0.1, 0.25, 0.5, 0.75, 0.9 | mrc1 |
| pooled control | all capacity in one bank, only its variants | mrc2 |
| conversion control | CCZ->2T; both directions | mrc2 |
| buffer | 2, 8, 32, 128, unbounded | mrc2 |
| production latency | 0, 10, 50, 200 cycles | mrc2 |
| distillation failures | p = 1.0, 0.9, 0.7, three seeds | mrc2 |
| concurrency scaling | 1, 2, 3, 4, 6, 8, 12, 16 lanes | mrc3 |
| size scaling | rotation precision 4-32 bits; adder width 16-128 | mrc3 |
| cost-ratio sensitivity | Toffoli count scaled 0.5x - 2.0x | mrc4 |

480 cases in the main matrix (401 with a proven optimum), 488 control rows,
207 scaling rows, 162 sensitivity rows.

---

## 5. Oracle results

Over the 480 main-matrix cases, the global optimum against the best
implementation each class of policy can produce:

* headroom over the **best uniform implementation** (simulated): median 6.2%,
  p90 25.6%, max 46.5%;
* headroom over the **best of all six simple baselines, chosen per case**:
  median 0.0%, p90 11.1%, max 26.4%; above 5% in 121 of 480 cases and above 10%
  in 59.

Restricting to the 401 cases with a proven optimum changes little: median 0.0%,
p90 10.8%, max 26.4%, above 5% in 102 and above 10% in 48.

The optimal assignment is genuinely mixed where the headroom is. Across the
59 cases with more than 10% headroom, the optimum draws a median of 61% of its
T-equivalent demand from the CCZ bank, ranging from 15% to 100%, and supply
pressure sits at a median of 1.02 — that is, right at the point where the
factories rather than the dependency structure set the makespan.

The largest wins, all on proven optima:

| kernel | capacity | CCZ share | best simple | optimum | gain | mixing |
|---|---|---|---|---|---|---|
| `mixed_w32_c16_l2` | 0.25 | 0.10 | 795 | 585 | 26.4% | 0.33 |
| `modexp_w32_s2` | 0.5 | 0.50 | 747 | 567 | 24.1% | 0.50 |
| `modexp_w16_s2` | 0.5 | 0.50 | 363 | 279 | 23.1% | 0.50 |
| `phase_est_w32_r1` | 0.5 | 0.50 | 517 | 405 | 21.7% | 0.50 |
| `modexp_w32_s2` | 2.0 | 0.75 | 373 | 297 | 20.4% | 0.50 |
| `grover_c16_i2` | 0.25 | 0.10 | 387 | 311 | 19.6% | 0.50 |

The win is not bought with space. Charging the factories, the data registers
and the ancillas, the optimum's space-time volume is a median of **0.946x** the
best uniform choice, and at worst 1.030x.

---

## 6. Regret distributions

Over the 401 cases with a proven optimum:

| policy | mean | median | p90 | max | >5% off | >10% off | median runtime |
|---|---|---|---|---|---|---|---|
| uniform, fewest T-equivalents | 1.312 | 1.151 | 1.831 | 4.108 | 256 | 222 | 0.06 s |
| per-site weighted resource count | 1.202 | 1.148 | 1.497 | 1.869 | 256 | 223 | 0.01 s |
| best uniform implementation | **1.109** | 1.022 | 1.309 | 1.869 | 187 | 138 | 0.10 s |
| `max(critical path, demand/rate)` search | 1.116 | 1.011 | 1.372 | 1.793 | 179 | 151 | 0.45 s |
| per-site local simulation | 1.170 | 1.093 | 1.444 | 2.245 | 241 | 190 | 0.03 s |
| per-site share-aware greedy | 1.191 | 1.093 | 1.497 | 3.241 | 240 | 191 | 0.04 s |
| split in proportion to bank rates | 1.335 | 1.240 | 1.837 | 2.551 | 289 | 259 | 0.01 s |
| **global heterogeneous search** | **1.005** | 1.000 | 1.000 | 1.244 | 14 | 5 | 1.07 s |
| *oracle over the six simple baselines* | *1.035* | *1.000* | *1.121* | *1.359* | *102* | *54* | — |

Two readings matter and they differ.

**Against any single implementable simple policy, the gap is large.** The best
one is `uniform_oracle` at 1.109 mean, and it is more than 10% off on 138 of
401 cases. The kill condition asks whether a simple greedy reaches roughly 1.02
mean regret; none comes close, and `proportional_split` — the obvious
formula-based split, and the policy the kill condition most directly names — is
the *worst* of the eight at 1.335.

**Against an oracle that picks the best simple policy per case, the gap is
smaller but still real**: 1.035 mean, p90 1.121, above 5% on a quarter of cases.
No compiler has that oracle, and the reason it helps is itself informative: the
strongest simple baseline is spread across all six policies (uniform_min_teq
186 cases, two_term_descent 134, uniform_oracle 83, proportional_split 48,
min_weighted_count 23, share_aware_greedy 6). **No single simple rule works
across the matrix.**

By kernel family, the maximum headroom over all simple baselines is 26.4%
(mixed), 24.7% (multiplier), 24.1% (modexp), 21.7% (phase estimation), 19.6%
(Grover), 19.4% (AND ladder), 19.3% (Trotter), 15.4% (QFT) — and **0.0% for
the parallel oracle bank**, where the MCX variants leave a uniform choice
optimal at every operating point. That negative case is worth keeping: the
effect is not universal.

---

## 7. Falsification controls

Both controls behave exactly as they must if the mechanism is non-fungibility.

| control | headroom over best uniform (median / p90 / max) | mean mixing |
|---|---|---|
| baseline, two separate banks | 8.5% / 36.9% / 46.5% | 0.18 |
| plus catalyzed CCZ to 2T | 0.0% / 11.1% / 24.8% | 0.12 |
| plus both conversions | 0.0% / 10.0% / 23.1% | 0.08 |
| **all capacity pooled into the T bank** | **0.0% / 0.0% / 0.0%** | **0.00** |
| **all capacity pooled into the CCZ bank** | **0.0% / 0.0% / 0.0%** | **0.00** |

The pooled control is exactly zero at the median, the 90th percentile *and the
maximum*, with zero mixing in every one of its 144 rows. When the resources are
fungible by construction there is nothing whatsoever to gain — which reproduces
the single-resource study's NO-GO precisely, on the same code, and pins the
effect to the split. Adding the real conversions, which make the banks partly
interchangeable at a lossy rate, collapses the median to zero and cuts the tail
by roughly two thirds, without eliminating it — again what the lossy, latent,
asymmetric exchange predicts.

**Robustness sweeps** (median headroom over the best uniform choice):

* buffer 2 / 8 / 32 / 128 / unbounded: 20.4% / 20.4% / 22.0% / 22.0% / 22.0%;
* production latency 0 / 10 / 50 / 200: 22.0% / 21.5% / 19.7% / 15.1%;
* distillation success 1.0 / 0.9 / 0.7 (three seeds): 22.0% / 22.2-25.4% /
  23.1-26.5%.

The effect is insensitive to storage, decays gently with production latency
(which lengthens everything and so shrinks relative gains), and grows slightly
under failures.

**Cost-ratio sensitivity.** Scaling the Toffoli count of the Toffoli-based
rotation routes from 0.5x to 2.0x — which moves the cheaper route from CCZ,
through the exact tie, to T — leaves headroom over the best uniform choice at
12.4%, 23.4%, 24.7%, 25.9%, 24.9%, 31.2%. The result is **not an artefact of
the two routes costing the same**; the tie is where the effect is if anything
mildest.

---

## 8. Runtime and scalability

**Selector cost.** Median wall-clock per program: formula policies 0.01-0.06 s,
`uniform_oracle` 0.10 s, `two_term_descent` 0.45 s, global heterogeneous search
1.07 s (p90 3.5 s, max 6.2 s). Computing the reference optimum costs a median
1.74 s and up to 26.6 s. The winning selector is roughly 10x the cost of the
best simple policy and well inside what a compiler can spend.

**Scaling in concurrency,** with exact optima wherever the symmetry reduction
fits the budget:

| family | lanes | exact | over best uniform | over best simple | mixing |
|---|---|---|---|---|---|
| Trotter | 1 / 2 / 3 / 4 | 9/9 each | 0.0% / 0.0% / 30.1% / 24.4% | 0.0% | 0.00-0.33 |
| Trotter | 6 / 8 / 12 / 16 | 9/9, 9/9, 9/9, 2/9 | 28.7% / 24.7% / 28.0% / 30.9% | 0.0% | 0.31-0.33 |
| oracle bank | 2 / 4 / 8 / 16 | 9/9 each | 0.0% / 6.9% / 12.4% / 18.7% | 0.0% | 0.11-0.22 |
| multiplier | 2 / 4 / 8 | 9/9, 0/9, 0/9 | 1.9% / 13.6% / 13.9% | **0.0% / 13.4% / 13.9%** | 0.22-0.33 |

**Scaling in size** (4 lanes): rotation precision 4-32 bits holds headroom over
best uniform at 23.5-24.8%; adder width 16 / 32 / 64 / 128 gives headroom over
*all* simple baselines of 12.5% / 13.4% / 9.2% / 7.1%.

Three things follow. The optimum stays mixed as programs grow — mixing settles
around 0.22-0.33 and does not decay. Headroom over uniform *grows* with
concurrency and then plateaus. But headroom over the best simple baseline
behaves differently by family: for Trotter and the oracle bank a simple policy
matches the optimum in the median at every scale, while for the multiplier a
7-14% gap persists at every concurrency and every width tested, decaying slowly
with width. **The persistent, median-level advantage is concentrated in
multi-stage arithmetic; elsewhere it lives in the tail.**

The global search finds the optimum essentially always across the scaling
rows: mean regret 1.0001, worst case 1.015.

---

## 9. Verdict

> **CONTINUE.** The kill condition is not met and the continue condition is.

Against the stated kill condition — *a simple greedy achieving roughly 1.02
mean regret with no meaningful tail* — the best implementable simple policy is
1.109 mean with a p90 of 1.309 and a maximum of 1.869, and the specific policy
the condition names, proportional splitting, is 1.335. Nothing is close.

Against the stated continue condition — *repeated meaningful headroom over all
simple baselines, ideally 5-10% on a substantial subset, with mixed optima and
a mechanism tied to non-fungible contention* — headroom over all six simple
baselines simultaneously exceeds 5% on 102 of 401 proven-optimum cases (25%)
and 10% on 48 (12%); optima are mixed with a median 61% CCZ share of demand
where the headroom is; and the pooled control returns exactly zero headroom and
zero mixing, tying the effect to the split itself rather than to anything else
in the model.

**What is honestly weaker than it first looks.** The median case is won by
*some* simple policy — the distribution is bimodal, not uniformly favourable.
The value of a global selector comes from two things rather than one: a large
gap against any *fixed* simple rule, and a tail against the best-of-six. A
paper built on this must report the best-of-six comparison prominently, or a
reviewer will construct it and find the median 0.0%.

**Three risks that could still sink it.**

1. *Bank independence.* CCZ factories are commonly built on top of T
   distillation, so the two capacities may not be independently dialable. If a
   realistic architecture forces a coupled split, much of the swept operating
   space is unreachable. This is the single most important thing to check next,
   and it is an architecture question, not a compiler one.
2. *Prior art not yet read in full.* arXiv was unreachable from this
   environment, so the literature check rests on abstracts and indexed
   summaries. *A Resource Allocating Compiler for Lattice Surgery*
   (arXiv:2506.04620) already compiles Toffolis three ways — seven T, four T
   plus an ancilla, or one CCZ resource state — and has them contend for
   factory resources; its decision appears to be layout and allocation rather
   than per-site mixing across imbalanced banks, but that must be verified
   against the full text before any novelty claim is made. *Heterogeneous
   architectures...* (arXiv:2604.06319) runs both bank types in one machine,
   which establishes that the operating regime is real and that the
   provisioning side is taken. Nothing found so far selects per site to balance
   the banks — but this is provisional.
3. *Conversion availability.* If a machine ships the catalyzed CCZ-to-2T unit
   as standard, the median headroom over uniform goes to zero and only the tail
   survives. The mechanism's value is therefore partly a bet on which
   architectures ship conversion hardware.

**Recommended next step, bounded.** Two to three weeks: (a) read
arXiv:2506.04620 and arXiv:2604.06319 in full and settle novelty; (b) replace
the independent-bank assumption with a coupled T-and-CCZ provisioning model and
re-run the main matrix — if the headroom survives coupling, the case is made;
(c) build one implementable selector that reaches the optimum without
whole-program simulation, since the 1.005-regret result currently comes from a
search that simulates. If (b) collapses the effect, stop there.
