"""Outlined lettering, effect ranges that grow with size, and review flags."""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
import rich_text
import text_effects


def letters(height=80, outline=0):
    """Three solid blocks, one with a counter; `outline` keeps only their rim."""
    solid = np.zeros((height + 40, 400), np.uint8)
    for x in (20, 140, 260):
        solid[20:20 + height, x:x + 90] = 1
    solid[45:20 + height - 25, 165:205] = 0
    if not outline:
        return solid
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * outline + 1, 2 * outline + 1))
    return solid - cv2.erode(solid, kernel)


class OutlinedLetteringTests(unittest.TestCase):
    def test_outline_only_lettering_yields_its_fill_and_outline_width(self):
        found = rich_text.hollow_body(letters(outline=5))
        self.assertIsNotNone(found)
        body, width = found
        self.assertAlmostEqual(5, width, delta=1.5)
        self.assertTrue(body[60, 60])
        # The counter of the middle letter is background, not fill.
        self.assertFalse(body[70, 185])
        self.assertFalse(body[5, 5])

    def test_solid_lettering_with_counters_is_ordinary_text(self):
        self.assertIsNone(rich_text.hollow_body(letters()))

    def test_open_strokes_are_ordinary_text(self):
        ink = np.zeros((120, 400), np.uint8)
        for x in range(20, 380, 40):
            ink[20:100, x:x + 6] = 1
        ink[58:64, 20:380] = 1
        self.assertIsNone(rich_text.hollow_body(ink))

    def test_small_text_is_never_treated_as_outlined(self):
        self.assertIsNone(rich_text.hollow_body(letters(height=24, outline=2)))


class EffectFitTests(unittest.TestCase):
    def page(self, radius, height=100):
        alpha = np.zeros((height + 80, 420), np.float32)
        for x in (50, 170, 290):
            alpha[40:40 + height, x:x + 80] = 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        rim = cv2.dilate(alpha, kernel)
        background, fill, edge = np.array([255, 255, 255.0]), np.array([255, 200, 0.0]), np.array([120, 0, 0.0])
        rgb = background * (1 - rim[..., None]) + edge * rim[..., None]
        rgb = rgb * (1 - alpha[..., None]) + fill * alpha[..., None]
        return rgb, alpha, background, fill

    def test_wide_outline_on_large_lettering_is_measured_in_full(self):
        rgb, alpha, background, fill = self.page(radius=7)
        fitted = text_effects.fit_effects(rgb, alpha, background, fill, 0.5)
        self.assertAlmostEqual(3.5, fitted["effects"]["outline"]["width_pt"], delta=0.5)
        self.assertFalse(fitted["needs_review"])

    def test_review_flag_is_for_fits_that_leave_visible_differences(self):
        rgb, alpha, background, fill = self.page(radius=0)
        clean = text_effects.fit_effects(rgb, alpha, background, fill, 0.5)
        self.assertFalse(clean["needs_review"])
        noisy = rgb.copy()
        noisy[60:120] = (40, 90, 200)
        self.assertTrue(text_effects.fit_effects(noisy, alpha, background, fill, 0.5)["needs_review"])

    def test_gradient_gains_a_middle_stop_only_when_the_blend_bends(self):
        mask = np.ones((100, 200), np.float32)
        y = np.linspace(0, 1, 100)[:, None, None]
        top, bottom = np.array([250, 230, 60.0]), np.array([200, 30, 20.0])
        straight = np.broadcast_to(top + (bottom - top) * y, (100, 200, 3))
        self.assertEqual(2, len(text_effects.infer_gradient(straight, mask)["stops"]))
        bent = np.broadcast_to(top + (bottom - top) * y ** 2.2, (100, 200, 3))
        gradient = text_effects.infer_gradient(bent, mask)
        self.assertEqual([0, 0.5, 1], [stop["position"] for stop in gradient["stops"]])


if __name__ == "__main__":
    unittest.main()
