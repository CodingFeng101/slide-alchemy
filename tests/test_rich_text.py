import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_text as extraction
import rich_text
from compose_component_pptx import compose
from text_effects import fit_effects, infer_gradient

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


class RichTextTests(unittest.TestCase):
    def compose_xml(self, item):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = dict(bbox_frac=[0.1, 0.1, 0.8, 0.3], **item)
            (root / "spec.json").write_text(json.dumps({"slides": [{"texts": [item]}]}), encoding="utf8")
            compose(root / "spec.json", root / "out.pptx")
            with zipfile.ZipFile(root / "out.pptx") as archive:
                return ET.fromstring(archive.read("ppt/slides/slide1.xml"))

    def test_inline_runs_preserve_text_and_override_inherited_face(self):
        xml = self.compose_xml({"text": "完成率 95%\n增长", "font_family": "Default", "font_face": "Default Medium",
                                "font_size_pt": 20, "runs": [{"text": "完成率 "},
                                {"text": "95%", "font_family": "Arial", "bold": True, "color": "#FF0000"},
                                {"text": "\n增长", "italic": True}]})
        paragraphs = xml.findall(".//a:p", NS)
        paragraphs = [p for p in paragraphs if p.findall("a:r", NS)]
        self.assertEqual(2, len(paragraphs))
        first = paragraphs[0].findall("a:r", NS)
        self.assertEqual(["完成率 ", "95%"], [r.find("a:t", NS).text for r in first])
        self.assertEqual("Default Medium", first[0].find("a:rPr/a:latin", NS).get("typeface"))
        self.assertEqual("Arial", first[1].find("a:rPr/a:ea", NS).get("typeface"))
        self.assertEqual("1", first[1].find("a:rPr", NS).get("b"))
        self.assertEqual("FF0000", first[1].find("a:rPr/a:solidFill/a:srgbClr", NS).get("val"))

    def test_mismatched_runs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "concatenated runs"):
            self.compose_xml({"text": "abc", "runs": [{"text": "ab"}]})

    def test_effects_are_native_and_ordered_before_fonts(self):
        effects = {"gradient": {"angle": 90, "stops": [{"position": 0, "color": "#FF0000"},
                   {"position": 1, "color": "#FFD200"}]}, "outline": {"width_pt": 1.5, "color": "#102030"},
                   "shadow": {"color": "#000000", "opacity": 0.4, "offset_x_pt": -2, "offset_y_pt": 2, "blur_pt": 1}}
        xml = self.compose_xml({"text": "测试", "effects": effects})
        properties = xml.find(".//a:rPr", NS)
        tags = [node.tag.split("}")[-1] for node in properties]
        self.assertEqual(["ln", "gradFill", "effectLst", "latin", "ea"], tags)
        self.assertEqual("19050", properties.find("a:ln", NS).get("w"))
        self.assertEqual("5400000", properties.find("a:gradFill/a:lin", NS).get("ang"))
        shadow = properties.find("a:effectLst/a:outerShdw", NS)
        self.assertEqual("8100000", shadow.get("dir"))
        self.assertEqual("40000", shadow.find("a:srgbClr/a:alpha", NS).get("val"))
        self.assertFalse(xml.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic"))

    def test_invalid_gradient_stops_and_effects_are_rejected(self):
        for effects in [{"unknown": {}}, {"gradient": {"stops": [{"position": 1, "color": "000000"},
                                                                                {"position": 0, "color": "FFFFFF"}]}},
                        {"outline": {"color": "000000", "width_pt": -1}}]:
            with self.subTest(effects=effects), self.assertRaises(ValueError):
                self.compose_xml({"text": "a", "effects": effects})

    def mask(self, text="Campus 95%"):
        path = next((p for p in [Path("C:/Windows/Fonts/arialbd.ttf"),
                    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")] if p.exists()), None)
        if path is None:
            self.skipTest("a sample font is required")
        im = Image.new("L", (500, 100))
        ImageDraw.Draw(im).text((20, 10), text, font=ImageFont.truetype(str(path), 48), fill=255)
        return np.array(im).astype(np.float32) / 255

    def test_gradient_is_inferred_and_plain_text_stays_plain(self):
        alpha = self.mask()
        y = np.arange(100)[:, None, None] / 99
        colours = np.array([240, 30, 20]) * (1 - y) + np.array([30, 70, 220]) * y
        rgb = 255 * (1 - alpha[..., None]) + colours * alpha[..., None]
        gradient = infer_gradient(rgb, alpha)
        self.assertIsNotNone(gradient)
        self.assertAlmostEqual(90, gradient["angle"], delta=1)
        plain = 255 * (1 - alpha[..., None]) + np.array([30, 40, 60]) * alpha[..., None]
        result = fit_effects(plain, alpha, [255, 255, 255], [30, 40, 60], 0.75)
        self.assertEqual({}, result["effects"])
        self.assertLess(result["pixel_rmse"], 0.1)

    def test_coloured_outline_is_fitted(self):
        alpha = self.mask()
        expanded = cv2.dilate(alpha, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        rgb = 255 * (1 - expanded[..., None]) + np.array([20, 50, 200]) * expanded[..., None]
        rgb = rgb * (1 - alpha[..., None]) + np.array([230, 30, 20]) * alpha[..., None]
        result = fit_effects(rgb, alpha, [255, 255, 255], [230, 30, 20], 0.75)
        self.assertIn("outline", result["effects"])
        self.assertAlmostEqual(1.5, result["effects"]["outline"]["width_pt"], delta=0.75)
        self.assertLess(result["pixel_rmse"], result["baseline_rmse"] * 0.5)

    def test_shifted_shadow_is_fitted(self):
        alpha = self.mask()
        blurred = cv2.GaussianBlur(alpha, (0, 0), 1)
        shifted = cv2.warpAffine(blurred, np.float32([[1, 0, 4], [0, 1, 2]]), (500, 100))
        rgb = np.repeat((255 * (1 - 0.5 * shifted))[..., None], 3, axis=2)
        rgb = rgb * (1 - alpha[..., None]) + np.array([20, 40, 80]) * alpha[..., None]
        result = fit_effects(rgb, alpha, [255, 255, 255], [20, 40, 80], 0.75)
        self.assertIn("shadow", result["effects"])
        shadow = result["effects"]["shadow"]
        self.assertAlmostEqual(3, shadow["offset_x_pt"], delta=1.5)
        self.assertLess(result["pixel_rmse"], result["baseline_rmse"] * 0.7)

    def test_style_boundaries_detect_colour_without_splitting_gradients(self):
        samples = [{"index": i, "color": np.array([20, 20, 20] if i < 3 else [220, 20, 20]),
                    "stroke": 3, "script": "latin"} for i in range(6)]
        self.assertEqual([3], rich_text.style_boundaries(samples, None))
        self.assertEqual([], rich_text.style_boundaries(samples, {"angle": 0}))
        for index, sample in enumerate(samples):
            sample["color"] = np.zeros(3)
            sample["stroke"] = 3.8 if index < 3 else 5.5
        self.assertEqual([3], rich_text.style_boundaries(samples, None))

    def test_font_boundary_preserves_word_offsets(self):
        class Matcher:
            def rank_fonts(self, mask, text, top_k):
                return [({"family": "A"}, 20, 0.9), ({"family": "B"}, 20, 0.89)], 2

        image = np.full((24, 160, 3), 255, np.uint8)
        for index in range(8):
            image[4:20, index * 20 + 3:index * 20 + 17] = 0
        text = "ABCD EFGH"
        box = extraction.OcrBox(text, 1, 0, 0, 160, 24)
        samples = [{"index": i if i < 4 else i + 1, "x0": i * 20, "x1": (i + 1) * 20,
                    "color": np.zeros(3)} for i in range(8)]
        result = rich_text.font_boundaries(image, box, text, samples, np.full(3, 255), Matcher())
        self.assertEqual([5], result)

    def test_aa_fill_does_not_turn_plain_edges_into_shadow(self):
        alpha = self.mask()
        rgb = 255 * (1 - alpha[..., None]) + np.array([30, 40, 60]) * alpha[..., None]
        measured = rich_text.fill_alpha(rgb, np.full(3, 255), np.array([30, 40, 60]))
        result = fit_effects(rgb, measured, [255, 255, 255], [30, 40, 60], 0.75)
        self.assertNotIn("shadow", result["effects"])

    def test_expected_copy_can_correct_only_whitespace(self):
        block = extraction.TextBlock("a", "OUTL INE", (0, 0, 1, 1), 14)
        extraction.snap_to_expected([block], ["OUTLINE"])
        self.assertEqual("OUTLINE", block.text)

    def test_recognized_initial_o_is_not_converted_to_a_bullet(self):
        alpha = self.mask("OUTLINE")
        image = np.repeat((255 * (1 - alpha))[..., None], 3, axis=2).astype(np.uint8)
        box = extraction.OcrBox("OUTLINE", 1, 20, 0, 400, 100,
                                [(20 + i * 35, 55 + i * 35) for i in range(7)])
        block = extraction.TextBlock("a", "OUTLINE", (0.04, 0, 0.8, 1), 36,
                                     bullet=True, source_box=box)
        rich_text.analyse_line(image, block, 0.75)
        self.assertFalse(block.bullet)
        record = extraction.block_record(block, 500, 100, 375)
        self.assertEqual("OUTLINE", record["text"])
        self.assertEqual(record["text"], "".join(run["text"] for run in record["runs"]))

    def test_punctuation_inherits_the_adjacent_writing_system(self):
        image = np.full((24, 100, 3), 255, np.uint8)
        for index in range(5):
            image[4:20, index * 20 + 3:index * 20 + 17] = 0
        box = extraction.OcrBox("测试，文本", 1, 0, 0, 100, 24,
                                [(i * 20, (i + 1) * 20) for i in range(5)])
        samples = rich_text.character_samples(image, box, box.text, np.full(3, 255))
        self.assertEqual(["cjk"] * 5, [sample["script"] for sample in samples])

    def test_one_pixel_strokes_have_a_finite_core_colour(self):
        image = np.full((5, 5, 3), 255, np.uint8)
        image[2, 2] = [0, 0, 180]
        box = extraction.OcrBox(".", 1, 0, 0, 5, 5, [(0, 5)])
        samples = rich_text.character_samples(image, box, box.text, np.full(3, 255))
        self.assertTrue(np.isfinite(samples[0]["color"]).all())
        self.assertEqual([180, 0, 0], samples[0]["color"].tolist())

    def test_merged_rich_lines_preserve_spans_and_bullet_prefixes(self):
        blocks = []
        for index, text in enumerate(["First", "Second"]):
            block = extraction.TextBlock(str(index), text, (0.1, 0.1 + index * 0.15, 0.3, 0.1), 14, bullet=True)
            block.runs = [{"text": "• " + text, "color": "#FF0000"}]
            block.style_report = {"spans": 1, "needs_review": index == 1}
            blocks.append(block)
        merged = extraction.merge_lines(blocks)
        self.assertEqual(1, len(merged))
        record = extraction.block_record(merged[0], 1600, 900, 960)
        self.assertEqual(record["text"], "".join(run["text"] for run in record["runs"]))
        self.assertEqual("• First\n• Second", record["text"])
        self.assertTrue(record["style_report"]["needs_review"])


if __name__ == "__main__":
    unittest.main()
