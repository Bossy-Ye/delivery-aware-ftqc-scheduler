"""Trace DQC-NAC's executed teleport-vs-migration decision path.

Run with DQC-NAC's own pins (qiskit 0.46, numpy<2, networkx 3.1, pymetis):

    PYTHONPATH=<dqcnac clone> python experiments/ftprim/probe_dqcnac.py OUT.json

DQC-NAC imports ``qoala``/``netqasm`` at module load; they come from a private
NetSquid index, so ``qoala_import_stub`` supplies import-only placeholders. They
are used only by the Qoala output parser, which this probe does not run
(``parse=False``); the partitioner, gate grouping and scheduler are unmodified.
"""
import io, json, logging, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qoala_import_stub  # noqa: E402,F401
from collections import Counter
from os import path

from qiskit import QuantumCircuit, transpile

import dqcnac
from dqcnac.compiler import CompileManager
from dqcnac.network_configuration import simple_network
from dqcnac.nonlocal_gate_scheduling import nonlocal_gate_schedule as ngs
from dqcnac.nonlocal_gate_scheduling.nonlocal_operations import CatEnt, CatDisEnt, Teleport

ROOT = path.dirname(dqcnac.__file__) + "/../examples/benchmark_circuits"

calls = Counter()
orig_cost = ngs.NonlocalGateSchedule.circuit_cost
def traced_cost(executed):
    calls["circuit_cost"] += 1
    return orig_cost(executed)
ngs.NonlocalGateSchedule.circuit_cost = staticmethod(traced_cost)
orig_tel = ngs.NonlocalGateSchedule.get_teleport
def traced_tel(self, gate, state):
    calls["get_teleport"] += 1
    return orig_tel(self, gate, state)
ngs.NonlocalGateSchedule.get_teleport = traced_tel
orig_multi = ngs.NonlocalGateSchedule.compile_multi_gate
def traced_multi(self, *a, **k):
    calls["compile_multi_gate"] += 1
    return orig_multi(self, *a, **k)
ngs.NonlocalGateSchedule.compile_multi_gate = traced_multi

# Capture the scheduler's own INFO log line "TEL COST: x  MOG COST: y".
buf = io.StringIO()
h = logging.StreamHandler(buf); h.setLevel(logging.INFO)
lg = logging.getLogger(ngs.__name__); lg.setLevel(logging.INFO); lg.addHandler(h)
lg.propagate = False

orig_run = ngs.NonlocalGateSchedule.run
captured = {}
def traced_run(self, dag, gate_grouping, count_non_local_gates=False):
    state, regs = orig_run(self, dag, gate_grouping, count_non_local_gates)
    ops = Counter(type(g).__name__ for _, g in state.executed
                  if isinstance(g, (CatEnt, CatDisEnt, Teleport)))
    captured["ops"] = dict(ops)
    captured["ebits_by_circuit_cost"] = orig_cost(state.executed)
    return state, regs
ngs.NonlocalGateSchedule.run = traced_run

rows = []
for circ_name, device, n_nodes in [("adder_n28", "grid_16_4", 2), ("ghz_n40", "grid_32_4", 2),
                                   ("ising_n34", "grid_32_4", 2), ("dnn_n33", "grid_32_4", 2),
                                   ("cat_n35", "grid_32_4", 2), ("knn_n41", "grid_32_4", 2)]:
    circ = QuantumCircuit.from_qasm_file(f"{ROOT}/{circ_name}.qasm")
    tr = transpile(circ, basis_gates=["rx", "ry", "rz", "x", "y", "z", "h", "cz"],
                   optimization_level=3, seed_transpiler=1)
    for grouping in (True, False):
        calls.clear(); captured.clear(); buf.seek(0); buf.truncate()
        net = simple_network(n_nodes, device, "lnn")
        t0 = time.time()
        try:
            CompileManager().run(tr, net, True, grouping, 0, False, True, parse=False)
            err = None
        except Exception as e:  # record, do not hide
            err = f"{type(e).__name__}: {e}"[:200]
        log = buf.getvalue()
        decisions = re.findall(r"TEL COST: (\S+)\s+MOG COST: (\S+)", log)
        tel_chosen = sum(1 for t, m in decisions if t != "None" and int(t) < int(m))
        rows.append(dict(circuit=circ_name, device=device, n_nodes=n_nodes,
                         use_tel=True, gate_grouping=grouping, error=err,
                         seconds=round(time.time() - t0, 2),
                         calls=dict(calls), decisions=len(decisions),
                         teleport_chosen=tel_chosen, ops=captured.get("ops"),
                         ebits_by_circuit_cost=captured.get("ebits_by_circuit_cost"),
                         first_decisions=decisions[:5]))
        print(json.dumps(rows[-1]), flush=True)
json.dump(rows, open(sys.argv[1], "w"), indent=1)
