# Novelty audit: reliability-aware choice of FT remote primitives

Candidate: fault-tolerant distributed compilers may pick the wrong remote-operation
strategy because they optimise communication resources (EPR pairs, remote-gate
count, latency) rather than end-to-end logical failure probability.

Search window: literature and repositories up to 2026-09-24. arXiv, Nature,
PMC, Zenodo and Semantic Scholar are blocked by this environment's egress
policy, so papers are known from search-engine abstracts and snippets unless a
code artifact was cloned. Every compiler claim below that says "from source" was
checked in code; `COMPILER_AUDIT.csv` has the per-compiler record with
file:line evidence.

## 1. What is already known (not novel)

| Source | What it establishes |
| --- | --- |
| Stack, Wang, Mueller, *Transversal fault tolerant distributed quantum computing operations*, Nat. Commun. 17, 8838 (2026); arXiv:2504.05611; artifact TMCBS (github.com/basilthebeagles/tmcbs @ c0490fa) | Circuit-level simulations of the transversal non-local CNOT and logical teleportation (surface and BB codes). The non-local CNOT reaches up to an order of magnitude lower LER than teleportation at the same d and noise, because it uses 2 code blocks instead of 3 and fewer measurements and feed-forward steps. Recommendation: schedule across nodes with non-local CNOTs and reserve teleportation for cases where it removes on the order of 10 non-local gates. Ebit noise 10x the physical rate is tolerated. |
| Liu et al., *Remote Entanglement in Lattice Surgery: To Distill, or Not to Distill*, arXiv:2603.06513 | A fidelity crossover that decides whether remote Bell pairs should be distilled before lattice surgery (resource trade-off vs code distance). This is a regime-dependent decision rule for a neighbouring choice. |
| *Design rules for fault-tolerant multi-gate teleportation*, arXiv:2607.01342 | Packing n remote gates into one ebit is fault tolerant only for n < ceil(d/2) (correlation-aware decoder) or n < floor(d/2). This is a reliability-derived rule for a remote primitive. |
| Chelluri et al., arXiv:2607.27204; Marton et al., PRR 2025 (arXiv:2504.15747); Shalby et al., PRA 2025 (arXiv:2503.04968); heterogeneous-distance lattice surgery arXiv:2609.26784; distributed lattice-surgery errors arXiv:2607.29186 | Lattice-surgery and teleportation interfaces over noisy links tolerate interface noise roughly 10x the local rate. Protocol characterisation only; no program-level choice. |
| NOBOL, arXiv:2609.01901; resource-adaptive DQEC, arXiv:2609.03048; entanglement boosting (PRX Quantum) | Alternative low-ebit logical interfaces. Their interface noise and resource trade-offs are analysed per protocol. |
| Filippov, Yang, Murali, arXiv:2508.19160; Chandra, Kaur, Seshadreesan, arXiv:2511.13657; *Impact of Network Constraints on FT-DQC*, arXiv:2606.17495; arXiv:2607.22998 | Resource estimation for distributed FTQC. Optimal code distance and communication-qubit allocation shift with network regime. No per-operation primitive selection by LER. |

Explicitly not novel (per the brief): "teleportation can be less reliable",
"non-local CNOT can outperform teleportation", "teleport only after about ten
remote gates".

## 2. Compilers inspected from source (decision logic on the executed path)

| Compiler | Mechanism choice | Objective | LER used? |
| --- | --- | --- | --- |
| DQC-NAC @ 564ae1b | TeleData vs cat-ent TeleGate, **only** on the ungrouped path; the default grouped path never evaluates teleportation | ebits: `circuit_cost` = sum of `len(qargs[1:])//2` over Teleport/CatEnt; teleport iff `tel_cost < mig_cost` | no |
| memQ DQC @ f3a6b96 | Fixed by the compilation model: cat-ent TeleGate inside windows, remote swaps (2 teleports) between windows chosen by partition acceptance | e-bit pairs (crossing x remote-gate ebit cost + 2 ebits per swap hop) | no |
| Chipmunq @ 324ef3d | None at the logical level; routes physical gates across couplers | path length + alpha x link error + beta x utilisation | no (physical link error only) |
| CUDA-Q Logical 0.1.1.post1 | None: first feasible lowering; multiple lowerings for a communication site are an error ("selection is ambiguous") | none | no |
| pytket-dqc @ 1ac175e | TeleGate only (embedding) | ebits | no |
| QuPort @ 6e41c8c | fixed | latency proxy | no |
| NetQMPI @ 2524443 | programmer-chosen | n/a | no |
| Labubu (IEEE ToN 2026), AutoComm (MICRO 2022) | TeleGate/TeleData per burst (from abstracts; no inspectable code) | entanglement / latency | not stated |

DQC-NAC detail requested by the brief, confirmed on the executed path
(`experiments/ftprim/probe_dqcnac.py`, `DQCNAC_PROBE.json`, 6 bundled benchmarks x
2 paths): with the default `CompileManager.run(use_gate_grouping=True)`,
`get_teleport` and `circuit_cost` are never called and every remote gate becomes
CatEnt/CatDisEnt. With `use_gate_grouping=False`, 12 decisions were made; each
compared two ebit counts from `circuit_cost` (teleport chosen 3 times; ties went
to migration). No noise, fidelity or QEC parameter exists in the network or
device model.

## 3. Novelty boundary for this study

No inspected or described system automatically selects among fault-tolerant
remote primitives using logical error rate as the objective. CUDA-Q Logical
explicitly defers such a policy ("a policy can later compare cost/evidence"). The
only reliability-derived guidance is a fixed rule of thumb (Stack et al., about 10
non-local gates) plus protocol-level rules for neighbouring choices (distil or
not, multi-gate packet size).

The candidate is therefore **not subsumed by an existing automatic system**. Per
the brief it survives only if program, hardware or QEC context produces decisions
that a simple fixed threshold or a known rule does not capture. The frozen
experiment tests exactly that (`EXPERIMENT_CONTRACT.md`).

## Sources

- https://www.nature.com/articles/s41467-026-75693-3 and https://arxiv.org/abs/2504.05611
- https://github.com/basilthebeagles/tmcbs
- https://github.com/qslab-unipr/dqcnac
- https://github.com/memQGit/dqc
- https://github.com/Wegii/chipmunq
- https://pypi.org/project/cudaq-logical/ and https://arxiv.org/abs/2609.13388
- https://ieeexplore.ieee.org/document/11488377/ (Labubu)
- https://arxiv.org/abs/2207.11674 (AutoComm)
- https://arxiv.org/abs/2603.06513, https://arxiv.org/abs/2607.01342, https://arxiv.org/abs/2607.27204,
  https://arxiv.org/abs/2504.15747, https://arxiv.org/abs/2503.04968, https://arxiv.org/abs/2609.26784,
  https://arxiv.org/abs/2607.29186, https://arxiv.org/abs/2609.01901, https://arxiv.org/abs/2609.03048,
  https://arxiv.org/abs/2508.19160, https://arxiv.org/abs/2511.13657, https://arxiv.org/abs/2606.17495,
  https://arxiv.org/abs/2607.22998
