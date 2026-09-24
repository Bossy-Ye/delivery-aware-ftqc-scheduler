"""Faithfulness checks for the composed TMCBS interaction patterns."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

tmcbs = pytest.importorskip("tmcbs")

from ftqc_delivery.ftprim import patterns as pat  # noqa: E402


@pytest.mark.parametrize("d", [3, 5])
def test_remote_k1_is_tmcbs_non_local_cnot(d):
    code = tmcbs.surface_code(d)
    ours = pat.remote(code, 2e-3, 2e-2, 1).circuit
    theirs = tmcbs.non_local_cnot(code, 2e-3, 2e-2)
    assert str(ours) == str(theirs)


def _count(circuit, name):
    return sum(1 for inst in circuit.flattened() if inst.name == name)


@pytest.mark.parametrize("strategy,k", [("R", 1), ("R", 3), ("T", 1), ("T", 2), ("T_rt", 1), ("T_rt", 3)])
def test_patterns_are_deterministic_and_well_formed(strategy, k):
    code = tmcbs.surface_code(3)
    p = pat.build(code, strategy, 1e-3, 1e-2, k)
    c = p.circuit
    # Noiseless version must have deterministic detectors and observables.
    c.without_noise().detector_error_model()
    assert c.num_observables == 2
    # Ebits consumed = n per ebit-consuming layer; one DEPOLARIZE2 layer each.
    assert p.ebit_pairs == p.nonlocal_layers * code.n
    ebit_noise = sum(1 for inst in c.flattened() if inst.name == "DEPOLARIZE2"
                     and inst.gate_args_copy() == [1e-2])
    assert ebit_noise == p.nonlocal_layers * code.n
    # Noiseless sampling never flips an observable.
    _, obs = c.without_noise().compile_detector_sampler().sample(64, separate_observables=True)
    assert not obs.any()


def test_round_accounting():
    code = tmcbs.surface_code(3)
    r = pat.remote(code, 1e-3, 1e-2, 4)
    t = pat.teleport(code, 1e-3, 1e-2, 4)
    trt = pat.teleport(code, 1e-3, 1e-2, 4, ret=True)
    assert r.time_rounds == 4 + 3 * 4
    assert t.time_rounds == 4 + 3 * 5
    assert trt.time_rounds == t.time_rounds + 3
    for pattern in (r, t, trt):
        assert pattern.block_rounds["B"] == pattern.time_rounds
        index = ({"A": 0, "B": 1} if pattern.strategy == "R" else
                 {"A": 0, "M": 1, "A'": 2, "B": 3, "M'": 4, "A''": 5})
        for name, blk in index.items():
            if name in pattern.block_rounds:
                assert _z_rounds(pattern.circuit, code.n, blk) == pattern.block_rounds[name], (pattern.strategy, name)


def _z_rounds(circuit, n, block):
    """Syndrome rounds run by ``block``: measurements of its first Z ancilla."""
    stride = n + 2 * ((n - 1) // 2)
    z0 = block * stride + n + (n - 1) // 2
    return sum(sum(1 for t in inst.targets_copy() if t.value == z0)
               for inst in circuit.flattened() if inst.name in ("MR", "MRZ"))


def test_bb_patterns_match_tmcbs_and_are_deterministic():
    code = tmcbs.bb_code("[[18,4,4]] BB")
    assert str(pat.remote(code, 1e-3, 1e-2, 1).circuit) == str(tmcbs.non_local_cnot(code, 1e-3, 1e-2))
    for strategy in ("R", "T", "T_rt"):
        c = pat.build(code, strategy, 1e-3, 1e-2, 2).circuit
        assert c.num_observables == 2 * code.k
        _, obs = c.without_noise().compile_detector_sampler().sample(64, separate_observables=True)
        assert not obs.any()


def test_ablation_without_quieting_equals_teleport():
    code = tmcbs.surface_code(3)
    full = pat.teleport(code, 1e-3, 1e-2, 2).circuit
    same = pat.teleport_ablation(code, 1e-3, 1e-2, 2).circuit
    assert str(full) == str(same)
    quiet = pat.teleport_ablation(code, 1e-3, 1e-2, 2, quiet_bell_blocks=True, quiet_bsm=True).circuit
    assert quiet.num_detectors == full.num_detectors
    assert quiet.detector_error_model().num_errors < full.detector_error_model().num_errors
