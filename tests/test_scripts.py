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


class ValidateElementAnalysisTests(unittest.TestCase):
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

    def test_auto_bold_uses_fringe_corrected_ratio(self):
        et = self.et
        heading = self.block("heading", (0, 0, 0.1, 0.05), size=22)
        heading.metrics.stroke_ratio_net = 0.076
        body = self.block("body", (0, 0.1, 0.1, 0.03), size=11)
        body.metrics.stroke_ratio_net = 0.046
        latin = self.block("Data", (0, 0.2, 0.1, 0.03), size=20, script="latin")
        latin.metrics.stroke_ratio_net = 0.08

        et.resolve_bold([heading, body, latin], "auto")

        self.assertEqual([True, False, False], [heading.bold, body.bold, latin.bold])

    def test_ratio_mode_thresholds_raw_ratio(self):
        block = self.block("x", (0, 0, 0.1, 0.03))
        block.metrics.stroke_ratio = 0.15

        self.et.resolve_bold([block], "ratio:0.145")

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
                [sys.executable, str(SCRIPTS / "extract_text.py"), str(page), "--out", str(out)],
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


if __name__ == "__main__":
    unittest.main()
