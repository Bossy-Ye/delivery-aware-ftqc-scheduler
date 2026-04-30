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
