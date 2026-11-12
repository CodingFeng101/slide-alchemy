import json
import sys
import tempfile
import unittest
import zipfile
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

    def test_plain_command_matches_locally_without_the_font_server(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "layout.json"
            layout = {"slides": [{"texts": [self.item()]}]}
            with patch.object(sys, "argv", ["extract_text.py", "slide.png", "--out", str(output)]), \
                    patch("font_store.FontStore") as store, patch("match_fonts.FontMatcher") as matcher, \
                    patch("font_store.RemoteFontMatcher") as remote, patch.object(extract_text, "build_layout", return_value=layout) as build:
                store.return_value.install_core.return_value = ("index.json", "model.onnx")
                extract_text.main()
                remote.assert_not_called()
                self.assertIs(matcher.return_value, build.call_args.kwargs["font_matcher"])
                self.assertTrue(build.call_args.kwargs["rich_text"])
            self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["font_matching_required"])

    def test_remote_match_flag_enables_server_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "layout.json"
            layout = {"slides": [{"texts": [self.item()]}]}
            with patch.object(sys, "argv", ["extract_text.py", "slide.png", "--out", str(output), "--remote-match"]), \
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

    def test_matched_text_effects_compose_as_characters_without_png_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = self.item()
            item["effects"] = {
                "gradient": {"angle": 90, "stops": [{"position": 0, "color": "#003399"}, {"position": 1, "color": "#00BBFF"}]},
                "outline": {"color": "#FFFFFF", "width_pt": 1},
                "shadow": {"color": "#000000", "offset_x_pt": 2, "offset_y_pt": 2},
            }
            spec = {"font_matching_required": True, "slides": [{"texts": [item]}]}
            (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            compose(root / "spec.json", root / "out.pptx")
            with zipfile.ZipFile(root / "out.pptx") as archive:
                xml = archive.read("ppt/slides/slide1.xml").decode()
            self.assertIn("<a:t>Campus</a:t>", xml)
            self.assertIn("<a:gradFill", xml)
            self.assertIn("<a:outerShdw", xml)
            self.assertNotIn("<p:pic>", xml)

    def test_uninstalled_matched_font_stops_composition_unless_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = {"font_matching_required": True, "slides": [{"texts": [self.item()]}]}
            (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            with patch("match_fonts.installed_font_names", return_value={"simsun"}):
                with self.assertRaisesRegex(ValueError, "not installed.*Arial.*--install-fonts"):
                    compose(root / "spec.json", root / "out.pptx")
                self.assertFalse((root / "out.pptx").exists())
                with patch("sys.stderr"):
                    compose(root / "spec.json", root / "out.pptx", allow_missing_fonts=True)
            self.assertTrue((root / "out.pptx").exists())

    def test_installed_font_check_reads_each_run_and_ignores_case(self):
        from compose_component_pptx import missing_fonts
        item = {"text": "A B", "font_family": "Arial",
                "runs": [{"text": "A", "font_face": "Arial Bold"}, {"text": " "}, {"text": "B", "font_family": "Roboto"}]}
        with patch("match_fonts.installed_font_names", return_value={"arial bold"}):
            self.assertEqual(["Roboto"], missing_fonts({"slides": [{"texts": [item]}]}))

    def test_chinese_text_excludes_fonts_built_for_other_regions(self):
        simplified, traditional, japanese = 1 << 18, 1 << 20, 1 << 17
        font = lambda pages: {"characters": "以赛促学體a", "codepages": pages}
        self.assertTrue(match_fonts.supports(font(simplified), "以赛促学"))
        self.assertFalse(match_fonts.supports(font(japanese), "以赛促学"))
        self.assertFalse(match_fonts.supports(font(traditional), "以赛促学"))
        # Characters outside GB2312 mark traditional text, which either region serves.
        self.assertTrue(match_fonts.supports(font(traditional), "體"))
        self.assertTrue(match_fonts.supports(font(japanese), "a"))
        # Indexes written before the field existed stay usable.
        self.assertTrue(match_fonts.supports({"characters": "以赛促学"}, "以赛促学"))

    def test_extraction_reports_progress_for_every_line(self):
        block = extract_text.TextBlock(id="s1_t1", text="标题\n第二行", bbox=(0, 0, 1, 1), font_size_pt=12)
        with patch("sys.stderr") as stream:
            extract_text.progress("run/slide_001.png", 2, 5, block)
        self.assertIn("slide_001.png [2/5] 标题 第二行", "".join(call.args[0] for call in stream.write.call_args_list))

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
