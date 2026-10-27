#!/usr/bin/env python3
"""Convert a simple component SVG into editable PowerPoint shapes.

Anything the converter cannot draw faithfully raises instead of being dropped
or approximated: a silently wrong shape looks like a design choice in the
finished deck and is much harder to catch than an error here.
"""
import argparse
import math
import re
import xml.etree.ElementTree as ET

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR_TYPE
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
PATH_TOKEN = re.compile(r"[A-Za-z]|" + NUMBER.pattern)
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# Paint properties that children inherit from their groups.
INHERITED = ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity")
ROOT_STYLE = {"fill": "#000000", "stroke": "none", "stroke-width": "1", "opacity": 1.0}
SKIPPED = ("defs", "title", "desc", "metadata")

NAMED_COLOURS = dict(pair.split(":") for pair in """
aliceblue:F0F8FF antiquewhite:FAEBD7 aqua:00FFFF aquamarine:7FFFD4 azure:F0FFFF beige:F5F5DC
bisque:FFE4C4 black:000000 blanchedalmond:FFEBCD blue:0000FF blueviolet:8A2BE2 brown:A52A2A
burlywood:DEB887 cadetblue:5F9EA0 chartreuse:7FFF00 chocolate:D2691E coral:FF7F50
cornflowerblue:6495ED cornsilk:FFF8DC crimson:DC143C cyan:00FFFF darkblue:00008B darkcyan:008B8B
darkgoldenrod:B8860B darkgray:A9A9A9 darkgreen:006400 darkgrey:A9A9A9 darkkhaki:BDB76B
darkmagenta:8B008B darkolivegreen:556B2F darkorange:FF8C00 darkorchid:9932CC darkred:8B0000
darksalmon:E9967A darkseagreen:8FBC8F darkslateblue:483D8B darkslategray:2F4F4F
darkslategrey:2F4F4F darkturquoise:00CED1 darkviolet:9400D3 deeppink:FF1493 deepskyblue:00BFFF
dimgray:696969 dimgrey:696969 dodgerblue:1E90FF firebrick:B22222 floralwhite:FFFAF0
forestgreen:228B22 fuchsia:FF00FF gainsboro:DCDCDC ghostwhite:F8F8FF gold:FFD700 goldenrod:DAA520
gray:808080 green:008000 greenyellow:ADFF2F grey:808080 honeydew:F0FFF0 hotpink:FF69B4
indianred:CD5C5C indigo:4B0082 ivory:FFFFF0 khaki:F0E68C lavender:E6E6FA lavenderblush:FFF0F5
lawngreen:7CFC00 lemonchiffon:FFFACD lightblue:ADD8E6 lightcoral:F08080 lightcyan:E0FFFF
lightgoldenrodyellow:FAFAD2 lightgray:D3D3D3 lightgreen:90EE90 lightgrey:D3D3D3 lightpink:FFB6C1
lightsalmon:FFA07A lightseagreen:20B2AA lightskyblue:87CEFA lightslategray:778899
lightslategrey:778899 lightsteelblue:B0C4DE lightyellow:FFFFE0 lime:00FF00 limegreen:32CD32
linen:FAF0E6 magenta:FF00FF maroon:800000 mediumaquamarine:66CDAA mediumblue:0000CD
mediumorchid:BA55D3 mediumpurple:9370DB mediumseagreen:3CB371 mediumslateblue:7B68EE
mediumspringgreen:00FA9A mediumturquoise:48D1CC mediumvioletred:C71585 midnightblue:191970
mintcream:F5FFFA mistyrose:FFE4E1 moccasin:FFE4B5 navajowhite:FFDEAD navy:000080 oldlace:FDF5E6
olive:808000 olivedrab:6B8E23 orange:FFA500 orangered:FF4500 orchid:DA70D6 palegoldenrod:EEE8AA
palegreen:98FB98 paleturquoise:AFEEEE palevioletred:DB7093 papayawhip:FFEFD5 peachpuff:FFDAB9
peru:CD853F pink:FFC0CB plum:DDA0DD powderblue:B0E0E6 purple:800080 rebeccapurple:663399
red:FF0000 rosybrown:BC8F8F royalblue:4169E1 saddlebrown:8B4513 salmon:FA8072 sandybrown:F4A460
seagreen:2E8B57 seashell:FFF5EE sienna:A0522D silver:C0C0C0 skyblue:87CEEB slateblue:6A5ACD
slategray:708090 slategrey:708090 snow:FFFAFA springgreen:00FF7F steelblue:4682B4 tan:D2B48C
teal:008080 thistle:D8BFD8 tomato:FF6347 turquoise:40E0D0 violet:EE82EE wheat:F5DEB3
white:FFFFFF whitesmoke:F5F5F5 yellow:FFFF00 yellowgreen:9ACD32
""".split())


def strip_ns(tag):
    return tag.split("}", 1)[-1]


def num(value, default=0.0):
    if value is None:
        return default
    m = NUMBER.match(str(value).strip())
    return float(m.group(0)) if m else default


def require_positive(value, name):
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def svg_dimensions(root):
    view_box = root.attrib.get("viewBox")
    if view_box:
        values = [float(x) for x in view_box.replace(",", " ").split()]
        if len(values) != 4:
            raise ValueError("viewBox must contain four numbers: min-x min-y width height")
        vb_x, vb_y, vb_w, vb_h = values
    else:
        vb_x = 0
        vb_y = 0
        vb_w = num(root.attrib.get("width"), 1920)
        vb_h = num(root.attrib.get("height"), 1080)
    return vb_x, vb_y, require_positive(vb_w, "SVG width"), require_positive(vb_h, "SVG height")


# --- paint -------------------------------------------------------------------


def parse_colour(value):
    """(RRGGBB or None for no paint, alpha 0..1)."""
    text = str(value).strip().lower()
    if text in ("none", "transparent"):
        return None, 1.0
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        alpha = 1.0
        if len(digits) == 8:
            alpha = int(digits[6:], 16) / 255
            digits = digits[:6]
        if re.fullmatch(r"[0-9a-f]{6}", digits):
            return digits.upper(), alpha
    m = re.fullmatch(r"rgba?\(([^)]*)\)", text)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1).strip()) if p]
        if len(parts) in (3, 4):
            channels = [
                round(float(p[:-1]) * 2.55) if p.endswith("%") else round(float(p))
                for p in parts[:3]
            ]
            hex_value = "".join(f"{max(0, min(255, c)):02X}" for c in channels)
            return hex_value, opacity(parts[3]) if len(parts) == 4 else 1.0
    if text in NAMED_COLOURS:
        return NAMED_COLOURS[text], 1.0
    raise ValueError(
        f"unsupported colour {value!r}; use #RRGGBB, rgb(), or a CSS colour name. "
        "Gradient and pattern paints cannot become editable fills; reclassify the component as PNG"
    )


def opacity(value):
    text = str(value).strip()
    amount = float(text[:-1]) / 100 if text.endswith("%") else float(text)
    return max(0.0, min(1.0, amount))


def own_properties(elem):
    """Presentation attributes, overridden by the `style` attribute."""
    props = {k: v for k, v in elem.attrib.items() if k in INHERITED + ("opacity", "display")}
    for declaration in elem.attrib.get("style", "").split(";"):
        if ":" in declaration:
            key, value = (part.strip() for part in declaration.split(":", 1))
            if key in INHERITED + ("opacity", "display"):
                props[key] = value.replace("!important", "").strip()
    return props


def inherit(parent, elem):
    own = own_properties(elem)
    style = dict(parent)
    for key in INHERITED:
        if key in own and own[key] != "inherit":
            style[key] = own[key]
    # Group opacity is approximated by multiplying it into each child.
    style["opacity"] = parent["opacity"] * opacity(own.get("opacity", 1))
    style["display"] = own.get("display", "inline")
    return style


def set_alpha(solid_fill, alpha):
    """Write <a:alpha> into a solid fill's colour; python-pptx has no API for it."""
    colour = solid_fill.find(qn("a:srgbClr"))
    for old in colour.findall(qn("a:alpha")):
        colour.remove(old)
    colour.append(colour.makeelement(qn("a:alpha"), {"val": str(round(alpha * 100000))}))


def apply_stroke(shape, style, stroke_scale):
    # New python-pptx shapes pick up the theme's effect style, which carries a
    # drop shadow the SVG never had.
    shape.shadow.inherit = False
    colour, alpha = parse_colour(style["stroke"])
    width = num(style["stroke-width"], 1) * stroke_scale
    if colour is None or width <= 0:
        shape.line.fill.background()
        return
    shape.line.color.rgb = RGBColor.from_string(colour)
    shape.line.width = round(Pt(1) * width)
    alpha *= opacity(style.get("stroke-opacity", 1)) * style["opacity"]
    if alpha < 1:
        set_alpha(shape._element.spPr.find(qn("a:ln")).find(qn("a:solidFill")), alpha)


def apply_paint(shape, style, stroke_scale):
    colour, alpha = parse_colour(style["fill"])
    if colour is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(colour)
        alpha *= opacity(style.get("fill-opacity", 1)) * style["opacity"]
        if alpha < 1:
            set_alpha(shape._element.spPr.find(qn("a:solidFill")), alpha)
    apply_stroke(shape, style, stroke_scale)


# --- geometry ----------------------------------------------------------------


def multiply(m, n):
    """m applied after n."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D,
            a * E + c * F + e, b * E + d * F + f)


def parse_transform(text):
    m = IDENTITY
    for name, args in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in NUMBER.findall(args)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate" and len(v) in (1, 2):
            t = (1, 0, 0, 1, v[0], v[1] if len(v) == 2 else 0)
        elif name == "scale" and len(v) in (1, 2):
            t = (v[0], 0, 0, v[1] if len(v) == 2 else v[0], 0, 0)
        elif name == "rotate" and len(v) in (1, 3):
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                t = multiply(multiply((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX" and len(v) == 1:
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY" and len(v) == 1:
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            raise ValueError(f"unsupported transform: {name}({args})")
        m = multiply(m, t)
    return m


def apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def box_transform(m, tag):
    """(x scale, y scale, clockwise degrees) for a box PowerPoint can rotate."""
    a, b, c, d, _, _ = m
    sx, sy = math.hypot(a, b), math.hypot(c, d)
    if sx == 0 or sy == 0:
        raise ValueError(f"<{tag}> has a degenerate transform")
    if abs(a * c + b * d) > 1e-6 * sx * sy or a * d - b * c <= 0:
        raise ValueError(
            f"skewed or mirrored <{tag}> cannot become a PowerPoint shape; "
            "apply the transform to the coordinates or reclassify the component as PNG"
        )
    return sx, sy, math.degrees(math.atan2(b, a))


def parse_path(d):
    """Subpaths of straight segments as ([(x, y), ...], closed)."""
    tokens = PATH_TOKEN.findall(d or "")
    subpaths = []
    current = None
    x = y = 0.0
    start = (0.0, 0.0)
    command = None
    i = 0

    def take(count):
        nonlocal i
        if i + count > len(tokens) or any(t.isalpha() for t in tokens[i:i + count]):
            raise ValueError(f"malformed path data near command {command!r}")
        values = [float(t) for t in tokens[i:i + count]]
        i += count
        return values

    def extend(point):
        nonlocal current
        if current is None:
            current = [[start], False]
            subpaths.append(current)
        current[0].append(point)

    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            command = token
            i += 1
            if command in "Zz":
                if current is not None:
                    current[1] = True
                current = None
                x, y = start
            elif command not in "MmLlHhVv":
                raise ValueError(
                    f"unsupported path command {command!r}: only straight segments (M L H V Z) "
                    "become editable shapes; flatten the curve, use ppt-master, or reclassify as PNG"
                )
            continue
        if command is None or command in "Zz":
            raise ValueError("path data must start with a move command")
        if command in "Mm":
            nx, ny = take(2)
            if command == "m" and subpaths:
                nx, ny = nx + x, ny + y
            x, y = nx, ny
            start = (x, y)
            current = [[start], False]
            subpaths.append(current)
            command = "l" if command == "m" else "L"
        elif command in "Ll":
            nx, ny = take(2)
            x, y = (nx + x, ny + y) if command == "l" else (nx, ny)
            extend((x, y))
        elif command in "Hh":
            (nx,) = take(1)
            x = nx + x if command == "h" else nx
            extend((x, y))
        else:
            (ny,) = take(1)
            y = ny + y if command == "v" else ny
            extend((x, y))

    return [(points, closed) for points, closed in subpaths if len(points) > 1]


class Converter:
    def __init__(self, slide, vb, slide_w, slide_h):
        self.slide = slide
        self.vb_x, self.vb_y, vb_w, vb_h = vb
        self.kx = Inches(slide_w) / vb_w
        self.ky = Inches(slide_h) / vb_h
        # SVG user units to points, for stroke widths.
        self.pt_per_unit = math.sqrt((slide_w * 72 / vb_w) * (slide_h * 72 / vb_h))

    def emu(self, x, y):
        return (x - self.vb_x) * self.kx, (y - self.vb_y) * self.ky

    def stroke_scale(self, m):
        return math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) * self.pt_per_unit

    def walk(self, elem, style, m):
        tag = strip_ns(elem.tag)
        if tag in SKIPPED:
            return
        style = inherit(style, elem)
        if style["display"] == "none":
            return
        m = multiply(m, parse_transform(elem.attrib.get("transform")))
        if tag in ("svg", "g"):
            for child in elem:
                if strip_ns(child.tag) == "svg":
                    raise ValueError("nested <svg> is not supported; flatten it into the root")
                self.walk(child, style, m)
            return
        draw = getattr(self, f"draw_{tag}", None)
        if draw is None:
            raise ValueError(
                f"unsupported SVG element: {tag}; simplify SVG, use ppt-master full converter, "
                "or reclassify as PNG"
            )
        draw(elem, style, m)

    def box(self, kind, x, y, w, h, m, tag):
        sx, sy, degrees = box_transform(m, tag)
        cx, cy = self.emu(*apply(m, x + w / 2, y + h / 2))
        width, height = w * sx * self.kx, h * sy * self.ky
        shape = self.slide.shapes.add_shape(
            kind, round(cx - width / 2), round(cy - height / 2), round(width), round(height)
        )
        if degrees % 360:
            shape.rotation = degrees % 360
        return shape, sx, sy

    def draw_rect(self, elem, style, m):
        x, y = num(elem.attrib.get("x")), num(elem.attrib.get("y"))
        w, h = num(elem.attrib.get("width")), num(elem.attrib.get("height"))
        if w <= 0 or h <= 0:
            return
        rx_attr, ry_attr = elem.attrib.get("rx"), elem.attrib.get("ry")
        rx = num(rx_attr if rx_attr is not None else ry_attr)
        ry = num(ry_attr if ry_attr is not None else rx_attr)
        rx, ry = min(max(rx, 0), w / 2), min(max(ry, 0), h / 2)
        kind = MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE if rx and ry else MSO_AUTO_SHAPE_TYPE.RECTANGLE
        shape, sx, sy = self.box(kind, x, y, w, h, m, "rect")
        if kind == MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE:
            # One radius for all corners, as a share of the shorter side.
            radius = min(rx * sx * self.kx, ry * sy * self.ky)
            shape.adjustments[0] = min(0.5, radius / min(w * sx * self.kx, h * sy * self.ky))
        apply_paint(shape, style, self.stroke_scale(m))

    def draw_circle(self, elem, style, m):
        r = num(elem.attrib.get("r"))
        self.draw_oval(num(elem.attrib.get("cx")), num(elem.attrib.get("cy")), r, r, style, m, "circle")

    def draw_ellipse(self, elem, style, m):
        self.draw_oval(num(elem.attrib.get("cx")), num(elem.attrib.get("cy")),
                       num(elem.attrib.get("rx")), num(elem.attrib.get("ry")), style, m, "ellipse")

    def draw_oval(self, cx, cy, rx, ry, style, m, tag):
        if rx <= 0 or ry <= 0:
            return
        shape, _, _ = self.box(MSO_AUTO_SHAPE_TYPE.OVAL, cx - rx, cy - ry, 2 * rx, 2 * ry, m, tag)
        apply_paint(shape, style, self.stroke_scale(m))

    def draw_line(self, elem, style, m):
        if parse_colour(style["stroke"])[0] is None:
            return  # an unstroked line draws nothing in SVG either
        x1, y1 = self.emu(*apply(m, num(elem.attrib.get("x1")), num(elem.attrib.get("y1"))))
        x2, y2 = self.emu(*apply(m, num(elem.attrib.get("x2")), num(elem.attrib.get("y2"))))
        line = self.slide.shapes.add_connector(
            MSO_CONNECTOR_TYPE.STRAIGHT, round(x1), round(y1), round(x2), round(y2)
        )
        apply_stroke(line, style, self.stroke_scale(m))

    def draw_polygon(self, elem, style, m):
        self.freeform([(self.points(elem.attrib.get("points")), True)], style, m)

    def draw_polyline(self, elem, style, m):
        self.freeform([(self.points(elem.attrib.get("points")), False)], style, m)

    def draw_path(self, elem, style, m):
        self.freeform(parse_path(elem.attrib.get("d")), style, m)

    @staticmethod
    def points(value):
        values = [float(v) for v in NUMBER.findall(value or "")]
        return list(zip(values[0::2], values[1::2]))

    def freeform(self, subpaths, style, m):
        subpaths = [
            ([tuple(round(v) for v in self.emu(*apply(m, x, y))) for x, y in points], closed)
            for points, closed in subpaths
            if len(points) > 1
        ]
        if not subpaths:
            return
        first = subpaths[0][0]
        builder = self.slide.shapes.build_freeform(first[0][0], first[0][1], scale=1.0)
        for index, (points, closed) in enumerate(subpaths):
            if index:
                builder.move_to(*points[0])
            builder.add_line_segments(points[1:], close=closed)
        shape = builder.convert_to_shape()
        apply_paint(shape, style, self.stroke_scale(m))


def main():
    ap = argparse.ArgumentParser(description="Convert a simple SVG component to editable PPTX shapes.")
    ap.add_argument("svg")
    ap.add_argument("pptx")
    ap.add_argument("--slide-width", type=float, default=13.333333)
    ap.add_argument("--slide-height", type=float, default=7.5)
    args = ap.parse_args()

    require_positive(args.slide_width, "slide width")
    require_positive(args.slide_height, "slide height")

    root = ET.parse(args.svg).getroot()
    vb = svg_dimensions(root)

    prs = Presentation()
    prs.slide_width = Inches(args.slide_width)
    prs.slide_height = Inches(args.slide_height)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    Converter(slide, vb, args.slide_width, args.slide_height).walk(root, dict(ROOT_STYLE), IDENTITY)

    prs.save(args.pptx)
    print(args.pptx)


if __name__ == "__main__":
    main()
