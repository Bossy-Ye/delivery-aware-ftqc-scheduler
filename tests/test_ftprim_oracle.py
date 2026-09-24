"""Oracle, scoring and threshold-policy checks on small synthetic programs."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
pytest.importorskip("ortools")

from ftqc_delivery.ftprim import oracle as O  # noqa: E402
from ftqc_delivery.ftprim.workloads import Workload  # noqa: E402


def _workload(gates):
    free, layer = {}, []
    for a, b in gates:
        l = max(free.get(a, 0), free.get(b, 0))
        layer.append(l)
        free[a] = free[b] = l + 1
    nq = 1 + max(max(g) for g in gates)
    per = [[] for _ in range(nq)]
    for i, (a, b) in enumerate(gates):
        per[a].append(i)
        per[b].append(i)
    return Workload("t", "t", "t", nq, list(gates), layer, max(layer) + 1, 0, 0, "", per)


def _costs(delta, tel, s_mem=0.0, rho=0.0):
    return O.Costs(e_remote=1e-4 + delta, e_local=1e-4, e_tel=tel, s_mem=s_mem, n=9, rho=rho)


def test_clean_pattern_threshold_matches_oracle():
    # Qubit 0 (QPU 0) interacts k times with qubits 1..k on QPU 1; one-way (no return).
    for k in (1, 2, 5, 9):
        w = _workload([(0, j) for j in range(1, k + 1)])
        homes = [0] + [1] * k
        cap = [1, k + 1]
        costs = _costs(delta=1e-4, tel=4.5e-4)          # K* = 4.5
        sol = O.solve(w, homes, cap, "failure", costs, time_limit=20)
        s = O.score(w, homes, sol.loc, costs)
        assert sol.status == "OPTIMAL"
        assert s["teleports"] == (1 if k >= 5 else 0)
        ebit = O.solve(w, homes, cap, "ebits", costs, time_limit=20)
        se = O.score(w, homes, ebit.loc, costs)
        assert se["batches"] == min(k, 1)


def test_threshold_policy_is_a_burst_rule():
    w = _workload([(0, j) for j in range(1, 6)])
    homes = [0] + [1] * 5
    cap = [1, 6]
    for K, moves in ((5, 1), (6, 0), (1, 1)):
        s = O.score(w, homes, O.threshold_policy(w, homes, cap, K), _costs(1e-4, 4.5e-4))
        assert s["teleports"] == moves


def test_capacity_is_respected():
    # Both QPUs are full, so any move must be paired with a move the other way.
    w = _workload([(0, j) for j in range(1, 6)])
    homes = [0] + [1] * 5
    cap = [1, 5]
    costs = _costs(1e-4, 1e-6)
    sol = O.solve(w, homes, cap, "failure", costs, time_limit=20)
    occupancy = sol.loc.sum(axis=0)
    assert (occupancy <= cap[1]).all() and (w.nq - occupancy <= cap[0]).all()
    assert O.score(w, homes, sol.loc, costs)["teleports"] % 2 == 0
    greedy = O.threshold_policy(w, homes, cap, 1)
    assert O.score(w, homes, greedy, costs)["teleports"] == 0   # no free slot for a one-way move


def test_rate_limited_generation_counts_batches():
    w = _workload([(0, 1)] * 4)
    homes = [0, 1]
    s = O.score(w, homes, O.static_loc(w, homes), _costs(1e-4, 1e-3, s_mem=1e-6, rho=50))
    assert s["batches"] == 4 and s["run_rounds"] == 200
