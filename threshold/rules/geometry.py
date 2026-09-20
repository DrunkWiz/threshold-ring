"""Point-in-polygon against Ring's motion zones.

Ring hands out the zone as normalised vertices in [0, 1] with the origin at
the top-left of the frame. A detection's position, normalised the same way,
can be tested against it directly. This is the piece of the API that makes a
rule about *the driveway* mean something more than a rule about *motion*.

Ray casting, with two details that matter:

  * A point exactly on an edge counts as inside. Zones are drawn by people
    around the area they care about, and a detection landing on the boundary
    of the driveway is in the driveway.
  * The polygon is treated as closed, so the caller never has to repeat the
    first vertex.
"""

from __future__ import annotations

from typing import Iterable, Sequence

Point = tuple[float, float]
Polygon = Sequence[Point]

EPSILON = 1e-9


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > EPSILON:
        return False
    return (
        min(a[0], b[0]) - EPSILON <= p[0] <= max(a[0], b[0]) + EPSILON
        and min(a[1], b[1]) - EPSILON <= p[1] <= max(a[1], b[1]) + EPSILON
    )


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    if polygon is None or len(polygon) < 3:
        return False  # a degenerate zone contains nothing, rather than everything

    x, y = point
    n = len(polygon)

    for i in range(n):
        if _on_segment(point, polygon[i], polygon[(i + 1) % n]):
            return True

    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        # Half-open comparison on y: a vertex is counted once, not twice, so a
        # ray passing exactly through a corner does not flip the answer.
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def zones_containing(point: Point | None, zones: Iterable) -> tuple[str, ...]:
    """The ids of every zone that contains the point.

    A point of None means the detector had no position for it, which is not
    the same as being outside every zone — the caller can tell the difference
    because it passed the None in.
    """
    if point is None:
        return ()
    hits = []
    for zone in zones:
        verts = getattr(zone, "vertices", None) or ()
        if point_in_polygon(point, verts):
            hits.append(getattr(zone, "id", ""))
    return tuple(h for h in hits if h)


def polygon_area(polygon: Polygon) -> float:
    """Shoelace area. Used to sort overlapping zones smallest-first."""
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0
