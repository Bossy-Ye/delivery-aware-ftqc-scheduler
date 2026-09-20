# Novelty matrix: does prior work already select implementations from carried resource state?

The capability in question, stated once and used as the test throughout:

> **per-site or per-phase selection among semantically equivalent
> logical-operation implementations, as a function of evolving resource state
> carried from earlier compiler decisions.**

## Evidence quality, stated first

This environment's network policy blocks arxiv.org and every mirror tried
(the proxy answers 403 to CONNECT; `pith.science` is blocked as well), so no
paper below could be read in full here. What was read is recorded per column,
and no claim is made beyond it. One work was read at the level of its
complete source code, which is stronger evidence about what a compiler
actually decides than any abstract.

| work | what was read | confidence |
|---|---|---|
| this pilot | the code in this repository | direct |
| A Resource Allocating Compiler for Lattice Surgery (arXiv:2506.04620) | complete source, `Alan-Robertson/Surface_Code_Compiler` commit `e5f1052`, 64 files | code-grounded |
| Harvest (arXiv:2608.03315) | abstract and indexed summaries | abstract-level |
| FT-Weave (arXiv:2609.20573) | abstract and indexed summaries | abstract-level |
| heterogeneous architectures (arXiv:2604.06319) | abstract and indexed summaries | abstract-level |

## Matrix

| capability | our current pilot | proposed stateful selector | Harvest (2608.03315) | Resource Allocating Compiler (2506.04620) | FT-Weave (2609.20573) |
|---|---|---|---|---|---|
| alternative implementations of one logical operation represented | yes, 2-5 per site with sources | yes | not indicated | **no**: one fixed 7-T Toffoli, no CCZ anywhere in 64 files | not indicated |
| different occurrences may differ | yes | yes | unknown | no | unknown |
| choice changes which magic-state species is consumed | yes, T vs CCZ | yes | not indicated | no, one species | not indicated |
| selection is joint across the program | yes, exact where affordable | yes | no, timestep-by-timestep greedy | no, first-fit binding of a gate to an idle factory | described as real-time and stage-aware |
| decisions depend on resource state carried from earlier decisions | yes, the cost model is a full state-carrying simulation | yes, by construction | not indicated; scheduling is per timestep under availability constraints | no | **plausibly yes, for assignment**: responds to stochastic preparation outcomes rather than nominal throughput |
| what the compiler primarily decides | which implementation each site uses | as the pilot | placement, routing, timestep scheduling, supply protocol, layout pruning | factory placement, gate-to-factory binding, routing, order | resource preparation, resource assignment, teleportation routing, correction handling |
| magic-state supply modelled with throughput, latency, buffers | yes | yes | yes, a configurable protocol-agnostic resource model | yes, a Litinski-style costing | yes, explicitly non-nominal |
| T and CCZ jointly provisioned | yes, three coupled models | yes | not indicated | not applicable, T only | not indicated |
| **implements the capability above** | **yes** | **yes** | not on available evidence | **no, code-verified** | **unresolved, and the closest risk** |

## Reading of the matrix

Against the one work whose code could be read, the capability is clearly
absent: that compiler has a single fixed Toffoli decomposition, no CCZ at all,
and binds each gate to the first idle factory that matches.

Harvest's variability is on the supply side: which protocol produces a state,
and which terminal delivers it. On the evidence available it chooses among
ways to *supply* an operation, not among ways to *implement* it. That
distinction is the whole claim, and it rests on an abstract.

FT-Weave is the closer risk and is newer (September 2026). It is described as
reacting to resource-preparation outcomes rather than to nominal throughput,
which is the "decisions depend on evolving resource state" half of the
capability. Whether it also selects among semantically equivalent
implementations, rather than assigning already-decided operations to resource
states, is exactly the question the abstract does not answer.

## Verdict

The capability is **not shown to be implemented** by any work examined, and is
**code-verified absent** in one. It is **not established as novel** either,
because the two nearest neighbours could only be read at abstract level and
one of them shares half the capability. Any claim of novelty must therefore be
written as conditional, and the condition is concrete: read Harvest and
FT-Weave in full, from a network that permits it, before making the claim in
public.

This is unchanged in kind from the previous audit
(`results/mrc_pilot/NOVELTY_AUDIT.md`); what changed is that FT-Weave now
exists and is a nearer neighbour than anything in that audit.
