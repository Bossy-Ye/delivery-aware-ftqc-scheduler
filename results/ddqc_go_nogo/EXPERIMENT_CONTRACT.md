# Experiment contract: does ignoring measurement-dependent control flow cost distributed compilers?

Frozen on 2026-09-24 before any placement experiment was run. Branch
`distributed-dynamic-compilation-pilot`, forked from commit `328b5f3`.
The GO/HOLD/NO_GO criteria in section 9 are copied from the research brief
and are not to be changed after results exist.

## 1. Research question

Does ignoring measurement-dependent control flow cause static distributed
quantum compilation to make substantially worse placement or communication
decisions?

## 2. Domain

Distributed quantum compilation: multiple QPUs joined by quantum links, qubit
placement across QPUs, remote two-qubit operations paid for in EPR pairs,
teleportation for moving qubits, and dynamic programs with
measurement-dependent `if`/`else` and repeat-until-success loops. General QEC
optimisation, single-QPU mapping, networking and classical distributed
computing are out of scope.

## 3. Structural precondition, measured before any placement experiment

The hypothesis needs branches whose *multi-qubit* interactions depend on the
measurement outcome, because single-qubit operations generate no inter-QPU
communication under any placement. A census of every measurement-conditioned
region in every available real dynamic program was run first, and is recorded
here as a pre-registered finding (`CENSUS.csv`, `CENSUS_SUMMARY.json`):

| source | programs | families | regions | local | present/absent | divergent | loop |
|---|---:|---:|---:|---:|---:|---:|---:|
| OpenQASM 3 spec examples | 11 | 11 | 47 | 41 | 4 | 0 | 2 |
| QASMBench | 5 | 5 | 49 | 48 | 1 | 0 | 0 |
| VeriQBench `dynamic/` | 203 | 7 | 333,310 | 333,310 | 0 | 0 | 0 |
| MQT Bench dynamic | 12 | 3 | 256 | 256 | 0 | 0 | 0 |
| Qualtran arithmetic, lowered | 10 | 10 | 132 | 0 | 132 | 0 | 0 |
| **all** | **241** | **36** | **333,794** | **333,655** | **137** | **0** | **2** |

No real program in the corpus contains a divergent region. The only
multi-qubit conditionals are present/absent: a two-qubit gate in one branch
and nothing in the other. Of those, 132 are the classically controlled `CZ`
of measurement-based AND uncomputation (Gidney 2018), which fires with
probability exactly 1/2 because it is conditioned on an X-basis measurement.

This finding bears directly on the frozen NO_GO criterion "realistic dynamic
programs rarely generate divergent distributed communication patterns". The
placement experiments below are still run in full, so that the decision rests
on measured headroom and not on the census alone.

## 4. Benchmarks

| source | repository | version | role |
|---|---|---|---|
| OpenQASM 3 examples | openqasm/openqasm | `7fbf9e9eb3692a1288c014d6efd43523701886c6` | real |
| QASMBench | pnnl/QASMBench | `357b942396d5c2b7cbc1c229c585a6ef5ccaebac` | real |
| VeriQBench | Veri-Q/Benchmark | `1c03e45371e5701f62c123943dec1cace4d46767` | real |
| MQT Bench | PyPI `mqt.bench` | 2.3.0 | real |
| Qualtran | PyPI `qualtran` | 0.7.0 | real |
| constructed controls | this study | — | infrastructure validation only |

Real programs are run in two groups: the 13 that contain any multi-qubit
conditional (the only ones where headroom is possible), and a sample of
local-only programs as structural negative controls. Constructed programs are
used only for the strong-divergence and identical-branch controls and cannot
supply GO evidence.

## 5. Cost model

* **Network**: `k` QPUs of capacity `c` on a topology graph; line, ring, 2-D
  grid and fully connected.
* **Remote two-qubit operation** between QPUs at graph distance `d` consumes
  `d` EPR pairs (entanglement swapping along the path) and costs `d` link
  latency units. Local operations cost nothing.
* **Moving a qubit** between QPUs by teleportation consumes `d` EPR pairs and
  `d` latency units. Reconfiguration is always charged; it is never free.
* **Expected cost** `E = sum over regions and branches of p(branch) x
  cost(branch)` plus unconditional cost. **Worst-case cost** is the maximum
  over branch outcomes. They are reported separately.
* **Link utilisation**: EPR pairs routed over the busiest link, a contention
  measure reported alongside the totals.

## 6. Compilation models

* **R0, existing tools (reference only).** What the audited compilers do:
  QuPort and memQ `dqc` never see branch interactions (weight 0); pytket-dqc
  rejects dynamic programs. Reported to show the practical gap, not used for
  the GO criteria.
* **Case 1, strongest static baseline.** One placement, chosen to minimise the
  cost of the program with every branch flattened in (each conditional
  interaction weighted 1). This is the best a control-flow-insensitive
  compiler that at least sees the branches can do.
* **Case 2, branch-aware objective, one placement.** One placement, chosen to
  minimise expected cost using the branch structure and probabilities.
* **Case 3, branch-dependent placement.** A placement before each region and
  a placement per branch after it, with every qubit move charged by
  teleportation, chosen to minimise expected cost.

All cases are evaluated under the same true branch probabilities. Placement
search is exhaustive where the space allows; beyond that it is a documented
local search, checked against the exhaustive optimum on every case where both
can run.

## 7. Controls and sweeps

* **Negative control**: branches with identical communication.
* **Strong-divergence control**: branches that communicate with different
  partners on different QPUs. The oracle must find headroom here, or the
  infrastructure is wrong.
* **Probability sweep**: `p` in {0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95};
  record whether the optimal placement changes.
* **Topology sweep**: line, ring, grid, fully connected.
* **Capacity sweep**: QPU count and capacity varied.

## 8. Mechanism hypotheses

H1 mutually exclusive communication edges; H2 unequal branch probabilities;
H3 an artefact of QPU capacity; H4 an artefact of network topology. Each is
tested with a discriminating run.

## 9. Frozen decision criteria

### GO — all of:

1. Multiple independently authored dynamic programs exhibit the phenomenon.
2. Control-flow-aware optimisation changes the selected placement for a
   meaningful subset of programs or probability regimes.
3. Expected communication decreases by roughly 25% or more on multiple
   nontrivial programs compared with the strongest faithful static baseline.
4. The benefit survives realistic accounting for remapping and teleportation.
5. The result occurs across more than one network configuration.
6. Existing published compilers do not already implement essentially the same
   analysis.
7. The phenomenon suggests a nontrivial compiler problem rather than a simple
   fixed heuristic such as "place the most probable branch first".

### HOLD

The effect is real but normally around 10-25%; only one realistic benchmark
shows a large effect; novelty remains uncertain; or a simple heuristic
captures most of the gain.

### NO_GO — any of:

* static compilation is usually within about 10% of the branch-aware oracle;
* optimal placement rarely changes with branch structure or probability;
* gains disappear after charging reconfiguration;
* the effect exists only in artificial examples;
* a trivial heuristic captures essentially all oracle improvement;
* existing work already provides the same capability;
* realistic dynamic programs rarely generate divergent distributed
  communication patterns.

## 10. Reproducibility

Every result row records repository, commit, program, QPU count, capacity,
topology, branch probabilities, compilation model, seed, the chosen
placements, expected and worst-case EPR pairs, remote operations, latency,
link utilisation and runtime. Seed `20260924` throughout.
