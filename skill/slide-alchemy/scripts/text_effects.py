"""Native editable text effects and bounded pixel fitting for common effects."""
import math

import cv2
import numpy as np
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
from pptx.oxml.ns import qn
from pptx.util import Pt


# A fit worse than this leaves visible differences: bevels, extrusion, texture.
# Plain text lands near 20-30 from antialiasing alone.
REVIEW_RMSE = 45
# An effect is kept when it lowers the squared pixel error to this share.
OUTLINE_GAIN = 0.85
SHADOW_GAIN = 0.78
# A gradient gets a middle stop when its midpoint is this far off a straight blend.
MIDDLE_STOP_DISTANCE = 40
# A shadow this close to the fill colour is part of the lettering.
SHADOW_FILL_DISTANCE = 100


def colour(value):
    value = str(value).lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return str(RGBColor.from_string(value.upper()))


def number(value, name, minimum=None, maximum=None):
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        raise ValueError(f"invalid {name}: {value!r}")
    return result


def colour_element(value, opacity=1):
    element = OxmlElement("a:srgbClr")
    element.set("val", colour(value))
    alpha = OxmlElement("a:alpha")
    alpha.set("val", str(round(number(opacity, "opacity", 0, 1) * 100000)))
    element.append(alpha)
    return element


def apply_effects(run, effects):
    """Write DrawingML properties before font children, in schema order."""
    if not effects:
        return
    unknown = set(effects) - {"gradient", "outline", "shadow"}
    if unknown:
        raise ValueError(f"unsupported text effects: {sorted(unknown)}")
    properties = run._r.get_or_add_rPr()
    if effects.get("outline"):
        spec = effects["outline"]
        outline = OxmlElement("a:ln")
        outline.set("w", str(Pt(number(spec["width_pt"], "outline width", 0))))
        fill = OxmlElement("a:solidFill")
        fill.append(colour_element(spec["color"], spec.get("opacity", 1)))
        outline.append(fill)
        old = properties.find(qn("a:ln"))
        if old is not None:
            properties.remove(old)
        properties.insert(0, outline)
    if effects.get("gradient"):
        spec = effects["gradient"]
        stops = spec["stops"]
        if len(stops) < 2:
            raise ValueError("a text gradient needs at least two stops")
        positions = [number(stop["position"], "gradient position", 0, 1) for stop in stops]
        if any(a >= b for a, b in zip(positions, positions[1:])):
            raise ValueError("gradient stops must have increasing positions")
        gradient = OxmlElement("a:gradFill")
        gradient.set("rotWithShape", "1")
        stop_list = OxmlElement("a:gsLst")
        for stop, position in zip(stops, positions):
            item = OxmlElement("a:gs")
            item.set("pos", str(round(position * 100000)))
            item.append(colour_element(stop["color"], stop.get("opacity", 1)))
            stop_list.append(item)
        gradient.append(stop_list)
        linear = OxmlElement("a:lin")
        angle = number(spec.get("angle", 90), "gradient angle") % 360
        linear.set("ang", str(round(angle * 60000)))
        linear.set("scaled", "1")
        gradient.append(linear)
        for tag in ("a:noFill", "a:solidFill", "a:gradFill", "a:blipFill", "a:pattFill", "a:grpFill"):
            old = properties.find(qn(tag))
            if old is not None:
                properties.remove(old)
        properties.insert(1 if properties.find(qn("a:ln")) is not None else 0, gradient)
    if effects.get("shadow"):
        spec = effects["shadow"]
        dx = number(spec.get("offset_x_pt", 0), "shadow x offset")
        dy = number(spec.get("offset_y_pt", 0), "shadow y offset")
        shadow = OxmlElement("a:outerShdw")
        shadow.set("blurRad", str(Pt(number(spec.get("blur_pt", 0), "shadow blur", 0))))
        shadow.set("dist", str(Pt(math.hypot(dx, dy))))
        shadow.set("dir", str(round((math.degrees(math.atan2(dy, dx)) % 360) * 60000)))
        shadow.set("rotWithShape", "0")
        shadow.append(colour_element(spec.get("color", "#000000"), spec.get("opacity", 0.5)))
        effect_list = OxmlElement("a:effectLst")
        effect_list.append(shadow)
        old = properties.find(qn("a:effectLst"))
        if old is not None:
            properties.remove(old)
        properties.insert_element_before(effect_list, "a:latin", "a:ea", "a:cs", "a:sym", "a:hlinkClick", "a:hlinkMouseOver", "a:extLst")


def hex_colour(rgb):
    return "#" + "".join(f"{int(c):02X}" for c in np.clip(np.round(rgb), 0, 255))


def gradient_field(shape, gradient, bounds=None):
    height, width = shape
    y, x = np.mgrid[:height, :width]
    angle = math.radians(gradient["angle"])
    projection = x * math.cos(angle) + y * math.sin(angle)
    left, top, right, bottom = bounds or (0, 0, width - 1, height - 1)
    corners = np.array([[left, top], [right, top], [left, bottom], [right, bottom]])
    limits = corners @ np.array([math.cos(angle), math.sin(angle)])
    extent = max(float(np.ptp(limits)), 1)
    position = np.clip((projection - limits.min()) / extent, 0, 1)
    stops = gradient["stops"]
    positions = [stop["position"] for stop in stops]
    colours = np.array([[int(colour(stop["color"])[i:i + 2], 16) for i in (0, 2, 4)] for stop in stops])
    return np.stack([np.interp(position, positions, colours[:, channel]) for channel in range(3)], axis=2)


def infer_gradient(rgb, mask):
    core = cv2.erode((mask > 0.75).astype(np.uint8), np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero(core)
    if len(xs) < 30:
        return None
    values = rgb[ys, xs].astype(np.float64)
    design = np.column_stack([np.ones(len(xs)), xs, ys])
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    residual = np.linalg.norm(values - design @ coefficients, axis=1)
    keep = residual <= np.percentile(residual, 80) + 1
    coefficients = np.linalg.lstsq(design[keep], values[keep], rcond=None)[0]
    fitted = design[keep] @ coefficients
    constant_error = np.mean((values[keep] - np.median(values[keep], axis=0)) ** 2)
    error = np.mean((values[keep] - fitted) ** 2)
    if constant_error < 80 or error > constant_error * 0.2 or error > 200:
        return None
    direction = np.linalg.svd(coefficients[1:], full_matrices=False)[0][:, 0]
    if direction[1] < 0 or (abs(direction[1]) < 0.01 and direction[0] < 0):
        direction = -direction
    angle = math.degrees(math.atan2(direction[1], direction[0])) % 360
    rows, cols = np.nonzero(mask > 0.2)
    corners = np.array([[cols.min(), rows.min()], [cols.max(), rows.min()],
                        [cols.min(), rows.max()], [cols.max(), rows.max()]])
    projection = corners @ direction
    first, last = corners[np.argmin(projection)], corners[np.argmax(projection)]
    start = np.array([1, *first]) @ coefficients
    end = np.array([1, *last]) @ coefficients
    if np.linalg.norm(end - start) < 45:
        return None
    stops = [{"position": 0, "color": hex_colour(start)}, {"position": 1, "color": hex_colour(end)}]
    along = np.column_stack([xs, ys]) @ direction
    position = (along - projection.min()) / max(float(np.ptp(projection)), 1)
    bands = [position < 0.1, (position > 0.45) & (position < 0.55), position > 0.9]
    if all(band.sum() >= 20 for band in bands):
        # A straight fit hides a blend that bends, so compare what is there.
        first, middle, last = (np.median(values[band], axis=0) for band in bands)
        # Ends far from the fit are a shadow or highlight at the edge, not the blend.
        trusted = max(np.linalg.norm(first - start), np.linalg.norm(last - end)) <= 60
        if trusted and np.linalg.norm(middle - (first + last) / 2) > MIDDLE_STOP_DISTANCE:
            stops = [{"position": 0, "color": hex_colour(first)}, {"position": 0.5, "color": hex_colour(middle)},
                     {"position": 1, "color": hex_colour(last)}]
    return {"angle": round(angle, 2), "stops": stops}


def shadow_direction(alpha, possible, residual):
    """Displaced shadows have directional residuals; AA rims mostly cancel."""
    solid = alpha >= 0.5
    _, labels = cv2.distanceTransformWithLabels((~solid).astype(np.uint8), cv2.DIST_L2, 3,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(solid)
    positions = np.zeros((labels.max() + 1, 2), np.float32)
    positions[labels[ys, xs]] = np.column_stack([xs, ys])
    ry, rx = np.nonzero(possible)
    delta = np.column_stack([rx, ry]) - positions[labels[ry, rx]]
    length = np.maximum(np.linalg.norm(delta, axis=1), 1)
    weights = np.linalg.norm(residual[ry, rx], axis=1)
    direction = np.sum(delta / length[:, None] * weights[:, None], axis=0) / max(float(weights.sum()), 1)
    return float(np.linalg.norm(direction))


def fit_effects(rgb, alpha, background, fill_colour, pt_per_px):
    """Fit simple gradients, coloured outlines, and a single outer shadow.

    alpha is the aligned base-font glyph mask, before decorative effects.
    Return a pixel error and explicit review flag alongside native parameters.
    """
    rgb = rgb.astype(np.float32)
    alpha = np.clip(alpha.astype(np.float32), 0, 1)
    background = np.asarray(background, np.float32)
    fill_colour = np.asarray(fill_colour, np.float32)
    gradient = infer_gradient(rgb, alpha)
    rows, cols = np.nonzero(alpha > 0.2)
    bounds = (cols.min(), rows.min(), cols.max(), rows.max()) if len(rows) else None
    fill = gradient_field(alpha.shape, gradient, bounds) if gradient else fill_colour
    effects = {"gradient": gradient} if gradient else {}
    # Effects grow with the lettering: a 110px headline carries an 8px outline
    # and a shadow 10px away, far outside what fits 14pt body text.
    height = int(rows.max() - rows.min() + 1) if len(rows) else 0
    step = max(1, round(height / 50))
    widest = max(4, round(height * 0.08))
    base = background * (1 - alpha[..., None]) + fill * alpha[..., None]
    before = float(np.mean((rgb - base) ** 2))
    best_error = before
    outer_alpha = alpha
    # Colours off the background-to-fill line distinguish an outline from
    # ordinary antialiasing. Gray rims around black text stay on that line.
    around = cv2.dilate((alpha > 0.5).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    ring = around & (alpha < 0.15)
    difference = rgb - background
    span = fill_colour - background
    coverage = np.clip(np.sum(difference * span, axis=2) / max(float(span @ span), 1), 0, 1)
    off_line = np.linalg.norm(rgb - (background + coverage[..., None] * span), axis=2)
    coloured = ring & (off_line > 45)
    if coloured.sum() >= 15:
        strong = coloured & (off_line >= np.percentile(off_line[coloured], 70))
        outline_colour = np.median(rgb[strong], axis=0)
        outline_fit = None
        for radius in range(1, widest + 1):
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
            expanded = cv2.dilate(alpha, kernel)
            outlined = background * (1 - expanded[..., None]) + outline_colour * expanded[..., None]
            predicted = outlined * (1 - alpha[..., None]) + fill * alpha[..., None]
            error = float(np.mean((rgb - predicted) ** 2))
            if outline_fit is None or error < outline_fit[0]:
                outline_fit = (error, predicted, expanded, radius)
        if outline_fit[0] < best_error * OUTLINE_GAIN:
            best_error, base, outer_alpha, radius = outline_fit
            effects["outline"] = {"color": hex_colour(outline_colour), "width_pt": round(radius * pt_per_px, 3)}
    # Fit black/coloured shadows behind the glyphs. Opacity is solved linearly.
    residual = base - rgb
    outside = outer_alpha < 0.2
    distance = cv2.distanceTransform(outside.astype(np.uint8), cv2.DIST_L2, 3)
    possible = (distance > 1.5) & (np.linalg.norm(residual, axis=2) > 30)
    if possible.sum() >= 20 and shadow_direction(outer_alpha, possible, residual) > 0.2:
        sampled = np.median(rgb[possible], axis=0)
        shadow_colour = sampled if np.ptp(sampled) > 40 else np.zeros(3)
        # A rim in nearly the fill's own colour is a soft edge or a bevel.
        # Fitted as a shadow it comes out opaque and misplaced.
        if shadow_colour.any() and np.linalg.norm(shadow_colour - fill_colour) < SHADOW_FILL_DISTANCE:
            possible[:] = False
        best_shadow = None
        shadow_error = best_error
        offsets = [k * step for k in range(-4, 5)]
        for sigma in (0, step, 2 * step, 3 * step):
            blurred = cv2.GaussianBlur(outer_alpha, (0, 0), sigma) if sigma else outer_alpha
            for dx in offsets:
                for dy in offsets:
                    if dx == 0 and dy == 0:
                        continue
                    shifted = cv2.warpAffine(blurred, np.float32([[1, 0, dx], [0, 1, dy]]), (alpha.shape[1], alpha.shape[0]))
                    contribution = shifted[..., None] * (1 - outer_alpha[..., None]) * (background - shadow_colour)
                    opacity = np.clip(np.sum(contribution * residual) / max(float(np.sum(contribution ** 2)), 1), 0, 1)
                    predicted = base - opacity * contribution
                    error = float(np.mean((rgb - predicted) ** 2))
                    if opacity >= 0.15 and error < shadow_error:
                        shadow_error = error
                        best_shadow = {"color": hex_colour(shadow_colour), "opacity": round(float(opacity), 3),
                                       "offset_x_pt": round(dx * pt_per_px, 3), "offset_y_pt": round(dy * pt_per_px, 3),
                                       "blur_pt": round(sigma * pt_per_px, 3)}
        if best_shadow and possible.any() and shadow_error < best_error * SHADOW_GAIN:
            best_error = shadow_error
            effects["shadow"] = best_shadow
    return {"effects": effects, "pixel_rmse": round(math.sqrt(best_error), 3),
            "needs_review": math.sqrt(best_error) > REVIEW_RMSE, "baseline_rmse": round(math.sqrt(before), 3)}
