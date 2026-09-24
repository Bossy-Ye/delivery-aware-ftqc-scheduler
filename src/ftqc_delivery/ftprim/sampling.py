"""Seeded sampling and Tesseract decoding (the decoder used for the paper's runs).

Each batch draws from ``dem.compile_sampler(seed=...)`` with a seed derived
from the point key and the batch index, so every count in the CSVs can be
regenerated exactly. Error bars use ``sinter.fit_binomial`` with a Bayes factor
of 1000, the rule TMCBS uses for the published figures.
"""

from __future__ import annotations

import hashlib
import time

import numpy as np


def point_seed(key: str, batch: int) -> int:
    digest = hashlib.sha256(f"{key}|{batch}".encode()).digest()
    return int.from_bytes(digest[:7], "big")


def decode_errors(circuit, shots: int, seed: int) -> int:
    import tesseract_decoder.tesseract as tess
    dem = circuit.detector_error_model()
    det, obs, _ = dem.compile_sampler(seed=seed).sample(shots=shots)
    decoder = tess.TesseractDecoder(tess.TesseractConfig(dem=dem))
    pred = decoder.decode_batch(det)
    return int(np.sum(np.any(pred != obs, axis=1)))


def estimate(circuit, key: str, target_errors: int, max_shots: int,
             first_batch: int = 2000, max_batch: int = 50000) -> dict:
    t0 = time.perf_counter()
    errors = shots = batch_index = 0
    batch = first_batch
    while shots < max_shots and errors < target_errors:
        batch = int(min(batch, max_shots - shots))
        errors += decode_errors(circuit, batch, point_seed(key, batch_index))
        shots += batch
        batch_index += 1
        if errors == 0:
            batch = min(2 * batch, max_batch)
        else:
            rate = errors / shots
            batch = int(min(max_batch, max(1000, 1.2 * (target_errors - errors) / rate)))
    lo, hi = interval(errors, shots)
    return dict(shots=shots, errors=errors, ler=errors / shots if shots else float("nan"),
                ci_low=lo, ci_high=hi, batches=batch_index,
                hit_shot_limit=errors < target_errors, seconds=round(time.perf_counter() - t0, 2))


def interval(errors: int, shots: int, factor: float = 1000.0):
    import sinter
    if shots <= 0:
        return float("nan"), float("nan")
    fit = sinter.fit_binomial(num_shots=shots, num_hits=errors, max_likelihood_factor=factor)
    return float(fit.low), float(fit.high)
