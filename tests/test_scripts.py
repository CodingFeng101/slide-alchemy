import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


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


class ValidateElementAnalysisTests(unittest.TestCase):
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
