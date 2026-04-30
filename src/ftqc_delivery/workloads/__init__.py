"""Constructed and semi-real workload generators."""

from .arithmetic import make_adder, make_modular_arithmetic_block, make_multiplier
from .constructed import (
    make_high_compressibility,
    make_low_compressibility,
    make_medium_compressibility,
)
from .qft import (
    make_approx_qft,
    make_exact_qft,
    make_hamiltonian_simulation_synthetic,
    make_phase_estimation_like,
)

__all__ = [
    "make_high_compressibility",
    "make_medium_compressibility",
    "make_low_compressibility",
    "make_adder",
    "make_multiplier",
    "make_modular_arithmetic_block",
    "make_exact_qft",
    "make_approx_qft",
    "make_phase_estimation_like",
    "make_hamiltonian_simulation_synthetic",
]
