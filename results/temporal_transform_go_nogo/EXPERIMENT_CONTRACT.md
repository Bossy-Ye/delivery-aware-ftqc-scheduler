# Experiment contract: can a semantics-preserving transformation reshape temporal magic-state demand?

Frozen on 2026-09-23, before any decisive run. Baseline repository commit
`7b75206d1c4e00e6f9fa891f221493c602987440`, 153 tests passing. Thresholds in
section 8 are not to be changed after results exist.

## 1. Research question

Can a semantics-preserving transformation of a real structured quantum program
materially reduce fault-tolerant execution time by reshaping *when* magic
states are demanded, without materially reducing T-count?

## 2. Hypothesis

Some structured programs expose legal execution and reordering freedom that
conventional lowering loses or exploits poorly. Rearranging independent
high-level regions can smooth bursts of magic-state demand and reduce FT
makespan even when the logical computation and the T-count are unchanged.

This is not a T-count experiment. The effect must come mainly from changing
*when* magic states are demanded.

## 3. What the existing FT model already does, stated up front

The execution model in `ftqc_delivery.mrc.execution` is a dependency-driven
list scheduler: it dispatches any operation whose predecessors have completed
and whose resource is in stock, with critical-path priority and program order
only as a tie-break. Two consequences are fixed before results are seen:

1. A pure permutation of already-independent regions cannot change the
   dependency graph, so it can change a schedule only through tie-breaking.
   Such a transformation is therefore not expected to do anything, and is not
   one of the transformations under test.
2. What a source-level transformation *can* change is the dependency graph
   itself, and hence which schedules are legal at all.

The experiment therefore tests transformations that change the graph.

## 4. Transformations under test

All of them keep the gate list, the operation multiset, the T-count and the
CCZ-count exactly as they were. Only the edges change.

### T1 `commuting` — commutation-aware lowering

Conventional lowering makes a gate depend on the previous gate touching any of
its lines. That is stricter than the physics. A control line is read, not
written; every line of a diagonal gate is read. Two gates that only read a
line commute exactly. Building the graph from reads and writes (read after
write, write after write, write after read) removes the false edges.

Legality: every pair of gates the resulting graph leaves unordered writes
nothing the other touches, so each such pair commutes exactly, and any two
linear extensions differ by transpositions of commuting gates. Verified per
workload, see section 6.

### T2 `pace(k)` — demand pacing

Chain the magic-consuming sites so that site *i* waits for site *i − k*: at
most *k* of them are ever in flight. Only edges are added, and adding an edge
to an acyclic graph removes orderings rather than creating them, so every
schedule of the result was already legal. Depth grows and work is unchanged,
so any makespan reduction cannot be reduced depth or reduced work. This is the
transformation that isolates temporal smoothing.

Applied at k in {1, 2, 4, 8}, on top of both the conventional and the
commuting graph.

### Not under test

Pure region reordering (subsumed by the scheduler, see section 3), anything
that changes the algorithm, the approximation, the precision, or the amount of
work, and anything requiring an independence the program does not have.

## 5. Workloads

The frozen corpus of `src/ftqc_delivery/mrc/corpus.py`, 22 programs from three
independently authored sources, unchanged from the previous study:

| source | version | programs |
|---|---|---|
| qmpa (Alan Robertson, UTS) | commit `47e27d38a55f5161baac7805f9cc06a8146aa064` | 5 |
| qualtran (Google Quantum AI) | 0.7.0 | 11 |
| QASMBench (PNNL) | commit `357b942396d5c2b7cbc1c229c585a6ef5ccaebac` | 6 |

Structures covered: QFT, phase estimation, state preparation including alias
sampling, QROM and lookup, SAT oracles, multipliers, dividers, square root,
parallel adders, modular arithmetic, an AND ladder. No synthetic workload is
used as evidence; none is used at all.

Inclusion rule: the program must be extractable by the existing decision-site
extractor without hand editing, every gate must be modelled, and the
transformation's legality must be verified at the level section 6 requires. A
workload whose verification fails is excluded from decisive results.

### Negative controls, fixed in advance

Chosen by structure, not by outcome: programs whose dependency chain is
genuinely serial, so the commuting graph can expose no freedom. Measured
before the decisive run, the workloads whose critical path is unchanged by T1
are `qmpa_draper8`, `qmpa_draper16`, `qt_multiand10`, `qb_sat_n7`,
`qb_sat_n11` and `qb_sqrt_n18`. Expected result: approximately zero
improvement. An abundant-supply control is also required, see section 7.

## 6. Semantic verification

Each workload is verified at the strongest level its size allows, and the
level is recorded in `TRANSFORMATION_VALIDATION.csv`:

* `unitary` (up to 11 qubits): the full unitary of the original gate order
  equals that of three random linear extensions of the transformed graph;
* `statevector` (up to 22 qubits): the same comparison on random input states;
* `structural` (larger): every unordered pair of gates is checked to write
  nothing the other touches, which is the premise of the commutation argument.

For pacing, preservation is inherited: the transformed graph's edges are a
superset of the original's, so its schedules are a subset of already-legal
ones.

## 7. Machine configurations

From the existing coupled models, at fixed factory area, model A (independent
banks) unless stated:

| label | role |
|---|---|
| `A_200_0.5` | constrained |
| `A_400_0.25`, `A_400_0.5`, `A_400_0.75` | constrained, with the split varied |
| `B_400_0.5`, `C_400_0.5` | constrained, shared raw stream and with catalysis |
| `A_800_0.5` | moderate |
| `A_3200_0.5` | abundant-supply control |

Buffer capacity is varied in the mechanism ablations (16, 32 default, 64), as
is the factory area, rather than relying on one tuned configuration.

## 8. Metrics

Primary: **FT makespan in logical cycles**.

Secondary, per run: total magic-state stall cycles, per-resource stalls, peak
buffer backlog and overflow (wasted production), peak and mean per-stage
demand, burstiness (coefficient of variation of per-stage demand), logical
depth (critical path), available parallelism, T-count and CCZ-count,
space-time volume, and factory utilisation.

Implementation choice is held **fixed** between the original and the
transformed program, so that nothing is measured except temporal structure.
Two frozen assignments are run: `ccz` (each eligible site consumes one CCZ
state) and `t` (each site is built from T states), so that the T-count claim
is checkable on a version whose demand is entirely T.

## 9. Screening gate

Two promising structured programs, one strongly dependent negative control,
constrained and abundant settings. If no valid transformation reaches 5% FT
makespan improvement under constrained supply while remaining near zero under
abundant supply, stop and report likely NO_GO.

## 10. Decision thresholds

### GO — all of:

1. At least 3 real programs show >=10% reduction in FT makespan.
2. They come from at least 2 independently authored sources.
3. Semantics verified equivalent.
4. T-count changes by <=2%, preferably 0%.
5. The improvement is primarily explained by reduced magic-state stalls and
   backlog rather than by reduced gate count.
6. The effect survives more than one constrained or moderate configuration.
7. The advantage becomes small or disappears under abundant supply.
8. At least one transformation pattern is general enough to become an
   automatic compiler pass rather than a per-program trick.

### HOLD

Improvements consistently 5-10%; only one or two workload families benefit;
the effect is real but legality or generalisation is unclear; or it needs a
narrow machine configuration.

### NO_GO

Improvements below 5% almost everywhere; benefit only in synthetic examples;
legal reordering opportunities rare; improvements vanish under proper
dependency checking; benefit mainly from lower T-count; only one tuned
configuration shows it; current compilers already do it; or the transformation
cannot plausibly become a compiler analysis.

## 11. Mechanism hypotheses to separate

* **H1 temporal smoothing**: bursts and backlog against finite-rate production
  fall.
* **H2 depth reduction**: the transformation simply shortened the dependency
  depth.
* **H3 work reduction**: less actual work. Excluded by construction here, and
  checked by comparing operation counts.
* **H4 model artifact**: the result depends on one buffer or factory setting.

Discriminators fixed in advance: H1 predicts the advantage grows as supply
tightens and vanishes under abundance, and that stalls and overflow fall. H2
predicts the advantage is largest under abundance, where makespan tracks
depth. Pacing increases depth, so any pacing win is evidence for H1 and
against H2. Buffer and factory-rate sweeps test H4.

## 12. Determinism

One seed, `20260923`, for the machine arrival series and for every random
linear extension. Distillation succeeds deterministically in all
configurations here, so a run reproduces exactly.

## 13. Outputs

`EXPERIMENT_CONTRACT.md`, `WORKLOADS.md`, `TRANSFORMATION_VALIDATION.csv`,
`RAW_RESULTS.csv`, `SCREENING_RESULTS.md`, `MECHANISM_ANALYSIS.md`,
`NOVELTY_AUDIT.md`, `GO_NO_GO_MEMO.md`. Existing result files elsewhere in the
repository are not modified.
