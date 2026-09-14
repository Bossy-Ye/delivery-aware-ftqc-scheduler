# Delivery-Aware FTQC Scheduler

This repository contains preliminary experiments for compiler-side scheduling
under bounded magic-state delivery in fault-tolerant quantum computing.

The project builds on the diagnostic model introduced in:

> "When T-Depth Misleads: Predicting Fault-Tolerant Quantum Execution Slowdown
> under Magic-State Delivery Constraints"

Paper 1 showed that static T-depth can misrepresent executable performance
when magic-state delivery is bounded. It introduced slack ratio and Delta_max
as indicators of structural flexibility and schedule-level delivery pressure.

This repository investigates the next question:

> Can compiler and architecture decisions reshape or provision temporal
> T-state demand so that bounded delivery causes fewer stalls and shorter
> executable makespan?

## Current Status

The project has moved through six preliminary stages:

- V1 implemented the basic DAG model, demand metrics, deterministic simulator,
  baseline schedulers, and a first delivery-aware scheduler.
- V2 tested `sigma_DA_v2` against the strong slack-smoothing baseline and fixed
  the capacity metric with `C_ref_star`.
- V3 shifted from scheduler tuning to limit analysis, smooth failure mining,
  stochastic robustness, effective-capacity degradation, and regime mapping.
- V4 validated the regime-aware compiler-architecture framing over broader
  sweeps, workload expansion, strategy validation, transpiler sanity checks,
  and case studies.
- V5 tested non-circularity with naive policy baselines, label permutation,
  feature ablation, train/test splits, and outcome-blind regime assignment.
- V6 added resource-aware validation so capacity and buffer expansion are no
  longer treated as free.

The current conclusion is intentionally conservative:

> The framework is useful as a regime-aware and resource-aware diagnostic, but
> it is not yet a dominant prescriptive decision tool.

In particular, V6 shows that `always_increase_C` is no longer exactly free once
resource penalties are added, but it remains near-oracle under the default
resource prices. Regime-aware recommendations strongly improve over
`always_smooth` and capacity-aware fixed policies, and they become more
competitive when delivery capacity is priced more aggressively.

## Resource-Aware Compilation Go/No-Go Study

A separate, self-contained study lives under `src/ftqc_delivery/rac/`,
`experiments/rac/`, `results/rac_pilot/` and `figures/rac_pilot/`. It asks a
different question from the rest of this repository.

Everything above treats the circuit as given and asks how to *schedule* it.
The go/no-go study leaves the circuit open: a program is a graph of decision
sites, each site offers several semantically equivalent implementations with
different T-count, T-depth and demand shape, and the compiler must choose one
per site. The question is whether choosing by T-depth is wrong often enough,
and by enough, to justify a new compiler mechanism.

Its conclusion is recorded in `results/rac_pilot/GO_NO_GO_MEMO.md`.

Key components:

- `rac/supply.py`: factories with throughput, production latency, staggering
  and a hard buffer cap, plus a stochastic variant whose distillations fail
- `rac/execution.py`: cycle-accurate greedy execution under that supply, and
  the previous study's static-schedule semantics for comparison
- `rac/variants.py`, `rac/library.py`, `rac/programs.py`: implementation
  variants, decision sites, and the pilot programs built from them
- `rac/cost.py`: the supply-constrained critical path (SCCP), an analytic
  cost model that never simulates
- `rac/select.py`: the compilation policies, the greedy baselines, and the
  exhaustive optimality reference
- `rac/multiresource.py`: an exploratory extension in which magic states are
  not fungible, used by the one follow-up direction the study recommends

Run the study in order:

```bash
PYTHONPATH=src python experiments/rac/rac1_decision_reversal.py
PYTHONPATH=src python experiments/rac/rac2_headroom.py
PYTHONPATH=src python experiments/rac/rac3_ablation.py
PYTHONPATH=src python experiments/rac/rac4_mechanism.py
PYTHONPATH=src python experiments/rac/rac5_stress.py
PYTHONPATH=src python experiments/rac/rac6_multiresource_probe.py
PYTHONPATH=src python experiments/rac/rac7_cost_model_timing.py
PYTHONPATH=src python experiments/rac/rac_plots.py
PYTHONPATH=src python experiments/rac/rac_report.py
```

`rac_report.py` prints every number quoted in the memo, straight from the
committed tables.

## Non-Fungible Magic States: T + CCZ Selection Study

A second, self-contained study lives under `src/ftqc_delivery/mrc/`,
`experiments/mrc/`, `results/mrc_pilot/` and `figures/mrc_pilot/`. It follows
directly from the NO-GO above.

The go/no-go study found no exploitable headroom when a program's magic states
all come from one pool. This study splits the pool. Real machines run T
factories and CCZ factories, and one logical operation can often be realised
from either, so selecting implementations becomes a question of which factory
to load. The question is whether choosing that globally, and differently for
different sites, beats simple uniform and per-site policies.

Its conclusion is recorded in `results/mrc_pilot/EVIDENCE_MEMO.md`.

Key components:

- `mrc/resources.py`: two factory banks with literature-anchored footprints and
  periods, bounded buffers, distillation failures, and the real conversions
  between the resources
- `mrc/execution.py`: cycle-accurate execution with per-resource stocks
- `mrc/library.py`: implementation variants that draw on different banks, each
  with its published source
- `mrc/kernels.py`: 24 kernels spanning family, size and concurrency
- `mrc/policies.py`: eight policies, and an exact optimality reference that
  exploits the interchangeability of sites within a stage

Run the study in order:

```bash
PYTHONPATH=src python experiments/mrc/mrc1_headroom.py
PYTHONPATH=src python experiments/mrc/mrc2_controls.py
PYTHONPATH=src python experiments/mrc/mrc3_scaling.py
PYTHONPATH=src python experiments/mrc/mrc4_sensitivity.py
PYTHONPATH=src python experiments/mrc/mrc_plots.py
PYTHONPATH=src python experiments/mrc/mrc_report.py
```

### Is it a compiler problem? (phases 1-8)

The follow-up investigation asks whether the T/CCZ result is an instance of a
general compiler problem: semantically equivalent implementations with
different, non-fungible resource signatures, where local selection fails. Its
decision is recorded in `results/mrc_pilot/RESEARCH_DECISION_MEMO.md`, and the
prior-work audit in `results/mrc_pilot/NOVELTY_AUDIT.md`.

Additional components:

- `mrc/resources.py`: `coupled_machine` builds three provisioning models at a
  fixed factory area: independent banks (A), one raw level-1 stream feeding
  15-to-1 T and 8-to-1 CCZ distillers (B), and B plus catalysed CCZ-to-2T
  units (C)
- `mrc/stagedp.py`: the stage-wise dynamic-programming selector over
  (stage, carried buffer state) with Pareto pruning; analytic or stage-local
  simulated stage costs
- `mrc/extract.py`: decision-site extraction from gate streams (qmpa and
  qualtran adapters), including symbolic recognition of compute/uncompute
  pairs and the per-site record of variants, sources, signatures, ancillas
  and equivalence assumptions

Experiments, in order:

```bash
PYTHONPATH=src python experiments/mrc/mrc5_coupled.py      # coupled provisioning
PYTHONPATH=src python experiments/mrc/mrc6_explain.py      # when does local selection fail
PYTHONPATH=src python experiments/mrc/mrc7_selector.py     # stage-DP selector vs proven optima
PYTHONPATH=src python experiments/mrc/mrc8_external.py     # external qmpa/qualtran workloads
```

The external run needs `qmpa` (github.com/Alan-Robertson/qmpa) and
`qualtran` installed; both are independently authored arithmetic libraries and
their circuits are reported separately from the synthetic kernels.

Outcome: HOLD. The mechanism survives coupled provisioning and is traced on
real programs, but on independently authored arithmetic it is rare and small
(median headroom zero, 9% of cases above 5%, none on serial chains), and the
selector only ties the best simple policy there. The memo lists what would
change the decision either way.

## Scope

This repository focuses on compiler-level demand shaping and lightweight
compiler-architecture strategy analysis:

- fixed delivery capacity `C`
- fixed or varied buffer size `B`
- schedule-induced demand traces
- deterministic and stochastic delivery models
- runtime, backlog, capacity, buffer, and Pareto trade-offs

It does not optimize physical factory architecture, code distance, qubit cost,
factory layout, or detailed routing.

In plain terms: architecture work asks how large the kitchen should be; this
repository asks when scheduling is enough, when buffer helps, when capacity is
needed, and when uncertainty requires margin.

## Main Components

Source modules live under `src/ftqc_delivery/`:

- `dag/`: lightweight DAG model, generators, ASAP/ALAP slack analysis
- `schedulers/`: static, capacity-aware, smooth, DA v1/v2, robust smooth
- `simulator/`: deterministic, stochastic, and effective-capacity models
- `metrics/`: demand shape, backlog shape, capacity/buffer thresholds,
  structural features, regime validation, strategy gain, and V6 resource
  objectives
- `workloads/`: constructed families and semi-real/synthetic arithmetic, QFT,
  phase-estimation-like, and Hamiltonian-style workloads

Experiments are versioned under `experiments/` as `exp0` through `exp24`.

## Quick Start

Create an environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the test suite:

```bash
PYTHONPATH=src pytest
```

Compile-check the Python sources and experiments:

```bash
python -m compileall src experiments tests
```

## Running Experiments

The main experiment generations are:

```bash
PYTHONPATH=src python experiments/exp1_schedule_reshaping.py
PYTHONPATH=src python experiments/exp2_required_capacity.py
PYTHONPATH=src python experiments/exp1_schedule_reshaping_v2.py
PYTHONPATH=src python experiments/exp2_required_capacity_v2.py
PYTHONPATH=src python experiments/exp6_optimal_gap_analysis.py
PYTHONPATH=src python experiments/exp7_smooth_failure_mining.py
PYTHONPATH=src python experiments/exp8_stochastic_delivery_v3.py
PYTHONPATH=src python experiments/exp9_effective_capacity_v3.py
PYTHONPATH=src python experiments/exp10_regime_map.py
PYTHONPATH=src python experiments/exp11_regime_stability.py
PYTHONPATH=src python experiments/exp12_strategy_validation.py
PYTHONPATH=src python experiments/exp13_workload_expansion.py
PYTHONPATH=src python experiments/exp14_transpiler_sanity.py
PYTHONPATH=src python experiments/exp15_case_studies.py
PYTHONPATH=src python experiments/exp16_strategy_match_analysis.py
PYTHONPATH=src python experiments/exp17_non_circularity_v5.py
PYTHONPATH=src python experiments/exp22_resource_penalized_strategy_validation.py
PYTHONPATH=src python experiments/exp23_budget_constrained_strategy_validation.py
PYTHONPATH=src python experiments/exp24_pareto_frontier_analysis.py
```

Several later experiments consume earlier CSV outputs. For a clean rebuild, run
them in numeric order.

## Outputs

Versioned outputs are written to:

```text
results/prelim_v1/
results/prelim_v2/
results/prelim_v3/
results/prelim_v4/
results/prelim_v5/
results/prelim_v6/
figures/prelim_v1/
figures/prelim_v2/
figures/prelim_v3/
figures/prelim_v4/
figures/prelim_v5/
figures/prelim_v6/
```

The most useful current summaries are:

- `results/prelim_v4/PRELIMINARY_REPORT_V4.md`
- `results/prelim_v5/PRELIMINARY_REPORT_V5.md`
- `results/prelim_v6/PRELIMINARY_REPORT_V6.md`
- `results/prelim_v6/exp22_resource_penalty_sweep_summary.csv`
- `results/prelim_v6/exp23_budget_constrained_summary.csv`
- `results/prelim_v6/exp24_pareto_frontier_summary.csv`

Large V6 per-case tables are reproducible and intentionally ignored by Git:

- `results/prelim_v6/exp22_resource_penalized_policy_comparison.csv`
- `results/prelim_v6/exp23_budget_constrained_policy_comparison.csv`

## Interpretation

The clean Paper 2 framing is no longer "a new scheduler beats smooth." V1 and
V2 showed that slack smoothing is a very strong deterministic baseline, and
`sigma_DA_v2` does not provide a decisive scheduler contribution.

The stronger framing is:

> Bounded magic-state delivery creates distinct execution regimes. Some require
> no intervention, some are solved well by slack smoothing, some are
> buffer-limited, some are capacity-limited, and some are sensitive to delivery
> uncertainty or effective-capacity degradation.

V5 supports that the regime assignment is not merely self-fulfilling. V6 adds
the necessary resource-aware caveat: if extra capacity is cheap enough, simply
increasing `C` remains hard to beat. The framework is most defensible as a
diagnostic and sensitivity tool unless stronger resource pricing or budget
constraints make the regime-aware policy clearly preferable.

## Validation

The current checked state passes:

```text
pytest
python -m compileall src experiments tests
```
