# Delivery-Aware FTQC Scheduler

This repository contains preliminary experiments for delivery-aware scheduling
under bounded magic-state delivery in fault-tolerant quantum computing.

The project builds on the diagnostic model introduced in:

> "When T-Depth Misleads: Predicting Fault-Tolerant Quantum Execution Slowdown
> under Magic-State Delivery Constraints"

The prior work showed that static T-depth can misrepresent executable
performance when magic-state delivery is bounded. It introduced slack ratio and
Delta_max as indicators of structural flexibility and schedule-level delivery
pressure.

This repository investigates the next question:

Can a compiler actively reshape temporal T-state demand so that the same
magic-state delivery capacity produces fewer stalls and shorter executable
makespan?

The main preliminary goal is to compare a new delivery-aware scheduler against
three baselines: depth-oriented scheduling, capacity-aware quota scheduling, and
slack-based smoothing.

Paper 1 showed that bounded magic-state delivery can make T-depth misleading and
that Delta_max predicts delivery-induced slowdown for a fixed schedule. This
repository tests the next step: whether a compiler can actively reshape T-state
demand to reduce Delta_max, stalls, executable makespan, and required delivery
capacity under the same bounded magic-state supply.

## Schedulers

- `static`: depth-oriented ASAP scheduling.
- `capacity_aware`: simple per-layer T quota scheduling.
- `smooth`: slack-based demand smoothing.
- `delivery_aware`: `sigma_DA`, a heuristic that combines slack, downstream
  criticality, delivery capacity, and buffer/backlog pressure.

## Scope

This is a compiler-side demand-shaping experiment. It does not optimize
magic-state factory architecture, physical qubit cost, code distance, routing,
or factory layout.

The question is:

> Given fixed delivery capacity `C` and buffer `B`, how should a circuit
> schedule consume magic states over time?

## Quick Start

Create an environment and install the small dependency set:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run tests:

```bash
PYTHONPATH=src pytest
```

Run the deterministic preliminary experiments:

```bash
PYTHONPATH=src python experiments/exp1_schedule_reshaping.py
PYTHONPATH=src python experiments/exp2_required_capacity.py
```

Optional baseline check:

```bash
PYTHONPATH=src python experiments/exp0_reproduce_paper1_baselines.py
```

## Outputs

CSV outputs are written under:

```text
results/prelim_v1/
```

Figures are written under:

```text
figures/prelim_v1/
```

The main preliminary deliverables are:

- `results/prelim_v1/exp1_schedule_reshaping.csv`
- `results/prelim_v1/exp2_required_capacity.csv`
- `results/prelim_v1/PRELIMINARY_REPORT.md`
- `figures/prelim_v1/fig1_demand_trace_static_vs_DA.pdf`
- `figures/prelim_v1/fig2_makespan_comparison.pdf`
- `figures/prelim_v1/fig3_delta_vs_static_penalty.pdf`
- `figures/prelim_v1/fig4_required_capacity_Cstar.pdf`

## Go / No-Go Signals

Continue toward Paper 2 if several of these hold:

- `sigma_DA` reduces executable makespan or stalls by at least 20% relative to
  `sigma_static` on high-compressibility DAGs.
- `sigma_DA` improves over `sigma_smooth` by 5-10% on some nontrivial
  workloads.
- `sigma_DA` matches or improves `sigma_ca` while avoiding large static-depth
  penalties.
- At least one semi-real multiplier or QFT workload shows stable improvement.
- `sigma_DA` reduces required capacity `C*_0.05` by at least one unit.
- Negative controls such as adders and low-compressibility DAGs do not degrade
  badly.

Stop or redesign if improvements only appear in constructed DAGs, if
`Delta_max` decreases without executable makespan improving, or if required
delivery capacity does not improve at all.
