import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "slide-alchemy" / "scripts"


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


class ScriptGuardTests(unittest.TestCase):
    def test_slice_asset_sheet_rejects_path_traversal_asset_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            Image.new("RGB", (40, 40), "#00ff00").save(tmp / "sheet.png")
            (tmp / "crops.json").write_text(
                json.dumps([{"id": "../escaped", "bbox": [10, 10, 20, 20]}]),
                encoding="utf-8",
            )

            result = run_script("slice_asset_sheet.py", tmp / "sheet.png", tmp / "crops.json", tmp / "out")

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((tmp / "escaped.png").exists())
            self.assertIn("invalid asset id", result.stderr + result.stdout)

    def test_slice_asset_sheet_rejects_empty_transparent_crop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            Image.new("RGB", (40, 40), "#00ff00").save(tmp / "sheet.png")
            (tmp / "crops.json").write_text(
                json.dumps([{"id": "empty", "bbox": [10, 10, 20, 20]}]),
                encoding="utf-8",
            )

            result = run_script("slice_asset_sheet.py", tmp / "sheet.png", tmp / "crops.json", tmp / "out")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("empty transparent crop", result.stderr + result.stdout)

    def test_inspect_edges_fails_on_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script("inspect_edges.py", tmp)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no PNG files found", result.stderr + result.stdout)

    def test_inspect_edges_fails_on_empty_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(tmp / "empty.png")

            result = run_script("inspect_edges.py", tmp)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("EMPTY", result.stdout)

    def test_build_contact_sheet_fails_on_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            result = run_script("build_contact_sheet.py", tmp, tmp / "contact.png")

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((tmp / "contact.png").exists())
            self.assertIn("no PNG files found", result.stderr + result.stdout)

    def test_compare_preview_fails_on_size_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            Image.new("RGB", (100, 80), "white").save(tmp / "source.png")
            Image.new("RGB", (80, 100), "white").save(tmp / "preview.png")

            result = run_script("compare_preview.py", tmp / "source.png", tmp / "preview.png", tmp / "compare")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("differs from source size", result.stderr + result.stdout)

    def test_validate_element_analysis_reports_bad_slides_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = tmp / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "ref_width": 1920,
                        "ref_height": 1080,
                        "components": {},
                        "slides": "not-an-array",
                    }
                ),
                encoding="utf-8",
            )

            result = run_script("validate_element_analysis.py", path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("slides must be an array", result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
