"""Small STL meshes for the tests: a box, and a square frame (a box with one square hole through it)."""
import struct
from pathlib import Path


def quad(a, b, c, d):
    return [(a, b, c), (a, c, d)]


def box(x, y, z):
    p = [(i * x, j * y, k * z) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    v = lambda i, j, k: p[i * 4 + j * 2 + k]
    return (quad(v(0, 0, 0), v(0, 1, 0), v(1, 1, 0), v(1, 0, 0)) + quad(v(0, 0, 1), v(1, 0, 1), v(1, 1, 1), v(0, 1, 1))
            + quad(v(0, 0, 0), v(1, 0, 0), v(1, 0, 1), v(0, 0, 1)) + quad(v(0, 1, 0), v(0, 1, 1), v(1, 1, 1), v(1, 1, 0))
            + quad(v(0, 0, 0), v(0, 0, 1), v(0, 1, 1), v(0, 1, 0)) + quad(v(1, 0, 0), v(1, 1, 0), v(1, 1, 1), v(1, 0, 1)))


def frame(outer, inner, h):
    """A square outer x outer plate, h thick, with a centered inner x inner square hole through it."""
    o0, o1 = 0.0, outer
    i0, i1 = (outer - inner) / 2, (outer + inner) / 2
    ring_out = [(o0, o0), (o1, o0), (o1, o1), (o0, o1)]
    ring_in = [(i0, i0), (i1, i0), (i1, i1), (i0, i1)]
    tris = []
    for k in range(4):
        a, b = ring_out[k], ring_out[(k + 1) % 4]
        c, d = ring_in[(k + 1) % 4], ring_in[k]
        tris += quad((*a, h), (*b, h), (*c, h), (*d, h))  # top
        tris += quad((*d, 0), (*c, 0), (*b, 0), (*a, 0))  # bottom
        tris += quad((*a, 0), (*b, 0), (*b, h), (*a, h))  # outer wall
        tris += quad((*d, h), (*c, h), (*c, 0), (*d, 0))  # inner wall
    return tris


def write(path: Path, tris) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            fh.write(struct.pack("<3f", 0, 0, 0) + b"".join(struct.pack("<3f", *p) for p in t) + b"\0\0")
    return path
