from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw


def clamp_bbox(bbox: dict) -> dict[str, float]:
    x = max(0.0, min(0.995, float(bbox.get("x", 0.0))))
    y = max(0.0, min(0.995, float(bbox.get("y", 0.0))))
    w = max(0.001, min(float(bbox.get("w", 0.001)), 1.0 - x))
    h = max(0.001, min(float(bbox.get("h", 0.001)), 1.0 - y))
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def canvas_inches(width_px: int, height_px: int) -> tuple[float, float]:
    ratio = width_px / max(height_px, 1)
    width = max(10.0, min(15.6, 7.5 * ratio))
    return round(width, 3), round(width / ratio, 3)


def rgb_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def estimate_background(image: Image.Image) -> str:
    rgb = image.convert("RGB")
    w, h = rgb.size
    samples = []
    edge = max(1, min(w, h) // 12)
    for box in [(0, 0, w, edge), (0, h - edge, w, h), (0, 0, edge, h), (w - edge, 0, w, h)]:
        crop = rgb.crop(box).resize((1, 1))
        samples.append(crop.getpixel((0, 0)))
    avg = tuple(int(sum(px[i] for px in samples) / len(samples)) for i in range(3))
    return rgb_hex(avg)


def dominant_palette(image: Image.Image, count: int = 6) -> list[str]:
    small = image.convert("RGB").resize((96, 96))
    colors = small.quantize(colors=count).convert("RGB").getcolors(96 * 96) or []
    colors = sorted(colors, key=lambda item: item[0], reverse=True)
    return [rgb_hex(rgb) for _n, rgb in colors[:count]]


def _find_visual_components(reference_path: Path, canvas_w: int, canvas_h: int) -> list[dict]:
    try:
        import cv2
    except Exception:
        return []
    image = cv2.imread(str(reference_path))
    if image is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 45, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    dilated = cv2.dilate(edges, kernel, iterations=2)
    contours, _hier = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    image_area = canvas_w * canvas_h
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < image_area * 0.008 or area > image_area * 0.35:
            continue
        if w < 24 or h < 24:
            continue
        boxes.append((x, y, w, h))
    boxes.sort(key=lambda item: (item[1], item[0]))
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x, y, w, h = box
        duplicate = False
        for kx, ky, kw, kh in kept:
            ix = max(0, min(x + w, kx + kw) - max(x, kx))
            iy = max(0, min(y + h, ky + kh) - max(y, ky))
            if ix * iy / max(w * h, 1) > 0.55:
                duplicate = True
                break
        if not duplicate:
            kept.append(box)
        if len(kept) >= 16:
            break
    slots = []
    for idx, (x, y, w, h) in enumerate(kept, start=1):
        slots.append({
            "id": f"slot_{idx:02d}",
            "asset_id": f"slot_{idx:02d}",
            "paper_concept": f"visual element {idx}",
            "display_label": "",
            "bbox_percent": clamp_bbox({"x": x / canvas_w, "y": y / canvas_h, "w": w / canvas_w, "h": h / canvas_h}),
            "composition_type": "full_frame_icon",
            "show_slot_caption": False,
            "z_index": 20 + idx,
            "confidence": 0.55,
            "detected_by": "cv_contour",
        })
    return slots


def _fallback_slots(count: int = 6) -> list[dict]:
    boxes = [
        (0.08, 0.26, 0.16, 0.22),
        (0.31, 0.26, 0.16, 0.22),
        (0.54, 0.26, 0.16, 0.22),
        (0.77, 0.26, 0.16, 0.22),
        (0.25, 0.58, 0.18, 0.22),
        (0.57, 0.58, 0.18, 0.22),
    ][:count]
    return [{
        "id": f"slot_{idx:02d}",
        "asset_id": f"slot_{idx:02d}",
        "paper_concept": f"visual element {idx}",
        "display_label": "",
        "bbox_percent": clamp_bbox({"x": x, "y": y, "w": w, "h": h}),
        "composition_type": "full_frame_icon",
        "show_slot_caption": False,
        "z_index": 20 + idx,
        "confidence": 0.25,
        "detected_by": "fallback_grid",
    } for idx, (x, y, w, h) in enumerate(boxes, start=1)]


def _normalize_items(items: list, prefix: str, canvas_id: str = "reference_canvas") -> list[dict]:
    normalized = []
    for idx, item in enumerate(items or [], start=1):
        if not isinstance(item, dict) or not isinstance(item.get("bbox_percent"), dict):
            continue
        item_id = str(item.get("id") or f"{prefix}_{idx:02d}")
        record = dict(item)
        record["id"] = item_id
        if prefix == "slot":
            record.setdefault("asset_id", item_id)
            record.setdefault("paper_concept", item.get("prompt_subject") or item.get("label") or f"visual element {idx}")
            record.setdefault("composition_type", "full_frame_icon")
            record.setdefault("show_slot_caption", False)
            record.setdefault("z_index", 20 + idx)
            record.setdefault("panel_id", str(item.get("panel_id") or canvas_id))
        else:
            record.setdefault("title", item.get("label") or item_id)
            record.setdefault("editable_in", "pptx")
        raw_bbox = dict(record["bbox_percent"])
        record["bbox_percent"] = clamp_bbox(record["bbox_percent"])
        try:
            raw_normalized = {key: round(float(raw_bbox[key]), 4) for key in ("x", "y", "w", "h")}
        except Exception:
            raw_normalized = {}
        record["bbox_was_clamped"] = record["bbox_percent"] != raw_normalized
        record.setdefault("confidence", 0.8)
        record.setdefault("detected_by", "vlm")
        normalized.append(record)
    return normalized


def _merge_vlm_layout(base: dict, vlm: dict) -> dict:
    merged = dict(base)
    panels = _normalize_items(vlm.get("panels", []), "panel")
    cards = _normalize_items(vlm.get("cards", []), "card")
    slots = _normalize_items(vlm.get("slots", []), "slot")
    legends = _normalize_items(vlm.get("legend_regions", []), "legend")
    if panels:
        merged["panels"] = panels
    if slots:
        merged["slots"] = slots
    merged["cards"] = cards
    merged["legend_regions"] = legends
    merged["confidence"] = float(vlm.get("confidence") or 0.75)
    merged["vlm_status"] = "used"
    if vlm.get("_vlm_model"):
        merged["vlm_model"] = str(vlm.get("_vlm_model"))
    merged.setdefault("warnings", [])
    return merged


def _draw_overlay(reference_path: Path, out_path: Path, layout: dict) -> None:
    with Image.open(reference_path).convert("RGB") as image:
        draw = ImageDraw.Draw(image)
        w, h = image.size
        for collection, color, width in [("panels", "#2D6FB7", 4), ("cards", "#8A5CF6", 3), ("slots", "#E17721", 3), ("legend_regions", "#4B9B52", 3)]:
            for item in layout.get(collection, []):
                box = item.get("bbox_percent")
                if not isinstance(box, dict):
                    continue
                x0 = int(float(box["x"]) * w)
                y0 = int(float(box["y"]) * h)
                x1 = int((float(box["x"]) + float(box["w"])) * w)
                y1 = int((float(box["y"]) + float(box["h"])) * h)
                draw.rectangle((x0, y0, x1, y1), outline=color, width=width)
                draw.text((x0 + 3, y0 + 3), str(item.get("id") or ""), fill=color)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)


def plan_reference_layout(
    reference_path: str | Path,
    out_dir: str | Path,
    mode: str = "hybrid",
    vlm_adapter: Callable[[str | Path, dict], dict] | None = None,
) -> dict:
    reference = Path(reference_path)
    out = Path(out_dir)
    with Image.open(reference).convert("RGB") as image:
        canvas_w, canvas_h = image.size
        width_in, height_in = canvas_inches(canvas_w, canvas_h)
        background = estimate_background(image)
        palette = dominant_palette(image)
    slots = _find_visual_components(reference, canvas_w, canvas_h) or _fallback_slots()
    panel = {
        "id": "reference_canvas",
        "title": "Editable Rebuild",
        "bbox_percent": clamp_bbox({"x": 0.025, "y": 0.065, "w": 0.95, "h": 0.84}),
        "editable_in": "pptx",
        "confidence": 0.5,
        "detected_by": "default_canvas",
    }
    for slot in slots:
        slot["panel_id"] = panel["id"]
    layout = {
        "summary": "Reference geometry inferred by editable rebuild layout planner.",
        "layout_mode": mode,
        "status": "pass",
        "canvas": {"width_px": canvas_w, "height_px": canvas_h, "width_in": width_in, "height_in": height_in, "background": background},
        "panels": [panel],
        "cards": [],
        "slots": slots,
        "legend_regions": [],
        "palette": palette,
        "confidence": 0.55 if slots else 0.25,
        "vlm_status": "not_requested",
        "warnings": [],
    }
    if mode in {"vlm", "hybrid"}:
        if vlm_adapter:
            try:
                vlm_layout = vlm_adapter(reference, layout)
                if isinstance(vlm_layout, dict):
                    layout = _merge_vlm_layout(layout, vlm_layout)
            except Exception as exc:
                layout["warnings"].append(f"vlm_layout_failed:{exc}")
                layout["vlm_status"] = "fallback"
        else:
            layout["vlm_status"] = "unavailable_fallback_to_heuristic"
            if mode == "vlm":
                layout["warnings"].append("layout_mode_vlm_requested_without_adapter")
    _draw_overlay(reference, out / "reference_geometry_overlay.png", layout)
    return layout
