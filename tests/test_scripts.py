import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "slide-alchemy" / "scripts"


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
  <path d="M 0 0 L 100 100" stroke="#ff0000" fill="none"/>
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
            self.assertIn("unsupported SVG element: path", result.stderr)
            self.assertFalse(pptx.exists())


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


if __name__ == "__main__":
    unittest.main()
