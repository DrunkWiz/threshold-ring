"""Point-in-polygon, against the real zone the Playground device reports."""

import unittest

from ring_client.emulator import MOTION_ZONE_VERTICES
from threshold.rules.geometry import point_in_polygon, polygon_area, zones_containing

REAL_ZONE = [(v["x"], v["y"]) for v in MOTION_ZONE_VERTICES]


class Zone(unittest.TestCase):
    def test_the_real_zone_is_the_whole_frame(self):
        """Worth stating: the device's one zone covers everything.

        So "inside a motion zone" is not a narrowing condition on this device.
        A demo that claims otherwise would be claiming something false, and
        this test is what stops that claim being made by accident.
        """
        self.assertTrue(point_in_polygon((0.01, 0.01), REAL_ZONE))
        self.assertTrue(point_in_polygon((0.99, 0.99), REAL_ZONE))
        self.assertTrue(point_in_polygon((0.5, 0.5), REAL_ZONE))

    def test_outside_the_frame_is_outside(self):
        self.assertFalse(point_in_polygon((1.4, 0.5), REAL_ZONE))
        self.assertFalse(point_in_polygon((-0.1, 0.5), REAL_ZONE))


class Edges(unittest.TestCase):
    SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]

    def test_a_point_on_an_edge_counts_as_inside(self):
        # Zones are drawn around the area someone cares about; the boundary
        # belongs to it.
        self.assertTrue(point_in_polygon((0.2, 0.5), self.SQUARE))
        self.assertTrue(point_in_polygon((0.5, 0.8), self.SQUARE))

    def test_a_vertex_counts_as_inside(self):
        self.assertTrue(point_in_polygon((0.2, 0.2), self.SQUARE))

    def test_a_ray_through_a_vertex_does_not_double_count(self):
        """The classic ray-casting bug: a horizontal ray that leaves through a
        corner flips `inside` twice and reports the point as outside."""
        diamond = [(0.5, 0.2), (0.8, 0.5), (0.5, 0.8), (0.2, 0.5)]
        self.assertTrue(point_in_polygon((0.5, 0.5), diamond))
        self.assertFalse(point_in_polygon((0.05, 0.5), diamond))

    def test_concave_shapes(self):
        # An L, to prove the notch is genuinely outside.
        ell = [(0, 0), (0.6, 0), (0.6, 0.4), (1.0, 0.4), (1.0, 1.0), (0, 1.0)]
        self.assertTrue(point_in_polygon((0.3, 0.2), ell))
        self.assertFalse(point_in_polygon((0.8, 0.2), ell))
        self.assertTrue(point_in_polygon((0.8, 0.7), ell))

    def test_degenerate_zones_contain_nothing(self):
        # Not everything: an empty zone that matched every event would fire
        # every rule attached to it, silently.
        self.assertFalse(point_in_polygon((0.5, 0.5), []))
        self.assertFalse(point_in_polygon((0.5, 0.5), [(0, 0), (1, 1)]))


class Lookup(unittest.TestCase):
    class FakeZone:
        def __init__(self, zid, verts):
            self.id = zid
            self.vertices = verts

    def test_reports_every_zone_containing_the_point(self):
        zones = [
            self.FakeZone("big", [(0, 0), (1, 0), (1, 1), (0, 1)]),
            self.FakeZone("small", [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]),
        ]
        self.assertEqual(zones_containing((0.5, 0.5), zones), ("big", "small"))
        self.assertEqual(zones_containing((0.9, 0.9), zones), ("big",))

    def test_no_point_is_not_the_same_as_outside(self):
        zones = [self.FakeZone("big", [(0, 0), (1, 0), (1, 1), (0, 1)])]
        self.assertEqual(zones_containing(None, zones), ())

    def test_area(self):
        self.assertAlmostEqual(polygon_area([(0, 0), (1, 0), (1, 1), (0, 1)]), 1.0)


if __name__ == "__main__":
    unittest.main()
