# Screening: is the opportunity worth a full evaluation?

Run under the frozen contract, before the full matrix. Two structured
programs (`qt_qft6`, `qt_aliassamp16`), one strongly dependent control
(`qt_multiand10`), two regimes (constrained `A_400_0.5`, abundant
`A_3200_0.5`), both frozen assignments, all seven transformations: 84 runs.
Raw rows: `SCREENING_RESULTS.csv`.

## The gate

> Stop early unless some valid transformation reaches 5% makespan improvement
> under constrained supply **while remaining near zero under abundant
> supply**.

The second half of that condition is the whole point: a transformation that
helps just as much when magic states are free was not helping by reshaping
magic-state demand.

| transformation | best gain, constrained | best gain, abundant | control | verdict |
|---|---:|---:|---:|---|
| commuting | +68.9% | **+81.8%** | 0.0% | gain is not supply-driven |
| commuting_pace1 | +8.7% | +8.7% | 0.0% | gain is not supply-driven |
| commuting_pace2 | +29.5% | +29.5% | 0.0% | gain is not supply-driven |
| commuting_pace4 | +40.1% | +40.8% | 0.0% | gain is not supply-driven |
| commuting_pace8 | +65.5% | +66.6% | 0.0% | gain is not supply-driven |
| conventional_pace4 | 0.0% | 0.0% | 0.0% | no constrained gain |

No transformation satisfies the conjunction. Every transformation that gains
under constrained supply gains the same amount or more when magic states are
abundant. **The screening gate fires: likely NO_GO.**

## Why, in one line of evidence

`qt_aliassamp16`, all-T assignment, the same program under two opposite
supply regimes:

| machine | conventional | commuting | improvement | stalls |
|---|---:|---:|---:|---:|
| A_400_0.5 (constrained) | 347 | 225 | +35.2% | 8 |
| A_3200_0.5 (abundant) | 347 | 224 | +35.4% | 6 |

The makespans are the same to within one cycle whether the factories are
constrained or sixteen times larger, and the program stalls for 6 to 8 cycles
out of 347. These programs are **depth-bound, not supply-bound**: what limits
them is the dependency chain, not magic-state delivery. A transformation that
shortens the chain helps, and it helps exactly as much when magic states cost
nothing.

The pacing transformations, which were designed to isolate temporal smoothing
by increasing depth while holding work constant, never beat the commuting
graph they are applied to; they claw back part of what pacing gave away. The
`conventional_pace4` row is exactly zero everywhere, which is the expected
result: pacing adds no constraint that conventional lowering had not already
imposed.

## Decision

The contract says stop and report likely NO_GO. The full matrix was run
anyway, as pre-registered confirmation across all 22 workloads, 8 machines and
both assignments, rather than to look for a better answer. Its results are in
`RAW_RESULTS.csv` and the memo.
