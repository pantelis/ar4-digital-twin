"""Standard DH frames from the kDB, as in Annin's spreadsheet.

Frame n is the frame of link n and joint n turns about the z axis of frame n-1. The world
frame is frame 0. Link n's transform is

    A_n = Rz(theta_offset_n + q_n) Tz(d_n) Tx(a_n) Rx(alpha_n)

    from twin_tools import dh
    rows = [dh.row(f"joints/j{n}.md") for n in range(1, 7)]
    frames = dh.frames(rows, q)       # [T_00, T_01, ..., T_06]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .kdb import si


@dataclass(frozen=True)
class DH:
    """One row of the DH table in SI units: radians and metres."""
    theta_offset: float
    alpha: float
    d: float
    a: float


def row(page: str) -> DH:
    """The joint page's four DH quantities, read with si so twin-check can trace them."""
    return DH(si(page, "dh_theta_offset"), si(page, "dh_alpha"), si(page, "dh_d"), si(page, "dh_a"))


def transform(r: DH, q: float) -> np.ndarray:
    """A_n for one row at joint value q."""
    ct, st = np.cos(r.theta_offset + q), np.sin(r.theta_offset + q)
    ca, sa = np.cos(r.alpha), np.sin(r.alpha)
    return np.array([[ct, -st * ca, st * sa, r.a * ct],
                     [st, ct * ca, -ct * sa, r.a * st],
                     [0.0, sa, ca, r.d],
                     [0.0, 0.0, 0.0, 1.0]])


def frames(rows: Sequence[DH], q: Sequence[float]) -> list[np.ndarray]:
    """[T_00, T_01, ..., T_0n], 4x4, with T_00 the identity."""
    if len(rows) != len(q):
        raise ValueError(f"{len(rows)} DH rows but {len(q)} joint values")
    out = [np.eye(4)]
    for r, qn in zip(rows, q):
        out.append(out[-1] @ transform(r, qn))
    return out


def axes(frames: Sequence[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
    """For joint n, the origin and unit z of frame n-1: the line the joint turns about."""
    return [(f[:3, 3].copy(), f[:3, 2].copy()) for f in frames[:-1]]
