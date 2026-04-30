"""Deterministic seeding helpers."""

from __future__ import annotations

import random


def seed_everything(seed: int) -> None:
    """Seed Python's standard random generator."""

    random.seed(seed)
