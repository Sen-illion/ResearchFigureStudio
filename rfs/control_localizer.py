from __future__ import annotations

import math
import inspect
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from .utils import read_json

VALID_RENDER_STYLES = {
    "filled_block_arrow",
    "line_connector",
    "elbow_connector",
    "branch_line_connector",
    "dashed_loop_connector",
}
VALID_ROUTE_INTENTS = {"straight", "orthogonal", "branch", "loop"}
VALID_VISUAL_WEIGHTS = {"chunky", "normal", "thin"}
VALID_PREFERRED_AXES = {"horizontal", "vertical", "horizontal_first", "vertical_first"}
VALID_LINE_PATTERNS = {"solid", "dash", "dashed"}


def _center(box: dict) -> tuple[float, float]:
    return float(box["x"]) + float(box["w"]) / 2, float(box["y"]) + float(box["h"]) / 2


def _nearest_slot(point: tuple[float, float], slots: list[dict]) -> dict | None:
    if not slots:
        return None
    px, py = point
    return min(slots, key=lambda slot: (_center(slot["bbox_percent"])[0] - px) ** 2 + (_center(slot["bbox_percent"])[1] - py) ** 2)


def _distance_to_bbox(point: tuple[float, float], obj: dict | None) -> float:
    if not obj or not isinstance(obj.get("bbox_percent"), dict):
        return 1.0
    box = obj["bbox_percent"]
    px, py = point
    x = float(box["x"])
    y = float(box["y"])
    w = float(box["w"])
    h = float(box["h"])
    dx = max(x - px, 0.0, px - (x + w))
    dy = max(y - py, 0.0, py - (y + h))
    return math.hypot(dx, dy)


def _coerce_choice(value, allowed: set[str], default: str = "") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "block_arrow": "filled_block_arrow",
        "chunky_arrow": "filled_block_arrow",
        "thick_arrow": "filled_block_arrow",
        "straight_arrow": "line_connector",
        "elbow": "elbow_connector",
        "orthogonal_connector": "elbow_connector",
        "branch_connector": "branch_line_connector",
        "dashed_loop": "dashed_loop_connector",
        "loop_connector": "dashed_loop_connector",
        "dashed": "dash",
    }
    text = aliases.get(text, text)
    return text if text in allowed else default


def _slot_by_id(slots: list[dict]) -> dict[str, dict]:
    return {str(slot.get("id")): slot for slot in slots if isinstance(slot, dict) and slot.get("id")}


def _bindable_objects(out_dir: Path, slots: list[dict]) -> list[dict]:
    bindable = [dict(slot) for slot in slots if isinstance(slot, dict) and isinstance(slot.get("bbox_percent"), dict)]
    seen = {str(item.get("id")) for item in bindable}
    try:
        geometry = read_json(out_dir / "reference_geometry.json")
    except Exception:
        geometry = {}
    for card in geometry.get("cards", []) if isinstance(geometry, dict) else []:
        if not isinstance(card, dict) or not isinstance(card.get("bbox_percent"), dict):
            continue
        card_id = str(card.get("id") or "")
        if not card_id or card_id in seen:
            continue
        enriched = dict(card)
        enriched.setdefault("display_label", card.get("title") or card_id)
        enriched.setdefault("paper_concept", card.get("title") or card_id)
        enriched.setdefault("semantic_role", "reference_card")
        enriched.setdefault("asset_type", "editable_card")
        bindable.append(enriched)
        seen.add(card_id)
    return bindable


def _edge_path(source: dict | None, target: dict | None) -> list[list[float]]:
    if not source or not target:
        return []
    sbox = source.get("bbox_percent") if isinstance(source.get("bbox_percent"), dict) else None
    tbox = target.get("bbox_percent") if isinstance(target.get("bbox_percent"), dict) else None
    if not sbox or not tbox:
        return []
    sx, sy = _center(sbox)
    tx, ty = _center(tbox)
    if abs(tx - sx) >= abs(ty - sy):
        start = (float(sbox["x"]) + (float(sbox["w"]) if tx >= sx else 0.0), sy)
        end = (float(tbox["x"]) + (0.0 if tx >= sx else float(tbox["w"])), ty)
    else:
        start = (sx, float(sbox["y"]) + (float(sbox["h"]) if ty >= sy else 0.0))
        end = (tx, float(tbox["y"]) + (0.0 if ty >= sy else float(tbox["h"])))
    return [[round(start[0], 4), round(start[1], 4)], [round(end[0], 4), round(end[1], 4)]]


def _sequence_controls(slots: list[dict], palette: list[str]) -> list[dict]:
    ordered = sorted(slots, key=lambda slot: (float(slot["bbox_percent"]["y"]), float(slot["bbox_percent"]["x"])))
    arrows = []
    for idx, (src, dst) in enumerate(zip(ordered[:-1], ordered[1:]), start=1):
        sbox = src["bbox_percent"]
        dbox = dst["bbox_percent"]
        sx = float(sbox["x"]) + float(sbox["w"])
        sy = float(sbox["y"]) + float(sbox["h"]) / 2
        tx = float(dbox["x"])
        ty = float(dbox["y"]) + float(dbox["h"]) / 2
        dx = tx - sx
        dy = ty - sy
        arrows.append({
            "id": f"arrow_{idx:02d}",
            "source": src["id"],
            "target": dst["id"],
            "source_id": src["id"],
            "target_id": dst["id"],
            "control_kind": "straight_arrow",
            "path_percent": [[round(sx, 4), round(sy, 4)], [round(tx, 4), round(ty, 4)]],
            "arrowhead_direction": round(math.degrees(math.atan2(dy, dx)), 2),
            "stroke_color": palette[2] if len(palette) > 2 else "#4A6FA5",
            "stroke_width_pt": 1.5,
            "dash_style": "solid",
            "line_pattern": "solid",
            "confidence": 0.35,
            "detected_by": "sequence_fallback",
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
        })
    return arrows


def _cv_line_controls(reference_path: Path, slots: list[dict], palette: list[str]) -> list[dict]:
    try:
        import cv2
    except Exception:
        return []
    image = cv2.imread(str(reference_path))
    if image is None:
        return []
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, math.pi / 180, threshold=40, minLineLength=max(24, min(width, height) // 14), maxLineGap=12)
    if lines is None:
        return []
    candidates = []
    for line in lines[:80]:
        x1, y1, x2, y2 = [int(v) for v in line[0]]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < min(width, height) * 0.06:
            continue
        p1 = (x1 / width, y1 / height)
        p2 = (x2 / width, y2 / height)
        source = _nearest_slot(p1, slots)
        target = _nearest_slot(p2, slots)
        if not source or not target or source["id"] == target["id"]:
            continue
        if _distance_to_bbox(p1, source) > 0.075 or _distance_to_bbox(p2, target) > 0.075:
            continue
        direction = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        candidates.append({
            "line": [p1, p2],
            "length": length,
            "source": source,
            "target": target,
            "direction": direction,
        })
    candidates.sort(key=lambda item: item["length"], reverse=True)
    arrows = []
    seen = set()
    for candidate in candidates:
        source = candidate["source"]["id"]
        target = candidate["target"]["id"]
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        p1, p2 = candidate["line"]
        arrows.append({
            "id": f"arrow_{len(arrows) + 1:02d}",
            "source": source,
            "target": target,
            "source_id": source,
            "target_id": target,
            "control_kind": "straight_arrow",
            "path_percent": [[round(p1[0], 4), round(p1[1], 4)], [round(p2[0], 4), round(p2[1], 4)]],
            "arrowhead_direction": round(candidate["direction"], 2),
            "stroke_color": palette[2] if len(palette) > 2 else "#4A6FA5",
            "stroke_width_pt": 1.4,
            "dash_style": "solid",
            "line_pattern": "solid",
            "confidence": 0.55,
            "detected_by": "cv_hough_line",
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
        })
        if len(arrows) >= max(1, min(16, len(slots) + 2)):
            break
    return arrows


def _normalize_controls(raw: list[dict], slots: list[dict], palette: list[str]) -> list[dict]:
    slot_ids = {str(slot.get("id")) for slot in slots}
    objects = _slot_by_id(slots)
    normalized = []
    for idx, item in enumerate(raw or [], start=1):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_id") or item.get("source") or "")
        target = str(item.get("target_id") or item.get("target") or "")
        path = item.get("path_percent")
        if source not in slot_ids or target not in slot_ids:
            continue
        points = []
        if isinstance(path, list):
            for point in path:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                points.append([round(max(0.0, min(1.0, float(point[0]))), 4), round(max(0.0, min(1.0, float(point[1]))), 4)])
        has_reference_path = len(points) >= 2
        if len(points) < 2:
            points = _edge_path(objects.get(source), objects.get(target))
        if len(points) < 2:
            continue
        dx = points[-1][0] - points[0][0]
        dy = points[-1][1] - points[0][1]
        dash_style = str(item.get("dash_style") or item.get("line_pattern") or "solid")
        line_pattern = _coerce_choice(dash_style, VALID_LINE_PATTERNS, "solid")
        render_style = _coerce_choice(item.get("render_style"), VALID_RENDER_STYLES, "")
        route_intent = _coerce_choice(item.get("route_intent"), VALID_ROUTE_INTENTS, "")
        visual_weight = _coerce_choice(item.get("visual_weight"), VALID_VISUAL_WEIGHTS, "")
        preferred_axis = _coerce_choice(item.get("preferred_axis"), VALID_PREFERRED_AXES, "")
        explicit_route_policy = str(item.get("route_policy") or "").strip()
        route_policy = explicit_route_policy or ("preserve_reference_path" if has_reference_path else "bbox_route_from_hint")
        route_style = str(item.get("route_style") or ("dashed_loop" if str(item.get("control_kind") or "").lower() == "dashed_loop" else ""))
        if line_pattern in {"dash", "dashed"} and len(points) >= 3 and not route_style:
            route_style = "dashed_spline_like"
        record = {
            "id": str(item.get("id") or f"arrow_{idx:02d}"),
            "source": source,
            "target": target,
            "source_id": source,
            "target_id": target,
            "target_ids": [str(target_id) for target_id in item.get("target_ids", []) if str(target_id) in slot_ids] if isinstance(item.get("target_ids"), list) else [],
            "control_kind": str(item.get("control_kind") or "straight_arrow"),
            "path_percent": points,
            "arrowhead_direction": float(item.get("arrowhead_direction") if item.get("arrowhead_direction") is not None else math.degrees(math.atan2(dy, dx))),
            "stroke_color": str(item.get("stroke_color") or (palette[2] if len(palette) > 2 else "#4A6FA5")),
            "stroke_width_pt": float(item.get("stroke_width_pt") or 1.5),
            "dash_style": dash_style,
            "line_pattern": "dash" if line_pattern in {"dash", "dashed"} else "solid",
            "route_style": route_style,
            "render_style": render_style,
            "route_intent": route_intent,
            "visual_weight": visual_weight,
            "preferred_axis": preferred_axis,
            "bend_side": str(item.get("bend_side") or ""),
            "fill_color": str(item.get("fill_color") or ""),
            "outline_color": str(item.get("outline_color") or ""),
            "outline_width_pt": item.get("outline_width_pt"),
            "block_arrow_thickness_percent": item.get("block_arrow_thickness_percent"),
            "line_cap": str(item.get("line_cap") or ""),
            "arrowhead_size": str(item.get("arrowhead_size") or ""),
            "binding_source": "vlm",
            "route_policy": route_policy,
            "confidence": float(item.get("confidence") or 0.8),
            "detected_by": str(item.get("detected_by") or "vlm"),
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
        }
        normalized.append({key: value for key, value in record.items() if value not in ("", [], None)})
    return normalized


def _draw_overlay(reference_path: Path, out_path: Path, arrows: list[dict]) -> None:
    with Image.open(reference_path).convert("RGB") as image:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        for arrow in arrows:
            points = arrow.get("path_percent") or []
            if len(points) < 2:
                continue
            xy = [(float(p[0]) * width, float(p[1]) * height) for p in points]
            color = str(arrow.get("stroke_color") or "#D94141")
            draw.line(xy, fill=color, width=4)
            end = xy[-1]
            prev = xy[-2]
            angle = math.atan2(end[1] - prev[1], end[0] - prev[0])
            head = 12
            left = (end[0] - head * math.cos(angle - 0.45), end[1] - head * math.sin(angle - 0.45))
            right = (end[0] - head * math.cos(angle + 0.45), end[1] - head * math.sin(angle + 0.45))
            draw.polygon([end, left, right], fill=color)
            draw.text((end[0] + 3, end[1] + 3), str(arrow.get("id") or ""), fill=color)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)


def _flow_edges(flow_graph: dict | None) -> list[dict]:
    if not isinstance(flow_graph, dict):
        return []
    return [item for item in flow_graph.get("edges", []) or [] if isinstance(item, dict)]


def _flow_graph_stats(flow_graph: dict | None, objects: list[dict]) -> dict:
    object_ids = {str(item.get("id") or "") for item in objects if isinstance(item, dict)}
    edges = _flow_edges(flow_graph)
    invalid = []
    for edge in edges:
        source = str(edge.get("source_id") or edge.get("source") or "")
        target = str(edge.get("target_id") or edge.get("target") or "")
        if source not in object_ids or target not in object_ids:
            invalid.append(str(edge.get("id") or f"{source}->{target}"))
    return {
        "flow_graph_used": bool(edges),
        "flow_graph_edge_count": len(edges),
        "invalid_flow_edge_count": len(invalid),
        "invalid_flow_edge_ids": invalid,
    }


def _call_control_adapter(adapter: Callable, reference: Path, bindable: list[dict], heuristic: list[dict], flow_graph: dict | None):
    try:
        signature = inspect.signature(adapter)
        if len(signature.parameters) >= 4:
            return adapter(reference, bindable, heuristic, flow_graph)
    except (TypeError, ValueError):
        pass
    return adapter(reference, bindable, heuristic)


def localize_reference_controls(
    reference_path: str | Path,
    slots: list[dict],
    palette: list[str],
    out_dir: str | Path,
    mode: str = "hybrid",
    control_adapter: Callable[[str | Path, list[dict], list[dict]], dict | list[dict]] | None = None,
    flow_graph: dict | None = None,
) -> dict:
    reference = Path(reference_path)
    out = Path(out_dir)
    warnings = []
    bindable = _bindable_objects(out, slots)
    flow_stats = _flow_graph_stats(flow_graph, bindable)
    if flow_stats["invalid_flow_edge_count"]:
        warnings.append(f"{flow_stats['invalid_flow_edge_count']}_invalid_flow_graph_edge(s)")
    cv_heuristic = _cv_line_controls(reference, bindable, palette)
    heuristic = cv_heuristic or _sequence_controls(slots, palette)
    _draw_overlay(reference, out / "reference_controls_candidates_overlay.png", heuristic)
    arrows = heuristic
    vlm_status = "not_requested"
    if mode in {"vlm", "hybrid"}:
        if control_adapter:
            try:
                raw = _call_control_adapter(control_adapter, reference, bindable, heuristic, flow_graph)
                raw_arrows = raw.get("arrows", []) if isinstance(raw, dict) else raw
                normalized = _normalize_controls(raw_arrows, bindable, palette)
                if normalized:
                    arrows = normalized
                    vlm_status = "used"
                    invalid_count = max(0, len(raw_arrows or []) - len(normalized))
                    if invalid_count:
                        warnings.append(f"{invalid_count}_invalid_vlm_control_arrow(s)_dropped")
                else:
                    vlm_status = "fallback"
                    warnings.append("control_adapter_returned_no_valid_arrows")
            except Exception as exc:
                vlm_status = "fallback"
                warnings.append(f"vlm_control_failed:{exc}")
        else:
            vlm_status = "unavailable_fallback_to_heuristic"
            if mode == "vlm":
                warnings.append("control_mode_vlm_requested_without_adapter")
    if mode == "manual":
        arrows = []
        vlm_status = "manual_empty"
    _draw_overlay(reference, out / "reference_controls_overlay.png", arrows)
    return {
        "summary": "Reference control localization report.",
        "mode": mode,
        "status": "ok",
        "vlm_status": vlm_status,
        "vlm_model": str(raw.get("_vlm_model")) if mode in {"vlm", "hybrid"} and isinstance(locals().get("raw"), dict) and raw.get("_vlm_model") else None,
        "bindable_object_count": len(bindable),
        "heuristic_arrow_count": len(heuristic),
        "cv_heuristic_arrow_count": len(cv_heuristic),
        "vlm_arrow_count": len(normalized) if isinstance(locals().get("normalized"), list) else 0,
        "merged_arrow_count": len(arrows),
        "warnings": warnings,
        "arrows": arrows,
        **flow_stats,
    }
