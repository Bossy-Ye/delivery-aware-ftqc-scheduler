# Experiment contract: reliability-aware choice of FT remote primitives

Status: FROZEN before the decisive runs (calibration grid, clean-pattern sweep,
workload matrix). Criteria may be tightened only with a written methodological
reason recorded before results are seen, and never relaxed.

## 1. Hypothesis (frozen)

> A resource-optimal distributed compilation decision and a
> logical-reliability-optimal decision disagree often enough, and with enough
> consequence, to justify a reliability-aware compiler analysis.

It is **not** the known fact that the two primitives have different logical error
rates (Stack et al. 2026 already show the non-local CNOT is up to 10x more
reliable than teleportation and suggest teleporting only when it removes about 10
non-local gates). The hypothesis is about **decisions**: on independently authored
programs and realistic hardware, the ebit/remote-gate/latency-optimal choice
between non-local gates and logical teleportation (one-way or round trip) must
differ from the failure-optimal choice, with large end-to-end consequences, and
in a way that neither a fixed threshold ("teleport iff k >= K") nor the paper's
rule of about 10 captures.

## 2. Logical error source

* Circuits: TMCBS (github.com/basilthebeagles/tmcbs @ c0490fa, the Nat. Commun.
  artifact), composed only from its builder calls, with its noise model (uniform
  circuit-level p; ebits as a perfect Bell pair followed by DEPOLARIZE2(p_ebit))
  and its cadence (1 + 3 settling rounds, 3 rounds after every operation).
  `src/ftqc_delivery/ftprim/patterns.py`.
* Faithfulness checks (`tests/test_ftprim_patterns.py`, all pass before the run):
  the composed remote pattern with k = 1 is instruction-for-instruction identical
  to `tmcbs.non_local_cnot` for the surface code and the [[18,4,4]] BB code; every
  pattern has deterministic detectors and observables without noise; per-block
  round counts read from the circuits match the time accounting.
* Decoder: Tesseract (tesseract-decoder 0.1.1.dev20260711233612, the TMCBS pin and
  the decoder of the paper's main runs) with the TMCBS default configuration.
  PyMatching cannot be used: these DEMs do not decompose into graphlike errors.
* Sampling: seeded per batch (`sampling.point_seed`); error bars are
  `sinter.fit_binomial` with Bayes factor 1000, the TMCBS rule.
* No analytical LER formula is used anywhere. Pattern and program failure are
  sums of per-operation contributions measured in these simulations; the
  additivity is itself tested (section 3).

## 3. Calibration grid and fitted costs

Patterns (one logical block A on QPU A interacting k times with block B on QPU B):
`R` = k transversal non-local CNOTs; `T` = TMCBS logical teleportation of A to
QPU B, then k local transversal CNOTs; `T_rt` = `T` plus the return teleportation;
`MEM` = two idle blocks for r extra rounds.

Grid (`CALIBRATION_GRID.json`, 234 circuits; set from the timing pilot in
section 10, since Tesseract time per shot grows steeply with pattern length):

| code | p | p_ebit / p | R: k | T: k | T_rt: k | MEM: r | stop at (errors / shot cap) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SC d=3 | 1e-3, 2e-3, 3e-3 | 1, 3, 10, 30 | 1, 2, 4, 8 | 1, 2, 4, 8 | 1, 2 | 0, 12 | 400 / 2e6 |
| SC d=5 | 1e-3, 2e-3 | 1, 3, 10, 30 | 1, 2, 4 | 1, 2 | 1 | 0, 12 | 200 / 5e5 (T_rt 3e5) |
| SC d=7 | 1e-3 | 1, 10 | 1, 2 | 1, 2 | none | 0, 12 | 100 / 2e5 (T 1.5e5, MEM 3e5) |
| BB [[18,4,4]] | 1e-3 | 1, 10 | 1, 2 | 1, 2 | 1 | 0, 12 | 200 / 3e5 (T 1e5, T_rt 6e4) |

Points that hit the shot cap are flagged and their intervals carried through.
Lines are fitted on k in {1, 2, 4}; the SC d=3 points at k = 8 are held out.
Where only T_rt(k = 1) exists, its slope is taken from T (same local CNOTs); where
no T_rt exists (SC d=7) the return costs the same as the outbound teleport (same
TMCBS protocol). Both substitutions are checked on SC d=3, where T_rt is
simulated at two k: b_Trt must lie within the bootstrap interval of b_T and
c_ret within that of c_tel, otherwise the substitution is reported as failed.

Fits (`costs.py`): weighted least-squares lines in k (and r); per-operation
excesses over plain memory: `e_remote = b_R - 6 s_mem`, `e_local = b_T - 6 s_mem`,
`e_tel = (a_T - a_R) - 6 s_mem`, `e_ret = (a_Trt - a_T) - 6 s_mem`; break-even
`K* = (a_T - a_R) / (b_R - b_T)` (one-way) and `(a_Trt - a_R) / (b_R - b_T)`
(return). Uncertainty: parametric bootstrap (1000 binomial resamples, seed 12345).
Additivity check: the SC d=3 hold-out simulations at k = 8 must fall inside
their Bayes intervals for at least 80% of hold-out points; otherwise the
composition model is reported as unreliable and the verdict cannot be GO.

## 4. Resources and latency

Every transversal non-local CNOT and every teleport consumes one batch of n Bell
pairs (n = data qubits per block; the TMCBS teleport builds its logical Bell pair
with one non-local CNOT). Ebits are generated continuously and may be buffered; a
run lasts `max(compute rounds, rho * batches)` rounds, where rho is the number of
syndrome rounds needed to generate one batch. Waiting costs memory on every live
block. rho grid: 0, 1, 3, 10, 30, 100, 300.

## 5. Regime classes (fixed before results, from published hardware numbers)

* Link fidelity: best trapped-ion photonic links reach 94-97% Bell fidelity at
  182-250 pairs/s (Saha et al. 2025; Oxford/Duke/IonQ). Cross-fridge microwave
  links are at 52-62%. With DEPOLARIZE2(p_ebit), F = 1 - 0.8 p_ebit, so 97% gives
  p_ebit ~ 0.04, i.e. p_ebit/p ~ 20-40 at p = 1e-3 to 2e-3.
* Rate: 250 pairs/s with ms-scale syndrome rounds (ions), or 1e5 pairs/s with 1 us
  rounds (superconducting), gives rho = n / (rate x round time) of about 100 to 500
  for d = 5-7. Multiplexing 10-100 links gives rho of about 3-50.
* **Realistic**: p in {1e-3, 2e-3}, p_ebit/p in {10, 30}, rho in {10, 30, 100, 300}.
* **Near-term optimistic**: p_ebit/p >= 3 and rho >= 1, not realistic.
* **Idealised**: p_ebit/p = 1 (distilled links) or rho = 0 (free, instantly
  buffered entanglement).
Only the realistic class counts for criterion G2; the others are reported.

## 6. Clean-pattern analysis (k = 1..30)

For every fitted point, rho and k, and for two scenarios (one-way: R vs T;
return needed: R vs T_rt): failure, Bell pairs and latency of each strategy
(`costs.pattern_metrics`); decisions under the ebit objective (ties go to the
non-local gate, the DQC-NAC/memQ default), the latency objective, and the failure
objective. Reported: inversions in both directions, the failure ratio of the
ebit choice to the failure choice, K*(regime), the best single K, K conditioned
on hardware, and the paper's K = 10 rule.

## 7. Workloads (independently authored; frozen list in `workloads.py`)

QFT family: qft_n29 (QASMBench), qft_n32, qpeexact_n24, ae_n24 (MQT Bench 2.3.0).
Arithmetic: adder_n28 (QASMBench), bigadder_n18, multiplier_n15, square_root_n18
(QASMBench), cdkm_adder_n24, vbe_adder_n22, draper_adder_n24 (MQT). Modular
arithmetic: modular_adder_n16, rg_qft_multiplier_n16 (MQT). Pauli rotations and
chemistry: ising_n34, ising_n26, vqe_uccsd_n8 (QASMBench). QAOA: qaoa_n24 (MQT).
QEC: qec9xz_n17 (QASMBench), steane_code_n26 (MQT). Other: swap_test_n25, knn_n25
(QASMBench). Excluded for oracle tractability: factor247_n15, vqe_n24, hhl_n14,
hhl_n10 (10^4-10^6 CX).

Lowering: Qiskit transpile to CX + single-qubit gates (optimization level 1,
seed 1); CX layers ASAP. Two QPUs; static partition = Kernighan-Lin min-cut
bisection (best of 8 seeds) shared by every policy; capacity = home count + 1
per QPU (primary) and + 25% (sensitivity). Execution model: lock-step layers of
3 rounds, +3 rounds for a layer preceded by a teleport, generation bound as in
section 4, memory on all logical qubits for the whole run.

## 8. Policies (identical decision space and semantics)

* **A**: exact ebit-optimal trajectory (CP-SAT), ties broken toward the lowest
  failure for the regime (the resource baseline at its best).
* **B**: the myopic burst rule "teleport an operand whose run of upcoming
  interactions with the other QPU is >= K" for K = 1..30. Reported: best single K
  over the realistic set (B_fixed), best K per regime (B_hw), and K = 10 (paper).
* **C**: failure-optimal trajectory: CP-SAT warm-started from A and all B, taken
  as the best of all candidates, with the solver's proven bound (optimality gap
  reported; solutions without an OPTIMAL certificate are labelled).
Limits: 120 s for the ebit solve, 20 s for its tie-break, 60 s for the failure
solve, CP-SAT seed 0.

Workload regimes (18): realistic = SC d=5 at p in {1e-3, 2e-3} with p_ebit/p in
{10, 30} and rho in {10, 100}, plus SC d=7 at p = 1e-3, p_ebit/p = 10, rho in
{10, 100}; contrast = SC d=5 at p = 1e-3 with p_ebit/p in {1, 3} and rho in {0, 3},
SC d=5 at p = 1e-3 with p_ebit/p in {10, 30} and rho = 0, and SC d=7 at
p = 1e-3 with p_ebit/p in {1, 10} and rho = 0. Solver runs use one CP-SAT worker
per workload process, four processes in parallel (limits above).

## 9. Metrics and decision criteria (frozen)

Per (workload, regime, policy): Bell pairs, non-local CNOTs, teleports,
failure probability (sum of calibrated contributions; 1 - exp(-sum)), run rounds,
solver time and status. "Communicating" workloads have at least 10 non-local CNOTs
under the static partition.

Benefit of C over A: `F_A / F_C`. Threshold recovery:
`sum(F_A - F_B) / sum(F_A - F_C)` over the instances considered.

GO requires all of:
* **G1** disagreement: in at least 50% of (communicating workload x realistic
  regime) instances, A and C differ on at least 10% of decisions, where the
  decision share is (CX whose local/remote status differs + teleport placements
  (qubit, layer) made by exactly one of A, C) / (all CX + teleport placements made
  by either).
* **G2** breadth: G1 and G3 hold in at least 2 distinct realistic (p, p_ebit/p, rho)
  regimes.
* **G3** consequence: median over communicating workloads of `F_A / F_C` >= 10
  in those regimes (an order of magnitude).
* **G4** overhead: where C beats A, C uses at most 3x A's Bell pairs and 2x its
  run rounds in at least 75% of instances.
* **G5** thresholds: B_fixed recovers < 80% of the oracle benefit on the
  realistic set.
* **G6** novelty: no existing compiler already chooses remote primitives by
  logical failure (`NOVELTY_AUDIT.md`: currently satisfied).
* **G7** needs program reasoning: B_hw recovers < 95% of the oracle benefit, and
  the failure-optimal break-even K* varies by at least 3x across realistic regimes.

NO_GO if any of:
* existing work subsumes the candidate;
* decisions almost always agree: in at least 90% of communicating realistic
  instances, A and C differ on under 5% of decisions;
* B_fixed recovers at least 95% of the oracle benefit on the realistic set;
* inversions only in constructed examples: clean-pattern inversions exist but G1
  fails on the workloads;
* small improvement: median `F_A / F_C` < 1.25 in every realistic regime;
* prohibitive overhead: G4 fails in more than half of the instances where C wins.

HOLD otherwise, for example: inversions that are real but mostly explained by a
threshold (B_fixed recovers 80-95%), confined to near-term/idealised regimes, or
only moderate (median ratio 1.25-10).

Precedence: a NO_GO trigger overrides HOLD; GO needs every G criterion.

## 10. Pilots run before freezing (disclosed)

* Smoke test (d = 3, 5 at p = 3e-3, p_ebit = 10p, TMCBS primitives): whole-
  experiment LERs of 2e-2 to 6e-2, used only to check the install.
* Decoder pilot: PyMatching fails on these DEMs; Tesseract takes ~0.35 ms/shot
  (d = 5, p = 1e-3) and ~1 ms/shot (d = 7) for single-gate primitives.
* Timing pilot on composed patterns (`TIMING_PILOT.log`, p = 1e-3, p_ebit = 10p;
  150-3000 shots per circuit): ms/shot ranges from 0.05 (SC d=3, R k=1) to 151
  (SC d=7, T k=4); BB [[18,4,4]] T k=1 costs 84 ms/shot. An earlier run of SC d=7
  R with k = 8 took 0.47 s/shot (600 shots, 0 errors) and was stopped. These set
  the grid in section 3.
* Raw counts seen in that pilot for SC d=3 at p = 1e-3, p_ebit/p = 10 (3000
  shots each): R k=1,2,4: 21, 34, 48 failures; T k=1,2,4: 36, 41, 52; T_rt k=1,2:
  52, 63; MEM(12): 23. Read informally they suggest a one-way break-even of order
  5-10 at that single point. They are superseded by the calibration run (new
  seeds, 400-failure stopping rule) and were not used to choose any criterion,
  which are the brief's, or any workload, which were fixed from sources before.
No other decision-relevant quantity was computed before this contract was frozen.
