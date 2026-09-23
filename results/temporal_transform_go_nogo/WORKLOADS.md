# Workloads considered, and why each was included or excluded

The corpus is the one frozen in `src/ftqc_delivery/mrc/corpus.py` for the
previous study, reused unchanged so that the workload set could not be
selected to suit this hypothesis. Twenty-two programs, three independently
authored sources, no synthetic programs at all.

| source | version | role |
|---|---|---|
| qmpa, Alan Robertson (UTS) | commit `47e27d38a55f5161baac7805f9cc06a8146aa064` | reversible multi-precision arithmetic |
| qualtran, Google Quantum AI | 0.7.0 | fault-tolerant algorithm library with explicit AND/AND-dagger markers |
| QASMBench, PNNL | commit `357b942396d5c2b7cbc1c229c585a6ef5ccaebac` | OpenQASM 2 benchmark suite |

## Included

| workload | source | structure | repeated/parallel regions | non-Clifford ops | reorderable region? | role |
|---|---|---|---|---|---|---|
| qt_qft6 | qualtran | textbook QFT, 6 qubits | 15 controlled-phase blocks | 30 Toffoli, 6 rotations, 4 T | yes: phase blocks share only control lines | target |
| qt_qft8 | qualtran | textbook QFT, 8 qubits | 28 blocks | 56 Toffoli, 15 rotations, 6 T | yes | target |
| qt_qpe3 | qualtran | textbook phase estimation, 3 bits | 10 controlled powers | 20 Toffoli, 8 T | yes | target |
| qt_aliassamp8 | qualtran | alias-sampling state preparation | 33 AND pairs across 13 levels | 66 Toffoli | yes | target |
| qt_aliassamp16 | qualtran | alias sampling, 16 outcomes | 39 AND pairs | 78 Toffoli | yes | target |
| qt_prepunif6 | qualtran | uniform superposition preparation | 5 AND pairs | 10 Toffoli, 2 rotations | yes | target |
| qt_qrom16x5 | qualtran | QROM, unary iteration over 16 entries | 14 AND pairs | 28 Toffoli | partly: the iteration chain is serial, the target writes are not | target |
| qt_add16 | qualtran | ripple-carry adder, 16 bits | 15 carries | 30 Toffoli | little: the carry chain is a true dependency | target |
| qt_modadd8 | qualtran | modular adder, 8 bits | 31 AND pairs | 62 Toffoli | little | target |
| qt_halfgt8 | qualtran | comparator keeping its ancilla | 8 ANDs | 8 Toffoli | partly | target |
| qmpa_mul6, qmpa_mul8 | qmpa | shift-and-add multipliers | 93 and 164 AND pairs | 186 / 328 Toffoli | partly | target |
| qmpa_div6 | qmpa | trial-subtraction divider | 18 AND pairs | 36 Toffoli | partly | target |
| qb_qram_n20 | QASMBench | QRAM lookup | 14 sites over 13 levels | 20 Toffoli | yes | target |
| qb_multiplier_n15, qb_multiply_n13 | QASMBench | multipliers | 18 and 6 sites | 36 / 6 Toffoli | partly | target |

## Negative controls, chosen by structure before the decisive run

Programs whose dependency chain is genuinely serial, so the commutation-aware
graph can expose no freedom. This was measured (critical path unchanged by the
transformation) before any makespan was compared.

| workload | source | why there is no freedom |
|---|---|---|
| qmpa_draper8, qmpa_draper16 | qmpa | one wide stage; all sites are already parallel, nothing to expose |
| qt_multiand10 | qualtran | a single serial AND ladder; every AND consumes the previous one's output |
| qb_sat_n7, qb_sat_n11 | QASMBench | SAT oracle whose clause chain writes and re-reads the same ancilla |
| qb_sqrt_n18 | QASMBench | 65 sites in one serial chain |

## Excluded, and why

* `Product`, `Square`, `PlusEqualProduct`, `MultiplyTwoReals`,
  `AddIntoPhaseGrad` (qualtran): declare no decomposition, so no gate stream
  exists to transform.
* `bwt_n21` (QASMBench): 25,600 Toffoli gates, outside the simulation budget.
* `KaliskiModInverse` (qualtran): raises on the parameters tried.
* `qmpa.parallel_add`: draws random values internally, so a run would not be
  reproducible from the frozen seed alone.
* Hand-written synthetic examples: not used, not even as sanity checks, to
  keep the evidence entirely external.

## A caveat carried forward from the previous study

`qmpa_draper8` and `qmpa_draper16` come from an upstream function whose
prefix rounds (P, G, C) are left unimplemented. They are used only as
independently authored wide gate streams, not as verified adders. They serve
here as negative controls, and no conclusion rests on them.
