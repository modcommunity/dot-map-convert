"""The zombie-zone nav flood must walk a 12-inch stair flight even when a spec asks for flood_step 0.3."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)

sys.path.append(os.path.join(os.path.dirname(ROOT), "zombie-zone-maps", "tools"))
try:
    import import_bsp as I  # noqa: E402
except ImportError:
    I = None


def box(x0, x1, y0, y1):
    return {"at": [(x0 + x1) / 2, (y0 + y1) / 2, 3.0], "size": [x1 - x0, y1 - y0, 6.0], "mat": "concrete"}


def stairs(rise):
    """A floor with a flight of six 0.6 m treads climbing to a landing."""
    boxes = [box(0, 14, -1, 0)]
    for i in range(6):
        boxes.append(box(4 + i * 0.6, 4.6 + i * 0.6, -1, rise * (i + 1)))
    top = rise * 6
    boxes.append(box(7.6, 14, -1, top))
    return boxes, top


@unittest.skipIf(I is None, "zombie-zone-maps is not checked out beside this repository")
class FloodStep(unittest.TestCase):
    def test_floor(self):
        self.assertEqual(I.flood_step(0.3), I.STAIR_RISE)
        self.assertEqual(I.flood_step(0.55), 0.55)

    def test_flight_reaches_landing(self):
        boxes, top = stairs(0.3048)
        saved = I.STEP, I.JUMP
        try:
            I.STEP = I.JUMP = I.flood_step(0.3)
            floors, *_ = I.build_nav(boxes, [[1.0, 0.0, 3.0]])
        finally:
            I.STEP, I.JUMP = saved
        self.assertTrue(any(abs(f[4] - top) < 0.05 and f[2] > 8 for f in floors), floors)


if __name__ == "__main__":
    unittest.main()
