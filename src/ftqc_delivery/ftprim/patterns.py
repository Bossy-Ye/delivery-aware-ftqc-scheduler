"""Interaction patterns composed from TMCBS primitives.

One logical block ``A`` on QPU A interacts ``k`` times with block ``B`` on QPU B.

* Strategy ``R`` keeps ``A`` in place and applies ``k`` transversal non-local
  CNOTs (TMCBS ``non_local_cnot`` body, fresh ebits for every gate).
* Strategy ``T`` teleports ``A`` to QPU B with TMCBS's logical teleportation
  protocol, applies ``k`` local transversal CNOTs, and with ``ret=True``
  teleports it back to QPU A with the same protocol.

Every call below is a TMCBS builder call with TMCBS's own noise model, and the
settling cadence is TMCBS's (one opening round plus ``ROUNDS_BETWEEN_OPS``
rounds, and ``ROUNDS_BETWEEN_OPS`` rounds after every operation). ``R`` with
``k == 1`` is instruction-for-instruction identical to ``tmcbs.non_local_cnot``,
which the tests assert.

Time accounting: TMCBS applies no noise to a block while other blocks run
rounds, so a block's failure contribution depends only on how many rounds it
runs. The patterns therefore give every live block one round per time step:
blocks that exist at the same time run the same number of rounds (``B`` keeps
running rounds while ``A`` is teleported), and the Bell-pair blocks of a
teleport settle in parallel with the rounds that precede it. ``schedule``
returns the per-block round counts so the accounting can be checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import stim
import tmcbs
from tmcbs.experiments import _ROUNDS_BETWEEN_OPS, make_builder

ROUNDS_BETWEEN_OPS = _ROUNDS_BETWEEN_OPS
SETTLE_ROUNDS = 1 + ROUNDS_BETWEEN_OPS


@dataclass(frozen=True)
class Pattern:
    """A composed circuit plus the bookkeeping needed to cost it."""

    strategy: str          # "R", "T" or "T_rt"
    k: int                 # logical two-block interactions
    circuit: stim.Circuit
    ebit_pairs: int        # physical Bell pairs consumed
    nonlocal_layers: int   # transversal layers that consume ebits
    teleports: int
    time_rounds: int       # rounds on the critical path (A/B timeline)
    block_rounds: Dict[str, int]
    blocks: int


def _settle(b, blocks: List[int]) -> None:
    b.extractionRound(blocks, firstPass=True)
    for _ in range(ROUNDS_BETWEEN_OPS):
        b.extractionRound(blocks, firstPass=False, errors=True)


def _rounds(b, blocks: List[int], n: int) -> None:
    for _ in range(n):
        b.extractionRound(blocks, firstPass=False, errors=True)


def _nonlocal_cnot(b, control: int, target: int) -> None:
    """TMCBS non-local CNOT body: control block -> ebit pair -> target block."""
    b.transversalOp("CX", [control, 0], typeArr=["BB", "e"])
    b.measureEbit0ThenCorrectEbit1()
    b.transversalOp("CX", [1, target], typeArr=["e", "BB"])
    b.transversalOp("H", [1], typeArr=["e"])
    b.measureEbit1ThenCorrectCB(control)


def _teleport(b, payload: int, near: int, far: int) -> None:
    """TMCBS logical teleportation body: payload -> far via Bell pair (near, far)."""
    b.transversalOp("H", [near], typeArr=["BB"])
    _nonlocal_cnot(b, near, far)
    b.transversalOp("CX", [payload, near], typeArr=["BB", "BB"])
    b.transversalOp("H", [payload], typeArr=["BB"])
    b.measureCBThenCorrectCB("CX", [near, far])
    b.measureCBThenCorrectCB("CZ", [payload, far])


def _readout(b, code, blocks: List[int]) -> None:
    b.measureDataQubits(blocks)
    for blk in blocks:
        b.endOfCircuitDetectorsForLogicalMeasurementReadout(blk)
    for i, blk in enumerate(blocks):
        b.obsOffset(blk, code.k * i)


def remote(code, p: float, p_ebit: float, k: int) -> Pattern:
    """Strategy R: ``k`` non-local CNOTs from A (QPU A) onto B (QPU B)."""
    if k < 1:
        raise ValueError("k must be >= 1")
    A, B = 0, 1
    b = make_builder(code, 2, p, ebits=True)
    b.initQubits(A)
    b.initQubits(B)
    b.prepareEbits(transError=p_ebit)
    _settle(b, [A, B])
    for j in range(k):
        if j:
            b.prepareEbits(transError=p_ebit)
        _nonlocal_cnot(b, A, B)
        _rounds(b, [A, B], ROUNDS_BETWEEN_OPS)
    _readout(b, code, [A, B])
    t = SETTLE_ROUNDS + k * ROUNDS_BETWEEN_OPS
    return Pattern("R", k, b.getCirc(), k * code.n, k, 0, t,
                   {"A": t, "B": t}, 2)


def teleport(code, p: float, p_ebit: float, k: int, ret: bool = False) -> Pattern:
    """Strategy T: teleport A to QPU B, ``k`` local CNOTs, optionally teleport back.

    Blocks: 0 = A (QPU A), 1 = Bell half (QPU A), 2 = A' (QPU B), 3 = B (QPU B);
    with ``ret``: 4 = return Bell half (QPU B), 5 = A'' (QPU A, final home).
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    A, M, A2, B = 0, 1, 2, 3
    nblocks = 6 if ret else 4
    b = make_builder(code, nblocks, p, ebits=True)
    b.initQubits(A, errors=True)
    for blk in range(1, nblocks):
        b.initQubits(blk)
    b.prepareEbits(transError=p_ebit)
    # A and B settle while the Bell-pair blocks settle (parallel time steps).
    _settle(b, [A, B])
    _settle(b, [M, A2])
    _teleport(b, A, M, A2)
    _rounds(b, [A2, B], ROUNDS_BETWEEN_OPS)
    for _ in range(k):
        b.transversalOp("CX", [A2, B], typeArr=["BB", "BB"])
        _rounds(b, [A2, B], ROUNDS_BETWEEN_OPS)
    rounds = {"A": SETTLE_ROUNDS, "M": SETTLE_ROUNDS,
              "A'": SETTLE_ROUNDS + ROUNDS_BETWEEN_OPS * (k + 1),
              "B": SETTLE_ROUNDS + ROUNDS_BETWEEN_OPS * (k + 1)}
    t = SETTLE_ROUNDS + ROUNDS_BETWEEN_OPS * (k + 1)
    teleports, ebits, layers = 1, code.n, 1
    if ret:
        M2, A3 = 4, 5
        # The return Bell pair settles in parallel with the last rounds on A', B
        # (just-in-time preparation; it adds no time to the A/B timeline).
        _settle(b, [M2, A3])
        b.prepareEbits(transError=p_ebit)
        _teleport(b, A2, M2, A3)
        _rounds(b, [A3, B], ROUNDS_BETWEEN_OPS)
        rounds.update({"M'": SETTLE_ROUNDS, "A''": SETTLE_ROUNDS + ROUNDS_BETWEEN_OPS})
        rounds["B"] += ROUNDS_BETWEEN_OPS
        t += ROUNDS_BETWEEN_OPS
        teleports, ebits, layers = 2, 2 * code.n, 2
        final = [A3, B]
    else:
        final = [A2, B]
    _readout(b, code, final)
    return Pattern("T_rt" if ret else "T", k, b.getCirc(), ebits, layers, teleports,
                   t, rounds, nblocks)


def memory_pair(code, p: float, rounds: int) -> stim.Circuit:
    """Two idle blocks for ``SETTLE_ROUNDS + rounds`` rounds (memory-rate calibration)."""
    b = make_builder(code, 2, p, ebits=False)
    b.initQubits(0)
    b.initQubits(1)
    _settle(b, [0, 1])
    _rounds(b, [0, 1], rounds)
    _readout(b, code, [0, 1])
    return b.getCirc()


def build(code, strategy: str, p: float, p_ebit: float, k: int) -> Pattern:
    if strategy == "R":
        return remote(code, p, p_ebit, k)
    if strategy == "T":
        return teleport(code, p, p_ebit, k, ret=False)
    if strategy == "T_rt":
        return teleport(code, p, p_ebit, k, ret=True)
    raise ValueError(strategy)


def code_by_name(name: str):
    """``SC3``/``SC5``/... rotated surface codes, or a TMCBS BB code name."""
    if name.startswith("SC"):
        return tmcbs.surface_code(int(name[2:]))
    return tmcbs.bb_code(name)
