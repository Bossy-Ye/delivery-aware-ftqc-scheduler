"""Why does the commuting transformation help, and why does pacing not?

Separates the four competing explanations named in the contract, and then
asks the fairness question the frozen grid cannot answer on its own: is the
negative result an artefact of charging one cycle per Clifford operation?
"""

from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_temporal import CONTROLS, MACHINES, TRANSFORMS, build_program, machine_for, _assignment_for, _demand_trace

from ftqc_delivery.mrc.corpus import CORPUS
from ftqc_delivery.mrc.execution import critical_path, execute, resource_counts
from ftqc_delivery.mrc.resources import CCZ, T, coupled_machine
from ftqc_delivery.utils.io import read_csv_rows, write_csv_rows

RESULT_DIR = Path(__file__).resolve().parents[2] / "results" / "temporal_transform_go_nogo"
SEED = 20260923


def correlation(xs, ys) -> float:
    if len(xs) < 3:
        return float("nan")
    mx, my = st.fmean(xs), st.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else float("nan")


def main() -> None:
    rows = [r for r in read_csv_rows(RESULT_DIR / "RAW_RESULTS.csv")]
    for r in rows:
        for k in ("improvement", "depth_reduction", "makespan", "depth", "total_stalls",
                  "t_waste", "ccz_waste", "t_count", "ccz_count", "burstiness", "peak_stage_demand"):
            r[k] = float(r[k])

    targets = [r for r in rows if r["role"] == "target"]
    comm = [r for r in targets if r["transformation"] == "commuting"]
    big = [r for r in comm if r["improvement"] >= 0.10]

    print("== H2 depth reduction: does the gain track depth? ==")
    print(f"  cases with >=10% gain: {len(big)} of {len(comm)}")
    print(f"  correlation(improvement, depth reduction) = {correlation([r['improvement'] for r in comm], [r['depth_reduction'] for r in comm]):.3f}")
    print(f"  on those cases, median improvement {st.median([r['improvement'] for r in big]):+.3f} "
          f"vs median depth reduction {st.median([r['depth_reduction'] for r in big]):+.3f}")

    print("\n== H1 temporal smoothing: do stalls and backlog explain it? ==")
    base = {(r['workload'], r['assignment'], r['machine']): r for r in rows if r['transformation'] == 'conventional'}
    deltas = []
    for r in big:
        b = base[(r['workload'], r['assignment'], r['machine'])]
        saved = b['makespan'] - r['makespan']
        stall_drop = b['total_stalls'] - r['total_stalls']
        deltas.append((saved, stall_drop, b['total_stalls']))
    print(f"  median cycles saved      : {st.median([d[0] for d in deltas]):8.1f}")
    print(f"  median stall cycles in the baseline: {st.median([d[2] for d in deltas]):8.1f}")
    print(f"  median stall reduction   : {st.median([d[1] for d in deltas]):8.1f}")
    print(f"  fraction of the saving that stall reduction can account for: "
          f"{st.median([d[1] / d[0] for d in deltas if d[0] > 0]):.3f}")
    print(f"  median burstiness before {st.median([base[(r['workload'], r['assignment'], r['machine'])]['burstiness'] for r in big]):.3f} "
          f"after {st.median([r['burstiness'] for r in big]):.3f}")

    print("\n== H3 work reduction ==")
    mismatch = [r for r in rows if r['t_count'] != base[(r['workload'], r['assignment'], r['machine'])]['t_count']
                or r['ccz_count'] != base[(r['workload'], r['assignment'], r['machine'])]['ccz_count']]
    print(f"  runs whose T or CCZ count differs from their baseline: {len(mismatch)} of {len(rows)}")

    print("\n== H4 model artefact: buffer size ==")
    out = []
    probe = [w for w in ("qt_qft6", "qt_aliassamp16", "qb_multiplier_n15", "qmpa_div6", "qt_multiand10")]
    for workload in probe:
        for buffer_capacity in (16, 32, 64):
            machine = coupled_machine("A", 400, 0.5, buffer_capacity=buffer_capacity, seed=SEED)
            costs = {}
            for transformation in ("conventional", "commuting", "commuting_pace4"):
                program = build_program(workload, transformation)
                assignment = _assignment_for(program, machine, "t")
                costs[transformation] = execute(program.instantiate(assignment), machine).makespan
            gain = (costs["conventional"] - costs["commuting"]) / costs["conventional"]
            out.append({"probe": "buffer", "workload": workload, "setting": buffer_capacity,
                        "conventional": costs["conventional"], "commuting": costs["commuting"],
                        "commuting_pace4": costs["commuting_pace4"], "improvement": round(gain, 4)})
            print(f"  {workload:18s} buffer={buffer_capacity:3d} conv={costs['conventional']:5d} "
                  f"comm={costs['commuting']:5d} gain={gain:+.3f}")

    print("\n== fairness probe, OUTSIDE the frozen grid: what if Cliffords were free? ==")
    print("  Charging one cycle per Clifford makes these programs depth bound. If")
    print("  Cliffords were free the same programs would be supply bound, which is")
    print("  the regime the hypothesis is about. Reported as a limitation, not as")
    print("  evidence: the contract's thresholds apply to the frozen grid only.")
    print(f"  {'workload':18s} {'w':>2s} {'conv':>6s} {'comm':>6s} {'pace2':>6s} {'pace4':>6s} "
          f"{'conv_stall':>10s} {'bound':>8s} {'comm_gain':>9s} {'pace_gain':>9s}")
    for workload in probe:
        for weight in (1, 0):
            machine = coupled_machine("A", 400, 0.5, seed=SEED)
            costs, stalls = {}, {}
            for transformation in ("conventional", "commuting", "commuting_pace2", "commuting_pace4"):
                program = build_program(workload, transformation)
                assignment = _assignment_for(program, machine, "t")
                trace = execute(program.instantiate(assignment), machine, clifford_weight=weight)
                costs[transformation] = trace.makespan
                stalls[transformation] = trace.total_stalls
            conv = costs["conventional"]
            comm_gain = (conv - costs["commuting"]) / conv if conv else 0
            pace_gain = (costs["commuting"] - min(costs["commuting_pace2"], costs["commuting_pace4"])) / max(1, costs["commuting"])
            bound = "supply" if stalls["conventional"] > 0.25 * conv else "depth"
            out.append({"probe": "clifford_weight", "workload": workload, "setting": weight,
                        "conventional": conv, "commuting": costs["commuting"],
                        "commuting_pace4": costs["commuting_pace4"], "improvement": round(comm_gain, 4)})
            print(f"  {workload:18s} {weight:2d} {conv:6d} {costs['commuting']:6d} "
                  f"{costs['commuting_pace2']:6d} {costs['commuting_pace4']:6d} "
                  f"{stalls['conventional']:10d} {bound:>8s} {comm_gain:+9.3f} {pace_gain:+9.3f}")

    write_csv_rows(RESULT_DIR / "MECHANISM_ABLATIONS.csv", out,
                   ["probe", "workload", "setting", "conventional", "commuting", "commuting_pace4", "improvement"])

    print("\n== sources and families reaching 10% (commuting, constrained) ==")
    con = [r for r in comm if r["regime"] == "constrained" and r["improvement"] >= 0.10]
    print(f"  workloads: {sorted({r['workload'] for r in con})}")
    print(f"  sources:   {sorted({r['source'] for r in con})}")
    print(f"  families:  {sorted({r['family'] for r in con})}")


if __name__ == "__main__":
    main()
