# Novelty audit: does existing work already do branch-aware distributed placement?

Searched through 2026-09-24 for distributed compilation of dynamic circuits,
control-flow-aware or measurement-aware placement, branch-sensitive
partitioning, adaptive placement driven by classical outcomes, expected-cost
placement, OpenQASM 3 control flow with distributed execution, and the named
systems. Where code was public it was read and run (see `ARTIFACT_AUDIT.md`);
where only a paper was found, the evidence level is stated.

## Evidence limits

This environment's network policy blocks arxiv.org and its mirrors (verified
again in the previous study: the proxy answers 403 to CONNECT). Papers could
therefore be read only through search-engine summaries unless their code was
on GitHub, which is reachable. Conclusions about paper-only systems are
abstract-level and are marked as such.

## Systems examined

| system | what it decides | handles measurement-dependent control flow? | branch-aware placement? | evidence |
|---|---|---|---|---|
| QuPort (neuralsorcerer/quport) | one global layout from a weighted interaction graph; Qiskit routing inside QPUs | accepts `if_else`/`while_loop`; drops any control-flow block touching 3+ qubits from the interaction graph | **no** | code read and run |
| memQ DQC (memQGit/dqc; arXiv:2609.15728, Sept 2026) | interaction-graph partitioning with time-sliced remapping, teleportation-based remote gates | parses OpenQASM 3, then passes `if`/`while` through as opaque statements with no qubits | **no** | code read and run |
| pytket-dqc (CQCL) | hypergraph partitioning, embedding, detached gates | rejects any circuit containing a measurement or conditional | **no** | code read |
| NetQMPI / NetQIR (NetQIR/netqmpi) | nothing automatically: an SPMD programming model with explicit `qsend`/`qrecv` | a `ClassicalControlledGate` primitive exists | **no** — placement is manual | code read |
| Qoala | an application execution environment for quantum-internet nodes, a NetQMPI backend | runtime scheduling of node programs | not a placement compiler | abstract-level |
| DisMap | noise-aware virtual topology guiding partitioning and mapping | not indicated | not indicated | abstract-level |
| AdaptDQC | selects among compilation strategies according to user goals | not indicated | not indicated | abstract-level |
| Time-aware partitioning (arXiv:2603.04126) | a beam search over qubit assignments across successive *time* steps | not indicated | placement varies over **time**, not by branch | abstract-level |
| RL distributed compilation (arXiv:2608.06892) | communication actions in a constrained MDP | not indicated | not indicated | abstract-level |
| Branch-aware constant propagation (arXiv:2606.02018) | constant propagation through dynamic-circuit branches | yes | not distributed; a single-QPU optimisation | abstract-level |
| Compile-time simplification of classically controlled ops (arXiv:2605.28439) | simplifies classically controlled operations at compile time | yes | not distributed | abstract-level |
| Dynamic-circuit benchmarking framework (arXiv:2604.03360) | computes *features* of dynamic circuits weighted by branch probability | yes | a benchmarking method, not a compiler | abstract-level |
| OpenQASM 3 to CUDA-Q transpilation (arXiv:2604.11599) | lowers OpenQASM 3 control flow to CUDA-Q kernels | yes | not distributed | abstract-level |

## Two things that must not be confused

**Placement that changes over time is not placement that changes by branch.**
Several distributed compilers (memQ DQC, the time-aware partitioner) remap
qubits between time segments. That is well studied. Branches are mutually
exclusive rather than sequential, and nothing found conditions a remapping on
a measurement outcome.

**Probability-weighted features are not probability-weighted placement.** The
dynamic-circuit benchmarking framework weights features by branch probability,
which is the same expected-value idea, applied to characterising circuits
rather than to compiling them.

## Verdict

No existing compiler, paper or artifact found performs placement or
partitioning as a function of measurement-dependent control flow or branch
probabilities. The two executable compilers that accept dynamic programs are
worse than control-flow-insensitive: they do not see branch communication at
all.

So the capability is **not subsumed by prior work**. That removes one NO_GO
trigger. It does not by itself make the capability worth building; whether it
is depends on the measured headroom, which is the subject of the report.
