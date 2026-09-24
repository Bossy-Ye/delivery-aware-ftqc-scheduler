# Artifact audit: what real distributed-quantum compilers do with measurement-dependent control flow

Four independently maintained projects were cloned and inspected at the
source level; the three that accept dynamic programs were also *run* on the
motivating example from the brief:

```text
measure q0
if q0 == 0: cx(q1, q2)
else:       cx(q1, q8)
cx(q2, q3); cx(q8, q7)
```

Capabilities below are taken from the implementation, not from READMEs.

---

```text
Project:                 QuPort
Repository:              github.com/neuralsorcerer/quport
Commit/release:          6e41c8c076f1ed54d626ea01c90fab994d5d95de (2026-08-16)
Input representation:    Qiskit QuantumCircuit
Supports dynamic control flow? partial — accepts if_else/while_loop/switch_case,
                         preserves their classical registers when splitting
Partitioning method:     weighted interaction graph -> initial layout, then
                         Qiskit routing inside each QPU
Placement method:        one global layout for the whole circuit
Communication model:     inter-QPU two-qubit ops extracted as RemoteOp events
Can placement vary by control-flow branch?          no
Can communication cost depend on branch probabilities? no
Relevant limitations observed in code:
  interaction.py, extract_twoq_weights(): iterates qc.data and skips every
  instruction whose qubit count is not exactly 2. A Qiskit if_else is one
  instruction whose qubits are the union of both branches, so any branch
  touching three or more qubits is dropped from the interaction graph.
  Executed on the example: weights = {(2,3): 1, (7,8): 1}. Both branch
  edges (1,2) and (1,8) are absent. QuPort does not compromise between
  branches; it never sees them. A conditional acting on exactly two qubits
  is counted once, as if unconditional.
  distributed.py mentions if_else/while_loop only to keep classical register
  references valid after splitting, so the result still converts to a DAG.
```

```text
Project:                 memQ DQC (the artifact of arXiv:2609.15728)
Repository:              github.com/memQGit/dqc
Commit/release:          f3a6b96a69d028282a9bec60c8543661e87b0e7f (2026-09-15)
Input representation:    OpenQASM 3.0
Supports dynamic control flow? no — branches pass through as opaque statements
Partitioning method:     interaction-graph partitioning across QPUs, with
                         time-sliced ("dynamic in time") remapping
Placement method:        qubit-to-QPU assignment per time segment
Communication model:     teleportation-based remote gates, EPR scheduling
Can placement vary by control-flow branch?          no
Can communication cost depend on branch probabilities? no
Relevant limitations observed in code:
  preprocessing/qasm/cleaning.py, clean_statement(): models gates,
  measurements, barriers and gate definitions; any other statement type
  falls through to a warning ("not supported in cleaning. Preserving
  statement.") and is returned with is_op=False and no qubits.
  Executed on the example: BranchingStatement -> is_op=False, qubits=[].
  The two branch CNOTs never reach the partitioner.
  Its time-sliced remapping is placement that changes *over time*, which is
  not placement that changes *by branch*: branches are mutually exclusive,
  not sequential.
```

```text
Project:                 pytket-dqc (Quantinuum)
Repository:              github.com/CQCL/pytket-dqc
Commit/release:          1ac175ed820ac02366b2ed71b653d5b96fc72ff7 (2026-06-01)
Input representation:    pytket Circuit
Supports dynamic control flow? no — rejected outright
Partitioning method:     hypergraph partitioning with embedding and
                         detached-gate refinement
Placement method:        one global assignment of qubits to servers
Communication model:     EPR-based non-local gates, with hyperedge packing
Can placement vary by control-flow branch?          no
Can communication cost depend on branch probabilities? no
Relevant limitations observed in code:
  circuits/hypergraph_circuit.py, from_circuit(): raises unless
  dqc_gateset_predicate holds, which is GateSetPredicate({Rz, H, CU1}).
  Measurements, resets and conditional operations are outside that set, so
  any dynamic program is refused before distribution begins.
```

```text
Project:                 NetQMPI
Repository:              github.com/NetQIR/netqmpi
Commit/release:          2524443adf52bd6de9ab6b6b2925a096ae8db454 (2026-09-22)
Input representation:    Python SPMD program over NetQASM/Qoala/Aer backends
Supports dynamic control flow? yes, as a programming primitive
                         (sdk/operations/gate.py: ClassicalControlledGate)
Partitioning method:     none — the programmer writes code per rank
Placement method:        manual, via qsend(qubits, dest_rank)/qrecv
Communication model:     explicit qsend/qrecv and quantum collectives
Can placement vary by control-flow branch?          only if the programmer writes it
Can communication cost depend on branch probabilities? no analysis exists
Relevant limitations observed in code:
  No function in the package partitions, places or assigns qubits
  automatically; searching the source for partition, placement,
  hypergraph or assignment routines finds none. NetQMPI is a programming
  model, so a branch-aware placement would have to be written by hand.
```

---

## Summary

| project | accepts dynamic programs | sees branch interactions | placement per branch | uses branch probabilities |
|---|---|---|---|---|
| QuPort | yes | **no** (dropped if 3+ qubits; counted as unconditional if 2) | no | no |
| memQ DQC | parses, then ignores | **no** (opaque, no qubits) | no | no |
| pytket-dqc | **no** (rejected) | — | no | no |
| NetQMPI | yes, as a primitive | manual only | manual only | no |

No inspected artifact performs branch-aware placement. The two that accept
dynamic programs are *blind* to branch communication rather than making a
compromise placement, which is a concrete, reproducible defect in current
tools. Whether fixing it is worth a research programme is a separate question,
and is the one the experiment answers.
