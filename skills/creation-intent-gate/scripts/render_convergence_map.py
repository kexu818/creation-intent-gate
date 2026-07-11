#!/usr/bin/env python3
"""Render a self-coherence x other-coherence map as PNG with SVG fallback."""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


WIDTH = 1800
HEIGHT = 1300
SCORE_MIN = 1.0
SCORE_MAX = 5.0

COLORS = {
    "keep": "#26825E",
    "skeleton": "#BE7C27",
    "rebuild": "#D45B3C",
    "fold": "#777B78",
}

DECISION_LABELS = {
    "keep": "保留 / 深做",
    "skeleton": "保留骨架 / 验证需求",
    "rebuild": "重构关系 / 责任边界",
    "fold": "暂停 / 折叠",
}

FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a self-coherence x other-coherence map from JSON."
    )
    parser.add_argument("input", type=Path, help="Input JSON path")
    parser.add_argument("output", type=Path, help="Preferred output path")
    parser.add_argument("--font", type=Path, help="Optional CJK font path")
    parser.add_argument(
        "--svg", action="store_true", help="Force dependency-free SVG output"
    )
    return parser.parse_args()


def load_font_path(explicit: Path | None) -> str:
    if explicit:
        if not explicit.exists():
            raise ValueError(f"Font does not exist: {explicit}")
        return str(explicit)
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise ValueError("No CJK font found. Pass one with --font.")


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def clamp_score(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not SCORE_MIN <= number <= SCORE_MAX:
        raise ValueError(f"{field} must be between 1 and 5")
    return number


def validate(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty array")
    if len(items) > 20:
        raise ValueError("items supports at most 20 paths per map")

    normalized = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"items[{index - 1}] must be an object")
        decision = str(raw.get("decision", "fold"))
        if decision not in COLORS:
            raise ValueError(
                f"items[{index - 1}].decision must be one of {', '.join(COLORS)}"
            )
        name = str(raw.get("name", "")).strip()
        if not name:
            raise ValueError(f"items[{index - 1}].name is required")
        normalized.append(
            {
                "id": str(raw.get("id", index)).strip() or str(index),
                "name": name,
                "self_score": clamp_score(
                    raw.get("self_score"), f"items[{index - 1}].self_score"
                ),
                "other_score": clamp_score(
                    raw.get("other_score"), f"items[{index - 1}].other_score"
                ),
                "decision": decision,
                "note": str(raw.get("note", "")).strip(),
            }
        )

    threshold = clamp_score(payload.get("threshold", 3.0), "threshold")
    return {
        "title": str(payload.get("title", "创造物自洽 × 他洽收敛")),
        "subtitle": str(
            payload.get("subtitle", "用评分显化判断，用证据和人的 Values 完成选择")
        ),
        "threshold": threshold,
        "items": normalized,
    }


def overlap_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    return max(0, right - left) * max(0, bottom - top)


def choose_label_box(
    draw: ImageDraw.ImageDraw,
    text: str,
    label_font: ImageFont.FreeTypeFont,
    point: tuple[int, int],
    radius: int,
    plot: tuple[int, int, int, int],
    occupied: list[tuple[int, int, int, int]],
) -> tuple[tuple[int, int], str, tuple[int, int, int, int]]:
    px, py = point
    raw_box = draw.textbbox((0, 0), text, font=label_font)
    width = raw_box[2] - raw_box[0]
    height = raw_box[3] - raw_box[1]
    gap = radius + 16
    candidates = [
        (px + gap, py, "lm"),
        (px - gap, py, "rm"),
        (px, py - gap, "mb"),
        (px, py + gap, "mt"),
        (px + gap, py - gap, "lb"),
        (px - gap, py - gap, "rb"),
    ]

    best = None
    for x, y, anchor in candidates:
        if anchor == "lm":
            box = (x, y - height // 2, x + width, y + height // 2)
        elif anchor == "rm":
            box = (x - width, y - height // 2, x, y + height // 2)
        elif anchor == "mb":
            box = (x - width // 2, y - height, x + width // 2, y)
        elif anchor == "mt":
            box = (x - width // 2, y, x + width // 2, y + height)
        elif anchor == "lb":
            box = (x, y - height, x + width, y)
        else:
            box = (x - width, y - height, x, y)

        outside = (
            max(0, plot[0] - box[0])
            + max(0, plot[1] - box[1])
            + max(0, box[2] - plot[2])
            + max(0, box[3] - plot[3])
        )
        collision = sum(overlap_area(box, other) for other in occupied)
        score = outside * 10000 + collision
        if best is None or score < best[0]:
            best = (score, (x, y), anchor, box)

    assert best is not None
    return best[1], best[2], best[3]


def choose_quadrant_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    title_font: ImageFont.FreeTypeFont,
    region: tuple[int, int, int, int],
    obstacles: list[tuple[int, int, int, int]],
) -> tuple[tuple[int, int], str, tuple[int, int, int, int]]:
    raw_box = draw.textbbox((0, 0), text, font=title_font)
    width = raw_box[2] - raw_box[0]
    height = raw_box[3] - raw_box[1]
    left, top, right, bottom = region
    pad_x, pad_y = 26, 22
    candidates = [
        (left + pad_x, top + pad_y, "la"),
        (right - pad_x, top + pad_y, "ra"),
        (left + pad_x, bottom - pad_y, "ld"),
        (right - pad_x, bottom - pad_y, "rd"),
    ]
    best = None
    for x, y, anchor in candidates:
        if anchor == "la":
            box = (x, y, x + width, y + height)
        elif anchor == "ra":
            box = (x - width, y, x, y + height)
        elif anchor == "ld":
            box = (x, y - height, x + width, y)
        else:
            box = (x - width, y - height, x, y)
        collision = sum(overlap_area(box, other) for other in obstacles)
        if best is None or collision < best[0]:
            best = (collision, (x, y), anchor, box)
    assert best is not None
    return best[1], best[2], best[3]


def render(payload: dict, output: Path, font_path: str) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#FCFCFB")
    draw = ImageDraw.Draw(image)

    title_font = font(font_path, 50)
    subtitle_font = font(font_path, 26)
    quadrant_font = font(font_path, 25)
    label_font = font(font_path, 24)
    small_font = font(font_path, 20)
    bubble_font = font(font_path, 24)

    draw.text((110, 72), payload["title"], font=title_font, fill="#1C2420")
    draw.text((110, 140), payload["subtitle"], font=subtitle_font, fill="#68716C")

    x0, y0, x1, y1 = 260, 235, 1640, 1020
    inner_pad = 52

    def score_x(score: float) -> int:
        ratio = (score - SCORE_MIN) / (SCORE_MAX - SCORE_MIN)
        return int(x0 + inner_pad + ratio * (x1 - x0 - 2 * inner_pad))

    def score_y(score: float) -> int:
        ratio = (score - SCORE_MIN) / (SCORE_MAX - SCORE_MIN)
        return int(y1 - inner_pad - ratio * (y1 - y0 - 2 * inner_pad))

    split_x = score_x(payload["threshold"])
    split_y = score_y(payload["threshold"])

    draw.rectangle((x0, y0, split_x, split_y), fill="#F6F1E8")
    draw.rectangle((split_x, y0, x1, split_y), fill="#E8F4EE")
    draw.rectangle((x0, split_y, split_x, y1), fill="#F0F2F3")
    draw.rectangle((split_x, split_y, x1, y1), fill="#FAEEEA")
    draw.rectangle((x0, y0, x1, y1), outline="#AEB6B1", width=2)

    dash = 15
    gap = 12
    y = y0
    while y < y1:
        draw.line((split_x, y, split_x, min(y + dash, y1)), fill="#BCC4BF", width=2)
        y += dash + gap
    x = x0
    while x < x1:
        draw.line((x, split_y, min(x + dash, x1), split_y), fill="#BCC4BF", width=2)
        x += dash + gap

    point_rows = []
    for item in sorted(
        payload["items"], key=lambda row: (row["self_score"], row["other_score"]), reverse=True
    ):
        px = score_x(item["other_score"])
        py = score_y(item["self_score"])
        radius = 29 if item["decision"] == "keep" else 25
        point_rows.append((item, px, py, radius))

    bubble_boxes = [
        (px - radius - 4, py - radius - 4, px + radius + 4, py + radius + 4)
        for _, px, py, radius in point_rows
    ]
    quadrant_specs = [
        ("自洽高 / 他洽待验证：保留骨架", "#8D5C20", (x0, y0, split_x, split_y)),
        ("双高：优先进入现实", "#1F6C4F", (split_x, y0, x1, split_y)),
        ("双低：暂停或折叠", "#616965", (x0, split_y, split_x, y1)),
        ("他洽高 / 自洽不足：重构关系", "#A4452E", (split_x, split_y, x1, y1)),
    ]
    quadrant_boxes = []
    for text, color, region in quadrant_specs:
        position, anchor, box = choose_quadrant_title(
            draw, text, quadrant_font, region, bubble_boxes
        )
        draw.text(position, text, font=quadrant_font, fill=color, anchor=anchor)
        quadrant_boxes.append(box)

    for tick in range(1, 6):
        tx = score_x(float(tick))
        ty = score_y(float(tick))
        draw.line((tx, y1, tx, y1 + 8), fill="#838C87", width=2)
        draw.text((tx, y1 + 16), str(tick), font=small_font, fill="#68716C", anchor="ma")
        draw.line((x0 - 8, ty, x0, ty), fill="#838C87", width=2)
        draw.text((x0 - 18, ty), str(tick), font=small_font, fill="#68716C", anchor="rm")

    occupied: list[tuple[int, int, int, int]] = list(quadrant_boxes)
    occupied.extend(bubble_boxes)

    for item, px, py, radius in point_rows:
        color = COLORS[item["decision"]]
        if item["decision"] == "keep":
            draw.ellipse(
                (px - radius - 6, py - radius - 6, px + radius + 6, py + radius + 6),
                outline="#173E30",
                width=3,
            )
        draw.ellipse(
            (px - radius, py - radius, px + radius, py + radius),
            fill=color,
            outline="#FFFFFF",
            width=3,
        )
        bubble_text = item["id"][:3]
        draw.text((px, py + 1), bubble_text, font=bubble_font, fill="#FFFFFF", anchor="mm")
        label = item["name"]
        position, anchor, box = choose_label_box(
            draw, label, label_font, (px, py), radius, (x0, y0, x1, y1), occupied
        )
        draw.text(position, label, font=label_font, fill="#222925", anchor=anchor)
        occupied.append(box)

    draw.line((x0, y1 + 70, x1 + 24, y1 + 70), fill="#333B37", width=3)
    draw.line((x1 + 24, y1 + 70, x1 + 8, y1 + 60), fill="#333B37", width=3)
    draw.line((x1 + 24, y1 + 70, x1 + 8, y1 + 80), fill="#333B37", width=3)
    draw.text(
        ((x0 + x1) // 2, y1 + 105),
        "他洽：用户 / 市场认同",
        font=quadrant_font,
        fill="#303834",
        anchor="ma",
    )

    y_label = Image.new("RGBA", (560, 70), (0, 0, 0, 0))
    y_draw = ImageDraw.Draw(y_label)
    y_draw.text(
        (280, 35),
        "自洽：与自身逻辑稳定",
        font=quadrant_font,
        fill="#303834",
        anchor="mm",
    )
    y_label = y_label.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    image.paste(y_label, (55, 350), y_label)
    draw = ImageDraw.Draw(image)

    legend_y = 1208
    legend_x = 110
    for decision in ("keep", "skeleton", "rebuild", "fold"):
        draw.ellipse(
            (legend_x, legend_y - 10, legend_x + 20, legend_y + 10),
            fill=COLORS[decision],
        )
        draw.text(
            (legend_x + 30, legend_y),
            DECISION_LABELS[decision],
            font=small_font,
            fill="#4F5853",
            anchor="lm",
        )
        legend_x += 285

    draw.text(
        (1690, legend_y),
        "坐标为分析判断，不是客观评分。",
        font=small_font,
        fill="#7B827E",
        anchor="rm",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, dpi=(180, 180))


def render_svg(payload: dict, output: Path) -> None:
    """Render a dependency-free SVG when Pillow or a CJK font is unavailable."""
    item_rows = (len(payload["items"]) + 1) // 2
    width = 1800
    path_legend_y = 1040
    decision_legend_y = path_legend_y + item_rows * 40 + 65
    height = decision_legend_y + 80
    x0, y0, x1, y1 = 260, 210, 1630, 850
    inner_pad = 70

    def score_x(score: float) -> int:
        ratio = (score - SCORE_MIN) / (SCORE_MAX - SCORE_MIN)
        return int(x0 + inner_pad + ratio * (x1 - x0 - 2 * inner_pad))

    def score_y(score: float) -> int:
        ratio = (score - SCORE_MIN) / (SCORE_MAX - SCORE_MIN)
        return int(y1 - inner_pad - ratio * (y1 - y0 - 2 * inner_pad))

    split_x = score_x(payload["threshold"])
    split_y = score_y(payload["threshold"])
    font_stack = "PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, sans-serif"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        f'<rect width="{width}" height="{height}" fill="#FCFCFB"/>',
        (
            f'<style>text{{font-family:{font_stack};fill:#202723}}'
            '.title{font-size:46px;font-weight:700}.subtitle{font-size:24px;fill:#68716C}'
            '.quad{font-size:22px;font-weight:700}.label{font-size:22px}'
            '.small{font-size:18px;fill:#68716C}.bubble{font-size:22px;fill:white}'
            '</style>'
        ),
        f'<text x="95" y="82" class="title">{escape(payload["title"])}</text>',
        f'<text x="95" y="128" class="subtitle">{escape(payload["subtitle"])}</text>',
        f'<rect x="{x0}" y="{y0}" width="{split_x-x0}" height="{split_y-y0}" fill="#F6F1E8"/>',
        f'<rect x="{split_x}" y="{y0}" width="{x1-split_x}" height="{split_y-y0}" fill="#E8F4EE"/>',
        f'<rect x="{x0}" y="{split_y}" width="{split_x-x0}" height="{y1-split_y}" fill="#F0F2F3"/>',
        f'<rect x="{split_x}" y="{split_y}" width="{x1-split_x}" height="{y1-split_y}" fill="#FAEEEA"/>',
        f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="#AEB6B1" stroke-width="2"/>',
        f'<line x1="{split_x}" y1="{y0}" x2="{split_x}" y2="{y1}" stroke="#BCC4BF" stroke-width="2" stroke-dasharray="14 12"/>',
        f'<line x1="{x0}" y1="{split_y}" x2="{x1}" y2="{split_y}" stroke="#BCC4BF" stroke-width="2" stroke-dasharray="14 12"/>',
        f'<text x="{x0+24}" y="{y0+36}" class="quad" fill="#8D5C20">自洽高 / 他洽待验证：保留骨架</text>',
        f'<text x="{x1-24}" y="{y0+36}" text-anchor="end" class="quad" fill="#1F6C4F">双高：优先进入现实</text>',
        f'<text x="{x0+24}" y="{y1-24}" class="quad" fill="#616965">双低：暂停或折叠</text>',
        f'<text x="{x1-24}" y="{y1-24}" text-anchor="end" class="quad" fill="#A4452E">他洽高 / 自洽不足：重构关系</text>',
    ]

    for tick in range(1, 6):
        tx = score_x(float(tick))
        ty = score_y(float(tick))
        parts.append(f'<text x="{tx}" y="{y1+28}" text-anchor="middle" class="small">{tick}</text>')
        parts.append(f'<text x="{x0-18}" y="{ty+6}" text-anchor="end" class="small">{tick}</text>')

    for item in payload["items"]:
        px = score_x(item["other_score"])
        py = score_y(item["self_score"])
        radius = 28 if item["decision"] == "keep" else 23
        color = COLORS[item["decision"]]
        if item["decision"] == "keep":
            parts.append(
                f'<circle cx="{px}" cy="{py}" r="{radius+6}" fill="none" stroke="#173E30" stroke-width="3"/>'
            )
        parts.append(
            f'<circle cx="{px}" cy="{py}" r="{radius}" fill="{color}" stroke="white" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{px}" y="{py+7}" text-anchor="middle" class="bubble">{escape(item["id"][:3])}</text>'
        )

    parts.extend(
        [
            f'<line x1="{x0}" y1="{y1+62}" x2="{x1+20}" y2="{y1+62}" stroke="#333B37" stroke-width="3"/>',
            f'<path d="M{x1+20},{y1+62} l-16,-10 m16,10 l-16,10" fill="none" stroke="#333B37" stroke-width="3"/>',
            f'<text x="{(x0+x1)//2}" y="{y1+105}" text-anchor="middle" class="quad">他洽：用户 / 市场认同</text>',
            f'<text x="75" y="{(y0+y1)//2}" text-anchor="middle" class="quad" transform="rotate(-90 75 {(y0+y1)//2})">自洽：与自身逻辑稳定</text>',
        ]
    )

    for index, item in enumerate(payload["items"]):
        column = index % 2
        row = index // 2
        entry_x = 120 + column * 840
        entry_y = path_legend_y + row * 40
        parts.append(
            f'<circle cx="{entry_x}" cy="{entry_y}" r="11" fill="{COLORS[item["decision"]]}"/>'
        )
        parts.append(
            f'<text x="{entry_x+22}" y="{entry_y+7}" class="label">{escape(item["id"])}　{escape(item["name"])}</text>'
        )

    legend_x = 120
    for decision in ("keep", "skeleton", "rebuild", "fold"):
        parts.append(
            f'<circle cx="{legend_x}" cy="{decision_legend_y}" r="10" fill="{COLORS[decision]}"/>'
        )
        parts.append(
            f'<text x="{legend_x+20}" y="{decision_legend_y+7}" class="small">{escape(DECISION_LABELS[decision])}</text>'
        )
        legend_x += 260
    parts.append(
        f'<text x="1690" y="{decision_legend_y+7}" text-anchor="end" class="small">坐标为分析判断，不是客观评分。</text>'
    )
    parts.append("</svg>")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def svg_output_path(output: Path) -> Path:
    return output if output.suffix.lower() == ".svg" else output.with_suffix(".svg")


def main() -> int:
    args = parse_args()
    try:
        payload = validate(json.loads(args.input.read_text(encoding="utf-8")))
        actual_output = args.output
        if args.svg or not PIL_AVAILABLE:
            actual_output = svg_output_path(args.output)
            render_svg(payload, actual_output)
        else:
            try:
                font_path = load_font_path(args.font)
                render(payload, args.output, font_path)
            except ValueError as exc:
                actual_output = svg_output_path(args.output)
                print(f"warning: {exc}; falling back to SVG", file=sys.stderr)
                render_svg(payload, actual_output)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(actual_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
