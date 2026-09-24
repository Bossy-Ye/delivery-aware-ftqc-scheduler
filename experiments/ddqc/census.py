"""Census of measurement-conditioned regions across independent dynamic-program sources.

Answers the precondition of the whole hypothesis before any placement is
computed: how often do real dynamic programs contain branches whose
multi-qubit communication depends on the measurement outcome?
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ftqc_delivery.ddqc.census import census_cirq, census_qasm2, census_qasm3, census_qiskit
from ftqc_delivery.utils.io import write_csv_rows

SCRATCH = Path("/tmp/claude-0/-home-user/e20503e7-ec17-5c34-979d-e2d3051d15b7/scratchpad")
RESULT_DIR = ROOT / "results" / "ddqc_go_nogo"

SOURCES = {
    "openqasm": ("openqasm/openqasm", "7fbf9e9eb3692a1288c014d6efd43523701886c6"),
    "qasmbench": ("pnnl/QASMBench", "357b942396d5c2b7cbc1c229c585a6ef5ccaebac"),
    "veriqbench": ("Veri-Q/Benchmark", "1c03e45371e5701f62c123943dec1cace4d46767"),
    "mqtbench": ("mqt.bench (PyPI)", "2.3.0"),
    "qualtran": ("quantumlib/Qualtran (PyPI)", "0.7.0"),
}


def programs():
    """Yield (census, family) for every dynamic program in every source."""

    for path in sorted((SCRATCH / "openqasm" / "examples").glob("*.qasm")):
        census = census_qasm3(path, path.stem, "openqasm")
        if census.regions:
            yield census, path.stem

    for group in ("small", "medium"):
        for folder in sorted((SCRATCH / "qasmbench" / group).iterdir()):
            files = [p for p in folder.glob("*.qasm") if "transpiled" not in p.name]
            if not files:
                continue
            census = census_qasm2(files[0], folder.name, "qasmbench")
            if census.regions:
                yield census, folder.name

    dynamic = SCRATCH / "veriqbench" / "dynamic"
    for path in sorted(dynamic.rglob("*.qasm")):
        census = census_qasm2(path, path.stem, "veriqbench")
        if census.regions:
            family = path.parent.name if path.parent != dynamic else path.stem
            yield census, family

    from mqt.bench import BenchmarkLevel, get_benchmark

    for name in ("dynamic_qft", "ghz_dynamic", "iqpe"):
        for size in (4, 6, 8, 12):
            try:
                circuit = get_benchmark(name, BenchmarkLevel.INDEP, size)
            except Exception:
                continue
            census = census_qiskit(circuit, f"{name}_{size}", "mqtbench")
            if census.regions:
                yield census, name

    import cirq
    from qualtran import QUInt
    from qualtran.bloqs import arithmetic, data_loading, mod_arithmetic

    builders = {
        "add8": lambda: arithmetic.Add(QUInt(8)),
        "sub8": lambda: arithmetic.Subtract(QUInt(8)),
        "cadd8": lambda: arithmetic.CAdd(QUInt(8)),
        "addk8": lambda: arithmetic.AddK(QUInt(8), k=93),
        "ltc8": lambda: arithmetic.LessThanConstant(8, 101),
        "gt8": lambda: arithmetic.GreaterThan(8, 8),
        "equals8": lambda: arithmetic.Equals(QUInt(8)),
        "modadd8": lambda: mod_arithmetic.ModAdd(8, mod=251),
        "modneg8": lambda: mod_arithmetic.ModNeg(QUInt(8), mod=251),
        "qrom16": lambda: data_loading.QROM.build_from_data(list(range(16)), target_bitsizes=(5,)),
    }

    def keep(op) -> bool:
        return (
            isinstance(op, cirq.ClassicallyControlledOperation)
            or cirq.is_measurement(op)
            or (len(op.qubits) <= 2 and not str(op.gate).startswith("And"))
        )

    for name, build in builders.items():
        try:
            circuit = build().decompose_bloq().flatten().to_cirq_circuit()
            lowered = cirq.Circuit(cirq.decompose(circuit, keep=keep))
        except Exception as error:
            print(f"  skipped qualtran {name}: {type(error).__name__}")
            continue
        census = census_cirq(lowered, f"qt_{name}", "qualtran")
        if census.regions:
            yield census, name


def main() -> None:
    warnings.simplefilter("ignore")
    rows = []
    for census, family in programs():
        counts = census.counts()
        total = sum(counts.values())
        rows.append(
            {
                "program": census.name,
                "source": census.source,
                "repository": SOURCES[census.source][0],
                "version": SOURCES[census.source][1],
                "family": family,
                "regions": total,
                **counts,
                "multi_qubit_conditional_regions": counts["present_absent"] + counts["divergent"] + counts["identical"],
                "novel_conditional_pairs": census.novel_conditional_pairs(),
                "unconditional_multi_qubit_ops": census.unconditional_multi_qubit_ops,
            }
        )
    fields = list(rows[0].keys())
    write_csv_rows(RESULT_DIR / "CENSUS.csv", rows, fields)

    summary = {}
    for source in SOURCES:
        sub = [r for r in rows if r["source"] == source]
        agg = {k: sum(r[k] for r in sub) for k in ("regions", "local", "present_absent", "divergent", "identical", "loop", "novel_conditional_pairs")}
        agg["programs"] = len(sub)
        agg["families"] = len({r["family"] for r in sub})
        agg["programs_with_any_divergent"] = sum(1 for r in sub if r["divergent"] > 0)
        agg["programs_with_multi_qubit_conditionals"] = sum(1 for r in sub if r["multi_qubit_conditional_regions"] > 0)
        summary[source] = agg
    total = {k: sum(v[k] for v in summary.values()) for k in next(iter(summary.values()))}
    summary["ALL"] = total
    (RESULT_DIR / "CENSUS_SUMMARY.json").write_text(json.dumps(summary, indent=2))

    print(f"{'source':11s} {'progs':>5s} {'fams':>4s} {'regions':>8s} {'local':>8s} {'pres/abs':>8s} {'diverg':>6s} {'ident':>5s} {'loop':>4s} {'novel':>5s} {'w/ multi':>8s} {'w/ div':>6s}")
    for source, agg in summary.items():
        print(f"{source:11s} {agg['programs']:5d} {agg['families']:4d} {agg['regions']:8d} {agg['local']:8d} "
              f"{agg['present_absent']:8d} {agg['divergent']:6d} {agg['identical']:5d} {agg['loop']:4d} "
              f"{agg['novel_conditional_pairs']:5d} {agg['programs_with_multi_qubit_conditionals']:8d} {agg['programs_with_any_divergent']:6d}")


if __name__ == "__main__":
    main()
