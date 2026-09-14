# Novelty audit: is per-site implementation selection across non-fungible magic-state pools already solved?

Status of the reading. The environment's egress policy blocks arxiv.org and
every mirror tried (ar5iv, alphaxiv, export.arxiv.org, journal hosts all
return 403), so none of the three papers could be read in full here. What was
read instead is stated per work below, and every judgement carries the
confidence its evidence supports. The one work whose *implementation* is
public was read at the code level, which is stronger evidence about what the
compiler actually decides than its abstract.

| work | evidence read here | confidence |
|---|---|---|
| arXiv:2506.04620, *A Resource Allocating Compiler for Lattice Surgery* | the complete source of the compiler it describes (github.com/Alan-Robertson/Surface_Code_Compiler, commit e5f1052, 64 Python files) plus the README and the abstract | code-grounded |
| arXiv:2608.03315, *Harvest: Resource-Aware Quantum Compilation for Magic State Protocols* (Pflieger, Swierkowska, Giortamis, Bhatotia, Aug 2026) | abstract and indexed summaries only | abstract-level |
| arXiv:2604.06319, *Heterogeneous architectures enable a 138x reduction in physical qubit requirements ...* (Mundada et al., Q-CTRL, Apr 2026) | abstract and indexed summaries only | abstract-level |

## The eight questions, per work

### 1. arXiv:2506.04620 (code read in full)

1. What is selected. Placement of extern blocks (factories) on the surface-code grid, binding of each T-consuming gate to a factory instance, routing between patches by biased A* search, and the ordering of gates by DAG layer. The compiler is a placement, allocation, routing and scheduling engine over a fixed gate-level DAG.
2. Alternative implementations of one logical operation represented? No. `Toffoli` in `src/surface_code_routing/lib_instructions.py:62-79` is one fixed decomposition (T-count 7, the Amy-Maslov-Mosca-Roetteler form). The T gate it emits is a callable parameter (`T=T`), so a program author could pass a different T realisation, but the compiler holds no library of alternatives and never chooses among them. `MAJ` and `UMA` (lines 96-109) build a Cuccaro adder from that one Toffoli.
3. Can different sites choose differently? Not by the compiler. A different choice at one site would have to be written into the program by hand. The only per-site decision is which idle extern serves a gate: `dag.py:424`, "Grab the next matching binding", takes the first idle extern that satisfies the gate.
4. Does implementation choice alter the magic-state species consumed? There is one species. The string "CCZ" does not occur anywhere in the 64 source files.
5. Joint or local? Extern binding is greedy and online during scheduling (first fit over idle externs, layer by layer). Nothing is chosen jointly across the program.
6. T and CCZ provisioned independently or jointly? Not applicable: T only.
7. Primary problem. Factory allocation, placement, routing and scheduling under a Litinski-style costing.
8. Solves our decision problem? No. It has no implementation alternatives, one magic-state species, and no global choice.

### 2. arXiv:2608.03315 Harvest (abstract-level)

1. What is selected. From the abstract: patch placement ("circuit-aware placement"), congestion-aware routing, timestep-by-timestep scheduling, the supply of magic states under a "protocol-agnostic resource model" in which states come from distillation factories or cultivation, and layout pruning ("reclaims up to 72.0% of unused layout footprint").
2. Alternative implementations of one logical operation? Nothing in the abstract indicates that the circuit's operations have alternative decompositions. The variability described is on the *supply* side: which protocol (distillation vs cultivation, "each trading footprint against preparation latency") produces a state, and which terminal delivers it.
3. Different sites choosing differently? Unknown at this evidence level. If Harvest picks the supplying protocol per consuming gate, that is a per-site choice among supply options, which is the closest thing in the three works to what this project does. It is still not a choice among program implementations with different resource signatures.
4. Species altered by the choice? Not indicated; the abstract speaks of magic states generically, in the T-gate sense.
5. Joint or local? "Schedules operations timestep by timestep under routing and availability constraints": greedy over time, with placement decided ahead. No global implementation choice is described.
6. T and CCZ jointly provisioned? Not applicable as far as the abstract shows.
7. Primary problem. Placement, routing, scheduling and magic-state supply/protocol co-optimisation for lattice surgery.
8. Solves our decision problem? Not on the evidence available. This is the work most likely to contain an overlap in its full text (protocol selection per operation), and it must be read in full before any paper is written.

### 3. arXiv:2604.06319 (abstract-level)

1. What is selected. Hardware modality and QEC encoding per subsystem ("task-specific hardware selection and QEC encoding"; processing modules separated from memory), plus a compiler that "schedule[s] and orchestrate[s]" algorithms across subsystems at the scale of a thousand logical qubits.
2. Alternative implementations of one logical operation? The heterogeneity is architectural: where and in which code an operation runs. No per-operation choice among Clifford+T decompositions is indicated.
3. Different sites choosing differently? Unknown. Assignment of operations to modules is a placement decision, not an implementation decision.
4. Species altered? Nothing on T versus CCZ.
5. Joint or local? Unknown beyond "schedule and orchestrate".
6. T and CCZ provisioning? Not indicated.
7. Primary problem. Heterogeneous architecture design with cross-subsystem scheduling and interface microarchitecture.
8. Solves our decision problem? Not on the evidence available.

### Directly related work found through their references and searches (abstract-level unless stated)

- Gidney and Fowler 2019 (arXiv:1812.01238): the origin of the T-versus-CCZ trade-off and the catalysed CCZ-to-2T conversion. A hand analysis of factory designs, not a compiler; it is where our variant costs come from.
- Ding et al., MICRO 2018, magic-state functional units: mapping and scheduling of multi-level distillation circuits. Factory-side allocation.
- Molavi, Xu, Tannu, Albarghouthi, OOPSLA 2025, dependency-aware compilation for surface-code architectures: routing and scheduling of a fixed circuit.
- PureMagic (arXiv:2512.06484): a dynamic scheduler for lattice surgery. Scheduling.
- C-Phase-aware compilation (arXiv:2605.14042) and the platform-aware compilation framework (arXiv:2609.08908): compilation targets and gate-set awareness; nothing read suggests per-site selection across resource pools.
- "When T-depth misleads" (arXiv:2604.11409): predicts slowdown under delivery constraints. This is the angle the single-resource study of this repository was found not to own (see `results/rac_pilot/GO_NO_GO_MEMO.md`).
- Quartz and other superoptimisers: rewrite among equivalent circuits, but with scalar gate-count costs, not multidimensional consumable resources.
- Outside quantum: module selection in high-level synthesis (choosing among functionally equivalent hardware modules with different area and latency, jointly with scheduling, under a resource budget) and instruction selection with heterogeneous functional units are the classical forms of "semantic equivalence does not imply resource interchangeability". Those are area or occupancy resources. Magic states are consumable, produced at a fixed rate, buffered and perishable in the sense that an unconsumed buffer slot is wasted production; the decision therefore interacts with the *temporal* supply state, which is what the mechanism found in this project (temporal alternation between banks across sequential stages) exploits. That distinction is the real content of any general-compiler claim, and it must be stated against the HLS lineage rather than as if implementation selection itself were new.

## Comparison matrix

| question | 2506.04620 (code) | Harvest (abstract) | 2604.06319 (abstract) | this project |
|---|---|---|---|---|
| what is selected | factory binding, placement, routes, order | placement, routes, timesteps, supply protocol, layout | hardware/code per subsystem, orchestration | implementation per decision site |
| alternatives of one operation represented | no (one Toffoli) | not indicated | not indicated | yes, with sources |
| sites of one family may differ | no | unknown | unknown | yes |
| choice changes species consumed | no (T only) | not indicated | not indicated | yes (T vs CCZ) |
| joint or local | local, greedy | timestep-greedy | unknown | joint (exact oracle, stage DP) |
| T and CCZ provisioning | T only | not indicated | not indicated | independent and coupled models |
| primary problem | allocation/routing/placement/scheduling | placement/routing/scheduling/supply | architecture/orchestration | implementation selection |
| solves our problem | no | not on available evidence | not on available evidence | - |

## Verdict on the novelty statement

The statement to test was: "Existing resource-aware FTQC compilers primarily
optimize generation, allocation, routing, placement, or scheduling of
magic-state resources; our problem concerns globally choosing among
semantically equivalent program implementations whose resource signatures load
different non-fungible resource pools."

- Against arXiv:2506.04620 the statement is **defensible and code-verified**: that compiler has no implementation alternatives, one species, and first-fit binding.
- Against Harvest and arXiv:2604.06319 the statement is **not contradicted by their abstracts but not established** either. Harvest's per-operation protocol choice is the nearest neighbour and is a supply-side choice, not an implementation choice, on the evidence available. This is exactly the situation the brief warned about (novelty from abstracts only), so the honest status is **CONDITIONAL**: the claim may be carried forward as a working hypothesis, must be written as "not addressed by [these works] to our knowledge", and must be re-audited against Harvest's full text before any submission.
- At the compiler-theory level the statement overreaches if read as "implementation selection under non-fungible resources is new": it is not (HLS module selection, heterogeneous instruction selection). What is new, as far as this audit can see, is the instance in which the resources are rate-limited, buffered, consumable streams from fixed hardware and equivalent implementations draw on different streams, so that the right choice at a site depends on the temporal supply state left by the other sites.

Result: **no NO_GO from the audit**, but no clean GO either. The novelty
boundary is narrower than the brief's phrasing and is conditional on a
full-text reading that could not be done from this environment.
