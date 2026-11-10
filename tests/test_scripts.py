import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "slide-alchemy" / "scripts"


def xfrm(xml, index=0):
    """(x, y, cx, cy) of the index-th shape transform in slide XML."""
    offs = re.findall(r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(\d+)" cy="(\d+)"/>', xml)
    return tuple(int(v) for v in offs[index])


def adjustment(xml):
    return int(re.search(r'<a:gd name="adj" fmla="val (\d+)"/>', xml).group(1))


class SimpleSvgToPptxTests(unittest.TestCase):
    def test_nonzero_viewbox_origin_maps_to_slide_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            svg = tmp_path / "shape.svg"
            pptx = tmp_path / "shape.pptx"
            svg.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 100 100">
  <rect x="-10" y="-10" width="10" height="10" fill="#ff0000" stroke="none"/>
</svg>
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "simple_svg_to_pptx.py"),
                    str(svg),
                    str(pptx),
                    "--slide-width",
                    "10",
                    "--slide-height",
                    "10",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            with zipfile.ZipFile(pptx) as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

            self.assertIn('<a:off x="0" y="0"/>', slide_xml)

    def test_rejects_unsupported_visible_elements(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            svg = tmp_path / "shape.svg"
            pptx = tmp_path / "shape.pptx"
            svg.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <text x="10" y="10">label</text>
</svg>
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "simple_svg_to_pptx.py"),
                    str(svg),
                    str(pptx),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsupported SVG element: text", result.stderr)
            self.assertFalse(pptx.exists())

    def convert(self, body, view_box="0 0 1920 1080"):
        """Convert an SVG body and return (returncode, stderr, slide XML or None)."""
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "shape.svg"
            pptx = Path(tmp) / "shape.pptx"
            svg.write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">{body}</svg>',
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "simple_svg_to_pptx.py"), str(svg), str(pptx)],
                capture_output=True,
                text=True,
            )
            if result.returncode:
                return result.returncode, result.stderr, None
            with zipfile.ZipFile(pptx) as archive:
                return 0, "", archive.read("ppt/slides/slide1.xml").decode("utf-8")

    def test_reads_inline_style_and_named_colours(self):
        code, err, xml = self.convert(
            '<rect x="0" y="0" width="100" height="100" style="fill:#ff0000;stroke:navy"/>'
        )

        self.assertEqual(0, code, err)
        self.assertIn('<a:srgbClr val="FF0000"/>', xml)
        self.assertIn('<a:srgbClr val="000080"/>', xml)

    def test_group_transform_and_paint_reach_children(self):
        code, err, xml = self.convert(
            '<g transform="translate(960 540)" fill="#00ff00">'
            '<rect x="0" y="0" width="192" height="108"/></g>'
        )

        self.assertEqual(0, code, err)
        # Half of a 13.333in x 7.5in slide.
        x, y, _, _ = xfrm(xml)
        self.assertAlmostEqual(6096000, x, delta=4)
        self.assertAlmostEqual(3429000, y, delta=4)
        self.assertIn('<a:srgbClr val="00FF00"/>', xml)

    def test_stroke_width_scales_with_the_viewbox(self):
        # 1920 units across a 960pt slide: 4 units is 2pt.
        code, err, xml = self.convert(
            '<rect x="0" y="0" width="100" height="100" fill="none" stroke="#000000" stroke-width="4"/>'
        )

        self.assertEqual(0, code, err)
        self.assertIn('<a:ln w="25400">', xml)

    def test_rounded_rect_radius_and_rotation(self):
        code, err, xml = self.convert(
            '<rect x="0" y="0" width="400" height="200" rx="50" fill="#000000" '
            'transform="rotate(30 200 100)"/>'
        )

        self.assertEqual(0, code, err)
        self.assertAlmostEqual(25000, adjustment(xml), delta=2)
        self.assertIn('rot="1800000"', xml)

    def test_polygons_and_straight_paths_become_freeforms(self):
        code, err, xml = self.convert(
            '<polygon points="50,0 100,50 50,100 0,50" fill="#00ff00"/>'
            '<path d="M 0 0 h 40 v 40 h -40 z M 10 10 h 20 v 20 h -20 z" fill="#0000ff"/>',
            view_box="0 0 100 100",
        )

        self.assertEqual(0, code, err)
        self.assertEqual(2, xml.count("<a:custGeom>"))

    def test_rejects_curves_and_skewed_boxes(self):
        code, err, _ = self.convert('<path d="M 0 0 C 10 10 20 20 30 30" stroke="#ff0000"/>')
        self.assertNotEqual(0, code)
        self.assertIn("unsupported path command 'C'", err)

        code, err, _ = self.convert('<rect width="10" height="10" transform="skewX(20)"/>')
        self.assertNotEqual(0, code)
        self.assertIn("skewed or mirrored <rect>", err)

    def test_opacity_and_no_theme_shadow(self):
        code, err, xml = self.convert(
            '<circle cx="50" cy="50" r="40" fill="#ff0000" fill-opacity="0.5"/>'
        )

        self.assertEqual(0, code, err)
        self.assertIn('<a:alpha val="50000"/>', xml)
        self.assertIn("<a:effectLst/>", xml)


class AssetQaTests(unittest.TestCase):
    def test_asset_qa_scans_nested_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            nested = tmp_path / "nested"
            nested.mkdir()
            image_path = nested / "icon.png"
            image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
            for y in range(5, 15):
                for x in range(5, 15):
                    image.putpixel((x, y), (255, 0, 0, 255))
            image.save(image_path)

            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "inspect_edges.py"), str(tmp_path)],
                capture_output=True,
                text=True,
            )
            contact_path = tmp_path / "contact.png"
            contact_result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_contact_sheet.py"),
                    str(tmp_path),
                    str(contact_path),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(str(image_path), result.stdout)
            self.assertEqual(0, contact_result.returncode, contact_result.stderr)
            self.assertTrue(contact_path.exists())

    def test_asset_qa_rejects_empty_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            inspect_result = subprocess.run(
                [sys.executable, str(SCRIPTS / "inspect_edges.py"), str(tmp_path)],
                capture_output=True,
                text=True,
            )
            contact_result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_contact_sheet.py"),
                    str(tmp_path),
                    str(tmp_path / "contact.png"),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, inspect_result.returncode)
            self.assertIn("no PNG files found", inspect_result.stderr)
            self.assertNotEqual(0, contact_result.returncode)
            self.assertIn("no PNG files found", contact_result.stderr)


class SliceAssetSheetTests(unittest.TestCase):
    def test_uses_key_color_from_crop_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sheet_path = tmp_path / "sheet.png"
            spec_path = tmp_path / "crops.json"
            output_dir = tmp_path / "output"

            sheet = Image.new("RGB", (40, 40), (255, 0, 255))
            for y in range(10, 30):
                for x in range(10, 30):
                    sheet.putpixel((x, y), (255, 0, 0))
            sheet.save(sheet_path)
            spec_path.write_text(
                json.dumps(
                    {
                        "key_color": "#ff00ff",
                        "crops": [{"id": "icon", "bbox": [0, 0, 40, 40]}],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "slice_asset_sheet.py"),
                    str(sheet_path),
                    str(spec_path),
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            icon = Image.open(output_dir / "icon.png").convert("RGBA")
            self.assertEqual(0, icon.getpixel((0, 0))[3])
            self.assertEqual(255, icon.getpixel((20, 20))[3])


    def test_rim_blended_with_the_key_is_unmixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sheet_path = tmp_path / "sheet.png"
            spec_path = tmp_path / "crops.json"
            output_dir = tmp_path / "output"

            # Blue square on green, ringed by a one-pixel 50/50 blend of the two.
            sheet = Image.new("RGB", (60, 60), (0, 255, 0))
            sheet.paste((22, 80, 220), (19, 19, 41, 41))
            sheet.paste((30, 120, 230), (20, 20, 40, 40))
            for x in range(19, 41):
                for y in (19, 40):
                    sheet.putpixel((x, y), (15, 168, 110))
                    sheet.putpixel((y, x), (15, 168, 110))
            sheet.paste((30, 120, 230), (20, 20, 40, 40))
            sheet.save(sheet_path)
            spec_path.write_text(
                json.dumps({"key_color": "#00ff00", "crops": [{"id": "icon", "bbox": [0, 0, 60, 60]}]}),
                encoding="utf-8",
            )

            run = lambda *extra: subprocess.run(
                [sys.executable, str(SCRIPTS / "slice_asset_sheet.py"), str(sheet_path), str(spec_path),
                 str(output_dir), *extra],
                capture_output=True, text=True,
            )
            result = run()
            self.assertEqual(0, result.returncode, result.stderr)
            r, g, b, a = Image.open(output_dir / "icon.png").convert("RGBA").getpixel((30, 19))
            self.assertLess(abs(a - 128), 20)
            self.assertLess(g, b)  # blue again, not green
            self.assertEqual((30, 120, 230, 255), Image.open(output_dir / "icon.png").getpixel((30, 30)))

            result = run("--edge-px", "0")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual((15, 168, 110, 255), Image.open(output_dir / "icon.png").convert("RGBA").getpixel((30, 19)))


class ValidateElementAnalysisTests(unittest.TestCase):
    def test_text_only_and_geometry_only_pages_accept_empty_png_plan(self):
        for components in [{}, {"card": {"category": "simple_geometry_svg_ooxml", "asset_plan": "svg_to_ooxml", "reuse": "once"}}]:
            with self.subTest(components=components):
                result = self.run_validator({
                    "ref_width": 1448, "ref_height": 1086,
                    "components": components, "slides": [{"slide": 1, "instances": []}],
                    "png_asset_sheet_plan": {"key_color": "#00FF00", "sheets": []},
                })
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def run_validator(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            analysis_json = Path(tmp) / "element_analysis.json"
            analysis_json.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_element_analysis.py"),
                    str(analysis_json),
                ],
                capture_output=True,
                text=True,
            )

    def test_accepts_nine_normal_and_four_complex_assets_per_sheet(self):
        components = {}
        normal_ids = []
        complex_ids = []
        for index in range(10):
            component_id = f"normal_{index}"
            normal_ids.append(component_id)
            components[component_id] = {
                "category": "icon_png",
                "asset_plan": "generate_png_asset",
                "reuse": "shared",
            }
        for index in range(5):
            component_id = f"complex_{index}"
            complex_ids.append(component_id)
            components[component_id] = {
                "category": "complex_png_whole",
                "asset_plan": "generate_png_whole",
                "reuse": "shared",
            }

        result = self.run_validator(
            {
                "ref_width": 1920,
                "ref_height": 1080,
                "components": components,
                "slides": [],
                "png_asset_sheet_plan": {
                    "key_color": "#00ff00",
                    "sheets": [
                        {"id": "normal_1", "max": 9, "components": normal_ids[:9]},
                        {"id": "normal_2", "max": 9, "components": normal_ids[9:]},
                        {"id": "complex_1", "max": 4, "components": complex_ids[:4]},
                        {"id": "complex_2", "max": 4, "components": complex_ids[4:]},
                    ]
                },
            }
        )

        self.assertEqual(0, result.returncode, result.stdout)

    def test_rejects_underfilled_nonfinal_asset_sheets(self):
        components = {
            f"complex_{index}": {
                "category": "complex_png_whole",
                "asset_plan": "generate_png_whole",
                "reuse": "shared",
            }
            for index in range(5)
        }
        result = self.run_validator(
            {
                "ref_width": 1920,
                "ref_height": 1080,
                "components": components,
                "slides": [],
                "png_asset_sheet_plan": {
                    "key_color": "#ff00ff",
                    "sheets": [
                        {"id": "complex_1", "components": ["complex_0"]},
                        {"id": "complex_2", "components": ["complex_1", "complex_2", "complex_3", "complex_4"]},
                    ]
                },
            }
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must contain 4 assets except for the final remainder sheet", result.stdout)

    def two_icons(self, plan=None):
        payload = {
            "ref_width": 1920,
            "ref_height": 1080,
            "components": {
                name: {"category": "icon_png", "asset_plan": "generate_png_asset", "reuse": "shared"}
                for name in ("a", "b")
            },
            "slides": [],
        }
        if plan is not None:
            payload["png_asset_sheet_plan"] = plan
        return self.run_validator(payload)

    def test_requires_a_sheet_plan_for_png_components(self):
        result = self.two_icons()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("png_asset_sheet_plan is required for PNG components: a, b", result.stdout)

    def test_rejects_unplanned_and_duplicated_components(self):
        unplanned = self.two_icons({"key_color": "#ff00ff", "sheets": [{"id": "s1", "components": ["a"]}]})
        self.assertNotEqual(0, unplanned.returncode)
        self.assertIn("PNG components on no sheet: b", unplanned.stdout)

        duplicated = self.two_icons({
            "key_color": "#ff00ff",
            "sheets": [{"id": "s1", "components": ["a", "b", "a"]}],
        })
        self.assertNotEqual(0, duplicated.returncode)
        self.assertIn("component a is already on png_asset_sheet_plan sheet 1", duplicated.stdout)

    def test_legacy_plan_without_sheets_only_warns(self):
        result = self.two_icons({"main_icons": ["a", "b"]})

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("WARNING\tpng_asset_sheet_plan has no sheets array", result.stdout)

    def test_rejects_schema_required_fields_and_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_json = Path(tmp) / "bad_element_analysis.json"
            bad_json.write_text(
                json.dumps(
                    {
                        "ref_width": 0,
                        "ref_height": 1080,
                        "components": {
                            "c1": {
                                "category": "icon_png",
                                "asset_plan": "generate_png_asset",
                            }
                        },
                        "slides": [
                            {
                                "slide": 1,
                                "instances": [
                                    {
                                        "component": "c1",
                                        "bbox_px": [0, 0, 10, 10],
                                        "bbox_frac": [-0.5, 0, 0.1, 0.1],
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_element_analysis.py"),
                    str(bad_json),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("ref_width must be an integer >= 1", result.stdout)
            self.assertIn("component c1: missing required key: reuse", result.stdout)
            self.assertIn("slide 1 instance ?: missing required key: id", result.stdout)
            self.assertIn("bbox_frac x/y must be non-negative", result.stdout)


def load_extract_text():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as error:
        raise unittest.SkipTest(f"extract_text needs {error.name}")
    spec = importlib.util.spec_from_file_location("extract_text", SCRIPTS / "extract_text.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtractTextLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.et = load_extract_text()

    def block(self, text, bbox, size=14.0, **extra):
        return self.et.TextBlock(id=text, text=text, bbox=bbox, font_size_pt=size, **extra)

    def glyph_mask(self, spans, height=20):
        """A one-line mask with ink in each (left, right) column span."""
        import numpy as np

        mask = np.zeros((height, max(right for _, right in spans) + 5), np.uint8)
        for left, right in spans:
            mask[2:height - 2, left:right] = 1
        return mask

    def test_space_width_gaps_become_spaces(self):
        # 30px em: glyphs 26px wide with 3px tracking, and a 12px (0.4 em)
        # gap after the second glyph and after the digit.
        spans = [(0, 26), (29, 55), (67, 79), (91, 117), (120, 146)]
        chars = [(0, 27), (28, 56), (64, 82), (88, 118), (119, 147)]
        mask = self.glyph_mask(spans)

        self.assertEqual("上线 3 个月", self.et.restore_spaces("上线3个月", chars, mask, 0, 30))
        # Page offset: the OCR box starts at x=500 and so do the char columns.
        shifted = [(a + 500, b + 500) for a, b in chars]
        self.assertEqual("上线 3 个月", self.et.restore_spaces("上线3个月", shifted, mask, 500, 30))

    def test_no_space_without_char_columns_or_after_full_width_punctuation(self):
        spans = [(0, 26), (29, 55), (67, 93)]
        chars = [(0, 27), (28, 56), (64, 94)]
        mask = self.glyph_mask(spans)

        self.assertEqual("上线月", self.et.restore_spaces("上线月", None, mask, 0, 30))
        self.assertEqual("人：张", self.et.restore_spaces("人：张", chars, mask, 0, 30))
        # A spaced string keeps its one space instead of gaining another.
        self.assertEqual("AI 2.0", self.et.restore_spaces("AI 2.0", [(0, 10), (11, 22), (36, 46), (47, 52), (53, 63)],
                                                          self.glyph_mask([(0, 10), (11, 22), (36, 46), (47, 52), (53, 63)]), 0, 30))

    def test_gap_wider_than_a_space_is_not_a_space(self):
        spans = [(0, 26), (60, 86)]  # 34px = 1.13 em: a lost glyph, not a space
        self.assertEqual("张明", self.et.restore_spaces("张明", [(0, 27), (59, 87)], self.glyph_mask(spans), 0, 30))

    def test_interpunct_lookalikes_between_words(self):
        self.assertEqual("中心 · 述职", self.et.normalise_interpunct("中心 • 述职"))
        self.assertEqual("携手同行·再创佳绩", self.et.normalise_interpunct("携手同行・再创佳绩"))
        self.assertEqual("• 第一条", self.et.normalise_interpunct("• 第一条"))

    def test_merge_follows_columns_not_reading_order(self):
        et = self.et
        blocks = [
            self.block("left 1", (0.10, 0.30, 0.20, 0.03)),
            self.block("right 1", (0.60, 0.30, 0.20, 0.03)),
            self.block("left 2", (0.10, 0.35, 0.20, 0.03)),
            self.block("right 2", (0.60, 0.35, 0.20, 0.03)),
        ]

        merged = et.merge_lines(blocks)

        self.assertEqual(["left 1\nleft 2", "right 1\nright 2"], [b.text for b in merged])
        self.assertAlmostEqual(0.05, merged[0].line_pitch)

    def test_merge_keeps_different_weights_apart(self):
        merged = self.et.merge_lines([
            self.block("heading", (0.10, 0.30, 0.20, 0.03), bold=True),
            self.block("body", (0.10, 0.35, 0.20, 0.03)),
        ])

        self.assertEqual(2, len(merged))

    def test_bullet_needs_the_middle_band(self):
        np = __import__("numpy")
        glyphs = np.zeros((20, 60), np.uint8)
        glyphs[2:18, 20:30] = 1
        glyphs[2:18, 40:50] = 1

        middle = glyphs.copy()
        middle[8:12, 2:6] = 1
        baseline = glyphs.copy()
        baseline[17:20, 2:5] = 1

        self.assertEqual(20, self.et.leading_bullet(middle, 16))
        self.assertEqual(0, self.et.leading_bullet(baseline, 16))

    def weighted(self, text, em, ratio, color="#333333"):
        block = self.block(text, (0, 0, 0.1, 0.03), color=color)
        block.metrics.em_ref_px = em
        block.metrics.stroke_ratio_area = ratio
        return block

    def test_auto_threshold_eases_with_size(self):
        et = self.et
        # 0.0915 + 0.75/em: 0.1165 at a 30px em, 0.1015 at 75px.
        body = self.weighted("body", 30, 0.112)
        heading = self.weighted("heading", 75, 0.112)
        tiny = self.weighted("tiny", 10, 0.2)

        et.resolve_bold([body, heading, tiny], "auto", offset=0.0)

        self.assertEqual([False, True, False], [body.bold, heading.bold, tiny.bold])

    def test_deck_valley_moves_the_threshold(self):
        et = self.et
        # Regular body sits 0.03 under the threshold, labels 0.01 under it:
        # two clusters, both below the threshold, with a valley between.
        body = [self.weighted(f"b{i}", 30, et.bold_threshold(30) - 0.032 + i * 0.001) for i in range(8)]
        labels = [self.weighted(f"l{i}", 40, et.bold_threshold(40) - 0.012 + i * 0.001, color=f"#0000{i:02X}") for i in range(6)]
        offset = et.deck_weight_offset(body + labels)

        self.assertTrue(-0.024 < offset < -0.016, offset)
        et.resolve_bold(body + labels, "auto", offset)
        self.assertFalse(any(b.bold for b in body))
        self.assertTrue(all(b.bold for b in labels))

    def test_single_weight_deck_keeps_the_threshold(self):
        et = self.et
        blocks = [self.weighted(f"b{i}", 30, et.bold_threshold(30) - 0.03 + i * 0.0005) for i in range(20)]

        self.assertEqual(0.0, et.deck_weight_offset(blocks))

    def test_siblings_share_the_majority_weight(self):
        et = self.et
        titles = [self.weighted(t, 40, et.bold_threshold(40) + d, color="#0450DA")
                  for t, d in (("演绎推理", -0.001), ("归纳推理", 0.0005), ("规则推理", 0.005))]
        other = self.weighted("说明", 29, et.bold_threshold(29) - 0.03, color="#555555")

        et.resolve_bold(titles + [other], "auto", offset=0.0)

        self.assertEqual([True, True, True, False], [b.bold for b in titles + [other]])

    def test_ratio_mode_thresholds_area_ratio(self):
        block = self.weighted("x", 30, 0.105)

        self.et.resolve_bold([block], "ratio:0.1")

        self.assertTrue(block.bold)

    def test_frame_adds_slack_and_lifts_for_exact_spacing(self):
        et = self.et
        single = self.block("one", (0.1, 0.5, 0.2, 0.04), size=20)
        spaced = self.block("two", (0.1, 0.5, 0.2, 0.10), size=20, line_pitch=0.08)

        x, y, w, _ = et.text_frame(single, 960, 540)
        self.assertAlmostEqual(0.1, x)
        self.assertAlmostEqual(0.2 * 1.35 + 12 / 960, w)
        self.assertAlmostEqual(0.5 - 20 * 0.16 / 540, y)

        _, spaced_y, _, _ = et.text_frame(spaced, 960, 540)
        added = 0.08 * 540 - 20 * 1.2
        self.assertAlmostEqual(0.5 - (20 * 0.16 + added * 0.6) / 540, spaced_y)

    def test_bullet_text_and_line_spacing_in_record(self):
        block = self.block("a\nb", (0.2, 0.2, 0.2, 0.1), bullet=True, mark_x=0.18,
                           line_pitch=0.05)

        record = self.et.block_record(block, 1600, 900, 960)

        self.assertEqual("• a\n• b", record["text"])
        self.assertEqual(round(0.05 * 540, 2), record["line_spacing_pt"])
        self.assertAlmostEqual(0.18, record["bbox_frac"][0])
        self.assertAlmostEqual(0.2, record["ink_bbox_frac"][0])


class ExtractTextOcrTests(unittest.TestCase):
    FONT = Path("C:/Windows/Fonts/msyhbd.ttc")

    def test_reads_and_measures_rendered_text(self):
        if not any(importlib.util.find_spec(name) for name in ("rapidocr", "rapidocr_onnxruntime")):
            self.skipTest("rapidocr is not installed")
        load_extract_text()
        if not self.FONT.exists():
            self.skipTest("Microsoft YaHei Bold is not available")

        from PIL import ImageDraw, ImageFont

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            page = tmp_path / "slide_001.png"
            out = tmp_path / "texts_layout.json"
            image = Image.new("RGB", (1600, 900), (255, 255, 255))
            ImageDraw.Draw(image).text(
                (200, 300), "智慧校园核心模块", font=ImageFont.truetype(str(self.FONT), 80),
                fill=(11, 52, 143),
            )
            image.save(page)

            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "extract_text.py"), str(page), "--out", str(out), "--ocr-only"],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            layout = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(1, layout["slides"][0]["slide"])
            texts = layout["slides"][0]["texts"]
            self.assertEqual(["智慧校园核心模块"], [t["text"] for t in texts])
            text = texts[0]
            self.assertTrue(text["bold"])
            # 80px on a 1600px page is 48pt on a 960pt slide.
            self.assertAlmostEqual(48, text["font_size_pt"], delta=4)
            x, y, _, _ = text["ink_bbox_px"]
            self.assertLess(abs(x - 200), 12)
            self.assertLess(abs(y - 300), 40)
            colour = [int(text["color"][i:i + 2], 16) for i in (1, 3, 5)]
            self.assertLess(sum(abs(a - b) for a, b in zip(colour, (11, 52, 143))), 40)


class ComposeTextTests(unittest.TestCase):
    def test_line_breaks_become_paragraphs_with_spacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            spec = tmp_path / "compose.json"
            pptx = tmp_path / "out.pptx"
            spec.write_text(
                json.dumps({
                    "slides": [{
                        "texts": [{
                            "text": "第一行\n第二行",
                            "bbox_frac": [0.1, 0.1, 0.3, 0.2],
                            "font_size_pt": 14,
                            "line_spacing_pt": 24,
                        }],
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            subprocess.run(
                [sys.executable, str(SCRIPTS / "compose_component_pptx.py"), str(spec), str(pptx)],
                check=True,
                capture_output=True,
                text=True,
            )

            with zipfile.ZipFile(pptx) as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

            self.assertEqual(2, slide_xml.count("<a:p>"))
            self.assertEqual(2, slide_xml.count('<a:spcPts val="2400"/>'))
            self.assertIn("<a:t>第二行</a:t>", slide_xml)


class ComposeShapeAndImageTests(unittest.TestCase):
    def compose(self, spec, with_icon=False):
        """Compose a spec; return (slide XML, presentation XML)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if with_icon:
                # 100x100 PNG with a 50x50 drawing in the middle and 25px of
                # transparent padding all round.
                icon = Image.new("RGBA", (100, 100), (255, 0, 255, 0))
                icon.paste((0, 0, 255, 255), (25, 25, 75, 75))
                icon.save(tmp_path / "icon.png")
            spec_path = tmp_path / "compose.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            pptx = tmp_path / "out.pptx"
            subprocess.run(
                [sys.executable, str(SCRIPTS / "compose_component_pptx.py"), str(spec_path), str(pptx)],
                check=True,
                capture_output=True,
                text=True,
            )
            with zipfile.ZipFile(pptx) as archive:
                return (
                    archive.read("ppt/slides/slide1.xml").decode("utf-8"),
                    archive.read("ppt/presentation.xml").decode("utf-8"),
                )

    def image_spec(self, **image):
        return {
            "ref_width": 1920,
            "ref_height": 1080,
            "slides": [{"images": [dict({"path": "icon.png", "bbox_px": [960, 540, 192, 108]}, **image)]}],
        }

    def test_visible_fit_aligns_the_drawing_to_the_bbox(self):
        slide_xml, _ = self.compose(self.image_spec(), with_icon=True)

        # The bbox is 1219200 x 685800 EMU; the 50px drawing fits its height,
        # so one PNG pixel is 13716 EMU and the 25px padding spills outside.
        for actual, expected in zip(xfrm(slide_xml), (6019800, 3086100, 1371600, 1371600)):
            self.assertAlmostEqual(expected, actual, delta=4)

    def test_frame_fit_stretches_the_whole_png(self):
        slide_xml, _ = self.compose(self.image_spec(fit="frame"), with_icon=True)

        for actual, expected in zip(xfrm(slide_xml), (6096000, 3429000, 1219200, 685800)):
            self.assertAlmostEqual(expected, actual, delta=4)

    def test_slide_height_follows_the_source_aspect_ratio(self):
        _, presentation_xml = self.compose({"ref_width": 1600, "ref_height": 1200, "slides": [{}]})

        height = int(re.search(r'<p:sldSz cx="\d+" cy="(\d+)"', presentation_xml).group(1))
        self.assertAlmostEqual(914400 * 10, height, delta=2)

    def test_fill_transparency_and_corner_radius(self):
        slide_xml, _ = self.compose({
            "ref_width": 1920,
            "ref_height": 1080,
            "slides": [{"geometry": [{
                "id": "card",
                "kind": "round_rect",
                "bbox_px": [0, 0, 200, 100],
                "fill": "#FFFFFF",
                "fill_transparency": 20,
                "corner_radius_px": 24,
            }]}],
        })

        self.assertIn('<a:alpha val="80000"/>', slide_xml)
        self.assertAlmostEqual(24000, adjustment(slide_xml), delta=2)

    def test_shapes_drop_the_theme_shadow(self):
        slide_xml, _ = self.compose({
            "ref_width": 1920,
            "ref_height": 1080,
            "slides": [{"geometry": [
                {"id": "card", "kind": "round_rect", "bbox_px": [0, 0, 200, 100], "fill": "#FFFFFF"},
                {"id": "rule", "kind": "line", "bbox_px": [0, 200, 400, 2], "fill": "#FF7A1A"},
            ]}],
        })

        self.assertEqual(2, slide_xml.count("<a:effectLst/>"))


class FakeImageApi:
    """A local OpenAI-compatible endpoint that records requests and returns a PNG."""

    def __init__(self, missing=()):
        import base64
        import io
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        png = io.BytesIO()
        Image.new("RGB", (32, 18), (30, 79, 216)).save(png, format="PNG")
        b64 = base64.b64encode(png.getvalue()).decode()
        self.requests = []
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                api.requests.append((self.path, self.headers["Content-Type"], body, self.headers["Authorization"]))
                if self.path in missing:
                    self.send_response(404)
                    self.end_headers()
                    return
                if self.path == "/v1/chat/completions":
                    reply = {"choices": [{"message": {"content": f"![image](data:image/png;base64,{b64})"}}]}
                else:
                    reply = {"data": [{"b64_json": b64}]}
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class GenerateImageTests(unittest.TestCase):
    KEY = "sk-test-secret"

    def run_script(self, api, *args, key=KEY):
        import os

        env = {k: v for k, v in os.environ.items() if not k.startswith(("SLIDE_ALCHEMY_IMAGE_", "OPENAI_"))}
        env["SLIDE_ALCHEMY_IMAGE_BASE_URL"] = api.base_url
        if key:
            env["SLIDE_ALCHEMY_IMAGE_API_KEY"] = key
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "generate_image.py"), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prompt_without_reference_generates(self):
        api = FakeImageApi()
        self.addCleanup(api.close)
        out = self.tmp_path / "nested" / "base.png"

        result = self.run_script(api, "a clean blue background", str(out))

        self.assertEqual(0, result.returncode, result.stderr)
        path, content_type, body, auth = api.requests[0]
        self.assertEqual("/v1/images/generations", path)
        self.assertEqual(f"Bearer {self.KEY}", auth)
        self.assertEqual(
            {"model": "gpt-image-2", "prompt": "a clean blue background"},
            json.loads(body),
        )
        with Image.open(out) as image:
            self.assertEqual((32, 18), image.size)
        self.assertEqual("images", json.loads(result.stdout)["route"])

    def test_reference_image_becomes_an_edit_with_a_prompt_file(self):
        api = FakeImageApi()
        self.addCleanup(api.close)
        source = self.tmp_path / "slide_001.png"
        Image.new("RGB", (16, 9), "white").save(source)
        prompt = self.tmp_path / "prompt.txt"
        prompt.write_text("去掉所有文字和卡片", encoding="utf-8")

        result = self.run_script(api, f"@{prompt}", str(self.tmp_path / "out.png"), "--reference", str(source))

        self.assertEqual(0, result.returncode, result.stderr)
        path, content_type, body, _ = api.requests[0]
        self.assertEqual("/v1/images/edits", path)
        self.assertTrue(content_type.startswith("multipart/form-data"))
        self.assertIn("去掉所有文字和卡片".encode("utf-8"), body)
        self.assertIn(b'name="image"; filename="slide_001.png"', body)

    def test_missing_images_endpoint_falls_back_to_chat(self):
        api = FakeImageApi(missing={"/v1/images/generations"})
        self.addCleanup(api.close)

        result = self.run_script(api, "icon sheet", str(self.tmp_path / "sheet.png"))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["/v1/images/generations", "/v1/chat/completions"],
            [request[0] for request in api.requests],
        )
        self.assertEqual("chat", json.loads(result.stdout)["route"])

    def test_images_route_does_not_fall_back(self):
        api = FakeImageApi(missing={"/v1/images/generations"})
        self.addCleanup(api.close)

        result = self.run_script(api, "icon sheet", str(self.tmp_path / "sheet.png"), "--route", "images")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("HTTP 404", result.stderr)
        self.assertEqual(1, len(api.requests))

    def test_missing_key_fails_without_a_request(self):
        api = FakeImageApi()
        self.addCleanup(api.close)

        result = self.run_script(api, "anything", str(self.tmp_path / "x.png"), key=None)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("SLIDE_ALCHEMY_IMAGE_API_KEY", result.stderr)
        self.assertEqual([], api.requests)


if __name__ == "__main__":
    unittest.main()
