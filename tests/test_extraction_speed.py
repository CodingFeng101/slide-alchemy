"""Reuse between runs, resuming after a failed page, and faster matching."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_text as extraction
import match_fonts
import rich_text


def reference_shape_error(source, candidate):
    """The comparison as first written: shift whole arrays nine times."""
    source = match_fonts.trim((source >= 96).astype(np.uint8))
    candidate = match_fonts.trim((candidate >= 96).astype(np.uint8))
    h = max(source.shape[0], candidate.shape[0]) + 8
    w = max(source.shape[1], candidate.shape[1]) + 8
    a = np.zeros((h, w), np.uint8)
    b = np.zeros_like(a)
    a[4:4 + source.shape[0], 4:4 + source.shape[1]] = source
    b[4:4 + candidate.shape[0], 4:4 + candidate.shape[1]] = candidate
    distance_a = cv2.distanceTransform(1 - a, cv2.DIST_L2, 3)
    distance_b = cv2.distanceTransform(1 - b, cv2.DIST_L2, 3)
    best = float("inf")
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.roll(b, (dy, dx), axis=(0, 1))
            distance = (distance_a[shifted > 0].mean()
                        + np.roll(distance_b, (dy, dx), axis=(0, 1))[a > 0].mean()) / 2
            overlap = np.abs(a.astype(np.float32) - shifted).sum() / (a.sum() + b.sum())
            best = min(best, float(distance) / max(1, source.shape[0]) + 0.25 * overlap)
    dimensions = (abs(source.shape[1] - candidate.shape[1]) / source.shape[1]
                  + abs(source.shape[0] - candidate.shape[0]) / source.shape[0])
    return best + 0.25 * dimensions


class MatchingSpeedTests(unittest.TestCase):
    def test_shape_error_keeps_its_values(self):
        random = np.random.default_rng(7)
        for _ in range(20):
            height, width = random.integers(8, 60, 2)
            source = (random.random((height, width)) > 0.6).astype(np.uint8) * 255
            other = (random.random((height + random.integers(-3, 4), width + random.integers(-3, 4))) > 0.6)
            candidate = other.astype(np.uint8) * 255
            self.assertAlmostEqual(reference_shape_error(source, candidate),
                                   match_fonts.shape_error(source, candidate), places=6)

    def test_unchanged_font_files_are_not_read_again(self):
        fonts = [path for directory in match_fonts.font_directories() if Path(directory).exists()
                 for path in Path(directory).glob("*.ttf")][:2]
        if not fonts:
            self.skipTest("no system fonts to index")
        first = match_fonts.index_fonts(fonts)
        self.assertEqual({str(path.resolve()) for path in fonts}, set(first["scanned"]))
        with patch("fontTools.ttLib.TTFont", side_effect=AssertionError("font file read again")):
            second = match_fonts.index_fonts(fonts, first)
        self.assertEqual(first["fonts"], second["fonts"])
        # A file whose size or time changed is read again.
        stale = dict(first, scanned={path: [0, 0] for path in first["scanned"]})
        self.assertEqual(first["fonts"], match_fonts.index_fonts(fonts, stale)["fonts"])

    def test_shortlist_passes_to_like_styled_text_only_while_it_fits(self):
        calls = []

        class Matcher:
            by_face = {}

            def __init__(self, pooled_error):
                self.pooled_error = pooled_error

            def match(self, mask, text, top_k=10, pool=None):
                calls.append(pool)
                error = 0.03 if pool is None else self.pooled_error
                return {"candidates": [{"path": "a.ttf", "index": 0, "shape_error": error}]}

        memory = {}
        rich_text.match_remembering(Matcher(0.03), memory, "body", None, "first")
        self.assertEqual([None], calls)
        result = rich_text.match_remembering(Matcher(0.035), memory, "body", None, "second")
        self.assertEqual([("a.ttf", 0)], calls[-1])
        self.assertEqual("style", result["shortlist"])
        # A looser fit than the text the shortlist came from means another font.
        calls.clear()
        result = rich_text.match_remembering(Matcher(0.07), memory, "body", None, "third")
        self.assertEqual([[("a.ttf", 0)], None], calls)
        self.assertNotIn("shortlist", result)
        # Another style starts from the whole library.
        calls.clear()
        rich_text.match_remembering(Matcher(0.03), memory, "title", None, "fourth")
        self.assertEqual([None], calls)


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.pages = []
        for number in (1, 2):
            path = root / f"slide_00{number}.png"
            cv2.imwrite(str(path), np.full((90, 160, 3), 255 - number, np.uint8))
            self.pages.append(str(path))
        self.cache = extraction.PageCache(root / ".text_cache")
        self.read = []

    def lines(self, path, slide_id, *rest):
        self.read.append(Path(path).name)
        return [extraction.TextBlock(id=f"{slide_id}_t1", text="标题", bbox=(0.1, 0.1, 0.3, 0.1), font_size_pt=20)]

    def build(self, **options):
        with patch.object(extraction, "extract_text", side_effect=self.lines):
            return extraction.build_layout(self.pages, cache=self.cache, **options)

    def test_second_run_reuses_every_unchanged_page(self):
        first = self.build()
        self.assertEqual(["slide_001.png", "slide_002.png"], self.read)
        with patch.object(extraction, "finish_page", side_effect=AssertionError("page redone")):
            second = self.build()
        self.assertEqual(["slide_001.png", "slide_002.png"], self.read)
        self.assertEqual(first, second)

    def test_changed_image_or_options_redo_only_what_they_touch(self):
        self.build()
        cv2.imwrite(self.pages[1], np.full((90, 160, 3), 200, np.uint8))
        self.read.clear()
        self.build()
        self.assertEqual(["slide_002.png"], self.read)
        self.read.clear()
        done = []
        real = extraction.finish_page
        with patch.object(extraction, "finish_page", side_effect=lambda *a: done.append(a[1]) or real(*a)):
            self.build(merge=False)
        # Lines are read once; only the later stage depends on merging.
        self.assertEqual([], self.read)
        self.assertEqual([1, 2], done)

    def test_failed_page_keeps_the_others_and_is_the_only_one_redone(self):
        real = extraction.finish_page
        done = []

        def flaky(path, number, *rest):
            if number == 2:
                raise RuntimeError("font file vanished")
            done.append(number)
            return real(path, number, *rest)

        with patch.object(extraction, "finish_page", side_effect=flaky):
            with self.assertRaises(SystemExit) as stopped:
                self.build()
        message = str(stopped.exception)
        self.assertIn("slide_002.png: RuntimeError: font file vanished", message)
        self.assertIn("Run the same command again", message)
        self.assertEqual([1], done)

        with patch.object(extraction, "finish_page", side_effect=lambda *a: done.append(a[1]) or real(*a)):
            layout = self.build()
        self.assertEqual([1, 2], done)
        self.assertEqual([1, 2], [slide["slide"] for slide in layout["slides"]])

    def test_without_a_cache_errors_surface_unchanged(self):
        with patch.object(extraction, "extract_text", side_effect=self.lines), \
                patch.object(extraction, "finish_page", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                extraction.build_layout(self.pages)

    def test_damaged_cache_file_is_ignored(self):
        self.build()
        for file in self.cache.directory.iterdir():
            file.write_bytes(b"not a pickle")
        self.read.clear()
        self.build()
        self.assertEqual(["slide_001.png", "slide_002.png"], self.read)


if __name__ == "__main__":
    unittest.main()
