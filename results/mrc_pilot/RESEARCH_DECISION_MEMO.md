# Research-decision memo: is resource-compositional implementation selection a compiler contribution?

Scope. This memo closes the bounded investigation that followed the T+CCZ
evidence memo (`EVIDENCE_MEMO.md`). It does not write the paper. Every number
below comes from a CSV in this directory; synthetic and external workloads are
never pooled. Kernel results from earlier phases are used as established and
were not rerun except where a code change required it (the share-aware
baseline's concurrency count was corrected in phase 7, see item 5).

## 1. Novelty boundary

Full detail: `NOVELTY_AUDIT.md`. The three named works could not be read in
full from this environment (arXiv and every mirror return 403), so the audit
rests on the complete source code of the compiler behind arXiv:2506.04620 and
on the abstracts of arXiv:2608.03315 (Harvest) and arXiv:2604.06319.

- arXiv:2506.04620 (code-verified): one fixed 7-T Toffoli, no CCZ anywhere in
  64 files, first-fit binding of gates to factory externs. Allocation, routing,
  placement and scheduling. Does not select implementations.
- Harvest (abstract-level): placement, routing, timestep scheduling and
  magic-state *supply* under a protocol-agnostic model. Its per-operation
  protocol choice (distillation vs cultivation) is the nearest neighbour and is
  a supply-side choice, not a choice among program implementations, as far as
  the abstract shows.
- arXiv:2604.06319 (abstract-level): heterogeneous hardware and encoding per
  subsystem with cross-subsystem orchestration. Not implementation selection.

Verdict: the novelty statement is defensible against the code-verified work,
not contradicted but not established against the other two, and overreaches
at the compiler-theory level unless it is placed against high-level-synthesis
module selection and heterogeneous instruction selection, where "equivalent
implementations with different resource signatures, chosen jointly" is
classical. The defensible novelty is the resource class: rate-limited,
buffered, consumable streams from fixed hardware, where equivalent
implementations draw on different streams and the right choice at a site
depends on the temporal supply state left by the other sites. Status:
CONDITIONAL on a full-text reading of Harvest before any submission.

## 2. Coupled provisioning result (phase 2, `mrc5_coupled.csv`)

Models at a fixed factory area, literature parameters (15-to-1 T distiller,
8-to-1 CCZ distiller from Gidney and Fowler 2019, catalysed CCZ-to-2T): A
independent banks; B one raw level-1 stream feeding both distillers; C model B
plus catalysis. Example composition, model C at 400 tiles and CCZ share 0.5:
14 T distillers, 2 CCZ distillers, raw stream 22 states per cycle, effective
T rate 1.27 and CCZ rate 0.33 per cycle. Eight decisive kernels and two null
kernels, three shares each; optima proven exactly in 208 of 216 decisive
cells.

Headroom of the exact optimum over the best of seven simple policies, decisive kernels (n = 24 per cell):

| area | model A med / p90 / >5% | model B med / p90 / >5% | model C med / p90 / >5% |
|---|---|---|---|
| 200 tiles | 5.4% / 10.7% / 12 | 1.3% / 14.7% / 9 | 4.1% / 11.9% / 12 |
| 400 tiles | 2.1% / 10.9% / 9 | 1.8% / 16.6% / 8 | 3.3% / 13.3% / 11 |
| 800 tiles | 0.0% / 13.8% / 7 | 0.0% / 11.8% / 8 | 0.0% / 6.4% / 5 |

Raw-stream sensitivity at 400 tiles (scarce, cheap, expensive, and the
literature-faithful "raw inside the factory footprint"): medians 0.5% to 6.5%,
p90 8% to 19%, 8 to 14 of 24 cells above 5%, for both B and C. Null kernels:
0.0% median in every model, maximum 4.8% in one cell. Coupling therefore does
not kill the effect and does not need unusual parameters to keep it; more area
(800 tiles) weakens it, as supply pressure falls. The kill condition is not
met. The caveat is that these are the synthetic decisive kernels; the external
workloads in item 7 are the real test.

## 3. Formulation

- Program: a DAG of operations. A decision site s has a variant set V(s) of
  fragments with identical semantics under stated preconditions (ancilla
  available, classical feed-forward allowed, a recognised uncompute partner).
- Resource signature of a variant: a vector of magic-state counts per species
  (here T and CCZ) together with its sequential consumption layers. Species
  are non-fungible: one cannot stand in for another except through the
  machine's conversions, which are lossy and rate-limited.
- Machine: per-species banks with production rate, latency and a bounded
  buffer, plus conversions (inputs, outputs, latency, concurrency) and, in the
  coupled models, a shared upstream stream. Production continues whether or
  not there is demand; a full buffer discards output; a consumer with empty
  stock stalls.
- Objective: makespan of the assigned program on the machine.
- Local information: a site's own signatures and the machine's nominal rates.
  Global information: the buffer trajectory induced by every other site's
  choice. Per-site policies use only the former; the exact oracle and the
  stage DP use the latter.
- What makes this a compiler problem rather than allocation: the choice
  changes *which* resource is demanded, not where an already-decided demand
  is served. The pooled control (one fungible pool) yields exactly zero
  headroom, so the problem exists only because the signatures load different
  pools. Relative to HLS module selection the resources are flows with
  buffers, not areas, and the coupling between sites is temporal.

## 4. When and why local selection fails (phase 4, `mrc6_features.csv`, `mrc6_rules.csv`)

Definition of failure: the exact optimum beats every simple policy by more
than 5%. Across the 480 synthetic cases this happens in 121 (25.2%).

- Mechanism, verified on cases: the optimum alternates banks across sequential
  stages so that production a uniform plan would waste is consumed. In the
  modular-exponentiation kernel the optimum runs mix, CCZ, mix, CCZ across its
  four stages for 567 cycles where the best uniform plan takes 747 and leaves
  170 T states discarded from a full buffer while the CCZ consumer stalls 359
  times.
- Necessary condition: every one of the 121 failures has at least two stages;
  single-stage kernels fail in 0 of 80 cases. Failure rates rise with the
  waste a uniform plan would incur (terciles: 10.6%, 25.2%, 39.8%).
- Predictability from structure alone is weak: the best single rule
  (supply CCZ share at most 0.65) reaches F1 0.53 leave-one-kernel-out; the
  best conjunction (imbalance at most 2.7 and at least 3 stages) reaches
  F1 0.57. Failure is a joint property of program structure and the machine's
  balance against per-stage demand. That is why a static rule cannot replace
  a selector that carries machine state, and it is the honest limit of any
  "structural" story.

## 5. Selector (phase 5, `mrc7_selector.csv`)

A stage-wise dynamic program over (stage, carried buffer stock) with Pareto
pruning of the frontier. Stage costs come from a two-term analytic model with
carried stock (mode "analytic"), optionally with the best five DP solutions
re-scored by one full simulation each ("r5"), or from a stage-local simulation
(mode "sim"). No global simulation search is involved.

On the 401 cases with a proven optimum:

| selector | mean | median | p90 | max | >5% | >10% | median seconds |
|---|---|---|---|---|---|---|---|
| best simple policy | 1.035 | 1.000 | 1.121 | 1.359 | 102 | 54 | - |
| global simulated search | 1.005 | 1.000 | 1.000 | 1.244 | 14 | 5 | 0.880 |
| stage DP, analytic + r5 | 1.004 | 1.000 | 1.000 | 1.200 | 11 | 4 | 0.093 |
| stage DP, sim | 1.006 | 1.000 | 1.005 | 1.208 | 15 | 9 | 0.227 |

The DP meets the 1.02 mean-regret target, dominates every simple baseline,
costs 5.7 times less than the search in total (8 to 20 times on the larger
families) and beats the search outright on 50 of 480 cases (worse on 33). The
tail is not gone: the analytic mode misjudges two-stage AND ladders (up to
1.20) and, on the external chains under coupled machines, misprices the
distiller pipeline (up to 1.15 in the phase 7 smoke test) where the sim mode
is exact. The selector is the technique; the search stays a reference. Note:
the share-aware baseline previously divided the machine by all concurrent
DAG nodes including Cliffords; it now counts only magic-consuming sites, which
strengthens that baseline on extracted programs and changes nothing on the
stored kernel results.

## 6. Decision-site extraction (phase 6, `mrc8_sites.csv`, `src/ftqc_delivery/mrc/extract.py`)

Implemented for gate streams over qubit lines, with adapters for qmpa
circuits and qualtran bloqs. Every Toffoli becomes a site; dependencies follow
qubit lines, including through dropped Cliffords. Per site the record holds:
family and role, gate index and lines, depth, partner site, allowed variants,
resource signature per variant, ancillas, source per variant, and the
equivalence assumption.

- Variants. A standalone Toffoli may use one CCZ state, 4 T with an ancilla
  and feed-forward (Jones 2013; Gidney 2018), or 7 T at depth 3 or 1. The
  compute half of a recognised compute/uncompute pair uses one CCZ or 4 T into
  a fresh ancilla and its uncompute is a measurement costing no magic states;
  in-place 7-T forms are dominated there and are not offered.
- Pair recognition is symbolic: line values are tracked as XOR-sets of atoms
  with hash-consed ANDs, and a later Toffoli on the same lines is the
  uncompute when both controls provably hold the compute-time values. On the
  eleven qualtran programs, whose IR marks And and And† explicitly, the rule
  agrees with the markers on every pair (e.g. 45/45 in ModSub, 41/41 in
  CModAdd, 15/15 in GreaterThan) with no false pairs. On the eight qmpa
  circuits every Toffoli belongs to a pair.
- Result on real arithmetic: all sites are pair computes with two variants
  (CCZ or 4 T); no standalone Toffolis occur in either library. Programs are
  narrow: width 1 for adders, comparators and modular adders, width 2 for the
  qmpa multipliers and dividers, width 4 for GreaterThan.
- Plan: rotations (phase-gradient adder vs Toffoli-count synthesis vs
  Clifford+T synthesis) as a second family with a genuinely different
  signature; controlled adders and CSWAP as multi-Toffoli sites; a bloq-graph
  front end so qualtran's own markers drive the sites; and an OpenQASM 3
  front end with annotations for uncompute intent.

## 7. External workloads (phase 7, `mrc8_external.csv`, `mrc8_sites.csv`)

Nineteen programs from two independently authored libraries (eight qmpa
circuits: adders, multipliers, dividers; eleven qualtran bloqs: adders,
subtractor, controlled and constant adders, two comparators, modular add,
subtract, negate and controlled add), 28 machines each (the synthetic grid's
20 independent-bank machines plus 8 coupled B/C machines), 532 cases,
Cliffords kept. Optima are proven exactly in 163 cases (the programs with at
most eight sites); elsewhere the reference is the best assignment found by the
search and every policy, so headroom is a lower bound on the optimum's and
selector regrets are relative to that reference. Nothing was arranged: the
extractor found the sites, and the machines are the ones the synthetic study
used.

- Structure. All Toffolis are compute/uncompute pairs, so every site has two
  variants (one CCZ or 4 T). Thirteen of nineteen programs are serial chains
  of width 1 (every adder, the comparator against a constant, modular add,
  subtract and negate, controlled modular add); the multipliers and dividers
  have width 2; GreaterThan has width 4.
- Headroom over the best of seven simple policies: mean 0.9%, median 0.0%,
  p90 4.2%, max 14.8%; above 5% in 48 of 532 cases (9%), above 10% in 6 of
  532 (1%, all GreaterThan). Over the best uniform plan: mean 1.1%. qmpa:
  mean 1.3%, above 5% in 35 of 224, none above 10%. qualtran: mean 0.7%,
  above 5% in 13 of 308.
- Every width-1 program has exactly zero headroom on all 28 machines. Headroom
  appears only where a stage holds two or more parallel sites: divider 5.4%
  (proven exact, identical on 13 of 20 independent-bank machines) and 8.6%,
  multipliers up to 5.2%, GreaterThan mean 4.5% and up to 14.8%. The coupled
  models show the same pattern (B: above 5% in 5 of 57; C: 8 of 95).
- Mechanism on real programs, verified by tracing: parallel sites in a wide
  stage contend for a small CCZ bank and the optimum sends some of them to the
  T bank. GreaterThan on 20 T factories and 1 CCZ factory: the best uniform
  plan is all-4T at 108 cycles with 18 T stalls; the reference runs the two
  4-wide stages as 2 CCZ + 2 T and the serial tail on CCZ, 92 cycles. Divider:
  moving one site of a 2-wide stage to T removes all 8 CCZ stalls (92 to 87).
  This is the intra-stage partitioning form of the mechanism; the temporal
  alternation across stages that drives the synthetic modexp kernels does not
  arise here because these programs' stages are single sites.
- The simplest static rule (one implementation per family, fewest
  T-equivalents, i.e. CCZ everywhere) is the best simple policy in 497 of 532
  cases.
- Selector on external programs: the stage DP as evaluated in phase 5 has mean
  regret 1.022 and exceeds 5% in 82 cases, and it is poor on the coupled
  machines (mean 1.04 on B, 1.07 on C; stage-local simulation worse at 1.066):
  the stage costs carry stock but not factory phase, and over 30 to 100
  single-site stages the error compounds. Adding the uniform plans as
  finalists (`include_uniform`, evaluated from stored makespans because
  finalists are ranked by exact simulation) gives mean 1.007, p90 1.027, max
  1.094, above 5% in 26 of 532, never worse than uniform; it beats the best
  simple policy in 39 cases and loses in 19, and captures on average 47%
  (median 56%) of the available gain on the 48 cases with more than 5%
  headroom. On external programs the selector is at parity with the best
  simple policy and recovers about half of the tail.
- Sensitivity, resource layers only (Cliffords dropped; six programs on the
  quick grid): the 42 cases (six programs, seven machines each, none with a proven optimum) show more headroom than with Cliffords kept: mean 3.5%, median 0.4%, p90 9.3%, max 21.4%, above 5% in 11 of 42 and above 10% in 3. Without the Clifford critical path the chains become supply-bound, so even the 32-bit adder gains up to 10% (5.3% on the independent-bank machines) and the multiplier and comparator reach 19% and 21% (qmpa_add32 max 10.0%, qmpa_div6 max 15.8%, qmpa_mul6 max 19.1%, qt_cadd8 max 9.0%, qt_gt8 max 21.4%, qt_modadd8 max 2.5%). The primary numbers above are the conservative ones; the effect grows as Clifford cost shrinks relative to magic-state delivery, which is the direction real lattice-surgery Clifford costs point when they are far below one cycle per gate, but this run is a small grid and its references are search-based.

## 8. Decision: HOLD

Not GO: on independently authored arithmetic the phenomenon is rare and
small. The median headroom is zero, 9% of cases exceed 5%, 1% exceed 10%, and
every serial-chain program shows none at all. The synthetic figures (25% of
cases failing local selection, gains up to 46%) are not representative of
these programs and cannot be used to claim prevalence. The selector is not yet
convincing: it needs the uniform guard to avoid losing, and with it ties the
best simple policy on external programs while recovering half of the tail.
The novelty claim is conditional on a full-text reading of Harvest.

Not NO_GO: the mechanism is real, was traced on real programs, survives
coupled provisioning at fixed area with literature parameters and without
unusual settings, is exactly zero in every null control, and the extractor
finds the sites in two independent libraries without hand-arrangement,
agreeing with qualtran's explicit markers on every pair.

What would turn HOLD into GO, in order:

1. An external workload class with wide Toffoli stages showing at least 10%
   headroom under the coupled models: parallel-prefix (Draper) adders,
   multi-operand adders, batches of Toffoli-count rotation synthesis, QROM and
   unary iteration. Run them through the extractor unchanged.
2. A second family with different signatures at the same site (rotations:
   phase-gradient vs Toffoli-count vs Clifford+T synthesis), to show the
   problem is not the AND/Toffoli special case.
3. A selector that carries factory phase across stages (or a rolling-horizon
   simulation) with mean regret at most 1.02 on the external cases and a
   clear win over the best simple policy on the tail.
4. Harvest read in full and the audit updated.

What would turn HOLD into NO_GO: item 1 giving a median below 5% on
wide-stage external programs under coupled machines, or Harvest already
selecting among implementations per operation.

## 9. Venue ceiling

- On today's evidence: a QCE or TQE-style paper on T/CCZ implementation
  selection under coupled provisioning, with the exact oracles, the coupled
  models, the traced mechanism, the extractor and honest external numbers.
  Modest and defensible.
- CGO becomes plausible only with items 1 to 3 above: an implementable
  selector that beats simple policies on external workloads where the
  headroom exists, framed as site extraction, equivalence records and
  resource signatures.
- PLDI is out of reach on the current evidence. The phenomenon is rare on real
  programs, the formal content is an instance of module selection with flow
  resources rather than a new compiler abstraction, and the novelty
  statement is conditional. Reaching it would need the general formulation
  to deliver something beyond the instance (a compositional cost calculus
  with a guarantee, or a bound showing local selection can be arbitrarily
  bad with a matching selector), two resource families, and external
  workloads where the effect is common rather than occasional.
