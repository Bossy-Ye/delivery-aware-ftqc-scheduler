# Novelty audit: does anything here not already exist?

The question is narrow, and is not whether these tools discuss resource
constraints. It is:

> Do they already perform the same high-level, semantics-preserving
> transformation, specifically to reshape temporal magic-state demand before
> full lowering?

Two things have to be separated, because they have opposite answers.

## The transformation that worked is standard practice

Transformation T1 builds the dependency graph from reads and writes rather
than from bare line contact, so two gates that only read a line are left
unordered. That is **commutation-aware dependency analysis**, and it is
shipped, documented functionality in a mainstream compiler.

Qiskit's `DAGDependency` is described by its own documentation as "an object
to represent a quantum circuit as a Directed Acyclic Graph (DAG) via operation
dependencies (i.e. lack of commutation)", where "the edges correspond to
non-commutation between two operations". That is transformation T1, exactly.
Qiskit also ships `CommutationAnalysis`, `CommutativeCancellation`, a
`CommutationChecker`, and commutation-aware routing built on the same
analysis.

So the measured makespan reductions in this study, which the mechanism
analysis attributes to depth reduction, come from a transformation any
competent toolchain can already apply. Claiming it would be claiming
commutation analysis.

| capability | this study | Qiskit | Qualtran / Bartiq | CUDA-Q Logical | Harvest |
|---|---|---|---|---|---|
| dependency graph built from commutation rather than line contact | yes (T1) | **yes, `DAGDependency`, `CommutationAnalysis`** | bloq graphs carry declared dataflow | lowers through a logical virtual machine; graph construction not described at this level | not described |
| commutation used to cancel or reorder gates | not attempted | **yes, `CommutativeCancellation`, commutation-aware SABRE** | not its purpose | not described | not described |
| pacing or rate-limiting of magic-state consumers | yes (T2), and it never helps | no | no | not described | schedules timestep by timestep under availability |
| transformation chosen to reshape *temporal magic-state demand* before lowering | attempted, found ineffective | no | no | not described | supply and schedule co-optimised, but the circuit is fixed |

Evidence quality: Qiskit's behaviour is taken from its own API documentation
and issue tracker, which is direct. CUDA-Q Logical (arXiv:2609.13388),
Harvest (arXiv:2608.03315) and the Qualtran/Bartiq stack are abstract-level
only: arxiv.org and every mirror tried are blocked by this environment's
network policy, as recorded in the previous study's audit. No claim is made
about them beyond what their abstracts and documentation state.

## The transformation that would have been novel did not work

Transformation T2, pacing magic-state consumers to smooth demand before
lowering, is not something the audited tools do. Harvest is the nearest: it
schedules operations timestep by timestep under magic-state availability
constraints, which is a scheduling response to supply, not a source-level
transformation of the program. So T2 is plausibly novel.

It is also useless here: it never beats the graph it is applied to, on any
workload, in any regime, and it is exactly zero when applied to conventional
lowering. Novelty without benefit is not a contribution.

## Verdict

The novelty gate fails, for the strongest possible reason: the part of this
work that produced real improvements is a standard compiler analysis that a
mainstream toolchain already implements, and the part that would have been new
produced no improvement at all.
