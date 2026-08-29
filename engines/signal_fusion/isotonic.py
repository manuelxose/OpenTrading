"""Isotonic regression (pool adjacent violators) — the only numeric machinery
confidence calibration needs.

Pure Python, deterministic, no external dependencies. Given strictly increasing
``x`` and corresponding ``y``, returns monotone non-decreasing ``y_fit`` of the
same length. Ties in ``x`` are collapsed by averaging ``y`` before fitting.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["isotonic_regression"]


def _collapse_x(x: Sequence[float], y: Sequence[float]) -> tuple[list[float], list[float]]:
    """Average ``y`` over equal ``x`` values, keeping ``x`` strictly increasing."""
    xs: list[float] = []
    sums: list[float] = []
    counts: list[int] = []
    for xi, yi in zip(x, y, strict=True):
        if xs and xi == xs[-1]:
            sums[-1] += yi
            counts[-1] += 1
        else:
            xs.append(xi)
            sums.append(yi)
            counts.append(1)
    return xs, [s / c for s, c in zip(sums, counts, strict=True)]


def isotonic_regression(x: Sequence[float], y: Sequence[float]) -> tuple[list[float], list[float]]:
    """Fit a monotone non-decreasing step function to ``(x, y)`` via PAV.

    Returns ``(xs, ys)`` where ``xs`` is strictly increasing and ``ys`` is
    monotone non-decreasing, with the same value repeated over each fitted
    block. Constant extrapolation (clamp to the endpoints) is applied by the
    caller when evaluating between breakpoints.
    """
    if len(x) != len(y):
        raise ValueError("x and y must have the same length")
    if not x:
        return [], []
    xs, ys = _collapse_x(x, y)

    blocks: list[list[float]] = [[value] for value in ys]
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(blocks) - 1:
            mean_left = sum(blocks[i]) / len(blocks[i])
            mean_right = sum(blocks[i + 1]) / len(blocks[i + 1])
            if mean_left > mean_right:
                blocks[i].extend(blocks[i + 1])
                blocks.pop(i + 1)
                changed = True
            else:
                i += 1

    fitted: list[float] = []
    for block in blocks:
        fitted.extend([sum(block) / len(block)] * len(block))
    return xs, fitted
