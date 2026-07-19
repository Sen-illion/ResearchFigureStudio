from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


def _hex_color(value: object, fallback: str = "#000000") -> str:
    if not isinstance(value, str):
        return fallback
    text = value.strip()
    if not text:
        return fallback
    if not text.startswith("#"):
        text = "#" + text
    try:
        ImageColor.getrgb(text)
        return text
    except ValueError:
        return fallback


def _bbox_px(bbox: dict, width: int, height: int) -> tuple[int, int, int, int]:
    x = int(round(float(bbox.get("x", 0)) * width))
    y = int(round(float(bbox.get("y", 0)) * height))
    w = int(round(float(bbox.get("w", 0)) * width))
    h = int(round(float(bbox.get("h", 0)) * height))
    return x, y, max(1, w), max(1, h)


def _font(size_px: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "calibrib.ttf" if bold else "calibri.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, max(4, int(size_px)))
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_text(draw: ImageDraw.ImageDraw, item: dict, canvas_w: int, canvas_h: int) -> None:
    if not item.get("visible", True):
        return
    if str(item.get("layer_ownership") or "editable_text_layer") != "editable_text_layer":
        return
    bbox = item.get("bbox_percent")
    if not isinstance(bbox, dict):
        return
    x, y, w, h = _bbox_px(bbox, canvas_w, canvas_h)
    text = str(item.get("text") or "")
    if not text:
        return
    font_size_pt = float(item.get("font_size_pt") or 8)
    size_px = max(4, int(round(font_size_pt * canvas_h / 387.0)))
    font = _font(size_px, bold=bool(item.get("bold")))
    color = _hex_color(item.get("color_hex"), "#263747")
    align = str(item.get("align") or "center").lower()
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = max(1, text_bbox[2] - text_bbox[0])
    text_h = max(1, text_bbox[3] - text_bbox[1])
    if align == "left":
        tx = x
    elif align == "right":
        tx = x + w - text_w
    else:
        tx = x + (w - text_w) / 2
    ty = y + (h - text_h) / 2
    draw.text((tx, ty), text, fill=color, font=font)


def _draw_arrow(draw: ImageDraw.ImageDraw, arrow: dict, canvas_w: int, canvas_h: int) -> None:
    path = arrow.get("path_percent")
    if not isinstance(path, list) or len(path) < 2:
        return
    points: list[tuple[int, int]] = []
    for point in path:
        if isinstance(point, list) and len(point) >= 2:
            points.append((int(round(float(point[0]) * canvas_w)), int(round(float(point[1]) * canvas_h))))
    if len(points) < 2:
        return
    color = _hex_color(arrow.get("stroke_color") or arrow.get("outline_color"), "#3F5063")
    line_width = max(1, int(round(float(arrow.get("stroke_width_pt") or 1.5) * canvas_h / 277.0)))
    render_style = str(arrow.get("render_style") or "").lower()
    if render_style == "filled_block_arrow":
        fill = _hex_color(arrow.get("fill_color"), "#AFC6DE")
        start, end = points[0], points[-1]
        thickness = max(8, int(round(float(arrow.get("block_arrow_thickness_percent") or 0.052) * canvas_h)))
        if abs(end[0] - start[0]) >= abs(end[1] - start[1]):
            y = int(round((start[1] + end[1]) / 2))
            left, right = sorted([start[0], end[0]])
            draw.rounded_rectangle((left, y - thickness // 2, right, y + thickness // 2), radius=thickness // 3, fill=fill, outline=color, width=line_width)
        else:
            x = int(round((start[0] + end[0]) / 2))
            top, bottom = sorted([start[1], end[1]])
            draw.rounded_rectangle((x - thickness // 2, top, x + thickness // 2, bottom), radius=thickness // 3, fill=fill, outline=color, width=line_width)
        return
    draw.line(points, fill=color, width=line_width, joint="curve")


def render_rebuild_preview(program: dict, out_dir: str | Path, preview_path: str | Path | None = None) -> Path:
    out = Path(out_dir)
    canvas = program.get("canvas", {}) if isinstance(program.get("canvas"), dict) else {}
    width = int(canvas.get("width_px") or 1600)
    height = int(canvas.get("height_px") or 900)
    background = _hex_color(canvas.get("background"), "#FFFFFF")
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    style = program.get("style", {}) if isinstance(program.get("style"), dict) else {}
    panel_styles = style.get("panel_styles", {}) if isinstance(style.get("panel_styles"), dict) else {}
    palette = style.get("palette") or ["#F7F8F7", "#D2DCDE", "#A09596"]

    for idx, panel in enumerate(program.get("panels", [])):
        bbox = panel.get("bbox_percent")
        if not isinstance(bbox, dict):
            continue
        x, y, w, h = _bbox_px(bbox, width, height)
        local_style = panel_styles.get(panel.get("id"), {}) if isinstance(panel_styles.get(panel.get("id")), dict) else {}
        fill = _hex_color(local_style.get("fill_color"), palette[idx % len(palette)])
        stroke = _hex_color(local_style.get("stroke_color"), "#FFFFFF")
        draw.rounded_rectangle((x, y, x + w, y + h), radius=max(2, min(12, h // 18)), fill=fill, outline=stroke, width=2)

    asset_by_id = {str(asset.get("id")): asset for asset in program.get("assets", []) if isinstance(asset, dict)}
    for slot in sorted(program.get("slots", []), key=lambda item: int(item.get("z_index") or 20)):
        bbox = slot.get("bbox_percent")
        if not isinstance(bbox, dict):
            continue
        x, y, w, h = _bbox_px(bbox, width, height)
        asset = asset_by_id.get(str(slot.get("asset_id") or slot.get("id")))
        asset_path = out / str(asset.get("path")) if asset else out / "assets" / f"{slot.get('asset_id')}.png"
        if asset_path.exists():
            with Image.open(asset_path) as asset_img:
                asset_img = asset_img.convert("RGB")
                asset_img.thumbnail((w, h), Image.Resampling.LANCZOS)
                left = x + (w - asset_img.width) // 2
                top = y + (h - asset_img.height) // 2
                image.paste(asset_img, (left, top))

    for arrow in program.get("arrows", []):
        if isinstance(arrow, dict):
            _draw_arrow(draw, arrow, width, height)

    text_program = program.get("text_program") if isinstance(program.get("text_program"), dict) else {}
    text_items = text_program.get("items", []) if isinstance(text_program, dict) else []
    visible_items = [item for item in text_items if isinstance(item, dict)]
    for item in sorted(visible_items, key=lambda item: (float(item.get("z_index") or 80), str(item.get("id") or ""))):
        _draw_text(draw, item, width, height)

    target = Path(preview_path) if preview_path else out / "rebuild_preview.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target
