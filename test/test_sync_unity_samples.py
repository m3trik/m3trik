#!/usr/bin/python
# coding=utf-8
"""Tests for sync_unity_samples.py -- unitytk's samples, exported from their recipes.

The script's logic runs here with stand-ins (a recipe folder, an export, a
description): the package.json writer, the semantic comparison, the meta
kept once made, and the refusal to report green without Maya. The committed
Shots sample is read for real (no Maya needed to read an FBX); one real run
exports it in an owned mayapy where Maya is installed.
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_unity_samples as s  # noqa: E402

#: A .meta holding a GUID and nothing else.
BARE_META = "fileFormatVersion: 2\nguid: abc\n"

PACKAGE = '{\n  "name": "com.example.pkg",\n  "version": "1.0.0",\n  "author": {\n    "name": "x"\n  }\n}\n'


def _recipe(name, description="what it shows"):
    return SimpleNamespace(NAME=name, DESCRIPTION=description, RECORDS=("animation",), build=lambda out: [])


def _run(argv):
    """``main(argv)``'s exit code and printed lines."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = s.main(argv)
    return code, out.getvalue()


class TestPackageJson(unittest.TestCase):
    """Added: 2026-11-05"""

    def test_the_samples_follow_the_recipes_and_every_other_key_keeps_its_place(self):
        entries = s.sample_entries([_recipe("Shots"), _recipe("Audio", "cues")])
        text = s.render_package_json(PACKAGE, entries)
        data = json.loads(text)
        self.assertEqual(list(data), ["name", "version", "author", "samples"])
        self.assertEqual(
            data["samples"],
            [
                {"displayName": "Shots", "description": "what it shows", "path": "Samples~/Shots"},
                {"displayName": "Audio", "description": "cues", "path": "Samples~/Audio"},
            ],
        )
        self.assertTrue(text.endswith("}\n"))
        again = s.render_package_json(text, entries)
        self.assertEqual(again, text, "idempotent")
        self.assertNotIn("samples", json.loads(s.render_package_json(text, [])), "no recipe, no entry")

    def test_the_committed_package_json_lists_exactly_the_recipes(self):
        manifest = s.records.unity_package() / "package.json"
        text = manifest.read_text(encoding="utf-8")
        self.assertEqual(
            json.loads(text)["samples"], s.sample_entries(s.recipes()), f"stale; run {s.SCRIPT}"
        )


class TestRecipes(unittest.TestCase):
    """Added: 2026-11-05"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def _write(self, stem, body):
        (self.folder / f"{stem}.py").write_text(body, encoding="utf-8")

    def test_each_module_is_a_recipe_by_its_name_and_private_modules_are_not(self):
        self._write("b", 'NAME = "Beta"\nDESCRIPTION = "b"\nRECORDS = ()\ndef build(out):\n    return []\n')
        self._write("a", 'NAME = "Zed"\nDESCRIPTION = "z"\nRECORDS = ()\ndef build(out):\n    return []\n')
        self._write("_helpers", "X = 1\n")
        found = s.recipes(self.folder)
        self.assertEqual([r.NAME for r in found], ["Beta", "Zed"])
        self.assertEqual(found[0].PATH, self.folder / "b.py")

    def test_a_recipe_missing_a_declaration_or_sharing_a_name_is_refused(self):
        self._write("a", 'NAME = "A"\ndef build(out):\n    return []\n')
        with self.assertRaisesRegex(ValueError, "declares no DESCRIPTION, RECORDS"):
            s.recipes(self.folder)
        self._write("a", 'NAME = "A"\nDESCRIPTION = "a"\nRECORDS = ()\ndef build(out):\n    return []\n')
        self._write("b", 'NAME = "A"\nDESCRIPTION = "b"\nRECORDS = ()\ndef build(out):\n    return []\n')
        with self.assertRaisesRegex(ValueError, "two recipes are named 'A'"):
            s.recipes(self.folder)

    def test_the_workspace_recipes_import_without_maya(self):
        """Read here for what the Package Manager lists; Maya is imported only
        inside ``build``."""
        names = [r.NAME for r in s.recipes()]
        self.assertIn("Shots", names)


class TestComparison(unittest.TestCase):
    """Added: 2026-11-05"""

    BASE = {
        "records": {"animation": {"version": 3, "shots": [{"clip": "A", "description": "x"}]}},
        "takes": {"A": [0.0417, 1.0]},
        "nodes": ["Box", "data_export"],
        "meshes": {"Box": {"vertices": 8}},
    }

    def test_equal_descriptions_have_no_differences(self):
        self.assertEqual(s.differences(self.BASE, json.loads(json.dumps(self.BASE))), [])

    def test_each_differing_leaf_is_named_with_both_values(self):
        fresh = json.loads(json.dumps(self.BASE))
        fresh["records"]["animation"]["shots"][0]["description"] = "y"
        fresh["takes"]["B"] = [1.0, 2.0]
        self.assertEqual(
            s.differences(self.BASE, fresh),
            [
                'records.animation.shots[0].description: "x" -> "y"',
                "takes.B[0]: absent -> 1.0",
                "takes.B[1]: absent -> 2.0",
            ],
        )

    def test_a_long_drift_line_names_the_first_few_and_counts_the_rest(self):
        line = s.summary([f"p{i}" for i in range(s.SHOWN + 3)])
        self.assertTrue(line.endswith("; and 3 more"), line)



class TestWhatASampleIsFor(unittest.TestCase):
    """A sample is described by what its feature reads -- the records its
    recipe names (``RECORDS``) -- and the delivery's structure, never by the
    handoff's prose: a wording edit to a record's description changed the
    committed sample's ``handoff.assembly[].spec`` and failed ``--check``
    (and push.ps1's Test-UnitySamples gate) until a Maya re-export was
    committed. Added: 2026-11-05"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.committed = s.records.unity_package() / s.SAMPLES / "Shots" / "Shots.fbx"
        self.copy = Path(self._tmp.name) / "Shots.fbx"
        shutil.copyfile(self.committed, self.copy)
        (self.shots,) = [r for r in s.recipes() if r.NAME == "Shots"]

    def _edit(self, key, change):
        import pythontk as ptk

        payload = ptk.FbxMedia.record(str(self.copy), key)
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
        change(payload)
        self.assertTrue(ptk.FbxMedia.set_record(str(self.copy), key, payload)["replaced"])

    def _differences(self):
        records = self.shots.RECORDS
        return s.differences(s.describe(self.committed, records), s.describe(self.copy, records))

    def test_the_shots_sample_reads_the_animation_record(self):
        self.assertEqual(tuple(self.shots.RECORDS), ("animation",))
        self.assertEqual(list(s.describe(self.committed, self.shots.RECORDS)["records"]), ["animation"])

    def test_a_reworded_handoff_is_no_drift(self):
        def reword(handoff):
            handoff["instructions"] = "Reworded."
            for row in handoff["assembly"]:
                row["spec"] = "Reworded."

        self._edit("handoff", reword)
        self.assertEqual(self._differences(), [])

    def test_a_renamed_shot_is_drift(self):
        def rename(animation):
            animation["shots"][0]["clip"] = "Arrive"

        self._edit("animation", rename)
        self.assertEqual(
            self._differences(), ['records.animation.shots[0].clip: "Approach" -> "Arrive"']
        )

    def test_a_file_embedded_since_is_drift(self):
        from unity_samples._images import write_png

        png = write_png(str(Path(self._tmp.name) / "Extra.png"), lambda x, y: (x * 16, y * 16, 0, 255))
        import pythontk as ptk

        self.assertEqual(ptk.FbxMedia.embed(str(self.copy), files=[png])["embedded"], ["Extra.png"])
        empty, line = self._differences()  # the Shots sample embeds nothing of its own
        self.assertEqual(empty, "media: {} -> absent")
        self.assertTrue(line.startswith("media.Extra.png: absent -> \"texels:"), line)


class TestTheDescribedMedia(unittest.TestCase):
    """An embedded file is described by what it holds: an image by its texels,
    so a packer's provenance chunk or a re-encode is no drift (the Materials
    sample's packed ORM map gained a source-hash text chunk, its texels the
    same), and a texel edit is; another file by its bytes. Added: 2026-11-07"""

    @staticmethod
    def _png(pixel, **text):
        import io

        from PIL import Image, PngImagePlugin

        image = Image.new("RGB", (4, 4))
        image.putdata([pixel(i % 4, i // 4) for i in range(16)])
        info = PngImagePlugin.PngInfo()
        for key, value in text.items():
            info.add_text(key, value)
        out = io.BytesIO()
        image.save(out, "PNG", pnginfo=info)
        return out.getvalue()

    def test_an_images_texels_not_its_encoding(self):
        plain = self._png(lambda x, y: (x * 60, y * 60, 0))
        stamped = self._png(lambda x, y: (x * 60, y * 60, 0), source="a hash of its sources")
        edited = self._png(lambda x, y: (x * 60, y * 60, 1))
        self.assertNotEqual(plain, stamped, "the bytes differ")
        self.assertEqual(s._digest(plain), s._digest(stamped), "the texels do not")
        self.assertTrue(s._digest(plain).startswith("texels:"))
        self.assertNotEqual(s._digest(plain), s._digest(edited), "one texel's channel moved")

    def test_a_file_that_is_no_image_by_its_bytes(self):
        sound = b"RIFF" + bytes(4) + b"WAVEfmt "
        self.assertEqual(s._digest(sound), "bytes:" + __import__("hashlib").sha256(sound).hexdigest())


class TestTheCommittedShotsSample(unittest.TestCase):
    """The committed FBX, read as --check reads it (no Maya). Added: 2026-11-05"""

    def test_it_holds_one_take_per_shot_and_the_record_of_their_descriptions(self):
        fbx = s.records.unity_package() / s.SAMPLES / "Shots" / "Shots.fbx"
        described = s.describe(fbx, ("animation",))
        self.assertEqual(
            described["takes"],
            [
                {"take": "Approach", "start": 0.0417, "end": 1.0},
                {"take": "Turn", "start": 1.0417, "end": 2.0},
                {"take": "Exit", "start": 2.0417, "end": 3.0},
            ],
            "one take per shot, in shot order, spanning its frames at 24 fps",
        )
        shots = described["records"]["animation"]["shots"]
        self.assertEqual([shot["clip"] for shot in shots], ["Approach", "Turn", "Exit"])
        self.assertEqual([shot["metadata"] for shot in shots], [{"section": "intro"}, {"section": "middle"}, {"section": "outro"}])
        self.assertEqual(described["records"]["animation"]["fps"], 24.0)
        self.assertNotIn("handoff", described["records"], "no producer provenance, no prose")
        self.assertEqual(described["nodes"], ["Box", "data_export"])
        self.assertLess(fbx.stat().st_size, 200_000, "a sample stays small")
        self.assertTrue(fbx.with_name("Shots.fbx.meta").is_file(), "every file ships its meta")


class TestTheCommittedMaterialsSample(unittest.TestCase):
    """The committed Materials FBX, read as --check reads it (no Maya), and the
    recipe's image writer. Added: 2026-11-05"""

    def test_it_states_its_four_materials_as_literal_gltf_with_their_images_inside(self):
        import pythontk as ptk

        fbx = s.records.unity_package() / s.SAMPLES / "Materials" / "Materials.fbx"
        record = s.describe(fbx, ("materials",))["records"]["materials"]
        self.assertEqual(record["version"], 2)
        self.assertEqual(record["asset"], {"version": "2.0"})
        by_name = {m["name"]: m for m in record["materials"]}
        self.assertEqual(sorted(by_name), ["Flat_MAT", "Glow_MAT", "Metal_MAT", "Tiled_MAT"])
        images = [i["uri"] for i in record["images"]]

        def image(info):
            return images[record["textures"][info["index"]]["source"]]

        metal = by_name["Metal_MAT"]["pbrMetallicRoughness"]
        self.assertEqual(image(metal["metallicRoughnessTexture"]), "Metal_ORM.png", "metal and roughness packed, glTF's layout")
        self.assertEqual(
            by_name["Glow_MAT"]["extensions"]["KHR_materials_emissive_strength"]["emissiveStrength"], 4.0
        )
        self.assertIn("KHR_materials_unlit", by_name["Flat_MAT"]["extensions"])
        transform = by_name["Tiled_MAT"]["pbrMetallicRoughness"]["baseColorTexture"]["extensions"]["KHR_texture_transform"]
        self.assertEqual(transform, {"offset": [0.25, -1.5], "scale": [3.0, 2.0]}, "Maya's repeat and offset, in glTF's UV space")
        embedded = {e["name"] for e in ptk.FbxMedia.embedded(str(fbx))}
        self.assertLessEqual(set(images), embedded, "every image the record names rides inside the FBX")
        self.assertLess(fbx.stat().st_size, 300_000, "a sample stays small")
        self.assertTrue(fbx.with_name("Materials.fbx.meta").is_file(), "every file ships its meta")

    def test_its_recipe_writes_the_same_png_bytes_on_every_run(self):
        from unity_samples._images import write_png

        with tempfile.TemporaryDirectory() as tmp:
            a = write_png(str(Path(tmp, "a.png")), lambda x, y: (x * 16, y * 16, 0, 255))
            b = write_png(str(Path(tmp, "b.png")), lambda x, y: (x * 16, y * 16, 0, 255))
            data = Path(a).read_bytes()
            self.assertEqual(data, Path(b).read_bytes())
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))


class TestTheCommittedRenderEffectsSample(unittest.TestCase):
    """The committed RenderEffects FBX, read as --check reads it (no Maya): every
    channel the render_effects record holds, each on its curve proxy in both
    takes, over the mapped emission and the group copy its materials record
    states. Added: 2026-11-07"""

    def setUp(self):
        self.fbx = s.records.unity_package() / s.SAMPLES / "RenderEffects" / "RenderEffects.fbx"
        (self.recipe,) = [r for r in s.recipes() if r.NAME == "RenderEffects"]

    def test_it_carries_every_channel_of_the_record_on_its_proxy_in_each_take(self):
        import pythontk as ptk

        described = s.describe(self.fbx, self.recipe.RECORDS)
        self.assertEqual(
            [t["take"] for t in described["takes"]], ["FadeOut", "FadeIn"], "one take per shot, in shot order"
        )
        record = described["records"]["render_effects"]
        self.assertEqual(
            {t["node"]: t["channels"] for t in record["tracks"]},
            {"Box": ["opacity"], "Panel": ["visibility"], "Sphere": ["highlight"]},
        )
        (sphere,) = [t for t in record["tracks"] if t["node"] == "Sphere"]
        self.assertEqual((sphere["highlight_color"], sphere["highlight_color_dim"]), ([0.2, 0.6, 1.0], [0.0, 0.0, 0.0]))
        self.assertEqual(
            record["materials"],
            [{"material": "Lamp_MAT_Signal", "channels": ["emission"], "emission_color": [1.0, 0.8, 0.3], "emission_strength": 1.0}],
        )
        self.assertEqual(
            {n for n in described["nodes"] if "__" in n},
            {"Box/Box__opacity", "Panel/Panel__visibility", "Sphere/Sphere__highlight", "data_export/Lamp_MAT_Signal__emission"},
            "one proxy per channel: under its node, or under the carrier for a material",
        )
        curves = ptk.MeshConvert.render_effect_curves(ptk.FbxFile.load(str(self.fbx), decode_arrays=ptk.FbxFile.CURVE_ARRAYS))
        channels = {("Box", "opacity"), ("Panel", "visibility"), ("Sphere", "highlight"), ("Lamp_MAT_Signal", "emission")}
        for take in ("FadeOut", "FadeIn"):
            self.assertEqual(set(curves[take]), channels, take)
        verdict = ptk.ExportVerifier(fbx=str(self.fbx), sidecar=None).run(["check_fbx_render_effects", "check_fbx_records"])
        self.assertTrue(verdict.ok, verdict.summary())

    def test_its_effects_are_drawn_over_a_mapped_emission_and_the_groups_copy(self):
        import pythontk as ptk

        record = s.describe(self.fbx, self.recipe.RECORDS)["records"]["materials"]
        by_name = {m["name"]: m for m in record["materials"]}
        self.assertEqual(sorted(by_name), ["Box_MAT", "Lamp_MAT_Signal", "Panel_MAT", "Sphere_MAT"])
        glow = by_name["Sphere_MAT"]
        self.assertEqual(glow["emissiveFactor"], [1.0, 1.0, 1.0])
        image = record["images"][record["textures"][glow["emissiveTexture"]["index"]]["source"]]["uri"]
        self.assertEqual(image, "Sphere_Emission.png")
        self.assertIn(image, {e["name"] for e in ptk.FbxMedia.embedded(str(self.fbx))}, "the map rides inside the FBX")
        self.assertEqual(by_name["Lamp_MAT_Signal"]["emissiveFactor"], [0.0, 0.0, 0.0], "the lamp group rests off")
        self.assertLess(self.fbx.stat().st_size, 300_000, "a sample stays small")
        self.assertTrue(self.fbx.with_name("RenderEffects.fbx.meta").is_file(), "every file ships its meta")

    def test_its_description_holds_each_takes_keys_and_its_maps_texels(self):
        """So a recipe edit to a key or to the map's texels is drift: the
        description held records, windows, nodes and mesh counts alone, and a
        stale FBX passed --check. Added: 2026-11-07"""
        described = s.describe(self.fbx, self.recipe.RECORDS)
        self.assertEqual(list(described["animation"]), ["FadeOut", "FadeIn"])
        for take in ("FadeOut", "FadeIn"):
            self.assertLessEqual(
                {"Box/Box__opacity:Lcl Scaling.X", "Sphere/Sphere__highlight:Lcl Scaling.X",
                 "Panel/Panel__visibility:Lcl Scaling.X", "data_export/Lamp_MAT_Signal__emission:Lcl Scaling.X"},
                set(described["animation"][take]),
                f"{take}: every proxy's curve",
            )
        fps = 24.0
        opacity = {t: v for t, v, _ in described["animation"]["FadeOut"]["Box/Box__opacity:Lcl Scaling.X"]}
        (start, end, _), _ = self.recipe.FADES
        self.assertEqual(
            (opacity[round(start / fps, 4)], opacity[round((start + end) / 2 / fps, 4)], opacity[round(end / fps, 4)]),
            (1.0, 0.5, 0.0),
            "the recipe's fade out, frame by frame in seconds",
        )
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(self.recipe.write_emission_map(str(Path(tmp, "map.png")))).read_bytes()
        self.assertEqual(described["media"], {"Sphere_Emission.png": s._digest(png)}, "the recipe's map, texel for texel")

    def test_its_emission_map_is_written_by_the_samples_one_png_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(self.recipe.write_emission_map(str(Path(tmp, "a.png")))).read_bytes()
            b = Path(self.recipe.write_emission_map(str(Path(tmp, "b.png")))).read_bytes()
        self.assertEqual(a, b, "the same bytes on every run")
        self.assertTrue(a.startswith(b"\x89PNG\r\n\x1a\n"))


class TestTheCommittedLightmapsSample(unittest.TestCase):
    """The committed Lightmaps FBX, read as --check reads it (no Maya): the
    lightmaps record v3 its recipe committed -- the floor's own map, the boxes'
    atlas and their rects, the probe at its point in its box -- with the
    export's highlight pass run (the lamp drawn into the probe, a copy for the
    boxes), every file it names inside, the maps texel for texel the recipe's.
    Added: 2026-11-07"""

    def setUp(self):
        self.fbx = s.records.unity_package() / s.SAMPLES / "Lightmaps" / "Lightmaps.fbx"
        (self.recipe,) = [r for r in s.recipes() if r.NAME == "Lightmaps"]

    def test_it_holds_each_objects_map_and_rect_and_the_probe_its_recipe_committed(self):
        import pythontk as ptk

        record = s.describe(self.fbx, self.recipe.RECORDS)["records"]["lightmaps"]
        self.assertEqual((record["version"], record["unit_scale"]), (3, 0.01), "v3, in centimetres")
        expected = {name: (self.recipe.BOX_ATLAS, rect) for name, rect in self.recipe.RECTS.items()}
        expected["Floor"] = (self.recipe.FLOOR_MAP, [1.0, 1.0, 0.0, 0.0])
        self.assertEqual({o["name"]: (o["map"], o["scaleOffset"]) for o in record["objects"]}, expected)
        self.assertEqual({o["name"]: o["hierarchy"] for o in record["objects"]}, {n: [n] for n in expected})
        probe = record["probe"]
        self.assertEqual(probe["position"], list(self.recipe.PROBE_AT))
        self.assertEqual(probe["box"], {"min": list(self.recipe.PROBE_BOX[0]), "max": list(self.recipe.PROBE_BOX[1])})
        stem = self.recipe.PROBE.rsplit(".", 1)[0]
        self.assertEqual(probe["map"], ptk.MeshConvert.HIGHLIGHT_PROBE_NAME.format(stem=stem), "the probe with the lamp drawn in")
        (copy,) = probe["highlights"]
        self.assertEqual(sorted(o["name"] for o in copy["objects"]), ["Box_A", "Box_B", "Box_C"], "the floor is the room's shell")
        (lamp,) = record["lights"]
        self.assertEqual((lamp["type"], lamp["position"], lamp["intensity"]), ("point", list(self.recipe.LAMP_AT), self.recipe.LAMP_INTENSITY))
        verdict = ptk.ExportVerifier(fbx=str(self.fbx), sidecar=None).run(["check_fbx_records", "check_fbx_dependencies"])
        self.assertTrue(verdict.ok, verdict.summary())
        embedded = {e["name"] for e in ptk.FbxMedia.embedded(str(self.fbx))}
        self.assertNotIn(self.recipe.PROBE, embedded, "the bake's own probe stays home: the delivered one replaces it")
        self.assertLess(self.fbx.stat().st_size, 200_000, "a sample stays small")
        self.assertTrue(self.fbx.with_name("Lightmaps.fbx.meta").is_file(), "every file ships its meta")

    def test_its_maps_are_the_recipes_texels(self):
        import numpy as np
        import pythontk as ptk  # first: it enables OpenCV's EXR codec
        import cv2

        with tempfile.TemporaryDirectory() as tmp:
            written = ptk.FbxMedia.extract_dependencies(str(self.fbx), tmp)
            pixels = self.recipe.lightmap_pixels()
            self.assertLessEqual(set(pixels), set(written))
            for name, expected in pixels.items():
                bgr = ptk.ImgUtils.cv2_read(written[name], cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
                self.assertEqual(bgr.shape, (self.recipe.MAP_SIZE, self.recipe.MAP_SIZE, 3), name)
                np.testing.assert_array_equal(
                    bgr[:, :, ::-1], expected.astype(np.float16).astype(np.float32), err_msg=f"{name}: half floats, as written"
                )


class TestTheCommittedShadowPlaneSample(unittest.TestCase):
    """The committed ShadowPlane FBX, read as --check reads it (no Maya): the
    shadows record v3 its recipe's three rigs made -- each plane's source,
    contact, rig type (the silhouette's draw choice) and fade terms -- every
    plane's horizon map and silhouette inside it, and one take: the lamp's
    sweep and each plane's placement (the Scene Exporter bakes the rig's
    driven transform channels, ShadowRig's documented FBX export; a reader
    following the source places it itself), and never a fade or visibility
    channel -- every reader fades a plane from the record's fade terms
    (shadows v3), so a keyed fade would fade it twice. Added: 2026-11-07;
    the placement keys and the never-keyed fade: 2026-11-08"""

    def setUp(self):
        self.fbx = s.records.unity_package() / s.SAMPLES / "ShadowPlane" / "ShadowPlane.fbx"
        (self.recipe,) = [r for r in s.recipes() if r.NAME == "ShadowPlane"]
        self.described = s.describe(self.fbx, self.recipe.RECORDS)

    def test_it_holds_one_plane_per_rig_each_with_its_horizon_map(self):
        import pythontk as ptk

        record = self.described["records"]["shadows"]
        self.assertEqual((record["version"], record["unit_scale"]), (3, 0.01), "v3, in centimetres")
        planes = {p["name"]: p for p in record["planes"]}
        expected = {
            f"{target}_{source}_shadow": (source, f"{target}_{source}_contact_loc", kind)
            for target, source, kind in self.recipe.RIGS
        }
        self.assertEqual(set(planes), set(expected))
        embedded = {e["name"] for e in ptk.FbxMedia.embedded(str(self.fbx))}
        for name, (source, contact, kind) in expected.items():
            plane = planes[name]
            self.assertEqual((plane["source"], plane["contact"]), (source, contact), name)
            self.assertEqual(plane["source_type"], "directional" if source == "Sun" else "point", name)
            self.assertEqual(plane["silhouette"]["draw"], kind == "projected", f"{name}: the rig type, as the draw choice")
            self.assertEqual((plane["intensity"], plane["falloff_power"], plane["ground"]), (1.0, 1.2, 0.0), name)
            self.assertEqual(plane["fade_height"], 2.0 * plane["height"], f"{name}: the rig's default fade height")
            self.assertTrue(plane["follow_source"], name)
            horizon = plane["horizon"]
            self.assertEqual((horizon["size"], horizon["spans"]), (128, 2), name)
            self.assertIn(horizon["texture"], embedded, f"{name}: its horizon map rides the FBX")
            self.assertIn(plane["silhouette"]["texture"], embedded, f"{name}: its silhouette rides it too")
        chair = planes["Chair_Sun_shadow"]
        self.assertEqual(chair["height"], self.recipe.SEAT[1] + self.recipe.BACK, "the chair's back over its seat")
        self.assertLess(self.fbx.stat().st_size, 400_000, "a sample stays small")
        self.assertTrue(self.fbx.with_name("ShadowPlane.fbx.meta").is_file(), "every file ships its meta")

    #: What a plane's take may key: its placement, the rig's driven
    #: transform channels (ShadowRig.BAKE_CHANNELS as the FBX writes them).
    PLACEMENT = sorted(
        [f"Lcl Translation.{a}" for a in "XYZ"]
        + [f"Lcl Rotation.{a}" for a in "XYZ"]
        + ["Lcl Scaling.X", "Lcl Scaling.Z"]
    )

    def test_the_lamps_sweep_is_its_one_take_and_its_only_animation(self):
        """The take keys the lamp's sweep and each plane's placement, nothing
        else: no fade (``opacity``) and no visibility on any plane (a
        whole-timeline bake keyed the rig's preview fade until it moved onto
        the material, 2026-11-08)."""
        first, last = self.recipe.FRAMES
        self.assertEqual(self.described["takes"], [{"take": "Take 001", "start": round(first / 24, 4), "end": last / 24}])
        (channels,) = self.described["animation"].values()
        planes = {f"{target}_{source}_shadow" for target, source, _kind in self.recipe.RIGS}
        placed = {plane: [] for plane in planes}
        other = []
        for channel in channels:
            node, _, prop = channel.rpartition(":")
            leaf = node.rsplit("/", 1)[-1]
            if leaf in placed:
                placed[leaf].append(prop)
            else:
                other.append(channel)
        self.assertEqual(sorted(other), [f"Lamp:Lcl Translation.{a}" for a in "XYZ"], "the lamp's sweep")
        for plane, props in placed.items():
            self.assertEqual(sorted(props), self.PLACEMENT, f"{plane}: its placement, no fade, no visibility")
        for (frame, at), key in zip(self.recipe.LAMP_KEYS, channels["Lamp:Lcl Translation.Y"]):
            self.assertEqual(key[:2], [round(frame / 24, 4), at[1]])


class TestTheCommittedArticulatedRigSample(unittest.TestCase):
    """The committed ArticulatedRig FBX, read as --check reads it (no Maya):
    the articulation record v2 its recipe's rig made -- every joint the node
    the rig built, chained by its parent links, on the identity anchor, its
    channels the joint type's and its limits the stops the recipe posed, in
    metres for the slide -- every moving part a grab part, the rig's controls
    gone, and one take, the shot, keying each channel on its joint.
    Added: 2026-11-08"""

    def setUp(self):
        self.fbx = s.records.unity_package() / s.SAMPLES / "ArticulatedRig" / "ArticulatedRig.fbx"
        (self.recipe,) = [r for r in s.recipes() if r.NAME == "ArticulatedRig"]
        self.described = s.describe(self.fbx, self.recipe.RECORDS)

    def test_it_holds_the_rig_its_recipe_built_with_the_limits_taken_from_its_poses(self):
        record = self.described["records"]["articulation"]
        self.assertEqual(record["version"], 2)
        (rig,) = record["rigs"]
        self.assertEqual(rig["name"], self.recipe.GROUP.lower())
        parts = [j[0] for j in self.recipe.JOINTS]
        self.assertEqual([j["name"] for j in rig["joints"]], [f"lamp_{p}_jnt" for p in parts])
        self.assertEqual(
            [j["parent"] for j in rig["joints"]],
            [None if parent == self.recipe.PARTS[0][0] else parts.index(parent) for _, parent, *_ in self.recipe.JOINTS],
            "chained by the parent links, the root on the base",
        )
        channels = {"universal": ["rx", "rz"], "hinge": ["rz"], "slide": ["tx"]}
        for joint, (part, _, kind, *_rest) in zip(rig["joints"], self.recipe.JOINTS):
            self.assertEqual(joint["anchor"], {"t": [0, 0, 0], "q": [0, 0, 0, 1]}, f"{part}: a Maya rig's identity anchor")
            self.assertEqual([c["channel"] for c in joint["channels"]], channels[kind], part)
            for c in joint["channels"]:
                unit = 0.01 if c["channel"] == "tx" else 1.0  # centimetres to metres
                lo, hi = self.recipe.STOPS[(part, c["channel"])]
                self.assertAlmostEqual(c["min"], lo * unit, places=9, msg=f"{part} {c['channel']}: from its pose")
                self.assertAlmostEqual(c["max"], hi * unit, places=9, msg=f"{part} {c['channel']}: from its pose")
        self.assertAlmostEqual(rig["joints"][1]["t"][0], 0.31, places=9, msg="the arm's rest in metres: the post's 31 cm")
        self.assertEqual(rig["grab"], [{"node": p, "joint": i} for i, p in enumerate(parts)], "every moving part")
        self.assertFalse([n for n in self.described["nodes"] if "_CTRL" in n], "the rig's controls dropped")
        self.assertLess(self.fbx.stat().st_size, 400_000, "a sample stays small")
        self.assertTrue(self.fbx.with_name("ArticulatedRig.fbx.meta").is_file(), "every file ships its meta")

    def test_its_one_take_is_the_shot_keying_each_channel_on_its_joint(self):
        ((shot, first, last),) = self.recipe.SHOTS
        self.assertEqual(self.described["takes"], [{"take": shot, "start": round(first / 24, 4), "end": last / 24}])
        channels = self.described["animation"][shot]
        lengths = {"rx": "Lcl Rotation.X", "rz": "Lcl Rotation.Z", "tx": "Lcl Translation.X"}
        rests = {"Extension": 14.0}  # the slide's joint stands 14 cm down the arm at rest: tx adds to it
        for frame, values in self.recipe.KEYS:
            for (part, channel), value in values.items():
                (label,) = [k for k in channels if k.endswith(f"lamp_{part}_jnt:{lengths[channel]}")]
                key = next(k for k in channels[label] if k[0] == round(frame / 24, 4))
                self.assertAlmostEqual(key[1], value + rests.get(part, 0.0), places=3, msg=f"{part} {channel} at {frame}")


class TestTheSamplesAreMadeApart(unittest.TestCase):
    """Each recipe runs in a new scene, with nothing of the last one's: a
    sample whose recipe defines no shots holds no other recipe's shot as a take.
    The one mayapy is standalone, where no scene-opened job drops the active
    shot store, so the driver drops it. Added: 2026-11-07"""

    def test_no_sample_holds_another_recipes_shots(self):
        found = s.recipes()
        shots = {r.NAME: {shot[0] for shot in getattr(r, "SHOTS", ())} for r in found}
        for recipe in found:
            for fbx in sorted((s.records.unity_package() / s.SAMPLES / recipe.NAME).glob("*.fbx")):
                takes = {t["take"] for t in s.describe(fbx, ())["takes"]}
                others = set().union(*(names for name, names in shots.items() if name != recipe.NAME)) - shots[recipe.NAME]
                self.assertFalse(takes & others, f"{recipe.NAME}: another recipe's shots as takes: {sorted(takes & others)}")

    def test_the_driver_drops_the_active_shot_store_after_each_new_scene(self):
        body = s.DRIVER.split('cmds.file(new=True, force=True)', 1)[1].split("done[name]", 1)[0]
        self.assertIn("ptk.ShotStore.clear_active()", body)


class TestSync(unittest.TestCase):
    """The sync over stand-in descriptions. Added: 2026-11-05"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.fresh, self.sample = root / "fresh", root / "sample"
        self.fresh.mkdir()
        (self.fresh / "M.fbx").write_bytes(b"new")
        self.described = {}
        patcher = patch.object(
            s, "describe", side_effect=lambda p, records=(): self.described[Path(p).read_bytes()]
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _sync(self, check):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            failed = s.sync_sample(_recipe("M"), {"M": ["M.fbx"]}, self.fresh, self.sample, check)
        return failed, out.getvalue()

    def test_a_missing_file_drifts_in_check_and_is_written_with_its_meta_otherwise(self):
        failed, said = self._sync(check=True)
        self.assertTrue(failed)
        self.assertIn("DRIFT: M", said)
        self.assertIn("missing", said)
        self.assertFalse(self.sample.exists(), "--check writes nothing")
        failed, _ = self._sync(check=False)
        self.assertFalse(failed)
        self.assertEqual((self.sample / "M.fbx").read_bytes(), b"new")
        meta = (self.sample / "M.fbx.meta").read_text(encoding="utf-8")
        self.assertRegex(meta, r"^fileFormatVersion: 2\nguid: [0-9a-f]{32}\nModelImporter:\n  serializedVersion: \d+\n$")

    def test_a_file_described_alike_is_left_alone_and_its_meta_kept(self):
        self.sample.mkdir()
        (self.sample / "M.fbx").write_bytes(b"old")
        (self.sample / "M.fbx.meta").write_text(BARE_META + s.IMPORTER_META[".fbx"], encoding="utf-8")
        self.described = {b"old": {"takes": {"A": [0, 1]}}, b"new": {"takes": {"A": [0, 1]}}}
        for check in (True, False):
            failed, said = self._sync(check)
            self.assertFalse(failed, said)
            self.assertEqual(said, "")
        self.assertEqual((self.sample / "M.fbx").read_bytes(), b"old", "bytes differ, the sample does not")
        self.assertIn("guid: abc", (self.sample / "M.fbx.meta").read_text(encoding="utf-8"))

    def test_a_file_described_otherwise_drifts_and_is_replaced(self):
        self.sample.mkdir()
        (self.sample / "M.fbx").write_bytes(b"old")
        (self.sample / "M.fbx.meta").write_text(BARE_META + s.IMPORTER_META[".fbx"], encoding="utf-8")
        self.described = {b"old": {"takes": {"A": [0, 1]}}, b"new": {"takes": {"A": [0, 2]}}}
        failed, said = self._sync(check=True)
        self.assertTrue(failed)
        self.assertIn("takes.A[1]: 1 -> 2", said)
        self.assertIn(f"run {s.SCRIPT}", said)
        self.assertFalse(self._sync(check=False)[0])
        self.assertEqual((self.sample / "M.fbx").read_bytes(), b"new")
        self.assertIn("guid: abc", (self.sample / "M.fbx.meta").read_text(encoding="utf-8"), "the GUID holds")


    def test_a_models_meta_states_its_importer_version_or_drifts(self):
        """A model's .meta holding only its GUID imports with the settings of a
        file from before the importer's versions: measured in Unity 6000.3
        (2026-11-05), a Legacy rig (an Animator Controller refuses its clips)
        and External (Legacy) materials (a Materials folder and a .fbm written
        beside the sample); stating the importer's version gives Unity's
        defaults for a new file, as a .meta Unity writes would. The GUID holds.
        Added: 2026-11-05"""
        self.sample.mkdir()
        (self.sample / "M.fbx").write_bytes(b"old")
        (self.sample / "M.fbx.meta").write_text(BARE_META, encoding="utf-8")
        self.described = {b"old": {"takes": {"A": [0, 1]}}, b"new": {"takes": {"A": [0, 1]}}}
        failed, said = self._sync(check=True)
        self.assertTrue(failed)
        self.assertIn("states no importer version", said)
        self.assertEqual((self.sample / "M.fbx.meta").read_text(encoding="utf-8"), BARE_META, "--check writes nothing")
        self.assertFalse(self._sync(check=False)[0])
        self.assertEqual(
            (self.sample / "M.fbx.meta").read_text(encoding="utf-8"), BARE_META + s.IMPORTER_META[".fbx"]
        )
        self.assertFalse(self._sync(check=True)[0], "a second run finds nothing")

    def test_a_delivery_file_the_recipe_stopped_producing_drifts_and_is_removed(self):
        """Bug: only the files the recipe returned were judged, so a generated
        file it stopped producing (and an orphaned ``.meta``) stayed in the
        sample and ``--check`` passed. The sample's own code (its demo, its
        assemblies), its subfolders and every live ``.meta`` are kept.
        Fixed: 2026-11-08"""
        self.sample.mkdir()
        (self.sample / "M.fbx").write_bytes(b"old")
        kept = {
            "M.fbx.meta": BARE_META + s.IMPORTER_META[".fbx"],
            "MDemo.cs": "class MDemo { }\n",
            "MDemo.cs.meta": BARE_META,
            "P.Samples.M.asmdef": "{}\n",
            "P.Samples.M.asmdef.meta": BARE_META,
            "Editor.meta": BARE_META,
            "Editor/MDemoRecipe.cs": "class R { }\n",
            "Editor/Notes.json": "{}\n",
        }
        stale = {"Old.png": "png", "Old.png.meta": BARE_META, "Gone.fbx.meta": BARE_META}
        for rel, text in {**kept, **stale}.items():
            (self.sample / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.sample / rel).write_text(text, encoding="utf-8")
        self.described = {b"old": {"takes": {"A": [0, 1]}}, b"new": {"takes": {"A": [0, 1]}}}
        failed, said = self._sync(check=True)
        self.assertTrue(failed, said)
        self.assertIn("Old.png: the recipe no longer produces it", said)
        self.assertIn("Gone.fbx.meta: the recipe no longer produces it", said)
        self.assertNotIn("Old.png.meta", said)  # its file is reported; the meta goes with it
        self.assertTrue((self.sample / "Old.png").is_file(), "--check writes nothing")
        failed, said = self._sync(check=False)
        self.assertFalse(failed, said)
        for rel in stale:
            self.assertFalse((self.sample / rel).exists(), rel)
        for rel in kept:
            self.assertTrue((self.sample / rel).is_file(), rel)
        self.assertEqual(self._sync(check=True), (False, ""), "a second run finds nothing")

    def test_a_recipe_the_export_holds_no_files_of_judges_none(self):
        """No entry for the recipe (an export that did not run it): nothing is
        judged extra, so nothing is removed."""
        self.sample.mkdir()
        (self.sample / "M.fbx").write_bytes(b"old")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            failed = s.sync_sample(_recipe("M"), {}, self.fresh, self.sample, False)
        self.assertFalse(failed, out.getvalue())
        self.assertTrue((self.sample / "M.fbx").is_file())


class TestExport(unittest.TestCase):
    """The one mayapy the recipes run in. Added: 2026-11-07"""

    def test_its_crashing_teardown_saves_no_recovery_scene(self):
        """mayapy's teardown crashes after the work (the driver's ``os._exit``),
        and Maya's crash handler saved the open scene as
        ``<scene>[Recovered-...].ma`` in the user's temp folder on every run:
        the child is launched with that save off, the rest of its environment
        inherited."""
        import pythontk as ptk

        seen = {}

        def run(app, script, *, artifact, env=None, **kwargs):
            seen["env"] = env
            Path(artifact).write_text("{}", encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ptk.ScriptRunner, "run_script_to_artifact", side_effect=run
        ):
            self.assertEqual(s.export([], Path(tmp), "mayapy"), {})
        env = seen["env"] or {}
        self.assertEqual(env.get("MAYA_DEBUG_NO_SAVE_ON_CRASH"), "1")
        self.assertIn("PATH", {k.upper() for k in env}, "the inherited environment, with it added")


class TestMain(unittest.TestCase):
    """Added: 2026-11-05"""

    def test_without_maya_it_never_reports_green(self):
        with patch.object(s, "find_mayapy", return_value=None), patch.object(s, "export") as export:
            code, said = _run(["--check"])
        self.assertEqual(code, s.CANNOT_RUN)
        self.assertIn("FAIL: no Maya", said)
        self.assertIn("never in the Maya-less CI", said)
        self.assertNotIn("in sync", said)
        export.assert_not_called()

    def test_a_run_whose_export_matches_the_committed_samples_is_in_sync(self):
        """The whole flow over a stand-in producer that hands back the
        committed files."""
        samples = s.records.unity_package() / s.SAMPLES

        def export(found, out_root, mayapy):
            produced = {}
            for recipe in found:
                (out_root / recipe.NAME).mkdir(parents=True)
                names = [p.name for p in (samples / recipe.NAME).glob("*.fbx")]
                for name in names:
                    shutil.copyfile(samples / recipe.NAME / name, out_root / recipe.NAME / name)
                produced[recipe.NAME] = names
            return produced

        with patch.object(s, "find_mayapy", return_value="mayapy"), patch.object(s, "export", side_effect=export):
            code, said = _run(["--check"])
        self.assertEqual(code, 0, said)
        self.assertIn("in sync: ", said)

    def test_a_sample_folder_no_recipe_makes_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Shots").mkdir()
            (Path(tmp) / "Gone").mkdir()
            self.assertEqual(s.orphans([_recipe("Shots")], Path(tmp)), ["Gone"])

    @unittest.skipUnless(s.find_mayapy(), "no Maya installed: the real export runs where Maya is")
    def test_the_real_export_matches_the_committed_samples(self):
        """One real run: the recipes in an owned mayapy this run launches."""
        code, said = _run(["--check"])
        self.assertEqual(code, 0, said)


if __name__ == "__main__":
    unittest.main()
