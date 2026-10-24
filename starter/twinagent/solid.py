"""Measure an STL mesh without FreeCAD: volume, size, whether it is closed, and its through holes.

A closed, connected mesh with V vertices, E edges and F faces has V - E + F = 2 - 2g, where g is
its genus: the number of holes that go all the way through it. A plate with two bores has g = 2.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

Triangle = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


@dataclass
class Measure:
    volume: float  # in the mesh's units cubed; FreeCAD exports millimetres
    size: tuple[float, float, float]  # bounding box extents along x, y, z
    closed: bool  # every edge is shared by exactly two triangles
    pieces: int  # connected parts
    through_holes: int | None  # the genus, when the mesh is closed and in one piece


def triangles(path: Path) -> list[Triangle]:
    data = Path(path).read_bytes()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):
            return [tuple(struct.unpack_from("<3f", data, 84 + 50 * i + 12 + 12 * k) for k in range(3))
                    for i in range(n)]
    out, corners = [], []
    for line in data.decode("ascii", errors="replace").splitlines():
        parts = line.split()
        if parts[:1] == ["vertex"]:
            corners.append(tuple(float(v) for v in parts[1:4]))
            if len(corners) == 3:
                out.append(tuple(corners))
                corners = []
    return out


def measure(path: Path, digits: int = 4) -> Measure:
    tris = triangles(path)
    if not tris:
        return Measure(0.0, (0.0, 0.0, 0.0), False, 0, None)
    volume = 0.0
    for (a, b, c) in tris:
        volume += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                   + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    xs, ys, zs = zip(*(p for t in tris for p in t))
    size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    ids: dict[tuple, int] = {}
    faces = []
    for t in tris:
        face = tuple(ids.setdefault(tuple(round(v, digits) for v in p), len(ids)) for p in t)
        if len(set(face)) == 3:  # drop triangles that collapse to a line
            faces.append(face)
    edges: dict[tuple[int, int], int] = {}
    for a, b, c in faces:
        for e in ((a, b), (b, c), (c, a)):
            key = (min(e), max(e))
            edges[key] = edges.get(key, 0) + 1
    closed = all(n == 2 for n in edges.values())

    parent = list(range(len(ids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in edges:
        parent[find(a)] = find(b)
    pieces = len({find(i) for f in faces for i in f})
    holes = None
    if closed and pieces == 1:
        euler = len(ids) - len(edges) + len(faces)
        holes = (2 - euler) // 2
    return Measure(abs(volume), size, closed, pieces, holes)
