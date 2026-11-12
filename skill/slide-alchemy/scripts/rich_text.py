"""Measure inline styles and simple effects from OCR-localized text lines."""
import re

import cv2
import numpy as np

from text_effects import fit_effects, gradient_field, hex_colour, infer_gradient


def foreground(crop, background):
    distance = np.abs(crop.astype(np.float32) - background).sum(axis=2)
    return (distance >= max(35, float(distance.max()) * 0.25)).astype(np.uint8)


def fill_alpha(rgb, background, fill):
    """Recover AA coverage near opaque fill, leaving displaced shadows outside."""
    span = np.asarray(fill) - background
    length = np.maximum(np.sum(span * span, axis=-1), 1)
    coverage = np.clip(np.sum((rgb - background) * span, axis=2) / length, 0, 1)
    predicted = background + coverage[..., None] * span
    on_colour = np.linalg.norm(rgb - predicted, axis=2) < 30
    core = (coverage > 0.8) & on_colour
    support = cv2.dilate(core.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return (coverage * support * on_colour).astype(np.float32)


def character_samples(image, box, text, background):
    """Keep character offsets so spans preserve all original spaces/punctuation."""
    from extract_text import BULLET_CHARS, is_cjk, stroke_metrics

    indices = [i for i, char in enumerate(text) if not char.isspace()]
    columns = box.chars
    if columns and len(columns) == len(indices) + 1 and box.text.lstrip()[0] in BULLET_CHARS:
        columns = columns[1:]
    if columns is None or len(columns) != len(indices):
        return []
    samples = []
    for index, (left, right) in zip(indices, columns):
        x0, x1 = max(0, int(round(left))), min(image.shape[1], int(round(right)))
        y0, y1 = max(0, box.y), min(image.shape[0], box.y + box.h)
        crop = image[y0:y1, x0:x1]
        if not crop.size:
            return []
        mask = foreground(crop, background)
        if not mask.any():
            return []
        depth = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        threshold = min(float(depth.max()), max(1, float(np.percentile(depth[mask > 0], 70))))
        core = depth >= threshold
        rgb = np.median(crop[core], axis=0)[::-1]
        fill_distance = np.linalg.norm(crop[..., ::-1].astype(float) - rgb, axis=2)
        fill_mask = (fill_distance < 70) & (mask > 0)
        width, _ = stroke_metrics(fill_mask.astype(np.uint8))
        char = text[index]
        script = "cjk" if is_cjk(char) else "latin"
        if not char.isalnum():
            following = next((c for c in text[index + 1:] if c.isalnum()), "")
            script = samples[-1]["script"] if samples else ("cjk" if is_cjk(following) else "latin")
        samples.append({"index": index, "x0": x0, "x1": x1, "color": rgb,
                        "stroke": width,
                        "script": script})
    return samples


def style_boundaries(samples, gradient, include_weight=True):
    boundaries = []
    for index in range(1, len(samples)):
        previous, current = samples[index - 1:index + 1]
        colour_change = not gradient and np.linalg.norm(previous["color"] - current["color"]) > 55
        script_change = previous["script"] != current["script"]
        if colour_change or script_change:
            boundaries.append(current["index"])
    # A persistent width change provides evidence for a weight/style boundary.
    for index in range(2, len(samples) - 1) if include_weight else []:
        left = np.array([s["stroke"] for s in samples[index - 2:index]])
        right = np.array([s["stroke"] for s in samples[index:index + 2]])
        low, high = sorted([float(np.median(left)), float(np.median(right))])
        if low > 0 and high > low * 1.35 and np.ptp(left) < low * 0.15 and np.ptp(right) < high * 0.15:
            boundaries.append(samples[index]["index"])
    return sorted(set(boundaries))


def font_boundaries(image, box, text, samples, background, matcher):
    """Propose boundaries from word gaps and sustained local font evidence."""
    boundaries = []
    for previous, current in zip(samples, samples[1:]):
        whitespace = text[previous["index"] + 1:current["index"]]
        before = text[:current["index"]].strip()
        after = text[current["index"]:].strip()
        if whitespace.isspace() and len(before) >= 3 and len(after) >= 3:
            boundaries.append(current["index"])
    windows = []
    for start in range(len(samples) - 3):
        group = samples[start:start + 4]
        chunk = text[group[0]["index"]:group[-1]["index"] + 1]
        crop = image[box.y:box.y + box.h, group[0]["x0"]:group[-1]["x1"]]
        if not crop.size:
            continue
        fill = np.median([sample["color"] for sample in group], axis=0)
        alpha = fill_alpha(crop[..., ::-1].astype(float), background[::-1], fill)
        if not (alpha >= 0.4).any():
            continue
        ranking, _ = matcher.rank_fonts(alpha * 255, chunk, 2)
        if len(ranking) < 2 or ranking[0][2] - ranking[1][2] <= 0.08:
            continue
        font = ranking[0][0]
        windows.append(((group[0]["index"] + group[-1]["index"]) / 2,
                        font.get("face_name", font["family"])))
    for index in range(2, len(windows) - 1):
        left, right = windows[index - 2:index], windows[index:index + 2]
        if (left[0][1] == left[1][1] and right[0][1] == right[1][1]
                and left[0][1] != right[0][1] and right[0][0] - left[-1][0] <= 4):
            boundaries.append(int((left[-1][0] + right[0][0] + 1) // 2))
    return sorted(set(boundaries))


# A part keeps a font of its own only when its match is this good and the
# line's font is this much worse for it. Anything less is matching noise.
CONFIDENT_MATCH = 0.08
STYLE_PENALTY = 0.08


def face_key(candidate):
    return candidate.get("face_name", candidate["family"]), candidate["bold"], candidate["italic"]


def selected(report):
    return report.get("selected_candidate", report["candidates"][0])


def adopt(run, report, candidate, pt_per_px, selection):
    """Point a run and its matching report at one candidate."""
    if candidate not in report["candidates"]:
        report["candidates"].append(candidate)
    report["selected_candidate"] = candidate
    report["selection"] = selection
    run.update(font_family=candidate["family"], font_face=candidate.get("face_name", candidate["family"]),
               bold=candidate["bold"], italic=candidate["italic"])
    if candidate.get("size_px"):
        run["font_size_pt"] = round(candidate["size_px"] * pt_per_px, 2)


def lettered(cuts, text):
    """Drop cuts that leave a stretch of punctuation alone.

    An interpunct or quote is no style of its own: it reads as a colour or
    script change, then gets matched to a symbol font.
    """
    cuts = list(cuts)
    index = 1
    while len(cuts) > 2 and index < len(cuts):
        if any(char.isalnum() for char in text[cuts[index - 1]:cuts[index]]):
            index += 1
        else:
            del cuts[index if index < len(cuts) - 1 else index - 1]
    return cuts


def share_face(units, pt_per_px, selection):
    """Give runs measured as one style one face, by majority.

    `units` are (run, report) pairs. Each was matched on its own, and near
    equal candidates trade places from run to run. The face most runs can
    accept wins. A run stays apart only on strong evidence: a confident match
    of its own that the common face would clearly worsen.
    """
    units = [(run, report) for run, report in units if report.get("candidates")]
    if len(units) < 2:
        return
    rankings = [{face_key(c): c for c in report["candidates"]} for _, report in units]
    best = [min(c["shape_error"] for c in ranking.values()) for ranking in rankings]
    weights = [len(run["text"].strip()) for run, _ in units]

    def support(key):
        fits = [weight for ranking, low, weight in zip(rankings, best, weights)
                if key in ranking and ranking[key]["shape_error"] - low <= STYLE_PENALTY]
        cost = sum(ranking[key]["shape_error"] for ranking in rankings if key in ranking)
        return sum(fits), -cost

    keys = sorted({key for ranking in rankings for key in ranking})
    chosen = max(keys, key=support)
    if support(chosen)[0] * 2 < sum(weights):
        return
    donor = max((ranking[chosen] for ranking in rankings if chosen in ranking),
                key=lambda c: -c["shape_error"])
    for (run, report), ranking, low in zip(units, rankings, best):
        own = ranking.get(chosen)
        penalty = own["shape_error"] - low if own else float("inf")
        if low <= CONFIDENT_MATCH and penalty > STYLE_PENALTY:
            continue
        if own is None:
            # The face missed this run's shortlist; record that it was taken
            # from the neighbouring runs instead of measured here.
            own = dict(donor, inherited=True)
        adopt(run, report, own, pt_per_px, selection)


def analyse_line(image, block, pt_per_px, matcher=None):
    from extract_text import font_height_px, ring_background

    box = block.source_box
    if box is None:
        return
    background_bgr = ring_background(image, box)
    text = block.text
    if (block.bullet and box.chars and box.text.lstrip()[0].isalnum()
            and box.chars[0][0] - box.x < box.h * 0.3):
        block.bullet = False
    samples = character_samples(image, box, text, background_bgr)
    raw_crop = image[box.y:box.y + box.h, box.x:box.x + box.w]
    all_ink = foreground(raw_crop, background_bgr)
    line_gradient = infer_gradient(raw_crop[..., ::-1], all_ink.astype(float))
    # Colour, script and weight changes are measured, so they always part the
    # line. Font evidence alone is a proposal, checked against the whole line.
    hard = style_boundaries(samples, line_gradient)
    proposed = []
    if matcher is not None and samples and not line_gradient:
        proposed = [cut for cut in font_boundaries(image, box, text, samples, background_bgr, matcher)
                    if cut not in hard]

    def measure(start, stop):
        chunk = text[start:stop]
        group = [s for s in samples if start <= s["index"] < stop]
        x0 = group[0]["x0"] if group else box.x
        x1 = group[-1]["x1"] if group else box.x + box.w
        y0, y1 = box.y, min(image.shape[0], box.y + box.h)
        crop = image[y0:y1, x0:x1]
        ink = foreground(crop, background_bgr)
        rgb = crop[..., ::-1].astype(float)
        if group:
            fill_colour = np.median([s["color"] for s in group], axis=0)
        else:
            depth = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
            if ink.any():
                threshold = min(float(depth.max()), max(1, float(np.percentile(depth[ink > 0], 70))))
                core = depth >= threshold
            else:
                core = ink > 0
            fill_colour = np.median(rgb[core], axis=0) if core.any() else np.array([0, 0, 0])
        if line_gradient:
            rows, cols = np.nonzero(ink)
            bounds = (cols.min(), rows.min(), cols.max(), rows.max()) if len(rows) else None
            fill = gradient_field(ink.shape, line_gradient, bounds)
        else:
            fill = fill_colour
        observed_alpha = fill_alpha(rgb, background_bgr[::-1], fill)
        fill_mask = (observed_alpha >= 0.4).astype(np.uint8)
        if not fill_mask.any():
            fill_mask = ink
            observed_alpha = ink.astype(np.float32)
        if not fill_mask.any() or not chunk.strip():
            return {"run": {"text": chunk}}
        rows, cols = np.nonzero(fill_mask)
        left, top, right, bottom = cols.min(), rows.min(), cols.max() + 1, rows.max() + 1
        glyph = observed_alpha[top:bottom, left:right] * 255
        run = {"text": chunk, "color": hex_colour(fill_colour), "bold": block.bold,
               "italic": block.italic, "font_family": block.font_family,
               "font_face": block.font_face, "font_size_pt": block.font_size_pt}
        # Pad the observed fill mask so outlines and shifted shadows are visible.
        pad = 12
        px0, py0 = max(0, x0 - pad), max(0, y0 - pad)
        px1, py1 = min(image.shape[1], x1 + pad), min(image.shape[0], y1 + pad)
        effect_crop = image[py0:py1, px0:px1, ::-1]
        alpha = np.zeros(effect_crop.shape[:2], np.float32)
        alpha[y0 - py0:y1 - py0, x0 - px0:x1 - px0] = observed_alpha
        fitted = fit_effects(effect_crop, alpha, background_bgr[::-1], fill_colour, pt_per_px)
        run["effects"] = fitted["effects"]
        piece = {"run": run}
        if matcher is not None:
            if fitted["effects"].get("outline"):
                radius = max(1, round(fitted["effects"]["outline"]["width_pt"] / pt_per_px / 2))
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
                glyph = cv2.dilate(observed_alpha, kernel) * 255
            match = matcher.match(glyph, chunk.strip())
            piece["report"] = match
            if match["candidates"]:
                first = match["candidates"][0]
                close = [candidate for candidate in match["candidates"]
                         if candidate["shape_error"] <= first["shape_error"] + 0.005]
                best = max(close, key=lambda candidate: candidate["model_similarity"])
                match["selected_candidate"] = best
                match["selection"] = "model_tiebreak" if best is not first else "shape_error"
                run.update(font_family=best["family"], font_face=best["face_name"],
                           bold=best["bold"], italic=best["italic"],
                           font_size_pt=round(best["size_px"] * pt_per_px, 2))
        else:
            script = "cjk" if re.search(r"[\u3400-\u9fff]", chunk) else "latin"
            run["font_size_pt"] = round(font_height_px((glyph > 0).astype(np.uint8), script) / (0.94 if script == "cjk" else 0.75) * pt_per_px, 2)
        run["style_fit"] = {k: v for k, v in fitted.items() if k != "effects"}
        run["ink_bbox_px"] = [int(x0 + left), int(y0 + top), int(right - left), int(bottom - top)]
        return piece

    cuts = lettered([0, *sorted(set(hard)), len(text)], text)

    pieces = []
    for start, stop in zip(cuts, cuts[1:]):
        inner = lettered([start, *(cut for cut in proposed if start < cut < stop), stop], text)
        # Words are matched one at a time, since a space rarely renders at the
        # source's width, and then share one face.
        parts = [measure(a, b) for a, b in zip(inner, inner[1:])]
        share_face([(part["run"], part["report"]) for part in parts if "report" in part],
                   pt_per_px, "line_style")
        pieces.extend(parts)

    runs = [piece["run"] for piece in pieces]
    reports = [piece["report"] for piece in pieces if "report" in piece]
    ink_boxes = [run["ink_bbox_px"] for run in runs if "ink_bbox_px" in run]
    if line_gradient and len(pieces) == 1 and "effects" in runs[0]:
        runs[0]["effects"]["gradient"] = line_gradient
    block.runs = runs
    if block.bullet and runs:
        runs[0]["text"] = "\u2022 " + runs[0]["text"]
    if reports:
        block.font_matches = reports
    if runs:
        block.font_family = runs[0].get("font_family", block.font_family)
        block.font_face = runs[0].get("font_face", block.font_face)
    block.style_report = {"character_positions": bool(samples), "spans": len(runs),
                          "font_matches": reports, "needs_review": not bool(samples)
                          or any(report.get("needs_review", False) for report in reports)
                          or any(r.get("style_fit", {}).get("needs_review", False) for r in runs)}
    if ink_boxes:
        x = min(b[0] for b in ink_boxes)
        y = min(b[1] for b in ink_boxes)
        right = max(b[0] + b[2] for b in ink_boxes)
        bottom = max(b[1] + b[3] for b in ink_boxes)
        block.bbox = (x / image.shape[1], y / image.shape[0], (right - x) / image.shape[1], (bottom - y) / image.shape[0])
        block.font_size_pt = max(r.get("font_size_pt", block.font_size_pt) for r in runs)
