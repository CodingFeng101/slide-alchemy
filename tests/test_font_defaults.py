import json
import sys
import tempfile
import unittest
import numpy as np
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_text
from compose_component_pptx import compose
from match_fonts import DEFAULT_FONT_SERVER, validate_font_matches
import match_fonts


class FontDefaultTests(unittest.TestCase):
    def item(self):
        candidate = {"family": "Arial", "face_name": "Arial", "bold": False, "italic": False}
        return {"text": "Campus", "font_family": "Arial", "font_face": "Arial",
                "bbox_frac": [0.1, 0.1, 0.7, 0.2], "ink_bbox_px": [10, 10, 100, 30],
                "font_matches": [{"candidates": [candidate]}]}

    def test_plain_command_enables_model_remote_and_rich_text(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "layout.json"
            layout = {"slides": [{"texts": [self.item()]}]}
            with patch.object(sys, "argv", ["extract_text.py", "slide.png", "--out", str(output)]), \
                    patch("font_store.FontStore") as store, patch("match_fonts.FontMatcher") as matcher, \
                    patch("font_store.RemoteFontMatcher") as remote, patch.object(extract_text, "build_layout", return_value=layout) as build:
                store.return_value.install_core.return_value = ("index.json", "model.onnx")
                extract_text.main()
                store.assert_called_once_with(DEFAULT_FONT_SERVER, None)
                store.return_value.install_core.assert_called_once_with(include_system=True)
                matcher.assert_called_once_with("index.json", "model.onnx")
                self.assertIs(remote.return_value, build.call_args.kwargs["font_matcher"])
                self.assertTrue(build.call_args.kwargs["rich_text"])
            self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["font_matching_required"])

    def test_explicit_ocr_only_preserves_legacy_measurement_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "layout.json"
            with patch.object(sys, "argv", ["extract_text.py", "slide.png", "--out", str(output), "--ocr-only"]), \
                    patch("font_store.FontStore") as store, patch.object(extract_text, "build_layout", return_value={"slides": []}) as build:
                extract_text.main()
                store.assert_not_called()
                self.assertIsNone(build.call_args.kwargs["font_matcher"])
                self.assertFalse(build.call_args.kwargs["rich_text"])

    def test_setup_failure_stops_before_ocr(self):
        with patch.object(sys, "argv", ["extract_text.py", "slide.png"]), \
                patch("font_store.FontStore", side_effect=OSError("offline")), \
                patch.object(extract_text, "build_layout") as build, patch("sys.stderr"):
            with self.assertRaises(SystemExit) as error:
                extract_text.main()
            self.assertEqual(2, error.exception.code)
            build.assert_not_called()

    def test_missing_results_stop_before_overwriting_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "layout.json"
            output.write_text("previous", encoding="utf-8")
            item = self.item()
            item.pop("font_matches")
            with patch.object(sys, "argv", ["extract_text.py", "slide.png", "--out", str(output)]), \
                    patch("font_store.FontStore") as store, patch("match_fonts.FontMatcher"), \
                    patch.object(extract_text, "build_layout", return_value={"slides": [{"texts": [item]}]}), patch("sys.stderr"):
                store.return_value.install_core.return_value = ("index.json", "model.onnx")
                with self.assertRaises(SystemExit):
                    extract_text.main()
            self.assertEqual("previous", output.read_text(encoding="utf-8"))

    def test_composition_rejects_missing_results_and_changed_font_style(self):
        missing = self.item()
        missing.pop("font_matches")
        changed = dict(self.item(), font_face="SimSun")
        bold = dict(self.item(), bold=True)
        unsupported = self.item()
        unsupported["font_matches"] = [{"status": "no_supported_font", "candidates": []}]
        for item in [missing, changed, bold, unsupported]:
            with self.subTest(item=item), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                spec = root / "spec.json"
                spec.write_text(json.dumps({"slides": [{"texts": [item]}]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    compose(spec, root / "out.pptx")
                self.assertFalse((root / "out.pptx").exists())

    def test_required_spec_catches_stripped_ocr_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"text": "Campus", "font_family": "Arial"}
            spec = {"font_matching_required": True, "slides": [{"texts": [item]}]}
            (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires font matching"):
                compose(root / "spec.json", root / "out.pptx")

    def test_every_visible_run_needs_its_own_match(self):
        item = self.item()
        item["text"] = "Campus 95%"
        item["runs"] = [{"text": "Campus ", "font_face": "Arial"}, {"text": "95%", "font_face": "Arial"}]
        with self.assertRaisesRegex(ValueError, "every text run"):
            validate_font_matches(item)

    def test_complete_matching_record_composes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = {"font_matching_required": True, "slides": [{"texts": [self.item()]}]}
            (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            compose(root / "spec.json", root / "out.pptx")
            self.assertTrue((root / "out.pptx").exists())

    def test_unrenderable_system_face_is_excluded_from_model_ranking(self):
        matcher = match_fonts.FontMatcher.__new__(match_fonts.FontMatcher)
        matcher.fonts = [{"family": "Broken", "characters": "Campus"}, {"family": "Good", "characters": "Campus"}]
        matcher.encode = lambda masks: np.array([[1.0, 0.0], [1.0, 0.0]])
        mask = np.full((10, 30), 255, np.uint8)

        def render(font, text, size):
            if font["family"] == "Broken":
                raise OSError("invalid reference")
            return mask

        with patch("match_fonts.render_text", side_effect=render), self.assertWarnsRegex(RuntimeWarning, "Broken"):
            ranking, eligible = matcher.rank_fonts(mask, "Campus")
        self.assertEqual(2, eligible)
        self.assertEqual("Good", ranking[0][0]["family"])


if __name__ == "__main__":
    unittest.main()
