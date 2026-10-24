"""dotbsp.vis: run-length rows, the compacted PVS, occluder hull winding and the packed blocks."""
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import vis  # noqa: E402


def _fake(clusters, raw, offsets):
    v = vis.Vis.__new__(vis.Vis)
    v.clusters, v.raw, v.offsets = clusters, raw, offsets
    return v


class Rows(unittest.TestCase):
    def test_a_zero_byte_skips_that_many_bytes(self):
        # 20 clusters = 3 bytes: 0x05, then two zero bytes as (0, 2)
        v = _fake(20, bytes([0x05, 0, 2]), [0])
        self.assertEqual(v.row(0), bytearray([0x05, 0, 0]))

    def test_a_missing_row_sees_everything(self):
        v = _fake(9, b"", [-1])
        self.assertEqual(v.row(0), bytearray(b"\xff\xff"))

    def test_compact_rows_drops_the_rest_and_shares_equal_offsets(self):
        raw = bytes([0x01, 0xEE, 0, 1])
        v = _fake(3, raw, [0, 2, 0])
        rows, offs = v.compact_rows()
        self.assertEqual(rows, bytes([0x01, 0, 1]))
        self.assertEqual(offs, [0, 1, 0])


class Hulls(unittest.TestCase):
    def test_a_cube_makes_twelve_triangles_facing_out(self):
        planes = [(1, 0, 0, 1), (-1, 0, 0, 1), (0, 1, 0, 1), (0, -1, 0, 1), (0, 0, 1, 1), (0, 0, -1, 1)]
        pts = vis._hull_points(planes)
        self.assertEqual(len(set(pts)), 8)
        tris = vis._hull_triangles(planes, pts)
        self.assertEqual(len(tris), 12)
        for a, b, c in tris:
            e1 = [b[i] - a[i] for i in range(3)]
            e2 = [c[i] - a[i] for i in range(3)]
            n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            centre = [(a[i] + b[i] + c[i]) / 3 for i in range(3)]
            # clockwise seen from outside: the right-handed normal points in
            self.assertLess(sum(n[i] * centre[i] for i in range(3)), 0)


class Pack(unittest.TestCase):
    def test_blocks_point_at_their_bytes(self):
        data = {"clusters": 2, "head": 0, "planes": [(1.0, 0.0, 0.0, 2.0)], "nodes": [(0, -1, -2)],
                "leaf_cluster": [0, 1], "leaf_area": [1, 1], "cluster_area": [1, 1], "pvs_offsets": [0, 1],
                "pvs": bytes([3, 3]), "portals": [(5, 1, 2)], "portal_entities": [],
                "occluder_vertices": [(0.0, 1.0, 2.0)] * 3, "occluder_indices": [0, 1, 2]}
        blob = bytearray(b"xx")
        rec = vis.pack(data, blob)
        p = rec["planes"]
        self.assertEqual(struct.unpack_from("<4f", blob, p["offset"]), (1.0, 0.0, 0.0, 2.0))
        n = rec["nodes"]
        self.assertEqual(struct.unpack_from("<3i", blob, n["offset"]), (0, -1, -2))
        self.assertEqual(bytes(blob[rec["pvs"]["offset"]:rec["pvs"]["offset"] + 2]), bytes([3, 3]))
        o = rec["occluder_indices"]
        self.assertEqual(struct.unpack_from("<3I", blob, o["offset"]), (0, 1, 2))
        self.assertEqual(rec["portals"], [[5, 1, 2]])

    def test_no_clusters_packs_only_occluders(self):
        rec = vis.pack({"clusters": 0, "occluder_vertices": [], "occluder_indices": []}, bytearray())
        self.assertEqual(rec, {"clusters": 0})


if __name__ == "__main__":
    unittest.main()
