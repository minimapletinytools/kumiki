"""Remaining degrees of freedom: a rank test over rows of unknowns.

A row is a linear form over named unknowns. Known rows span what the
drawing pins down; a target is solved when its rows lie in that span.
"""

from dataclasses import dataclass
from typing import Hashable, List, Mapping, Sequence, Tuple, TypeVar

import numpy as np

Unknown = TypeVar("Unknown", bound=Hashable)


@dataclass(frozen=True)
class Remaining:
    """How many of a target's degrees of freedom are still free, and which.

    Each entry of `free` weights the target's rows: that combination of them isn't known yet.
    """
    count: int
    free: Tuple[Tuple[float, ...], ...]


def _matrix(rows: Sequence[Mapping[Unknown, float]], columns: List[Unknown]) -> np.ndarray:
    index = {column: i for i, column in enumerate(columns)}
    out = np.zeros((len(rows), len(columns)))
    for r, row in enumerate(rows):
        for column, value in row.items():
            out[r, index[column]] = value
    return out


def remaining(
    known: Sequence[Mapping[Unknown, float]],
    target: Sequence[Mapping[Unknown, float]],
    relative_tolerance: float = 1e-9,
) -> Remaining:
    """The degrees of freedom of `target` not fixed by `known`."""
    columns = list(dict.fromkeys(column for row in (*known, *target) for column in row))
    if not target or not columns:
        return Remaining(count=0, free=())
    known_matrix = _matrix(known, columns)
    target_matrix = _matrix(target, columns)

    stacked = np.vstack([known_matrix, target_matrix])
    tolerance = relative_tolerance * max(float(np.linalg.norm(stacked, 2)), 1.0)

    if len(known):
        _, values, basis = np.linalg.svd(known_matrix, full_matrices=False)
        basis = basis[values > tolerance]
        target_matrix = target_matrix - target_matrix @ basis.T @ basis

    left, values, _ = np.linalg.svd(target_matrix, full_matrices=False)
    free = left[:, values > tolerance].T
    return Remaining(count=len(free), free=tuple(tuple(float(w) for w in combination) for combination in free))
