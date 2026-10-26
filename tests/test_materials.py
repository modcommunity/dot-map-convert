"""Surface properties: a packed material record decides what a surface is, not its name."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotbsp import materials, rules  # noqa: E402


def vtf_rgba(alphas, w=4, h=4):
    head = bytearray(80)
    head[0:4] = b"VTF\0"
    struct.pack_into("<IIIHHIH", head, 4, 7, 2, 80, w, h, 0, 1)
    struct.pack_into("<i", head, 52, 0)
    head[56] = 1
    struct.pack_into("<iBB", head, 57, -1, 0, 0)
    return bytes(head) + b"".join(bytes((200, 40, 40, a)) for a in alphas)


def pak(**mats):
    out = {}
    for name, (vmt, alphas) in mats.items():
        out["materials/%s.vmt" % name] = vmt.encode()
        if alphas is not None:
            out["materials/%s.vtf" % name] = vtf_rgba(alphas)
    return out


def vmt(*keys):
    return '"LightmappedGeneric"\n{\n"$basetexture" "%%s"\n%s\n}\n' % "\n".join('"%s" 1' % k for k in keys)


class Kinds(unittest.TestCase):
    def resolve(self, name, keys, alphas, rows=None, flags=0):
        p = pak(**{name: (vmt(*keys).replace("%s", name), alphas)})
        r = materials.Resolver(p, rows)
        props = r.properties(name, flags)
        return r.kind(name, None, props), props

    def test_smooth_alpha_is_glass_tinted_by_the_texture(self):
        (kind, why), props = self.resolve("x/pane", ["$translucent"], [128] * 16)
        self.assertEqual((kind, why), ("glass", "translucent"))
        self.assertGreater(materials.tint(props)[0], materials.tint(props)[2])

    def test_cut_out_translucent_is_a_card(self):
        (kind, _), _p = self.resolve("x/coin", ["$translucent"], [0] * 8 + [255] * 8)
        self.assertEqual(kind, "foliage_card")

    def test_alpha_test_card_by_name(self):
        self.assertEqual(self.resolve("x/chainfence", ["$alphatest"], [0] * 8 + [255] * 8)[0][0], "fence")
        self.assertEqual(self.resolve("x/metalgrate", ["$alphatest"], [0] * 8 + [255] * 8)[0][0], "grate")
        self.assertEqual(self.resolve("x/ironbars", ["$alphatest"], [0] * 8 + [255] * 8)[0][0], "bars")

    def test_a_mostly_solid_card_stays_solid(self):
        self.assertEqual(self.resolve("x/panel", ["$alphatest"], [255] * 15 + [0])[0], (None, "solid"))

    def test_opaque_translucent_stays_solid(self):
        self.assertEqual(self.resolve("x/decal", ["$translucent"], [255] * 16)[0], (None, "solid"))

    def test_additive_is_a_glow(self):
        self.assertEqual(self.resolve("x/beam", ["$additive"], None)[0][0], "glow")

    def test_flag_without_a_record_is_reported_not_guessed(self):
        r = materials.Resolver({})
        props = r.properties("base/thing", materials.SURF_TRANS)
        self.assertEqual(r.kind("base/thing", None, props), (None, "unknown"))
        props = r.properties("base/bush01a", materials.SURF_TRANS)
        self.assertEqual(r.kind("base/bush01a", None, props), ("foliage_card", "name"))

    def test_patch_include(self):
        p = pak(**{"x/glassy": ('"patch"\n{\n"include" "materials/x/base.vmt"\n}\n', None)})
        p.update(pak(**{"x/base": (vmt("$translucent").replace("%s", "x/base"), [100] * 16)}))
        props = materials.Resolver(p).properties("x/glassy")
        self.assertTrue(props["translucent"])

    def test_nocull_alone_is_two_sided_not_see_through(self):
        (kind, why), props = self.resolve("x/rope", ["$nocull"], None)
        self.assertEqual((kind, why, props["two_sided"]), (None, "plain", True))


class Rows(unittest.TestCase):
    def test_a_row_overrides_and_opaque_forbids(self):
        class R:
            def __init__(self, k):
                self.k = k

            def get(self, n, g=None):
                return {"kind": self.k}
        (kind, why), _p = Kinds().resolve("x/pane", ["$translucent"], [128] * 16, R("opaque"))
        self.assertEqual((kind, why), (None, "row"))
        (kind, _), _p = Kinds().resolve("x/pane", ["$translucent"], [128] * 16, R("fence"))
        self.assertEqual(kind, "fence")

    def test_rule_tiers_answer_by_glob_and_highest_tier(self):
        lo, hi = rules.Tier("default"), rules.Tier("game")
        lo.materials["X/*"] = ["glass"]
        hi.materials["X/PANE"] = ["opaque"]
        rs = rules.RuleSet([lo, hi])
        self.assertEqual(rs.material("x/pane", None)["kind"], "opaque")
        self.assertEqual(rs.material("x/other", None)["kind"], "glass")
        self.assertIsNone(rs.material("y/other", None))
        lo.materials["bad"] = ["nonsense"]
        with self.assertRaises(ValueError):
            rs.material("bad", None)


class DefaultRows(unittest.TestCase):
    def test_shipped_defaults_name_the_cutouts_no_record_describes(self):
        rs = rules.RuleSet.build()
        for name, kind in (("halflife/{ladder2", "ladder"), ("de_piranesi/{pi_window", "foliage_card"),
                           ("models/props_combine/stasisshield_sheet_dx7", "shield"), ("effects/exit1", "glow")):
            self.assertEqual((rs.material(name, "") or {}).get("kind"), kind, name)


if __name__ == "__main__":
    unittest.main()
