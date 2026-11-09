import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_text as extraction
import match_fonts as fonts
from compose_component_pptx import compose


class FontMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidates = [Path("C:/Windows/Fonts/arial.ttf"),
                      Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        cls.font_path = next((p for p in candidates if p.exists()), None)

    def index(self):
        if self.font_path is None:
            self.skipTest("a test font is required")
        return next(f for f in fonts.index_fonts([self.font_path])["fonts"]
                    if f["path"] == str(self.font_path.resolve()))

    def test_normalization_preserves_aspect_ratio_and_empty_ink_is_rejected(self):
        mask = np.full((20, 100), 255, np.uint8)
        normalized = fonts.model_input(mask)
        self.assertEqual((1, 48, 256), normalized.shape)
        ink = fonts.trim(normalized[0])
        self.assertAlmostEqual(5, ink.shape[1] / ink.shape[0], delta=0.05)
        with self.assertRaisesRegex(ValueError, "visible ink"):
            fonts.model_input(np.zeros((10, 10), np.uint8))

    def test_character_coverage_excludes_missing_glyphs(self):
        font = {"characters": "Campus2026"}
        self.assertTrue(fonts.supports(font, "Campus 2026"))
        self.assertFalse(fonts.supports(font, "Campus校园"))

    def test_shape_comparison_retains_width_difference(self):
        mask = np.zeros((20, 60), np.uint8)
        mask[2:18, 5:9] = 255
        mask[2:18, 40:44] = 255
        self.assertEqual(0, fonts.shape_error(mask, mask))
        import cv2
        stretched = cv2.resize(mask, (90, 20))
        self.assertGreater(fonts.shape_error(mask, stretched), 0.1)

    def test_crop_uses_colour_aware_extraction_and_clips_to_image(self):
        image = np.full((40, 100, 3), 255, np.uint8)
        image[10:30, 15:20] = 0
        mask = fonts.crop_mask(image, [-2, -3, 105, 45])
        self.assertEqual((20, 5), mask.shape)
        self.assertTrue((mask == 255).all())
        with self.assertRaisesRegex(ValueError, "outside"):
            fonts.crop_mask(image, [200, 200, 20, 20])

    def test_crop_recovers_light_edges_of_gradient_text(self):
        image = np.full((40, 100, 3), 255, np.uint8)
        image[10:20, 15:20] = [0, 0, 100]
        image[20:30, 15:20] = [0, 0, 200]
        image[10:30, 20:25] = [130, 130, 255]
        mask = fonts.crop_mask(image, [10, 5, 30, 30])
        self.assertEqual((20, 10), mask.shape)
        self.assertTrue((mask == 255).all())
        image[10:30, 15:20] = [0, 0, 100]
        image[10:30, 20:25] = 255
        image[10:30, 20:21] = [130, 130, 255]
        self.assertEqual((20, 5), fonts.crop_mask(image, [10, 5, 30, 30]).shape)

    def test_cjk_glyph_comparison_tolerates_tracking(self):
        first = np.zeros((24, 22), np.uint8)
        first[2:22, 2:6] = 255
        first[2:6, 2:20] = 255
        second = np.fliplr(first)
        source = np.concatenate([first, np.zeros((24, 12), np.uint8), second], axis=1)
        candidate = np.concatenate([first, np.zeros((24, 4), np.uint8), second], axis=1)
        glyphs = fonts.glyph_masks(source, "校园")
        self.assertEqual(2, len(glyphs))
        self.assertLess(fonts.text_shape_error(source, candidate, glyphs, "校园"),
                        fonts.shape_error(source, candidate))

    def test_synthetic_bold_can_be_matched_for_a_family_without_bold_face(self):
        font = self.index()
        matcher = fonts.FontMatcher.__new__(fonts.FontMatcher)
        matcher.fonts = [dict(font, bold=False, weight=400)]
        matcher.trained_faces = set()
        matcher.encode = lambda masks: np.ones((len(masks), 64), np.float32) / 8
        mask = fonts.render_text(dict(font, synthetic_bold=True), "Campus", 48)
        best = matcher.match(mask, "Campus")["candidates"][0]
        self.assertTrue(best["bold"])
        self.assertTrue(best["synthetic_bold"])
        self.assertEqual(0, best["shape_error"])

    def test_shortlist_is_refined_and_records_unseen_fonts(self):
        font = self.index()
        matcher = fonts.FontMatcher.__new__(fonts.FontMatcher)
        matcher.fonts = [font]
        matcher.trained_faces = set()
        matcher.encode = lambda masks: np.ones((len(masks), 64), np.float32) / 8
        result = matcher.match(fonts.render_text(font, "Campus", 36), "Campus")
        self.assertEqual("ranked", result["status"])
        self.assertEqual(1, len(result["candidates"]))
        self.assertEqual(0, result["candidates"][0]["shape_error"])
        self.assertFalse(result["candidates"][0]["seen_in_training"])
        self.assertIsNone(result["margin"])
        matcher.fonts = []
        self.assertEqual("no_supported_font", matcher.match(np.ones((5, 5)), "字")["status"])

    def test_changed_font_file_rejects_stale_index(self):
        if importlib.util.find_spec("onnxruntime") is None:
            self.skipTest("onnxruntime is required")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "font.ttf").write_bytes(b"changed")
            (path / "index.json").write_text(json.dumps({"version": 1, "fonts": [
                {"path": "font.ttf", "index": 0, "sha256": "old"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "rebuild the index"):
                fonts.FontMatcher(path / "index.json", path / "missing.onnx")

    def test_only_top_ten_model_candidates_are_refined(self):
        face = self.index()
        matcher = fonts.FontMatcher.__new__(fonts.FontMatcher)
        matcher.fonts = [dict(face, family=f"Face {i}") for i in range(12)]
        matcher.trained_faces = set()
        features = np.zeros((13, 64), np.float32)
        features[0, 0] = 1
        features[1:, 0] = np.linspace(0, 1, 12)
        matcher.encode = lambda masks: features
        result = matcher.match(fonts.render_text(face, "Campus", 36), "Campus")
        self.assertEqual(12, result["eligible_fonts"])
        self.assertEqual(10, len(result["candidates"]))
        families = {c["family"] for c in result["candidates"]}
        self.assertNotIn("Face 0", families)
        self.assertNotIn("Face 1", families)

    def test_extraction_matches_each_line_before_merging(self):
        class Matcher:
            def match(self, mask, text):
                return {"status": "ranked", "candidates": [
                    {"family": "Test Font", "face_name": "Test Font Medium",
                     "bold": True, "italic": False, "size_px": 24}]}

        blocks = [extraction.TextBlock("t1", "Campus", (0.1, 0.1, 0.3, 0.1), 14),
                  extraction.TextBlock("t2", "Project", (0.1, 0.25, 0.3, 0.1), 14)]
        with patch.object(extraction, "read_image", return_value=np.zeros((200, 400, 3))), \
                patch.object(extraction, "extract_text", return_value=blocks), \
                patch.object(fonts, "crop_mask", return_value=np.ones((20, 120), np.uint8) * 255):
            layout = extraction.build_layout(["slide_001.png"], bold_mode="off", font_matcher=Matcher())
        records = layout["slides"][0]["texts"]
        self.assertEqual(1, len(records))
        self.assertEqual("Test Font", records[0]["font_family"])
        self.assertEqual("Test Font Medium", records[0]["font_face"])
        self.assertAlmostEqual(57.6, records[0]["font_size_pt"], places=2)
        self.assertTrue(records[0]["bold"])
        self.assertEqual(["t1", "t2"], [m["line_id"] for m in records[0]["font_matches"]])

    def test_different_font_families_are_not_merged(self):
        first = extraction.TextBlock("a", "a", (0.1, 0.1, 0.3, 0.1), 14, font_family="A")
        second = extraction.TextBlock("b", "b", (0.1, 0.25, 0.3, 0.1), 14, font_family="B")
        self.assertEqual(2, len(extraction.merge_lines([first, second])))

    def test_shared_style_uses_common_near_best_candidate(self):
        def candidate(family, error):
            return {"family": family, "bold": False, "italic": False, "shape_error": error}
        blocks = []
        for name, ranking in [("a", [candidate("A", 0.02), candidate("B", 0.03)]),
                              ("b", [candidate("B", 0.01), candidate("A", 0.04)])]:
            block = extraction.TextBlock(name, name, (0, 0, 0.1, 0.1), 14)
            block.metrics.em_ref_px = 32
            block.font_matches = [{"candidates": ranking}]
            blocks.append(block)
        extraction.harmonise_font_matches(blocks)
        self.assertEqual(["B", "B"], [b.font_matches[0]["selected_candidate"]["family"] for b in blocks])
        for block in blocks:
            block.font_matches[0].pop("selected_candidate", None)
        blocks[1].font_matches[0]["candidates"][1]["shape_error"] = 0.2
        blocks[0].font_matches[0]["candidates"][1]["shape_error"] = 0.2
        extraction.harmonise_font_matches(blocks)
        self.assertTrue(all("selected_candidate" not in b.font_matches[0] for b in blocks))
        blocks[1].color = "#FFFFFF"
        for block in blocks:
            block.font_matches[0].pop("selected_candidate", None)
        extraction.harmonise_font_matches(blocks)
        self.assertTrue(all("selected_candidate" not in b.font_matches[0] for b in blocks))

    def test_composer_writes_east_asian_and_latin_font(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {"slides": [{"slide": 1, "texts": [
                {"text": "校园 Campus", "bbox_frac": [0.1, 0.1, 0.5, 0.1],
                 "font_family": "Test Font", "font_face": "Test Font Medium"}]}]}
            (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            compose(root / "spec.json", root / "out.pptx")
            with zipfile.ZipFile(root / "out.pptx") as archive:
                xml = archive.read("ppt/slides/slide1.xml").decode()
            self.assertIn('<a:latin typeface="Test Font Medium"', xml)
            self.assertIn('<a:ea typeface="Test Font Medium"', xml)


if __name__ == "__main__":
    unittest.main()
