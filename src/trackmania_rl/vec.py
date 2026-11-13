"""Small 3-D vector helpers (standard library only)."""
from __future__ import annotations

import math


def add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def scale(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def normalize(a, fallback=None, eps=1e-9):
    n = norm(a)
    if n < eps:
        if fallback is None:
            raise ValueError("cannot normalize a null vector")
        return list(fallback)
    return [a[0] / n, a[1] / n, a[2] / n]


def lerp(a, b, t):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]


def project_on_segment(p, a, b):
    """Return (t in [0,1], closest point) of point p on segment [a, b]."""
    ab = sub(b, a)
    den = dot(ab, ab)
    t = 0.0 if den == 0.0 else max(0.0, min(1.0, dot(sub(p, a), ab) / den))
    return t, add(a, scale(ab, t))


def point_segment_distance(p, a, b):
    return norm(sub(p, project_on_segment(p, a, b)[1]))


def mat_T_vec(rows, v):
    """rows is a 3x3 matrix given by rows; returns M^T v."""
    return [rows[0][i] * v[0] + rows[1][i] * v[1] + rows[2][i] * v[2] for i in range(3)]


def column(rows, j):
    return [rows[0][j], rows[1][j], rows[2][j]]
