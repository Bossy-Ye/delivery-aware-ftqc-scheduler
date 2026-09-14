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

## 7. External workloads (phase 7, `mrc8_external.csv`)

PENDING_MRC8

## 8. Decision

PENDING_DECISION

## 9. Venue ceiling

PENDING_VENUE
