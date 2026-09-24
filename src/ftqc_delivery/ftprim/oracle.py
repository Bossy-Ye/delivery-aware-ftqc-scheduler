"""Remote-operation decisions for whole programs on two QPUs.

Decision space (shared by every policy): the QPU of each logical qubit at each
CX layer. A CX whose qubits sit on different QPUs is a transversal non-local
CNOT; a change of QPU between layers is a logical teleportation. Capacity limits
how many data blocks each QPU holds (Bell-pair blocks are separate).

Execution model (identical for optimisation and scoring): lock-step layers.
Every layer takes ``ROUNDS`` syndrome rounds; a layer preceded by at least one
teleport takes ``ROUNDS`` more (the post-teleport rounds), and all live blocks
run rounds throughout. Ebits are generated continuously and may be buffered,
so the run cannot be shorter than ``rho`` rounds per consumed ebit batch
(``n`` Bell pairs; one per non-local CNOT or teleport).

Failure model (sum of calibrated contributions, valid while the total is
small; scored as 1 - exp(-sum)):
    sum over CX of e_remote or e_local  +  teleports * e_tel
    + s_mem * n_qubits * run_rounds
where ``e_*`` are per-operation excesses over plain memory, all taken from the
TMCBS pattern simulations for the same code, p and p_ebit.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

ROUNDS = 3
SETTLE = 4


@dataclass(frozen=True)
class Costs:
    e_remote: float
    e_local: float
    e_tel: float
    s_mem: float
    n: int            # Bell pairs per ebit batch (data qubits per block)
    rho: float        # rounds to generate one batch; 0 = unconstrained

    @property
    def delta(self) -> float:
        return self.e_remote - self.e_local


@dataclass
class Solution:
    loc: np.ndarray            # [nq, L] QPU per layer
    status: str
    seconds: float
    objective: Optional[float] = None
    bound: Optional[float] = None


def score(w, homes: Sequence[int], loc: np.ndarray, costs: Costs) -> Dict[str, float]:
    """Resources, latency and failure of a placement trajectory."""
    L = w.n_layers
    prev = np.array(homes)[:, None]
    full = np.concatenate([prev, loc], axis=1)
    moves = full[:, 1:] != full[:, :-1]                   # [nq, L]
    n_moves = int(moves.sum())
    move_layers = int(moves.any(axis=0).sum())
    remote = sum(1 for (a, b), l in zip(w.gates, w.layer) if loc[a, l] != loc[b, l])
    local = len(w.gates) - remote
    batches = remote + n_moves
    compute_rounds = SETTLE + ROUNDS * (L + move_layers)
    run_rounds = max(compute_rounds, costs.rho * batches)
    comm = remote * costs.e_remote + local * costs.e_local + n_moves * costs.e_tel
    memory = costs.s_mem * w.nq * run_rounds
    total = comm + memory
    return dict(remote_ops=remote, local_ops=local, teleports=n_moves, move_layers=move_layers,
                ebit_pairs=batches * costs.n, batches=batches, run_rounds=run_rounds,
                compute_rounds=compute_rounds, fail_ops=comm, fail_memory=memory,
                fail_sum=total, fail_prob=-math.expm1(-total))


def static_loc(w, homes) -> np.ndarray:
    return np.repeat(np.array(homes)[:, None], w.n_layers, axis=1)


def capacities(nq: int, homes: Sequence[int], slack: int) -> List[int]:
    return [sum(1 for h in homes if h == s) + slack for s in (0, 1)]


def _scale(costs: Costs, nq: int) -> Dict[str, int]:
    """Integer objective weights for CP-SAT (relative precision ~1e-6)."""
    vals = [costs.delta, costs.e_tel, costs.s_mem * nq]
    top = max(abs(v) for v in vals if v) if any(vals) else 1.0
    unit = top / 1e6
    return dict(delta=int(round(costs.delta / unit)), tel=int(round(costs.e_tel / unit)),
                mem=int(round(costs.s_mem * nq / unit)), unit=unit)


def solve(w, homes: Sequence[int], cap: Sequence[int], objective: str, costs: Costs,
          time_limit: float = 60.0, fix_batches: Optional[int] = None, workers: int = 4,
          hint: Optional[np.ndarray] = None) -> Solution:
    """Exact (CP-SAT) optimum of ``objective`` in {"ebits", "failure"}.

    ``fix_batches`` constrains the number of ebit batches, used for the
    lexicographic tie-break of the ebit objective by failure.
    """
    from ortools.sat.python import cp_model
    t0 = time.perf_counter()
    nq, L = w.nq, w.n_layers
    m = cp_model.CpModel()
    x = [[m.NewBoolVar(f"x{q}_{l}") for l in range(L)] for q in range(nq)]
    mv = [[m.NewBoolVar(f"m{q}_{l}") for l in range(L)] for q in range(nq)]
    for q in range(nq):
        for l in range(L):
            prev = x[q][l - 1] if l else (1 if homes[q] else 0)
            if isinstance(prev, int):
                if prev:
                    m.Add(mv[q][l] == 1 - x[q][l])
                else:
                    m.Add(mv[q][l] == x[q][l])
            else:
                m.AddBoolXOr([x[q][l], prev, mv[q][l].Not()])
    y = []
    for gi, ((a, b), l) in enumerate(zip(w.gates, w.layer)):
        v = m.NewBoolVar(f"y{gi}")
        m.AddBoolXOr([x[a][l], x[b][l], v.Not()])
        y.append(v)
    z = [m.NewBoolVar(f"z{l}") for l in range(L)]
    for l in range(L):
        for q in range(nq):
            m.AddImplication(mv[q][l], z[l])
        m.Add(z[l] <= sum(mv[q][l] for q in range(nq)))
    for l in range(L):
        col = sum(x[q][l] for q in range(nq))
        m.Add(col <= cap[1])
        m.Add(nq - col <= cap[0])
    batches = sum(y) + sum(mv[q][l] for q in range(nq) for l in range(L))
    if fix_batches is not None:
        m.Add(batches == fix_batches)
    if objective == "ebits" and fix_batches is None:
        m.Minimize(batches)
    else:
        s = _scale(costs, nq)
        compute = SETTLE + ROUNDS * L + ROUNDS * sum(z)
        horizon = SETTLE + ROUNDS * 2 * L + int(math.ceil(costs.rho)) * (len(w.gates) + nq * L) + 1
        run = m.NewIntVar(0, horizon, "run")
        m.Add(run >= compute)
        if costs.rho > 0:
            # run >= rho * batches, with rho kept rational to 1e-3.
            num = int(round(costs.rho * 1000))
            m.Add(1000 * run >= num * batches)
        m.Minimize(s["delta"] * sum(y) + s["tel"] * sum(mv[q][l] for q in range(nq) for l in range(L))
                   + s["mem"] * run)
    if hint is not None:
        for q in range(nq):
            for l in range(L):
                m.AddHint(x[q][l], int(hint[q, l]))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 0
    status = solver.Solve(m)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solution(loc=static_loc(w, homes), status=name, seconds=time.perf_counter() - t0)
    loc = np.array([[solver.Value(x[q][l]) for l in range(L)] for q in range(nq)], dtype=np.int8)
    return Solution(loc=loc, status=name, seconds=time.perf_counter() - t0,
                    objective=solver.ObjectiveValue(), bound=solver.BestObjectiveBound())


def threshold_policy(w, homes: Sequence[int], cap: Sequence[int], K: int) -> np.ndarray:
    """Myopic rule: before a remote CX, teleport an operand whose run of upcoming
    interactions with the other QPU has length >= K (capacity permitting)."""
    nq, L = w.nq, w.n_layers
    cur = list(homes)
    occ = [cur.count(0), cur.count(1)]
    loc = np.zeros((nq, L), dtype=np.int8)
    pos = [0] * nq  # next index into per_qubit for each qubit
    by_layer: Dict[int, List[int]] = {}
    for gi, l in enumerate(w.layer):
        by_layer.setdefault(l, []).append(gi)

    def burst(q: int, side: int, start: int) -> int:
        run = 0
        for gi in w.per_qubit[q][start:]:
            a, b = w.gates[gi]
            other = b if a == q else a
            if cur[other] != side:
                break
            run += 1
        return run

    for l in range(L):
        for gi in by_layer.get(l, []):
            a, b = w.gates[gi]
            if cur[a] != cur[b]:
                ba = burst(a, cur[b], pos[a])
                bb = burst(b, cur[a], pos[b])
                for q, bl, dest in sorted([(a, ba, cur[b]), (b, bb, cur[a])], key=lambda t: -t[1]):
                    if bl >= K and occ[dest] < cap[dest]:
                        occ[cur[q]] -= 1
                        occ[dest] += 1
                        cur[q] = dest
                        break
            pos[a] += 1
            pos[b] += 1
        loc[:, l] = cur
    return loc
