"""Geometry helpers for abd unit bboxes with rotate/scale (combo-center frame)."""

from __future__ import annotations

import math
from typing import Any

_BOX_FACE_INDICES = (
    (0, 1, 5, 4),
    (2, 3, 7, 6),
    (0, 3, 7, 4),
    (1, 2, 6, 5),
    (0, 1, 2, 3),
    (4, 5, 6, 7),
)


def vec3_float(
    value: dict[str, Any] | None,
    *,
    default: float = 0.0,
) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"x": default, "y": default, "z": default}
    return {
        axis: float(value.get(axis, default)) for axis in ("x", "y", "z")
    }


def rotate_to_degrees(rotate: dict[str, Any] | None) -> tuple[float, float, float]:
    """Resolve abd rotate to degrees (template: degrees; assembly export may use radians)."""
    rot = vec3_float(rotate)
    values = [rot["x"], rot["y"], rot["z"]]
    if any(abs(v) > 2 * math.pi for v in values):
        return rot["x"], rot["y"], rot["z"]
    return tuple(math.degrees(v) for v in values)


def is_negligible_rotation(rotate: dict[str, Any] | None) -> bool:
    if not isinstance(rotate, dict):
        return True
    rx, ry, rz = rotate_to_degrees(rotate)
    return all(abs(angle) < 1e-6 for angle in (rx, ry, rz))


def rotation_matrix_xyz_deg(
    rx_deg: float,
    ry_deg: float,
    rz_deg: float,
) -> tuple[tuple[float, float, float], ...]:
    """Intrinsic XYZ Euler rotation matrix (column vectors)."""
    rx, ry, rz = map(math.radians, (rx_deg, ry_deg, rz_deg))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    return (
        (cy * cz, -cy * sz, sy),
        (sx * sy * cz + cx * sz, -sx * sy * sz + cx * cz, -sx * cy),
        (-cx * sy * cz + sx * sz, cx * sy * sz + sx * cz, cx * cy),
    )


def mat_vec_mul(
    matrix: tuple[tuple[float, float, float], ...],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = vector
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )


def local_box_vertices_ordered(
    size: dict[str, float],
    scale: dict[str, float],
) -> list[tuple[float, float, float]]:
    """Eight box vertices in face-index order, relative to abd pivot (position).

    X/Z grow in +X/+Z; depth grows toward -Y (position.y is the front face).
    """
    sx = size["x"] * scale["x"]
    sy = size["y"] * scale["y"]
    sz = size["z"] * scale["z"]
    return [
        (0.0, 0.0, 0.0),
        (sx, 0.0, 0.0),
        (sx, -sy, 0.0),
        (0.0, -sy, 0.0),
        (0.0, 0.0, sz),
        (sx, 0.0, sz),
        (sx, -sy, sz),
        (0.0, -sy, sz),
    ]


def abd_world_vertices(
    position: dict[str, Any],
    size: dict[str, Any],
    *,
    rotate: dict[str, Any] | None = None,
    scale: dict[str, Any] | None = None,
) -> list[list[float]]:
    """Return eight world-frame vertices for an abd unit (for oriented box drawing)."""
    pos = vec3_float(position)
    local_vertices = local_box_vertices_ordered(
        vec3_float(size),
        vec3_float(scale, default=1.0),
    )

    if is_negligible_rotation(rotate):
        return [
            [pos["x"] + x, pos["y"] + y, pos["z"] + z]
            for x, y, z in local_vertices
        ]

    rx, ry, rz = rotate_to_degrees(rotate)
    rot_mat = rotation_matrix_xyz_deg(rx, ry, rz)
    return [
        [
            pos["x"] + rotated[0],
            pos["y"] + rotated[1],
            pos["z"] + rotated[2],
        ]
        for rotated in (mat_vec_mul(rot_mat, vertex) for vertex in local_vertices)
    ]


def abd_aabb_minmax(
    position: dict[str, Any],
    size: dict[str, Any],
    *,
    rotate: dict[str, Any] | None = None,
    scale: dict[str, Any] | None = None,
) -> tuple[list[float], list[float]]:
    """Axis-aligned min/max corners for overlap checks and view bounds."""
    vertices = abd_world_vertices(position, size, rotate=rotate, scale=scale)
    mins = [min(v[i] for v in vertices) for i in range(3)]
    maxs = [max(v[i] for v in vertices) for i in range(3)]
    return mins, maxs


def oriented_box_faces(vertices: list[list[float]]) -> list[list[list[float]]]:
    """Build six quadrilateral faces from eight ordered box vertices."""
    return [[vertices[i] for i in face] for face in _BOX_FACE_INDICES]
