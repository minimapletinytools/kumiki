"""Remaining degrees of freedom: a rank test over rows of unknowns.

A row is a linear form over named unknowns. Known rows span what the
drawing pins down; a target is solved when its rows lie in that span.
"""

from dataclasses import dataclass
from typing import Dict, Generic, Hashable, List, Mapping, Sequence, Tuple, TypeVar

import numpy as np

Unknown = TypeVar("Unknown", bound=Hashable)


@dataclass(frozen=True)
class Remaining(Generic[Unknown]):
    """How many of a target's degrees of freedom are still free, and which.

    One entry per free DOF in each of:
    - `free`: weights over the target's rows; that combination of them isn't known yet.
    - `free_quantities`: the same combination as a row over the unknowns.
    - `free_motions`: a unit change to the unknowns that leaves every known row at zero and
      moves the target. Its sign is arbitrary, and with several free DOFs so is the basis.
    """
    count: int
    free: Tuple[Tuple[float, ...], ...]
    free_quantities: Tuple[Dict[Unknown, float], ...] = ()
    free_motions: Tuple[Dict[Unknown, float], ...] = ()


def _by_column(values: np.ndarray, columns: List[Unknown]) -> Dict[Unknown, float]:
    return {column: float(value) for column, value in zip(columns, values) if abs(value) > 1e-12}


#: Row entries below this are treated as zero.
_DUST = 1e-12


def rank_svd(matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the SVD of `matrix` after zeroing entries below `_DUST`.

    Assumes `matrix` is scaled near 1; LAPACK can fail to converge on tiny leftover entries.
    """
    cleaned = np.array(matrix, dtype=float, copy=True)
    cleaned[np.abs(cleaned) < _DUST] = 0.0
    return np.linalg.svd(cleaned, full_matrices=False)


def rows_matrix(rows: Sequence[Mapping[Unknown, float]], columns: List[Unknown]) -> np.ndarray:
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
    """Return the degrees of freedom of the `target` rows that the `known` rows leave free."""
    columns = list(dict.fromkeys(column for row in (*known, *target) for column in row))
    if not target or not columns:
        return Remaining(count=0, free=())
    known_matrix = rows_matrix(known, columns)
    target_matrix = rows_matrix(target, columns)

    stacked = np.vstack([known_matrix, target_matrix])
    tolerance = relative_tolerance * max(float(np.linalg.norm(stacked, 2)), 1.0)

    # Some BLAS builds (macOS Accelerate) raise spurious floating point warnings in matmul.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        unknown_part = target_matrix
        if len(known):
            _, values, basis = rank_svd(known_matrix)
            basis = basis[values > tolerance]
            unknown_part = target_matrix - target_matrix @ basis.T @ basis

        left, values, right = rank_svd(unknown_part)
        kept = values > tolerance
        weights = left[:, kept].T
        quantities = weights @ target_matrix
    if not (np.isfinite(unknown_part).all() and np.isfinite(quantities).all()):
        raise FloatingPointError("the rows gave non-finite values")
    return Remaining(
        count=len(weights),
        free=tuple(tuple(float(w) for w in combination) for combination in weights),
        free_quantities=tuple(_by_column(quantity, columns) for quantity in quantities),
        free_motions=tuple(_by_column(motion, columns) for motion in right[kept]),
    )
