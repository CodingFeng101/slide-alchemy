#!/usr/bin/env python3
"""Extract editable text layout from slide images with OCR and pixel measurement.

The OCR model does the one thing only a model can do -- turn pixels into
characters. Everything else (position, size, colour, weight) is measured from
the pixels, because a vision model asked for sixty text boxes returns sixty
approximations.

Two parts of the measurement chain are load-bearing and easy to get wrong:

  * The ink mask needs a saturation test, not just a colour-distance test. A
    green tick is 136 away from dark grey text in L1, and the distance
    threshold is 130 -- six apart. Saturation separates them by a mile.
  * Stroke width must come from a distance transform, not from ink coverage.
    Coverage cannot tell a dense regular glyph from a simple bold one.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# --- filters -----------------------------------------------------------------

MIN_CONF = 0.5
SHORT_STRING_CONF = 0.75
SHORT_STRING_LEN = 2
LONE_GLYPH_CONF = 0.90
MAX_SKEW = 0.45

# --- ink separation ----------------------------------------------------------

RING_PAD = 4
MIN_INK_DISTANCE = 60
INK_DISTANCE_RATIO = 0.45
TEXT_COLOUR_TOLERANCE = 130
SATURATION_HEADROOM = 45

# --- style measurement -------------------------------------------------------

HEIGHT_PERCENTILE = 80
STROKE_PERCENTILE = 88
# Measured glyph height as a share of the em, for the face the composer uses
# (Microsoft YaHei) as PowerPoint renders it: CJK 0.93-0.96 across 11-48pt,
# regular and bold alike; Latin with capitals or ascenders 0.73-0.77. The
# source face does not matter here -- what has to match is the rebuilt ink.
CJK_FACE_RATIO = 0.94
LATIN_FACE_RATIO = 0.75
# Colours measured off small anti-aliased glyphs drift line to line, so the
# merge test is loose. Geometry and size carry the decision; colour only has
# to rule out a genuinely different run of text.
MERGE_COLOUR_TOLERANCE = 100

ITALIC_SLANT = 0.13

# Weight is the stroke width over the em, with the width taken as twice the
# ink area over the outline length (a stroke of width w and length L has area
# wL and perimeter about 2L). Counting anti-aliased pixels by their coverage
# makes the width continuous and sub-pixel; the distance transform used before
# moves in steps of about a pixel, which put 15-18pt regular text on the same
# step as bold headings.
#
# Rendered fonts (YaHei, DengXian, HarmonyOS Sans, Noto Sans SC, SimHei at
# 16-80px em, both polarities, 1x and 1.15x resampling): regular and light
# faces measure at most 0.099 of the em at 16px, falling to 0.076 at 80px;
# bold and black faces 0.108-0.156; medium in between. Body text drawn by image
# models sits heavier than a true regular -- 0.094-0.119 at a 27-36px em on
# generated slides, where headings from a 44px em up measure 0.112-0.148. The
# composer only has regular and bold, so that medium-looking body text has to
# land on regular. Hence a threshold that is high for small text and eases with
# size: it keeps every rendered bold from a 30px em up and every generated
# heading, and gives up bold below about a 26px em (13pt), where a missed bold
# is the lesser error. Sizes are taken on a 1920px-wide page so the decision
# does not move with the render resolution.
BOLD_RATIO_BASE = 0.0915
BOLD_RATIO_SIZE_PX = 0.75
REFERENCE_PAGE_WIDTH = 1920.0
# Below this em the glyphs are too few pixels to show weight at all.
MIN_BOLD_EM_PX = 12
# Weight is relative within a deck: one generated deck's regular body text
# measured heavier than another deck's bold labels at the same size. So `auto`
# takes each block's margin over the threshold above and looks across the whole
# deck for the valley between the regular cluster and the bold one -- a local
# minimum of the smoothed margin density, inside this window, well below the
# peaks on both sides, with enough blocks on each side. Without such a valley
# (a single-weight deck, a handful of blocks) the threshold is used as is.
# Measured: a year-end deck splits at +0.003, a course deck at -0.022.
WEIGHT_VALLEY_WINDOW = (-0.035, 0.02)
WEIGHT_VALLEY_BANDWIDTH = 0.003
WEIGHT_VALLEY_DEPTH = 0.6
WEIGHT_VALLEY_MIN_SHARE = 0.1
WEIGHT_VALLEY_MIN_BLOCKS = 8
# Blocks on one page within this share of each other's em and this colour
# distance are taken as one style and given one weight.
SIBLING_EM_TOLERANCE = 0.06
SIBLING_COLOUR_TOLERANCE = 60

# --- text box frame ----------------------------------------------------------

# Slack for font substitution on the opening machine: the same string is wider
# there, and a box cut to the measured width wraps.
TEXT_WIDTH_SLACK = 1.35
TEXT_WIDTH_EXTRA_PT = 12.0
TEXT_HEIGHT_EXTRA_PT = 6.0
# PowerPoint puts line leading above the first baseline, so a text box has to
# start a little above the ink it is meant to cover.
BASELINE_LIFT = 0.16
# With exact line spacing PowerPoint also puts about 0.6 of whatever the
# spacing adds over single spacing (1.2 em) above the first line. Measured on
# PowerPoint 365 renders: 0.55-0.66 across six paragraphs.
SINGLE_SPACING_EM = 1.2
EXACT_SPACING_LIFT = 0.6

BULLET_CHARS = "•·‣▪◦●○∙–—-"

# --- spaces ------------------------------------------------------------------

# OCR drops the spaces in mixed CJK text ("上线 3 个月" reads as "上线3个月"),
# and the rebuilt line comes out narrower than the source. Measured on
# generated slides, an ink gap that holds a space is 0.36-0.49 em, and a gap
# without one -- including digit-to-CJK -- at most 0.31 em.
SPACE_GAP_EM = 0.33
# A space with an interpunct in it spans about 0.7 em. Anything much wider is
# part of a glyph the ink mask lost (a lighter-coloured name, say), not a space.
SPACE_GAP_MAX_EM = 0.9
# Full-width punctuation carries its own whitespace inside the glyph, so a wide
# gap next to it is not a missing space.
NO_SPACE_AFTER = set("，。、；：！？（《“‘【〔「『")
NO_SPACE_BEFORE = set("，。、；：！？）》”’】〕」』")
# OCR reads the interpunct between CJK words as a bullet or katakana dot.
INTERPUNCT_LOOKALIKES = "•・･∙"
CJK_PATTERN = re.compile(r"[㐀-鿿豈-﫿　-〿]")

# --- columns -----------------------------------------------------------------

# OCR reads side-by-side labels on one row as a single line. A gap this wide
# is never a space inside one phrase (a space with an interpunct spans 0.7 em).
COLUMN_GAP_EM = 1.0
# A narrower gap still parts two labels when the lettering on either side is
# visibly different. A title with a wide space keeps one style and stays whole.
STYLE_GAP_EM = 0.4
# Tracked-out titles have wide gaps everywhere; a column gap stands out.
COLUMN_GAP_OVER_TYPICAL = 3.0
COLUMN_COLOUR_DISTANCE = 90
COLUMN_HEIGHT_RATIO = 1.12
COLUMN_SLANT_DIFFERENCE = 0.09

# --- paragraphs --------------------------------------------------------------

# Lines of one paragraph keep one pitch; the next list item sits further down.
PARAGRAPH_PITCH_TOLERANCE = 0.25
CENTRE_TOLERANCE = 0.008

DEFAULT_SLIDE_WIDTH_IN = 13.333333

_engine = None
_engine_name = None


def _ocr_engine():
    """RapidOCR 3.x (`rapidocr`), or the older `rapidocr_onnxruntime` build.

    The older package stops at Python 3.12; 3.x runs on 3.13+ and ships its
    models in the wheel, so neither needs a download at run time.
    """
    global _engine, _engine_name
    if _engine is None:
        try:
            from rapidocr import RapidOCR
        except ImportError:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as error:
                raise SystemExit(
                    "rapidocr and onnxruntime are required: pip install -r requirements.txt"
                ) from error
            _engine_name = "rapidocr-onnxruntime"
            _engine = RapidOCR()
        else:
            _engine_name = "rapidocr"
            # 3.x pads its boxes more. A loose box around a small badge puts
            # the background sample on the card outside the badge, and the
            # badge itself then measures as text. This padding matches the
            # older build's boxes, which the measurement was tuned on.
            _engine = RapidOCR(params={"Det.unclip_ratio": 1.1, "Global.log_level": "warning"})
    return _engine


def run_ocr(image):
    """(quad, text, confidence, chars) from whichever engine is installed.

    `chars` holds each recognised character's (left, right) columns; only
    RapidOCR 3.x reports them, and the older build gives None.
    """
    engine = _ocr_engine()
    if _engine_name == "rapidocr":
        result = engine(image, return_word_box=True, return_single_char_box=True)
        if result.boxes is None:
            return []
        words = result.word_results or [None] * len(result.txts)
        return [
            (quad, text, score, char_columns(word))
            for quad, text, score, word in zip(result.boxes, result.txts, result.scores, words)
        ]
    lines, _ = engine(image)
    return [(quad, text, conf, None) for quad, text, conf in (lines or [])]


def char_columns(word_result):
    if not word_result:
        return None
    columns = []
    for char, _, quad in word_result:
        if len(char) != 1:
            return None
        xs = [float(point[0]) for point in quad]
        columns.append((min(xs), max(xs)))
    return columns


def read_image(path):
    """cv2.imread cannot open non-ASCII paths on Windows; decoding bytes can."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise ValueError(f"cannot read image: {path}")
    return image


@dataclass
class OcrBox:
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int
    # (left, right) page columns of each non-space character, when the OCR
    # engine reports them.
    chars: list = None


@dataclass
class TextMetrics:
    stroke_px: float = 0.0
    stroke_ratio: float = 0.0
    stroke_ratio_area: float = 0.0
    # The em in pixels on a page scaled to REFERENCE_PAGE_WIDTH.
    em_ref_px: float = 0.0
    stroke_cv: float = 0.0
    slant: float = 0.0


@dataclass
class TextBlock:
    id: str
    text: str
    # Measured glyph bounds, in page fractions [x, y, w, h].
    bbox: tuple
    font_size_pt: float
    color: str = "#111827"
    bold: bool = False
    italic: bool = False
    script: str = "cjk"
    align: str = "left"
    bullet: bool = False
    # Left edge of the line including its bullet mark, in page fractions.
    mark_x: float = 0.0
    # Line-to-line distance of a merged paragraph, in page-height fractions.
    line_pitch: float = 0.0
    conf: float = 1.0
    metrics: TextMetrics = field(default_factory=TextMetrics)
    font_family: str = "Microsoft YaHei"
    font_face: str = ""
    font_matches: list = field(default_factory=list)
    source_box: OcrBox = None
    runs: list = field(default_factory=list)
    style_report: dict = field(default_factory=dict)


def clamp_bbox(x, y, w, h):
    x = min(1.0, max(0.0, float(x)))
    y = min(1.0, max(0.0, float(y)))
    w = min(1.0 - x, max(0.0, float(w)))
    h = min(1.0 - y, max(0.0, float(h)))
    return (x, y, w, h)


def read_boxes(image):
    """Run OCR and drop the three classes of result that cause damage."""
    boxes = []

    for quad, text, conf, chars in run_ocr(image):
        text = str(text or "").strip()
        conf = float(conf)
        if not text or conf < MIN_CONF:
            continue
        # A short, low-confidence string is usually an icon read as a glyph.
        # Left in, it both writes nonsense into the deck and lets the ink mask
        # eat the icon.
        if conf < SHORT_STRING_CONF and len(text) <= SHORT_STRING_LEN:
            continue
        # A lone latin character is an icon far more often than it is text.
        # "01" and "02" style markers are two characters and survive this.
        if len(text) == 1 and not CJK_PATTERN.search(text) and conf < LONE_GLYPH_CONF:
            continue

        xs = [float(p[0]) for p in quad]
        ys = [float(p[1]) for p in quad]
        x, y = min(xs), min(ys)
        w, h = max(xs) - x, max(ys) - y
        if w <= 1 or h <= 1:
            continue
        # Slanted text rebuilt in a horizontal box lands wrong; leave it in the
        # background instead.
        if abs(ys[0] - ys[1]) > h * MAX_SKEW:
            continue

        boxes.append(OcrBox(text, conf, int(x), int(y), int(round(w)), int(round(h)), chars))

    return boxes


def any_ink(crop, background):
    """Everything that is not background, whatever its colour."""
    distance = np.abs(crop.astype(np.int16) - background.astype(np.int16)).sum(axis=2)
    return (distance >= max(35, float(distance.max()) * 0.25)).astype(np.uint8)


def segment_style(crop, background):
    mask, colour = ink_mask(crop, background)
    rows = np.where(mask.any(axis=1))[0]
    height = float(rows[-1] - rows[0] + 1) if rows.size else 0.0
    return colour.astype(np.float32), height, slant(mask)


def styles_differ(left, right):
    (colour_a, height_a, slant_a), (colour_b, height_b, slant_b) = left, right
    if min(height_a, height_b) <= 0:
        return False
    return (
        float(np.abs(colour_a - colour_b).sum()) > COLUMN_COLOUR_DISTANCE
        or max(height_a, height_b) / min(height_a, height_b) > COLUMN_HEIGHT_RATIO
        or abs(slant_a - slant_b) >= COLUMN_SLANT_DIFFERENCE
    )


def split_columns(image, box):
    """Part an OCR line that runs across side-by-side labels.

    One box for two labels gives both a single font, colour and size, and
    leaves the second label's position to the width of a space.
    """
    glyphs = [i for i, char in enumerate(box.text) if not char.isspace()]
    if not box.chars or len(box.chars) != len(glyphs) or len(glyphs) < 4:
        return [box]
    crop = image[box.y:box.y + box.h, box.x:box.x + box.w]
    if crop.size == 0:
        return [box]
    background = ring_background(image, box)
    ink = any_ink(crop, background)
    columns = np.where(ink.any(axis=0))[0]
    rows = np.where(ink.any(axis=1))[0]
    if columns.size < 2:
        return [box]
    em = float(rows[-1] - rows[0] + 1)
    blanks = [(int(a) + 1, int(b)) for a, b in zip(columns, columns[1:]) if b - a > 1]
    wide = [(a, b) for a, b in blanks if b - a >= STYLE_GAP_EM * em]
    if not wide:
        return [box]
    typical = float(np.median([b - a for a, b in blanks if (a, b) not in wide] or [0]))
    wide = [(a, b) for a, b in wide if b - a >= COLUMN_GAP_OVER_TYPICAL * typical]

    boundaries = [(box.chars[k][1] + box.chars[k + 1][0]) / 2.0 for k in range(len(glyphs) - 1)]
    edges = [int(columns[0]), *[x for gap in wide for x in gap], int(columns[-1]) + 1]
    spans = list(zip(edges[::2], edges[1::2]))
    styles = [segment_style(crop[:, a:b], background) for a, b in spans]
    cuts = []
    for index, (a, b) in enumerate(wide):
        centre = box.x + (a + b) / 2.0
        k = min(range(len(boundaries)), key=lambda n: abs(boundaries[n] - centre))
        if abs(boundaries[k] - centre) > em * 0.6:
            continue
        if b - a >= COLUMN_GAP_EM * em or styles_differ(styles[index], styles[index + 1]):
            cuts.append((k + 1, a, b))
    # Every part keeps at least two characters; a lone glyph is a mark.
    cuts = [cut for cut in cuts if 2 <= cut[0] <= len(glyphs) - 2]
    if not cuts:
        return [box]

    parts = []
    starts = [(0, int(columns[0])), *[(k, b) for k, _, b in cuts]]
    stops = [*[(k, a) for k, a, _ in cuts], (len(glyphs), int(columns[-1]) + 1)]
    for (first, left), (last, right) in zip(starts, stops):
        if last - first < 2:
            return [box]
        text = box.text[glyphs[first]:glyphs[last - 1] + 1].strip()
        left, right = max(0, left - 2), min(box.w, right + 2)
        parts.append(OcrBox(text, box.conf, box.x + left, box.y, right - left, box.h,
                            box.chars[first:last]))
    return parts


def ring_background(image, box):
    """The median colour of a ring just outside the box.

    Sampling inside the box risks sampling the glyphs themselves; the ring is
    what "the colour underneath this text" actually means.
    """
    h, w = image.shape[:2]
    x0 = max(0, box.x - RING_PAD)
    y0 = max(0, box.y - RING_PAD)
    x1 = min(w, box.x + box.w + RING_PAD)
    y1 = min(h, box.y + box.h + RING_PAD)

    outer = image[y0:y1, x0:x1].reshape(-1, 3)
    inner = image[box.y:box.y + box.h, box.x:box.x + box.w].reshape(-1, 3)
    if outer.shape[0] <= inner.shape[0]:
        return np.median(outer, axis=0)

    mask = np.ones((y1 - y0, x1 - x0), dtype=bool)
    mask[box.y - y0:box.y - y0 + box.h, box.x - x0:box.x - x0 + box.w] = False
    ring = image[y0:y1, x0:x1][mask]
    return np.median(ring if ring.size else outer, axis=0)


def ink_mask(crop, background):
    """Separate glyph pixels from whatever else the OCR box caught.

    Returns the mask and the dominant text colour.
    """
    crop_f = crop.astype(np.int16)
    d_bg = np.abs(crop_f - background.astype(np.int16)).sum(axis=2)
    threshold = max(MIN_INK_DISTANCE, float(d_bg.max()) * INK_DISTANCE_RATIO)
    candidate = d_bg >= threshold

    if not candidate.any():
        return candidate.astype(np.uint8), background.astype(np.int16)

    text_colour = np.median(crop_f[candidate], axis=0)
    d_text = np.abs(crop_f - text_colour).sum(axis=2)

    # max-min stands in for saturation, which avoids an HSV conversion and is
    # what actually separates coloured icons from neutral glyphs.
    saturation = crop_f.max(axis=2) - crop_f.min(axis=2)
    text_saturation = float(text_colour.max() - text_colour.min())

    strict = (
        candidate
        & (d_text < TEXT_COLOUR_TOLERANCE)
        & (saturation <= text_saturation + SATURATION_HEADROOM)
    )
    return strict.astype(np.uint8), text_colour


def components(mask):
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return [
        (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
         int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
        for i in range(1, count)
        if stats[i, cv2.CC_STAT_AREA] >= 3
    ]


def font_height_px(mask, script="cjk"):
    """Glyph height from connected components, not from the whole-line box.

    Brackets, commas and quotes have wildly different extents; the 80th
    percentile of component heights tracks the body of the text instead.

    Thin anti-aliased strokes break a glyph into pieces, so components far
    shorter than the tallest are dropped before the percentile is taken. When
    the percentile still lands well under the ink extent, the glyph fragmented
    rather than being small -- CJK fills its em box, so the extent is the
    better answer there.
    """
    heights = [h for _, _, _, h in components(mask)]
    extent = float(mask.shape[0])
    if not heights:
        return extent

    tallest = max(heights)
    solid = [h for h in heights if h >= tallest * 0.5] or heights
    measured = float(np.percentile(solid, HEIGHT_PERCENTILE))

    floor = extent * (0.8 if script == "cjk" else 0.55)
    return extent if measured < floor else measured


def core_colour(crop, mask, fallback):
    """Median colour of the eroded mask.

    Anti-aliased edge pixels are a blend of glyph and background; sampling them
    washes dark text lighter and light text greyer.
    """
    core = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    pixels = crop[core.astype(bool)]
    if pixels.shape[0] < 8:
        pixels = crop[mask.astype(bool)]
    if pixels.shape[0] == 0:
        b, g, r = fallback
    else:
        b, g, r = np.median(pixels, axis=0)
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def stroke_metrics(mask):
    """Stroke width from a distance transform, and its variation.

    The distance transform reports the actual stroke thickness, independent of
    how complicated the character is.
    """
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    values = distance[distance > 0]
    if values.size == 0:
        return 0.0, 0.0
    width = float(np.percentile(values, STROKE_PERCENTILE)) * 2.0

    thick = distance[distance > 0.8]
    variation = float(np.std(thick) / np.mean(thick)) if thick.size > 4 else 0.0
    return width, variation


def area_stroke_px(crop, mask, background, text_colour):
    """Stroke width as twice the ink area over the outline length.

    Each pixel near the glyphs counts by how far it sits from the background
    towards the text colour, so the anti-aliased rim adds its true share
    instead of a whole pixel or none.
    """
    crop_f = crop.astype(np.float32)
    background = np.asarray(background, np.float32)
    span = np.asarray(text_colour, np.float32) - background
    span_sq = float((span * span).sum())
    if span_sq < 1.0:
        return 0.0
    coverage = np.clip(((crop_f - background) * span).sum(axis=2) / span_sq, 0.0, 1.0)
    near = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1).astype(bool)
    coverage = np.where(near, coverage, 0.0)

    solid = (coverage >= 0.5).astype(np.uint8)
    contours, _ = cv2.findContours(solid, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    return 2.0 * float(coverage.sum()) / perimeter if perimeter > 0 else 0.0


def bold_threshold(em_px):
    return BOLD_RATIO_BASE + BOLD_RATIO_SIZE_PX / em_px


def slant(mask):
    """Shear the mask until the vertical projection is most peaked.

    Vertical strokes line up at the true slant, which maximises the variance
    of the column sums.
    """
    h, w = mask.shape
    if h < 4 or w < 4:
        return 0.0

    best_angle, best_variance = 0.0, -1.0
    for angle in np.arange(-0.05, 0.36, 0.03):
        matrix = np.float32([[1, angle, -angle * h / 2], [0, 1, 0]])
        sheared = cv2.warpAffine(mask, matrix, (w, h), flags=cv2.INTER_NEAREST)
        variance = float(np.var(sheared.sum(axis=0)))
        if variance > best_variance:
            best_angle, best_variance = float(angle), variance
    return best_angle


def leading_bullet(mask, glyph_height):
    """Column where the text starts, if a bullet glyph precedes it.

    Returns 0 when there is no bullet. Both this and the textual strip below
    are needed: geometry alone leaves the character in the text, and text
    alone leaves the mark in the picture.
    """
    boxes = sorted(components(mask), key=lambda item: item[0])
    if len(boxes) < 2 or glyph_height <= 0:
        return 0

    x, y, w, h = boxes[0]
    gap = boxes[1][0] - (x + w)
    # A bullet sits in the middle band of the line. A speck at the baseline or
    # the top is the edge of a badge or card the OCR box caught, not a mark.
    centre = (y + h / 2) / mask.shape[0]
    if (
        w <= glyph_height * 0.55
        and h <= glyph_height * 0.60
        and gap >= glyph_height * 0.18
        and 0.2 <= centre <= 0.8
    ):
        return boxes[1][0]
    return 0


def ink_gaps(mask, origin_x, min_width, max_width):
    """Page-column centres of interior blank runs between the two widths."""
    columns = np.where(mask.any(axis=0))[0]
    gaps = []
    for left, right in zip(columns, columns[1:]):
        if min_width <= right - left - 1 <= max_width:
            gaps.append(origin_x + (left + right) / 2.0)
    return gaps


def restore_spaces(text, chars, mask, origin_x, em_px):
    """Put back the spaces OCR drops, where the ink has a space-wide gap.

    Each wide gap is assigned to the nearest boundary between two recognised
    characters, using the per-character columns the OCR engine reports.
    Without them the text is returned as read.
    """
    glyphs = [(i, c) for i, c in enumerate(text) if not c.isspace()]
    if not chars or len(chars) != len(glyphs) or len(glyphs) < 2 or em_px <= 0:
        return text

    boundaries = [
        (chars[k][1] + chars[k + 1][0]) / 2.0 for k in range(len(glyphs) - 1)
    ]
    spaced = set()
    for gap in ink_gaps(mask, origin_x, SPACE_GAP_EM * em_px, SPACE_GAP_MAX_EM * em_px):
        k = min(range(len(boundaries)), key=lambda n: abs(boundaries[n] - gap))
        if abs(boundaries[k] - gap) <= em_px * 0.6:
            spaced.add(k)

    out = []
    for k, (i, char) in enumerate(glyphs):
        out.append(char)
        if k + 1 == len(glyphs):
            break
        following_index, following = glyphs[k + 1]
        already = following_index > i + 1
        if already:
            out.append(" ")
        elif k in spaced and char not in NO_SPACE_AFTER and following not in NO_SPACE_BEFORE:
            out.append(" ")
    return "".join(out)


def normalise_interpunct(text):
    """A dot read between two words is the interpunct, not a bullet."""
    chars = list(text)
    for i, char in enumerate(chars):
        if char in INTERPUNCT_LOOKALIKES and 0 < i < len(chars) - 1 and text[:i].strip():
            chars[i] = "·"
    return "".join(chars)


def strip_bullet(text):
    stripped = text.lstrip()
    if stripped and stripped[0] in BULLET_CHARS:
        return stripped[1:].lstrip(), True
    return text, False


def is_cjk(text):
    return bool(CJK_PATTERN.search(text))


def deck_weight_offset(blocks):
    """Where this deck's own regular/bold valley sits, relative to the threshold."""
    margins = np.array([
        weight_margin(block) for block in blocks if block.metrics.em_ref_px >= MIN_BOLD_EM_PX
    ])
    if margins.size < WEIGHT_VALLEY_MIN_BLOCKS:
        return 0.0
    grid = np.arange(-0.1, 0.1, 0.0005)
    density = np.exp(
        -((grid[:, None] - margins[None, :]) ** 2) / (2 * WEIGHT_VALLEY_BANDWIDTH ** 2)
    ).sum(axis=1)

    low, high = WEIGHT_VALLEY_WINDOW
    best, best_score = 0.0, WEIGHT_VALLEY_DEPTH
    for i in range(1, grid.size - 1):
        x = grid[i]
        if not low <= x <= high:
            continue
        if density[i] > density[i - 1] or density[i] > density[i + 1]:
            continue
        below = float((margins < x).mean())
        if below < WEIGHT_VALLEY_MIN_SHARE or below > 1 - WEIGHT_VALLEY_MIN_SHARE:
            continue
        score = density[i] / min(density[:i].max(), density[i + 1:].max())
        if score < best_score:
            best, best_score = float(x), score
    return best


def resolve_bold(blocks, mode, offset=None):
    """Decide weight.

    `auto` compares the area-based stroke width with a share of the em that
    eases with size, shifted by `offset` to where this deck's own regular and
    bold clusters part (found from `blocks` when not given). When the guess is
    wrong for a template, pin a threshold on `stroke_ratio_area` with
    `ratio:<value>` instead -- the measurements stay in the JSON so one
    calibration serves a whole batch of same-template slides.
    """
    mode = (mode or "auto").strip().lower()
    if mode == "off" or not blocks:
        for block in blocks:
            block.bold = False
        return
    if mode == "on":
        for block in blocks:
            block.bold = True
        return
    if mode.startswith("ratio:"):
        try:
            threshold = float(mode.split(":", 1)[1])
        except ValueError:
            threshold = 0.1
        for block in blocks:
            block.bold = block.metrics.stroke_ratio_area >= threshold
        return

    if offset is None:
        offset = deck_weight_offset(blocks)
    for block in blocks:
        block.bold = block.metrics.em_ref_px >= MIN_BOLD_EM_PX and weight_margin(block) >= offset
    harmonise_siblings(blocks, offset)


def weight_margin(block):
    return block.metrics.stroke_ratio_area - bold_threshold(max(block.metrics.em_ref_px, 1.0))


def siblings(left, right):
    """Same size and colour on one page: almost always one style, like a row of card titles."""
    a, b = left.metrics.em_ref_px, right.metrics.em_ref_px
    return (
        a > 0 and b > 0
        and abs(a - b) <= max(a, b) * SIBLING_EM_TOLERANCE
        and colour_distance(left.color, right.color) <= SIBLING_COLOUR_TOLERANCE
    )


def harmonise_siblings(blocks, offset=0.0):
    """Give each group of sibling blocks one weight, by majority.

    The same style measures a little differently from string to string, and a
    style that sits near the threshold otherwise comes out with some titles of
    a row bold and the rest regular. A tie goes by the group's mean margin.
    """
    parent = list(range(len(blocks)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if siblings(blocks[i], blocks[j]):
                parent[root(i)] = root(j)

    groups = {}
    for i, block in enumerate(blocks):
        groups.setdefault(root(i), []).append(block)
    for group in groups.values():
        if len(group) < 2:
            continue
        bold = sum(block.bold for block in group)
        if bold * 2 == len(group):
            verdict = sum(weight_margin(block) - offset for block in group) >= 0
        else:
            verdict = bold * 2 > len(group)
        for block in group:
            block.bold = verdict


def photo_regions(analysis_path):
    """Photograph boxes per slide, as page fractions, from element_analysis.json."""
    data = json.loads(Path(analysis_path).read_text(encoding="utf-8-sig"))
    components = data.get("components", {})
    regions = {}
    for slide in data.get("slides", []):
        for instance in slide.get("instances", []):
            if components.get(instance.get("component"), {}).get("category") == "photo_source_crop":
                x, y, w, h = instance["bbox_px"]
                regions.setdefault(slide["slide"], []).append(
                    (x / data["ref_width"], y / data["ref_height"], w / data["ref_width"], h / data["ref_height"]))
    return regions


def inside(box, regions, page_w, page_h):
    cx, cy = (box.x + box.w / 2) / page_w, (box.y + box.h / 2) / page_h
    return any(x <= cx <= x + w and y <= cy <= y + h for x, y, w, h in regions)


def extract_text(image_path, slide_id, bold_mode="auto", expected=None,
                 slide_width_pt=DEFAULT_SLIDE_WIDTH_IN * 72, skip_regions=()):
    """Read one page into text blocks with measured style."""
    image = read_image(image_path)
    page_h, page_w = image.shape[:2]
    pt_per_px = slide_width_pt / page_w

    blocks = []

    # Writing on a banner or sign inside a photograph stays in the cropped
    # photograph; rebuilt as text boxes it would be drawn twice.
    boxes = [part for box in read_boxes(image) if not inside(box, skip_regions, page_w, page_h)
             for part in split_columns(image, box)]
    for index, box in enumerate(boxes):
        crop = image[box.y:box.y + box.h, box.x:box.x + box.w]
        if crop.size == 0:
            continue

        background = ring_background(image, box)
        mask, text_colour = ink_mask(crop, background)
        if mask.sum() < 4:
            continue

        # OCR boxes routinely swallow a neighbouring icon. Re-deriving the
        # bounds from the ink is what stops the rebuilt text from sitting on
        # top of it.
        cols = np.where(mask.any(axis=0))[0]
        rows = np.where(mask.any(axis=1))[0]
        left, right = int(cols[0]), int(cols[-1]) + 1
        top, bottom = int(rows[0]), int(rows[-1]) + 1
        mark_left = left

        text, had_bullet_char = strip_bullet(box.text)
        script = "cjk" if is_cjk(text) else "latin"
        glyph_px = font_height_px(mask[top:bottom, left:right], script)
        line_em = glyph_px / (CJK_FACE_RATIO if script == "cjk" else LATIN_FACE_RATIO)
        text, _ = strip_bullet(
            normalise_interpunct(restore_spaces(box.text, box.chars, mask, box.x, line_em))
        )

        bullet_start = leading_bullet(mask[top:bottom, left:right], glyph_px)
        if bullet_start:
            left += bullet_start
            had_bullet_char = True
            mask_view = mask[top:bottom, left:right]
            if mask_view.sum() < 4:
                continue
            glyph_px = font_height_px(mask_view, script)

        region = mask[top:bottom, left:right]
        crop_region = crop[top:bottom, left:right]
        if region.size == 0 or region.sum() < 4:
            continue

        face_ratio = CJK_FACE_RATIO if script == "cjk" else LATIN_FACE_RATIO
        em_px = glyph_px / face_ratio

        stroke_px, stroke_cv = stroke_metrics(region)
        area_px = area_stroke_px(crop_region, region, background, text_colour)
        slant_value = slant(region)

        blocks.append(
            TextBlock(
                id=f"{slide_id}_t{index + 1}",
                text=text,
                bbox=clamp_bbox(
                    (box.x + left) / page_w,
                    (box.y + top) / page_h,
                    (right - left) / page_w,
                    (bottom - top) / page_h,
                ),
                font_size_pt=round(em_px * pt_per_px, 2),
                color=core_colour(crop_region, region, text_colour),
                italic=slant_value > ITALIC_SLANT,
                script=script,
                bullet=had_bullet_char,
                mark_x=(box.x + mark_left) / page_w,
                conf=round(box.conf, 3),
                source_box=box,
                metrics=TextMetrics(
                    stroke_px=round(stroke_px, 2),
                    stroke_ratio=round(stroke_px / em_px, 3) if em_px > 0 else 0.0,
                    stroke_ratio_area=round(area_px / em_px, 4) if em_px > 0 else 0.0,
                    em_ref_px=round(em_px * REFERENCE_PAGE_WIDTH / page_w, 2),
                    stroke_cv=round(stroke_cv, 3),
                    slant=round(slant_value, 3),
                ),
            )
        )

    resolve_bold(blocks, bold_mode)
    if expected:
        snap_to_expected(blocks, expected)
    return blocks


def snap_to_expected(blocks, expected):
    """Correct near-miss transcriptions against known copy, e.g. PPTX XML text.

    Only exact-length near matches are replaced. The known copy is more
    reliable than reading pixels, but it must never introduce text that is not
    on the page.
    """
    pool = [line.strip() for line in expected if line and line.strip()]
    for block in blocks:
        current = block.text.strip()
        if not current or current in pool:
            continue
        for candidate in pool:
            if "".join(candidate.split()) == "".join(current.split()):
                block.text = candidate
                break
            if len(candidate) != len(current):
                continue
            differences = sum(1 for a, b in zip(candidate, current) if a != b)
            if differences and differences <= max(1, len(current) // 8):
                block.text = candidate
                break


def colour_distance(left, right):
    def channels(value):
        value = value.lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    try:
        a, b = channels(left), channels(right)
    except (ValueError, IndexError):
        return 255
    return sum(abs(x - y) for x, y in zip(a, b))


def left_aligned(previous, block):
    return abs(block.bbox[0] - previous.bbox[0]) <= max(0.006, previous.bbox[2] * 0.15)


def centred(previous, block):
    middle = lambda b: b.bbox[0] + b.bbox[2] / 2
    return abs(middle(block) - middle(previous)) <= CENTRE_TOLERANCE


def even_pitch(chain):
    """Cut a chain where the line pitch changes: that is the next paragraph."""
    parts, current, pitch = [], [chain[0]], None
    for previous, block in zip(chain, chain[1:]):
        step = (block.bbox[1] + block.bbox[3]) - (previous.bbox[1] + previous.bbox[3])
        if pitch is not None and abs(step - pitch) > pitch * PARAGRAPH_PITCH_TOLERANCE:
            parts.append(current)
            current, pitch = [block], None
            continue
        pitch = step if pitch is None else pitch
        current.append(block)
    parts.append(current)
    return parts


def continues(previous, block):
    """Is `block` the next line of the paragraph `previous` starts?"""
    line_height = previous.bbox[3]
    if line_height <= 0:
        return False

    gap = block.bbox[1] - (previous.bbox[1] + previous.bbox[3])
    if not -line_height * 0.25 <= gap <= line_height * 1.5:
        return False
    if not (left_aligned(previous, block) or centred(previous, block)):
        return False

    return (
        abs(block.font_size_pt - previous.font_size_pt) <= max(1.0, previous.font_size_pt * 0.12)
        and colour_distance(block.color, previous.color) <= MERGE_COLOUR_TOLERANCE
        and block.bold == previous.bold
        and block.bullet == previous.bullet
        and block.font_family == previous.font_family
        and block.font_face == previous.font_face
        and (not (block.font_matches or previous.font_matches)
             or block.italic == previous.italic)
    )


def merge_lines(blocks):
    """Join consecutive OCR lines that belong to one paragraph.

    OCR reports one box per line, so a four-line paragraph becomes four text
    boxes and editing it means editing four things.

    Lines are chained by looking downward for each block's own successor,
    rather than by scanning in reading order. Reading order interleaves
    side-by-side columns, which severs every paragraph on a two-column page.
    """
    if not blocks:
        return blocks

    ordered = sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
    successor = {}
    claimed = set()

    for i, block in enumerate(ordered):
        best = None
        for j in range(i + 1, len(ordered)):
            if j in claimed or not continues(block, ordered[j]):
                continue
            if best is None or ordered[j].bbox[1] < ordered[best].bbox[1]:
                best = j
        if best is not None:
            successor[i] = best
            claimed.add(best)

    chains = []
    for i, head in enumerate(ordered):
        if i in claimed:
            continue

        chain = [head]
        cursor = i
        while cursor in successor:
            cursor = successor[cursor]
            chain.append(ordered[cursor])
        chains.extend(even_pitch(chain))

    merged = []
    for chain in chains:
        head = chain[0]
        if len(chain) == 1:
            merged.append(head)
            continue

        left = min(b.bbox[0] for b in chain)
        top = min(b.bbox[1] for b in chain)
        right = max(b.bbox[0] + b.bbox[2] for b in chain)
        bottom = max(b.bbox[1] + b.bbox[3] for b in chain)
        # Bottoms rather than tops: a line of all-lowercase or punctuation has
        # a lower top, but every line sits on its baseline.
        pitches = [
            (b.bbox[1] + b.bbox[3]) - (a.bbox[1] + a.bbox[3])
            for a, b in zip(chain, chain[1:])
        ]
        runs = []
        if all(block.runs for block in chain):
            for block in chain:
                if runs:
                    runs.append({"text": "\n"})
                runs.extend(block.runs)
        merged.append(
            TextBlock(
                id=head.id,
                text="\n".join(b.text for b in chain),
                bbox=clamp_bbox(left, top, right - left, bottom - top),
                font_size_pt=head.font_size_pt,
                color=head.color,
                bold=head.bold,
                italic=head.italic,
                script=head.script,
                align=head.align if all(left_aligned(a, b) for a, b in zip(chain, chain[1:])) else "center",
                bullet=head.bullet,
                mark_x=min(b.mark_x for b in chain),
                line_pitch=float(np.median(pitches)),
                conf=min(b.conf for b in chain),
                metrics=head.metrics,
                font_family=head.font_family,
                font_face=head.font_face,
                font_matches=[match for b in chain for match in b.font_matches],
                runs=runs,
                style_report={"lines": [b.style_report for b in chain],
                              "needs_review": any(b.style_report.get("needs_review", False) for b in chain)}
                if any(b.style_report for b in chain) else {},
            )
        )

    return sorted(merged, key=lambda b: (b.bbox[1], b.bbox[0]))


def text_frame(block, slide_width_pt, slide_height_pt):
    """The text box to compose, in page fractions.

    The measured ink bounds are too tight to compose into: the opening machine
    substitutes fonts, and PowerPoint draws leading above the first baseline.
    The frame starts at the bullet mark, sits a little above the ink, and
    leaves width slack so the text does not wrap.
    """
    x, y, w, h = block.bbox
    if block.bullet:
        w += x - block.mark_x
        x = block.mark_x
    lift_pt = block.font_size_pt * BASELINE_LIFT
    if block.line_pitch > 0:
        spacing_pt = block.line_pitch * slide_height_pt
        added_pt = spacing_pt - block.font_size_pt * SINGLE_SPACING_EM
        lift_pt += max(0.0, added_pt) * EXACT_SPACING_LIFT
    lift = lift_pt / slide_height_pt
    extra_w = TEXT_WIDTH_EXTRA_PT / slide_width_pt
    extra_h = TEXT_HEIGHT_EXTRA_PT / slide_height_pt
    top = max(0.0, y - lift)
    height = h + lift + extra_h
    if block.font_matches or block.runs:
        height = max(height, block.font_size_pt * 1.3 / slide_height_pt)
    width = w * TEXT_WIDTH_SLACK + extra_w
    if block.align == "center":
        # Slack on both sides keeps centred lines over the source ink.
        x = max(0.0, x - (width - w) / 2)
    return clamp_bbox(x, top, width, height)


def slide_number(path, index):
    digits = re.findall(r"\d+", Path(path).stem)
    return int(digits[-1]) if digits else index + 1


def to_px(bbox, page_w, page_h):
    x, y, w, h = bbox
    return [round(x * page_w), round(y * page_h), round(w * page_w), round(h * page_h)]


def to_frac(bbox):
    return [round(v, 6) for v in bbox]


def block_record(block, page_w, page_h, slide_width_pt):
    slide_height_pt = slide_width_pt * page_h / page_w
    frame = text_frame(block, slide_width_pt, slide_height_pt)
    text = block.text
    if block.bullet:
        # The bullet glyph was stripped from the OCR text and measured as a
        # mark; write it back so the composed box shows it.
        text = "\n".join(f"• {line}" for line in text.split("\n"))
    record = {
        "id": block.id,
        "text": text,
        "bbox_px": to_px(frame, page_w, page_h),
        "bbox_frac": to_frac(frame),
        "ink_bbox_px": to_px(block.bbox, page_w, page_h),
        "ink_bbox_frac": to_frac(block.bbox),
        "font_size_pt": block.font_size_pt,
        "color": block.color,
        "bold": block.bold,
        "italic": block.italic,
        "align": block.align,
        "font_family": block.font_family,
        "bullet": block.bullet,
        "script": block.script,
        "conf": block.conf,
        "metrics": {
            "stroke_px": block.metrics.stroke_px,
            "stroke_ratio": block.metrics.stroke_ratio,
            "stroke_ratio_area": block.metrics.stroke_ratio_area,
            "em_ref_px": block.metrics.em_ref_px,
            "stroke_cv": block.metrics.stroke_cv,
            "slant": block.metrics.slant,
        },
    }
    if block.font_matches:
        record["font_matches"] = block.font_matches
        record["font_face"] = block.font_face
    if block.runs:
        record["runs"] = block.runs
        record["style_report"] = block.style_report
    if block.line_pitch > 0:
        # Merged lines keep the page's own spacing; PowerPoint's default
        # single spacing packs them much tighter than most slide designs.
        record["line_spacing_pt"] = round(block.line_pitch * slide_height_pt, 2)
    return record


def harmonise_font_matches(blocks):
    """Choose a common near-best face for blocks already measured as one style."""
    groups = []
    for block in blocks:
        if not block.font_matches or not block.font_matches[0]["candidates"]:
            continue
        group = next((group for group in groups
                      if all(siblings(block, member) and block.script == member.script
                             and block.bold == member.bold and block.italic == member.italic
                             for member in group)), None)
        if group is None:
            groups.append([block])
        else:
            group.append(block)

    for group in groups:
        if len(group) < 2:
            continue
        rankings = []
        for block in group:
            candidates = block.font_matches[0]["candidates"]
            rankings.append({(c.get("face_name", c["family"]), c["bold"], c["italic"]): c
                             for c in candidates})
        shared = set.intersection(*(set(ranking) for ranking in rankings))
        if not shared:
            continue
        chosen = min(sorted(shared), key=lambda key: sum(ranking[key]["shape_error"]
                                                         for ranking in rankings))
        # A shared style is only accepted when it stays close to every line's
        # own best result. Preserve individual rankings for later inspection.
        penalties = [ranking[chosen]["shape_error"] - min(c["shape_error"] for c in ranking.values())
                     for ranking in rankings]
        if max(penalties) > 0.08 or float(np.mean(penalties)) > 0.025:
            continue
        for block, ranking in zip(group, rankings):
            block.font_matches[0]["selected_candidate"] = ranking[chosen]
            block.font_matches[0]["selection"] = "shared_style"


def run_script(run):
    return "cjk" if is_cjk(run["text"]) else "latin"


def harmonise_runs(blocks, pt_per_px):
    """Give text measured as one style one face, weight and size.

    Each line is matched on its own, and near-equal candidates swap places from
    line to line. Left alone, three cards of one design come out in three
    fonts, and a paragraph cannot merge because its lines disagree.
    """
    from rich_text import share_face

    units = []
    for block in blocks:
        visible = [run for run in block.runs if run["text"].strip()]
        if len(visible) != len(block.font_matches):
            continue
        units.extend((block, run, report) for run, report in zip(visible, block.font_matches)
                     if report.get("candidates") and "color" in run)

    def alike(left, right):
        return (siblings(left[0], right[0]) and run_script(left[1]) == run_script(right[1])
                and colour_distance(left[1]["color"], right[1]["color"]) <= SIBLING_COLOUR_TOLERANCE)

    groups = []
    for unit in units:
        group = next((g for g in groups if all(alike(unit, member) for member in g)), None)
        if group is None:
            groups.append([unit])
        else:
            group.append(unit)

    for group in groups:
        if len(group) < 2:
            continue
        share_face([(run, report) for _, run, report in group], pt_per_px, "shared_style")
        # One face at near-equal sizes is one size.
        faces = {}
        for _, run, _ in group:
            faces.setdefault((run["font_face"], run["bold"], run["italic"]), []).append(run)
        for runs in faces.values():
            size = float(np.median([run["font_size_pt"] for run in runs]))
            for run in runs:
                if abs(run["font_size_pt"] - size) <= size * 0.08:
                    run["font_size_pt"] = round(size, 2)
    for block in blocks:
        styled = [run for run in block.runs if run.get("font_size_pt")]
        if styled:
            block.font_family = styled[0].get("font_family", block.font_family)
            block.font_face = styled[0].get("font_face", block.font_face)
            block.font_size_pt = max(run["font_size_pt"] for run in styled)


def progress(path, position, total, block):
    """One line per text line, so a long matching run is visibly alive."""
    text = block.text.replace("\n", " ")
    print(f"{Path(path).name} [{position}/{total}] {text[:24]}", file=sys.stderr, flush=True)


def build_layout(image_paths, bold_mode="auto", merge=True, expected=None,
                 slide_width_in=DEFAULT_SLIDE_WIDTH_IN, font_matcher=None, rich_text=False,
                 photo_regions=None):
    slide_width_pt = slide_width_in * 72
    slides = []
    ref_w = ref_h = None

    seen = {}
    pages = []
    for index, path in enumerate(image_paths):
        page_h, page_w = read_image(path).shape[:2]
        if ref_w is None:
            ref_w, ref_h = page_w, page_h

        number = slide_number(path, index)
        if number in seen:
            raise SystemExit(
                f"{Path(path).name} and {Path(seen[number]).name} both map to slide {number}; "
                "name the pages slide_001.png, slide_002.png, ..."
            )
        seen[number] = path
        blocks = extract_text(path, f"s{number}", bold_mode, expected, slide_width_pt,
                              (photo_regions or {}).get(number, ()))
        pages.append((path, number, page_w, page_h, blocks))

    # Weight is decided across the deck, before lines merge, since merging
    # keeps bold and regular lines apart.
    offset = 0.0
    if (bold_mode or "auto").strip().lower() == "auto":
        offset = deck_weight_offset([block for *_, blocks in pages for block in blocks])
        for *_, blocks in pages:
            resolve_bold(blocks, "auto", offset)

    for path, number, page_w, page_h, blocks in pages:
        line_count = len(blocks)
        if rich_text:
            from rich_text import analyse_line
            image = read_image(path)
            for position, block in enumerate(blocks, 1):
                progress(path, position, line_count, block)
                analyse_line(image, block, slide_width_pt / page_w, font_matcher)
            if font_matcher is not None:
                harmonise_runs(blocks, slide_width_pt / page_w)
        elif font_matcher is not None:
            from match_fonts import crop_mask

            image = read_image(path)
            for position, block in enumerate(blocks, 1):
                progress(path, position, line_count, block)
                mask = crop_mask(image, to_px(block.bbox, page_w, page_h))
                result = font_matcher.match(mask, block.text)
                result["line_id"] = block.id
                block.font_matches = [result]
            harmonise_font_matches(blocks)
            for block in blocks:
                result = block.font_matches[0]
                if result["candidates"]:
                    best = result.get("selected_candidate", result["candidates"][0])
                    block.font_family = best["family"]
                    block.font_face = best.get("face_name", best["family"])
                    block.bold = best["bold"]
                    block.italic = best["italic"]
                    if best.get("size_px"):
                        block.font_size_pt = round(best["size_px"] * slide_width_pt / page_w, 2)
        if merge:
            blocks = merge_lines(blocks)
        print(f"{Path(path).name}: {line_count} lines -> {len(blocks)} text boxes")

        slides.append({
            "slide": number,
            "source": Path(path).name,
            "width": page_w,
            "height": page_h,
            "texts": [block_record(b, page_w, page_h, slide_width_pt) for b in blocks],
        })

    return {
        "method": "ocr",
        "ocr_engine": _engine_name,
        "bold_mode": bold_mode,
        "bold_offset": round(offset, 4),
        "slide_width_in": slide_width_in,
        "ref_width": ref_w,
        "ref_height": ref_h,
        "slides": slides,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("images", nargs="+", help="Source slide images, e.g. source/slide_*.png")
    ap.add_argument("--out", default="analysis/texts_layout.json")
    ap.add_argument(
        "--bold-mode",
        default="auto",
        help="auto | off | on | ratio:<stroke_ratio_area threshold>, e.g. ratio:0.1",
    )
    ap.add_argument("--no-merge-lines", action="store_true",
                    help="Keep one text box per OCR line instead of merging paragraphs")
    ap.add_argument("--expected", help="UTF-8 file of known text, one string per line "
                                       "(e.g. text from PPTX XML) to correct near-miss OCR")
    ap.add_argument("--slide-width-in", type=float, default=DEFAULT_SLIDE_WIDTH_IN,
                    help="Composed slide width; must match slide_width_in in the compose spec")
    ap.add_argument("--element-analysis",
                    help="element_analysis.json; text inside its photo_source_crop boxes is left in the photograph")
    ap.add_argument("--font-index", help="Local font index from match_fonts.py index")
    ap.add_argument("--font-model", help="Trained ONNX font encoder from train_font_matcher.py")
    ap.add_argument("--rich-text", action=argparse.BooleanOptionalAction, default=True,
                    help="Measure inline styles and editable effects (enabled by default)")
    ap.add_argument("--ocr-only", action="store_true",
                    help="Explicit legacy OCR measurement mode for analysis")
    ap.add_argument("--font-server", help="Font release URL ending in /fonts/v1, used to download the core pack")
    ap.add_argument("--remote-match", action="store_true",
                    help="Also send poor local matches to the font server (off by default)")
    ap.add_argument("--font-cache", type=Path, help="Downloaded font cache directory")
    args = ap.parse_args()

    if args.slide_width_in <= 0:
        raise SystemExit("--slide-width-in must be positive")
    if bool(args.font_index) != bool(args.font_model):
        ap.error("--font-index and --font-model must be supplied together")
    font_matcher = None
    if args.ocr_only:
        if args.font_index or args.font_model or args.font_server or args.font_cache or args.remote_match:
            ap.error("--ocr-only conflicts with font matching options")
        args.rich_text = False
    else:
        from font_store import FontStore, RemoteFontMatcher
        from match_fonts import DEFAULT_FONT_SERVER, FontMatcher
        try:
            store = FontStore(args.font_server or DEFAULT_FONT_SERVER, args.font_cache)
            if not args.font_index:
                args.font_index, args.font_model = store.install_core(include_system=True)
            font_matcher = FontMatcher(args.font_index, args.font_model)
            # Local fonts decide by default. The server is opt-in because a slow
            # response stalls every poorly matched line.
            if args.remote_match:
                font_matcher = RemoteFontMatcher(font_matcher, store)
        except (OSError, ValueError) as error:
            ap.exit(2, f"Font matching setup failed. Check the font server or cache. {error}\n")
    expected = None
    if args.expected:
        expected = Path(args.expected).read_text(encoding="utf-8-sig").splitlines()

    layout = build_layout(
        args.images,
        bold_mode=args.bold_mode,
        merge=not args.no_merge_lines,
        expected=expected,
        slide_width_in=args.slide_width_in,
        font_matcher=font_matcher,
        rich_text=args.rich_text,
        photo_regions=photo_regions(args.element_analysis) if args.element_analysis else None,
    )
    layout["font_matching_required"] = not args.ocr_only
    if not args.ocr_only:
        from match_fonts import validate_font_matches
        try:
            for slide in layout["slides"]:
                for item in slide["texts"]:
                    validate_font_matches(item)
        except ValueError as error:
            ap.exit(2, f"Font matching incomplete. {error}\n")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
