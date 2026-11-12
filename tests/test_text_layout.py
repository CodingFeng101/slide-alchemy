"""Column splitting, one-font-per-line, shared styles and paragraph merging."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "skill/slide-alchemy/scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_text as extraction
import rich_text

EM = 40


def row(groups, gap=4):
    """A white page with one row of square glyphs.

    `groups` lists (glyph count, colour, gap before the group); returns the
    image and the OCR box covering the row, with per-glyph columns.
    """
    image = np.full((120, 900, 3), 255, np.uint8)
    x, chars = 40, []
    for count, colour, lead in groups:
        x += lead
        for _ in range(count):
            image[40:40 + EM, x:x + EM] = colour
            chars.append((float(x), float(x + EM)))
            x += EM + gap
    left, right = int(chars[0][0]), int(chars[-1][1])
    text = "".join(chr(0x4E00 + i) for i in range(len(chars)))
    return image, extraction.OcrBox(text, 1.0, left - 3, 36, right - left + 6, EM + 8, chars)


def block(text, x, y, w=0.3, h=0.03, **values):
    values.setdefault("font_size_pt", 14)
    return extraction.TextBlock(id=text, text=text, bbox=(x, y, w, h), **values)


def candidate(face, error, size=20):
    return {"family": face, "face_name": face, "bold": False, "italic": False,
            "shape_error": error, "size_px": size, "model_similarity": 0.9}


class ColumnSplitTests(unittest.TestCase):
    BLACK, BLUE = (20, 20, 20), (200, 80, 20)

    def test_gap_wider_than_an_em_parts_side_by_side_labels(self):
        image, box = row([(4, self.BLACK, 0), (4, self.BLACK, 2 * EM)])
        parts = extraction.split_columns(image, box)
        self.assertEqual([box.text[:4], box.text[4:]], [part.text for part in parts])
        self.assertEqual([4, 4], [len(part.chars) for part in parts])
        self.assertLess(parts[0].x + parts[0].w, parts[1].x)
        self.assertAlmostEqual(box.chars[4][0], parts[1].x, delta=3)

    def test_wide_space_inside_one_title_keeps_the_line_whole(self):
        image, box = row([(4, self.BLACK, 0), (4, self.BLACK, int(0.6 * EM))])
        self.assertEqual([box], extraction.split_columns(image, box))

    def test_the_same_gap_parts_labels_of_different_colour(self):
        image, box = row([(4, self.BLACK, 0), (4, self.BLUE, int(0.6 * EM))])
        self.assertEqual(2, len(extraction.split_columns(image, box)))

    def test_tracked_out_title_is_not_cut_into_characters(self):
        image, box = row([(6, self.BLACK, 0)], gap=int(1.2 * EM))
        self.assertEqual([box], extraction.split_columns(image, box))

    def test_boxes_without_character_columns_are_left_alone(self):
        image, box = row([(4, self.BLACK, 0), (4, self.BLACK, 2 * EM)])
        box.chars = None
        self.assertEqual([box], extraction.split_columns(image, box))


class OneFontPerLineTests(unittest.TestCase):
    def analyse(self, first, second, text=None):
        """Analyse a two-word line; each word gets its own (face, error) ranking."""
        image, box = row([(4, (20, 20, 20), 0), (4, (20, 20, 20), int(0.6 * EM))])
        text = box.text[:4] + " " + box.text[4:]
        box.text = text
        line = extraction.TextBlock(id="t", text=text, bbox=(0, 0, 1, 1), font_size_pt=20, source_box=box)
        rankings = {text[:4]: first, text[5:]: second}
        asked = []

        class Matcher:
            def match(self, mask, chunk, top_k=10):
                asked.append(chunk)
                return {"status": "ranked", "candidates": [candidate(face, error) for face, error in rankings[chunk]]}

        with patch.object(rich_text, "font_boundaries", return_value=[5]):
            rich_text.analyse_line(image, line, 0.5, Matcher())
        self.assertEqual([text[:4], text[5:]], asked)
        self.assertEqual(text, "".join(run["text"] for run in line.runs))
        return [run["font_face"] for run in line.runs if run["text"].strip()], line

    def test_words_whose_rankings_nearly_tie_share_one_face(self):
        faces, line = self.analyse([("Hei", 0.050), ("Sans", 0.052)], [("Sans", 0.050), ("Hei", 0.055)])
        self.assertEqual(1, len(set(faces)))
        for run, report in zip([r for r in line.runs if r["text"].strip()], line.font_matches):
            self.assertEqual(run["font_face"], report["selected_candidate"]["face_name"])

    def test_a_confidently_different_word_keeps_its_own_face(self):
        faces, _ = self.analyse([("Hei", 0.03), ("Sans", 0.20)], [("Sans", 0.03), ("Hei", 0.20)])
        self.assertEqual(["Hei", "Sans"], faces)

    def test_a_poorly_matched_word_takes_the_face_of_the_line(self):
        faces, line = self.analyse([("Hei", 0.05)], [("Odd", 0.19)])
        self.assertEqual(["Hei", "Hei"], faces)
        self.assertTrue(line.font_matches[1]["selected_candidate"]["inherited"])

    def test_punctuation_between_colours_gets_no_font_of_its_own(self):
        image, box = row([(3, (20, 20, 20), 0), (1, (200, 80, 20), 0), (3, (20, 20, 20), 0)])
        text = box.text[:3] + "\u00b7" + box.text[4:]
        box.text = text
        line = extraction.TextBlock(id="t", text=text, bbox=(0, 0, 1, 1), font_size_pt=20, source_box=box)
        asked = []

        class Matcher:
            def match(self, mask, chunk, top_k=10):
                asked.append(chunk)
                return {"status": "ranked", "candidates": [candidate("Hei", 0.05)]}

        with patch.object(rich_text, "font_boundaries", return_value=[]):
            rich_text.analyse_line(image, line, 0.5, Matcher())
        self.assertTrue(all(any(char.isalnum() for char in chunk) for chunk in asked), asked)
        self.assertEqual(text, "".join(run["text"] for run in line.runs))


class SharedStyleTests(unittest.TestCase):
    def line(self, text, ranking, colour="#202020"):
        metrics = extraction.TextMetrics(em_ref_px=30)
        item = block(text, 0.1, 0.1, color=colour, metrics=metrics)
        report = {"candidates": [candidate(face, error, size) for face, error, size in ranking]}
        report["selected_candidate"] = report["candidates"][0]
        best = report["candidates"][0]
        item.runs = [{"text": text, "color": colour, "font_family": best["family"], "font_face": best["face_name"],
                      "bold": False, "italic": False, "font_size_pt": best["size_px"] * 0.5}]
        item.font_matches = [report]
        return item

    def test_lines_of_one_style_take_one_face_and_size(self):
        first = self.line("专业学习重技术", [("Hei", 0.050, 28), ("Sans", 0.052, 29)])
        second = self.line("理论学习与实践", [("Sans", 0.050, 30), ("Hei", 0.055, 29)])
        extraction.harmonise_runs([first, second], 0.5)
        faces = {item.runs[0]["font_face"] for item in (first, second)}
        self.assertEqual(1, len(faces))
        self.assertEqual(first.runs[0]["font_size_pt"], second.runs[0]["font_size_pt"])
        self.assertEqual("shared_style", second.font_matches[0]["selection"])
        self.assertEqual(first.font_face, second.font_face)
        for item in (first, second):
            selected = item.font_matches[0]["selected_candidate"]
            self.assertEqual(selected["face_name"], item.runs[0]["font_face"])

    def test_different_colours_or_a_costly_compromise_keep_their_own_faces(self):
        first = self.line("专业学习重技术", [("Hei", 0.05, 28), ("Sans", 0.052, 29)])
        other_colour = self.line("理论学习与实践", [("Sans", 0.05, 30), ("Hei", 0.055, 29)], "#D02020")
        extraction.harmonise_runs([first, other_colour], 0.5)
        self.assertEqual(["Hei", "Sans"], [first.runs[0]["font_face"], other_colour.runs[0]["font_face"]])
        far = self.line("理论学习与实践", [("Sans", 0.05, 30), ("Hei", 0.20, 29)])
        extraction.harmonise_runs([first, far], 0.5)
        self.assertEqual("Sans", far.runs[0]["font_face"])


class PhotoTextTests(unittest.TestCase):
    def test_text_inside_a_cropped_photograph_is_left_in_the_photograph(self):
        import json
        import tempfile

        analysis = {
            "ref_width": 200, "ref_height": 100,
            "components": {"photo": {"category": "photo_source_crop"}, "icon": {"category": "icon_png"}},
            "slides": [{"slide": 2, "instances": [
                {"component": "photo", "id": "p", "bbox_px": [100, 0, 100, 100]},
                {"component": "icon", "id": "i", "bbox_px": [0, 0, 50, 50]},
            ]}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analysis.json"
            path.write_text(json.dumps(analysis), encoding="utf-8")
            regions = extraction.photo_regions(path)
        self.assertEqual({2: [(0.5, 0.0, 0.5, 1.0)]}, regions)
        banner = extraction.OcrBox("banner", 1.0, 700, 40, 100, 30, None)
        title = extraction.OcrBox("title", 1.0, 100, 40, 100, 30, None)
        self.assertTrue(extraction.inside(banner, regions[2], 1000, 500))
        self.assertFalse(extraction.inside(title, regions[2], 1000, 500))


class ParagraphMergeTests(unittest.TestCase):
    def test_centred_lines_merge_into_a_centred_paragraph(self):
        lines = [block("专业学习重技术，轻理想信念", 0.10, 0.50, w=0.30), block("教育，不够深入。", 0.16, 0.54, w=0.18)]
        merged = extraction.merge_lines(lines)
        self.assertEqual(1, len(merged))
        self.assertEqual("center", merged[0].align)
        frame = extraction.text_frame(merged[0], 960, 540)
        self.assertAlmostEqual(0.25, frame[0] + frame[2] / 2, delta=0.002)

    def test_left_aligned_paragraph_keeps_left_alignment(self):
        lines = [block("现有党员37名，", 0.6, 0.50, w=0.12), block("涵盖本科生与研究生，结构合理、", 0.6, 0.54, w=0.22)]
        merged = extraction.merge_lines(lines)
        self.assertEqual(["left"], [item.align for item in merged])

    def test_wider_pitch_starts_the_next_paragraph(self):
        lines = [block("a1", 0.6, 0.50), block("a2", 0.6, 0.54), block("b1", 0.6, 0.60), block("b2", 0.6, 0.64)]
        merged = extraction.merge_lines(lines)
        self.assertEqual(["a1\na2", "b1\nb2"], [item.text for item in merged])

    def test_unrelated_lines_at_different_positions_stay_apart(self):
        lines = [block("left", 0.1, 0.50, w=0.2), block("right", 0.5, 0.54, w=0.2)]
        self.assertEqual(2, len(extraction.merge_lines(lines)))


if __name__ == "__main__":
    unittest.main()
