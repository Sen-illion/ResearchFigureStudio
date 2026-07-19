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


def _bbox_iou(a: dict, b: dict) -> float:
    ax0, ay0 = float(a["x"]), float(a["y"])
    ax1, ay1 = ax0 + float(a["w"]), ay0 + float(a["h"])
    bx0, by0 = float(b["x"]), float(b["y"])
    bx1, by1 = bx0 + float(b["w"]), by0 + float(b["h"])
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = float(a["w"]) * float(a["h"]) + float(b["w"]) * float(b["h"]) - inter
    return inter / max(union, 0.000001)


def _is_same_frame_box(box: dict, frame: dict) -> bool:
    fb = frame.get("bbox_percent") if isinstance(frame, dict) else None
    if not isinstance(fb, dict):
        return False
    if _bbox_iou(box, fb) > 0.55:
        return True
    tolerance = 0.012
    return (
        abs(float(box["x"]) - float(fb["x"])) <= tolerance
        and abs(float(box["y"]) - float(fb["y"])) <= tolerance
        and abs(float(box["w"]) - float(fb["w"])) <= tolerance * 2
        and abs(float(box["h"]) - float(fb["h"])) <= tolerance * 2
    )


def _hex_from_rgb_array(values) -> str:
    try:
        import numpy as np
    except Exception:
        return "#59AFCB"
    if values is None or len(values) == 0:
        return "#59AFCB"
    rgb = np.median(values, axis=0).astype(int)
    return rgb_hex((int(rgb[0]), int(rgb[1]), int(rgb[2])))


def _dash_style_from_edge_runs(edge_crop, thickness: int) -> str:
    try:
        import numpy as np
    except Exception:
        return "solid"
    if edge_crop.size == 0:
        return "solid"
    h, w = edge_crop.shape[:2]
    bands = [
        edge_crop[:thickness, :].max(axis=0),
        edge_crop[max(0, h - thickness):, :].max(axis=0),
        edge_crop[:, :thickness].max(axis=1),
        edge_crop[:, max(0, w - thickness):].max(axis=1),
    ]
    dashed_votes = 0
    for band in bands:
        values = np.asarray(band) > 0
        if values.size < 16:
            continue
        # Close tiny gaps caused by anti-aliasing, then count meaningful on/off runs.
        closed = np.convolve(values.astype(int), np.ones(3, dtype=int), mode="same") > 0
        runs = []
        current = bool(closed[0])
        length = 1
        for value in closed[1:]:
            if bool(value) == current:
                length += 1
            else:
                runs.append((current, length))
                current = bool(value)
                length = 1
        runs.append((current, length))
        on_runs = [length for is_on, length in runs if is_on and length >= 3]
        off_runs = [length for is_on, length in runs if not is_on and length >= 4]
        on_ratio = float(closed.mean())
        if len(on_runs) >= 3 and len(off_runs) >= 2 and 0.10 <= on_ratio <= 0.82:
            dashed_votes += 1
    return "dash" if dashed_votes >= 2 else "solid"


def _find_frame_components(reference_path: Path, canvas_w: int, canvas_h: int) -> list[dict]:
    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    image = cv2.imread(str(reference_path))
    if image is None:
        return []
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 35, 110)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    candidate_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    candidate_edges = cv2.dilate(candidate_edges, kernel, iterations=1)
    contours, hierarchy = cv2.findContours(candidate_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    image_area = canvas_w * canvas_h
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < image_area * 0.006 or area > image_area * 0.82:
            continue
        if w < 36 or h < 28:
            continue
        aspect = w / max(h, 1)
        if aspect < 0.25 or aspect > 5.8:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approx) < 4 or len(approx) > 18:
            continue

        thickness = max(3, min(14, int(min(w, h) * 0.06)))
        crop_edges = edges[y:y + h, x:x + w]
        crop_rgb = rgb[y:y + h, x:x + w]
        if crop_edges.size == 0 or crop_rgb.size == 0:
            continue

        ring_mask = np.zeros((h, w), dtype=bool)
        ring_mask[:thickness, :] = True
        ring_mask[max(0, h - thickness):, :] = True
        ring_mask[:, :thickness] = True
        ring_mask[:, max(0, w - thickness):] = True
        center_mask = ~ring_mask
        if not center_mask.any():
            continue
        ring_edge_density = float((crop_edges[ring_mask] > 0).mean())
        center_edge_density = float((crop_edges[center_mask] > 0).mean())
        center_pixels = crop_rgb[center_mask]
        ring_pixels = crop_rgb[ring_mask]
        center_median = np.median(center_pixels, axis=0)
        color_distance = np.linalg.norm(ring_pixels.astype(float) - center_median.astype(float), axis=1)
        stroke_pixels = ring_pixels[color_distance > 18]
        stroke_coverage = float(len(stroke_pixels) / max(len(ring_pixels), 1))
        if ring_edge_density < 0.045 and stroke_coverage < 0.12:
            continue
        if center_edge_density > max(0.30, ring_edge_density * 3.2):
            continue

        bbox = clamp_bbox({"x": x / canvas_w, "y": y / canvas_h, "w": w / canvas_w, "h": h / canvas_h})
        candidates.append({
            "id": f"card_{len(candidates)+1:02d}",
            "semantic_role": "outer_group_boundary" if area > image_area * 0.16 else "subcard_frame",
            "bbox_percent": bbox,
            "shape_kind": "rounded_rect" if len(approx) > 4 else "rect",
            "fill_color": _hex_from_rgb_array(center_pixels),
            "fill_transparency": 1.0,
            "stroke_color": _hex_from_rgb_array(stroke_pixels if len(stroke_pixels) else ring_pixels),
            "stroke_width_pt": 1.5,
            "dash_style": _dash_style_from_edge_runs(crop_edges, thickness),
            "corner_radius": 0.08 if len(approx) > 4 else 0.0,
            "editable_in": "pptx",
            "z_index": 12,
            "confidence": round(min(0.9, 0.45 + ring_edge_density + stroke_coverage), 3),
            "detected_by": "cv_hollow_frame",
        })

    candidates.sort(key=lambda item: (float(item["bbox_percent"]["y"]), float(item["bbox_percent"]["x"])))
    kept: list[dict] = []
    for item in candidates:
        if any(_bbox_iou(item["bbox_percent"], other["bbox_percent"]) > 0.72 for other in kept):
            continue
        item["id"] = f"card_{len(kept)+1:02d}"
        kept.append(item)
        if len(kept) >= 24:
            break
    return kept


def _find_visual_components(reference_path: Path, canvas_w: int, canvas_h: int, excluded_frames: list[dict] | None = None) -> list[dict]:
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
        bbox = clamp_bbox({"x": x / canvas_w, "y": y / canvas_h, "w": w / canvas_w, "h": h / canvas_h})
        if any(_is_same_frame_box(bbox, frame) for frame in excluded_frames or []):
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
            if prefix == "card":
                record.setdefault("semantic_role", item.get("semantic_role") or "subcard_frame")
                record.setdefault("shape_kind", item.get("shape_kind") or "rounded_rect")
                record.setdefault("stroke_color", item.get("stroke_color") or "#59AFCB")
                record.setdefault("stroke_width_pt", item.get("stroke_width_pt") or 1.5)
                dash_style = str(item.get("dash_style") or "solid").lower()
                record["dash_style"] = "dash" if dash_style == "dashed" else dash_style
                record.setdefault("fill_color", item.get("fill_color") or "#FFFFFF")
                record.setdefault("fill_transparency", item.get("fill_transparency", 1.0))
                record.setdefault("corner_radius", item.get("corner_radius", 0.08))
                record.setdefault("z_index", item.get("z_index", 12))
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
    if cards:
        merged["cards"] = cards
    merged["legend_regions"] = legends
    merged["confidence"] = float(vlm.get("confidence") or 0.75)
    merged["vlm_status"] = "used"
    if vlm.get("_vlm_model"):
        merged["vlm_model"] = str(vlm.get("_vlm_model"))
    merged.setdefault("warnings", [])
    return merged


def _design_layers(design_plan: dict | None) -> list[dict]:
    if not isinstance(design_plan, dict):
        return []
    if isinstance(design_plan.get("layers"), list):
        return [item for item in design_plan["layers"] if isinstance(item, dict)]
    layer_plan = design_plan.get("layer_plan") if isinstance(design_plan.get("layer_plan"), dict) else {}
    return [item for item in layer_plan.get("layers", []) or [] if isinstance(item, dict)]


def _apply_design_seed(layout: dict, design_plan: dict | None) -> dict:
    layers = _design_layers(design_plan)
    if not layers:
        layout["design_seed_status"] = "not_available"
        return layout
    panels = _normalize_items([item for item in layers if str(item.get("kind") or "") == "panel"], "panel")
    cards = _normalize_items([item for item in layers if str(item.get("kind") or "") == "card"], "card")
    slots = _normalize_items([item for item in layers if str(item.get("kind") or "") == "visual_slot"], "slot")
    legends = _normalize_items([item for item in layers if str(item.get("kind") or "") == "legend"], "legend")
    ignored_count = sum(1 for item in layers if str(item.get("kind") or "") in {"background", "text", "connector", "ignore"})
    if panels:
        layout["panels"] = panels
    if cards:
        layout["cards"] = cards
    if slots:
        layout["slots"] = slots
    if legends:
        layout["legend_regions"] = legends
    layout["design_seed_status"] = "used" if panels or cards or slots or legends else "no_layout_layers"
    layout["design_seed_layer_count"] = len(layers)
    layout["design_seed_ignored_layer_count"] = ignored_count
    layout["design_seed_slot_count"] = len(slots)
    layout["design_seed_card_count"] = len(cards)
    layout["design_seed_panel_count"] = len(panels)
    layout.setdefault("warnings", [])
    if ignored_count:
        layout["warnings"].append(f"{ignored_count}_non_layout_design_layer(s)_ignored")
    return layout


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
    design_plan: dict | None = None,
) -> dict:
    reference = Path(reference_path)
    out = Path(out_dir)
    with Image.open(reference).convert("RGB") as image:
        canvas_w, canvas_h = image.size
        width_in, height_in = canvas_inches(canvas_w, canvas_h)
        background = estimate_background(image)
        palette = dominant_palette(image)
    cards = _find_frame_components(reference, canvas_w, canvas_h)
    slots = _find_visual_components(reference, canvas_w, canvas_h, excluded_frames=cards) or _fallback_slots()
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
        "cards": cards,
        "slots": slots,
        "legend_regions": [],
        "palette": palette,
        "confidence": 0.55 if slots else 0.25,
        "vlm_status": "not_requested",
        "warnings": [],
    }
    layout = _apply_design_seed(layout, design_plan)
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
