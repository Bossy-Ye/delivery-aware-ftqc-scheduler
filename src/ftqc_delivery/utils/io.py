"""Small CSV I/O helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write dictionaries to a CSV file with a fixed field order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV file into a list of dictionaries."""

    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))
