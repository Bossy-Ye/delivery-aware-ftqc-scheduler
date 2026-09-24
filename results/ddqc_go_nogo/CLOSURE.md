# Closure: control-flow-aware placement candidate closed as NO_GO

The research lead closed this candidate as NO_GO on 2026-09-24, before the
full placement matrix completed. The matrix was stopped at 260 of 392
configurations and its partial output was not written, so no `RAW_RESULTS.csv`
exists for this study and none of its numbers should be quoted.

The evidence gathered before closure, all committed in this directory:

* `CENSUS.csv`, `CENSUS_SUMMARY.json`: 241 real dynamic programs from five
  independent sources, 333,794 measurement-conditioned regions, 99.96% of them
  single-qubit only, and no divergent region at all.
* `MECHANISM_H1_H2.json`: a single placement's expected cost depends only on
  each interaction's marginal probability; exclusive and independent twins
  give identical results, and divergent regions give exactly zero headroom at
  p = 1/2.
* `ARTIFACT_AUDIT.md`, `NOVELTY_AUDIT.md`: no inspected compiler does
  branch-aware placement; QuPort and memQ DQC are blind to branch
  communication when run on the motivating example.
