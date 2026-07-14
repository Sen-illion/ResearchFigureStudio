from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import write_json

ROUTER_VERSION = "reference-constrained-orthogonal-v1"
AESTHETIC_ROUTER_VERSION = "reference-tunnel-aesthetic-v2"
DEFAULT_REFERENCE_TUNNEL_PERCENT = 0.024


def _bbox_center(bbox: dict[str, Any]) -> list[float]:
    return [
        round(float(bbox["x"]) + float(bbox["w"]) / 2, 4),
        round(float(bbox["y"]) + float(bbox["h"]) / 2, 4),
    ]


def _anchor_point(obj: dict | None, anchor: str) -> list[float] | None:
    if not obj or not isinstance(obj.get("bbox_percent"), dict):
        return None
    bbox = obj["bbox_percent"]
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    points = {
        "left_mid": [x, y + h / 2],
        "right_mid": [x + w, y + h / 2],
        "top_mid": [x + w / 2, y],
        "bottom_mid": [x + w / 2, y + h],
        "center": [x + w / 2, y + h / 2],
    }
    point = points.get(anchor) or points["center"]
    return [round(point[0], 4), round(point[1], 4)]


def _edge_path(source: dict | None, target: dict | None) -> list[list[float]]:
    if not source or not target:
        return []
    sbox = source.get("bbox_percent") if isinstance(source.get("bbox_percent"), dict) else None
    tbox = target.get("bbox_percent") if isinstance(target.get("bbox_percent"), dict) else None
    if not sbox or not tbox:
        return []
    sx, sy = _bbox_center(sbox)
    tx, ty = _bbox_center(tbox)
    dx = tx - sx
    dy = ty - sy
    if abs(dx) >= abs(dy):
        s_anchor = "right_mid" if dx >= 0 else "left_mid"
        t_anchor = "left_mid" if dx >= 0 else "right_mid"
    else:
        s_anchor = "bottom_mid" if dy >= 0 else "top_mid"
        t_anchor = "top_mid" if dy >= 0 else "bottom_mid"
    s = _anchor_point(source, s_anchor)
    t = _anchor_point(target, t_anchor)
    return [s, t] if s and t else []


def _clean_path(points: list[list[float] | None]) -> list[list[float]]:
    cleaned: list[list[float]] = []
    for point in points:
        if not point or len(point) < 2:
            continue
        x = min(1.0, max(0.0, float(point[0])))
        y = min(1.0, max(0.0, float(point[1])))
        rounded = [round(x, 4), round(y, 4)]
        if not cleaned or abs(cleaned[-1][0] - rounded[0]) > 0.001 or abs(cleaned[-1][1] - rounded[1]) > 0.001:
            cleaned.append(rounded)
    if len(cleaned) <= 2:
        return cleaned
    simplified = [cleaned[0]]
    for index in range(1, len(cleaned) - 1):
        prev = simplified[-1]
        cur = cleaned[index]
        nxt = cleaned[index + 1]
        same_x = abs(prev[0] - cur[0]) < 0.001 and abs(cur[0] - nxt[0]) < 0.001
        same_y = abs(prev[1] - cur[1]) < 0.001 and abs(cur[1] - nxt[1]) < 0.001
        if not (same_x or same_y):
            simplified.append(cur)
    simplified.append(cleaned[-1])
    return simplified


def _segments(points: list[list[float]]) -> list[tuple[list[float], list[float]]]:
    return [(points[i], points[i + 1]) for i in range(max(0, len(points) - 1))]


def _path_length(points: list[list[float]]) -> float:
    total = 0.0
    for a, b in _segments(points):
        total += ((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2) ** 0.5
    return round(total, 4)


def _path_normal(points: list[list[float]]) -> list[float]:
    if len(points) < 2:
        return [0.0, 0.0]
    dx = float(points[-1][0]) - float(points[0][0])
    dy = float(points[-1][1]) - float(points[0][1])
    length = (dx * dx + dy * dy) ** 0.5
    if length < 0.0001:
        return [0.0, 0.0]
    return [-dy / length, dx / length]


def _point_distance(a: list[float], b: list[float]) -> float:
    return ((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2) ** 0.5


def _point_segment_distance(point: list[float], a: list[float], b: list[float]) -> float:
    px, py = float(point[0]), float(point[1])
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom < 0.0000001:
        return _point_distance(point, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    proj = [ax + t * dx, ay + t * dy]
    return _point_distance(point, proj)


def _max_distance_to_polyline(points: list[list[float]], reference: list[list[float]]) -> float:
    segments = _segments(reference)
    if not segments:
        return 0.0
    distances = []
    for point in points:
        distances.append(min(_point_segment_distance(point, a, b) for a, b in segments))
    return round(max(distances, default=0.0), 4)


def _lane_offset(lane_index: int, lane_count: int, tunnel_percent: float) -> float:
    if lane_count <= 1:
        return 0.0
    centered = float(lane_index) - (float(lane_count) - 1.0) / 2.0
    step = min(0.006, max(0.002, tunnel_percent / max(lane_count, 1)))
    return max(-tunnel_percent * 0.82, min(tunnel_percent * 0.82, centered * step))


def _shift_point(point: list[float], normal: list[float], offset: float) -> list[float]:
    return [
        round(min(1.0, max(0.0, float(point[0]) + normal[0] * offset)), 4),
        round(min(1.0, max(0.0, float(point[1]) + normal[1] * offset)), 4),
    ]


def _aesthetic_tunnel_path(
    points: list[list[float]],
    lane_index: int,
    lane_count: int,
    role: str,
    tunnel_percent: float = DEFAULT_REFERENCE_TUNNEL_PERCENT,
) -> tuple[list[list[float]], dict[str, Any]]:
    original = _clean_path(points)
    if len(original) < 2:
        return original, {
            "routing_algorithm": AESTHETIC_ROUTER_VERSION,
            "route_generation_status": "aesthetic_no_path",
            "reference_tunnel_percent": tunnel_percent,
            "reference_path_delta_max": 0.0,
            "reference_tunnel_preserved": True,
        }
    normal = _path_normal(original)
    offset = _lane_offset(lane_index, lane_count, tunnel_percent)
    adjusted = [list(point) for point in original]
    if abs(offset) > 0.0001 and len(original) == 2:
        mid = [
            (float(original[0][0]) + float(original[1][0])) / 2.0,
            (float(original[0][1]) + float(original[1][1])) / 2.0,
        ]
        adjusted = [original[0], _shift_point(mid, normal, offset), original[-1]]
    elif role in {"main_flow", "module_flow"}:
        # Single-lane arrows keep the exact reference geometry; the PPT renderer
        # still softens them through curve connectors, halo, and line caps.
        adjusted = original
    adjusted = _clean_path(adjusted)
    delta = _max_distance_to_polyline(adjusted, original)
    return adjusted, {
        "routing_algorithm": AESTHETIC_ROUTER_VERSION,
        "route_generation_status": "aesthetic_tunnel_adjusted" if adjusted != original else "aesthetic_style_only",
        "reference_tunnel_percent": tunnel_percent,
        "reference_path_delta_max": delta,
        "reference_tunnel_preserved": delta <= tunnel_percent,
        "lane_offset_percent": round(offset, 4),
    }


def _orientation(a: list[float], b: list[float], c: list[float]) -> float:
    return (float(b[1]) - float(a[1])) * (float(c[0]) - float(b[0])) - (float(b[0]) - float(a[0])) * (float(c[1]) - float(b[1]))


def _share_endpoint(a1: list[float], a2: list[float], b1: list[float], b2: list[float]) -> bool:
    pairs = ((a1, b1), (a1, b2), (a2, b1), (a2, b2))
    return any(abs(p[0] - q[0]) < 0.002 and abs(p[1] - q[1]) < 0.002 for p, q in pairs)


def _segments_cross(a1: list[float], a2: list[float], b1: list[float], b2: list[float]) -> bool:
    if _share_endpoint(a1, a2, b1, b2):
        return False
    # Fast reject by segment bounding boxes.
    if max(min(a1[0], a2[0]), min(b1[0], b2[0])) > min(max(a1[0], a2[0]), max(b1[0], b2[0])):
        return False
    if max(min(a1[1], a2[1]), min(b1[1], b2[1])) > min(max(a1[1], a2[1]), max(b1[1], b2[1])):
        return False
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)
    return o1 * o2 < 0 and o3 * o4 < 0


def _point_inside_bbox(point: list[float], bbox: dict[str, Any], pad: float = 0.0) -> bool:
    x = float(bbox["x"]) - pad
    y = float(bbox["y"]) - pad
    w = float(bbox["w"]) + pad * 2
    h = float(bbox["h"]) + pad * 2
    return x <= float(point[0]) <= x + w and y <= float(point[1]) <= y + h


def _segment_bbox_overlap(a: list[float], b: list[float], bbox: dict[str, Any], pad: float = 0.004) -> bool:
    if _point_inside_bbox(a, bbox, pad=pad) or _point_inside_bbox(b, bbox, pad=pad):
        return True
    x0 = float(bbox["x"]) - pad
    y0 = float(bbox["y"]) - pad
    x1 = float(bbox["x"]) + float(bbox["w"]) + pad
    y1 = float(bbox["y"]) + float(bbox["h"]) + pad
    edges = [
        ([x0, y0], [x1, y0]),
        ([x1, y0], [x1, y1]),
        ([x1, y1], [x0, y1]),
        ([x0, y1], [x0, y0]),
    ]
    return any(_segments_cross(a, b, e0, e1) for e0, e1 in edges)


def _candidate_lanes(source: dict, target: dict, obstacles: dict[str, dict], axis: str, limit: int = 18) -> list[float]:
    sbox = source["bbox_percent"]
    tbox = target["bbox_percent"]
    if axis == "x":
        base = [
            float(sbox["x"]),
            float(sbox["x"]) + float(sbox["w"]),
            float(sbox["x"]) + float(sbox["w"]) / 2,
            float(tbox["x"]),
            float(tbox["x"]) + float(tbox["w"]),
            float(tbox["x"]) + float(tbox["w"]) / 2,
        ]
        for obj in obstacles.values():
            bbox = obj.get("bbox_percent") if isinstance(obj.get("bbox_percent"), dict) else None
            if not bbox:
                continue
            base.extend([float(bbox["x"]) - 0.014, float(bbox["x"]) + float(bbox["w"]) + 0.014])
    else:
        base = [
            float(sbox["y"]),
            float(sbox["y"]) + float(sbox["h"]),
            float(sbox["y"]) + float(sbox["h"]) / 2,
            float(tbox["y"]),
            float(tbox["y"]) + float(tbox["h"]),
            float(tbox["y"]) + float(tbox["h"]) / 2,
        ]
        for obj in obstacles.values():
            bbox = obj.get("bbox_percent") if isinstance(obj.get("bbox_percent"), dict) else None
            if not bbox:
                continue
            base.extend([float(bbox["y"]) - 0.014, float(bbox["y"]) + float(bbox["h"]) + 0.014])
    midpoint = (sum(base[:6]) / 6) if len(base) >= 6 else 0.5
    lanes = sorted({round(min(0.985, max(0.015, value)), 4) for value in base}, key=lambda value: abs(value - midpoint))
    return sorted(lanes[:limit])


def _crossing_count(points: list[list[float]], existing_segments: list[tuple[list[float], list[float]]]) -> int:
    count = 0
    for a, b in _segments(points):
        for c, d in existing_segments:
            if _segments_cross(a, b, c, d):
                count += 1
    return count


def _obstacle_overlaps(points: list[list[float]], obstacles: dict[str, dict]) -> list[str]:
    overlaps = []
    for obj_id, obj in obstacles.items():
        bbox = obj.get("bbox_percent") if isinstance(obj.get("bbox_percent"), dict) else None
        if not bbox:
            continue
        if any(_segment_bbox_overlap(a, b, bbox) for a, b in _segments(points)):
            overlaps.append(obj_id)
    return overlaps


def _score_candidate(points: list[list[float]], obstacles: dict[str, dict], existing_segments: list[tuple[list[float], list[float]]]) -> tuple[float, dict[str, Any]]:
    overlaps = _obstacle_overlaps(points, obstacles)
    crossings = _crossing_count(points, existing_segments)
    bends = max(0, len(points) - 2)
    length = _path_length(points)
    near_edge_penalty = sum(1 for x, y in points if x < 0.012 or x > 0.988 or y < 0.012 or y > 0.988)
    score = len(overlaps) * 1000 + crossings * 80 + bends * 8 + length * 16 + near_edge_penalty * 10
    return score, {
        "candidate_score": round(score, 4),
        "obstacle_overlap_count": len(overlaps),
        "obstacle_overlap_ids": overlaps[:12],
        "crossing_count": crossings,
        "bend_count": bends,
        "path_length": length,
    }


def _best_fallback_path(
    source: dict | None,
    target: dict | None,
    obstacles: dict[str, dict],
    existing_segments: list[tuple[list[float], list[float]]],
) -> tuple[list[list[float]], dict[str, Any]]:
    if not source or not target:
        return [], {"routing_algorithm": ROUTER_VERSION, "route_generation_status": "missing_source_or_target"}
    direct = _edge_path(source, target)
    if len(direct) < 2:
        return [], {"routing_algorithm": ROUTER_VERSION, "route_generation_status": "missing_anchor_points"}

    sx, sy = direct[0]
    tx, ty = direct[-1]
    x_lanes = _candidate_lanes(source, target, obstacles, "x")
    y_lanes = _candidate_lanes(source, target, obstacles, "y")
    candidates = [_clean_path(direct)]
    candidates.extend(_clean_path([direct[0], [x, sy], [x, ty], direct[-1]]) for x in x_lanes)
    candidates.extend(_clean_path([direct[0], [sx, y], [tx, y], direct[-1]]) for y in y_lanes)
    # Two-lane orthogonal paths can move around large central obstacles without
    # changing the source-target semantics from the reference-derived program.
    for x in x_lanes[:12]:
        for y in y_lanes[:12]:
            candidates.append(_clean_path([direct[0], [x, sy], [x, y], [tx, y], direct[-1]]))
            candidates.append(_clean_path([direct[0], [sx, y], [x, y], [x, ty], direct[-1]]))

    best_path: list[list[float]] = direct
    best_meta: dict[str, Any] = {}
    best_score = float("inf")
    seen: set[tuple[tuple[float, float], ...]] = set()
    for candidate in candidates:
        if len(candidate) < 2:
            continue
        key = tuple((point[0], point[1]) for point in candidate)
        if key in seen:
            continue
        seen.add(key)
        score, meta = _score_candidate(candidate, obstacles, existing_segments)
        if score < best_score:
            best_score = score
            best_path = candidate
            best_meta = meta
    best_meta.update({
        "routing_algorithm": ROUTER_VERSION,
        "route_generation_status": "fallback_route_selected",
        "candidate_count": len(seen),
    })
    return best_path, best_meta


def _infer_role(arrow: dict, out_counts: dict[str, int], in_counts: dict[str, int], panel_ids: set[str]) -> str:
    kind = str(arrow.get("control_kind") or arrow.get("type") or "").lower()
    source = str(arrow.get("source_id") or arrow.get("source") or "")
    target = str(arrow.get("target_id") or arrow.get("target") or "")
    if "loop" in kind or "dashed" in kind:
        return "feedback_loop"
    # Branch/convergence semantics should win over panel membership. Some RFS
    # programs use panel-like IDs for central modules, and treating those first
    # collapses every connector into the same main-flow style.
    if out_counts.get(source, 0) > 1:
        return "branch"
    if in_counts.get(target, 0) > 1:
        return "convergence"
    if source in panel_ids or target in panel_ids:
        return "main_flow"
    return "module_flow"


def _style_for_role(role: str, arrow: dict, mode: str = "reference") -> dict[str, Any]:
    kind = str(arrow.get("control_kind") or arrow.get("type") or "").lower()
    if str(mode).lower() == "aesthetic":
        if role == "main_flow":
            return {"route_style": "soft_curve", "stroke_width_pt": 2.35, "arrowhead_size": "med", "line_cap": "round", "halo_width_pt": 4.4, "halo_color": "#FFFFFF"}
        if role == "branch":
            return {"route_style": "metro_bundle", "stroke_width_pt": 1.45, "arrowhead_size": "sm", "line_cap": "round", "halo_width_pt": 3.2, "halo_color": "#FFFFFF"}
        if role == "convergence":
            return {"route_style": "metro_bundle", "stroke_width_pt": 1.45, "arrowhead_size": "sm", "line_cap": "round", "halo_width_pt": 3.2, "halo_color": "#FFFFFF"}
        if role == "feedback_loop":
            return {"route_style": "dashed_loop", "stroke_width_pt": 1.75, "arrowhead_size": "sm", "line_cap": "round", "line_pattern": "dash", "halo_width_pt": 3.0, "halo_color": "#FFFFFF"}
        if "elbow" in kind:
            return {"route_style": "rounded_elbow", "stroke_width_pt": 1.6, "arrowhead_size": "sm", "line_cap": "round", "halo_width_pt": 3.0, "halo_color": "#FFFFFF"}
        return {"route_style": "soft_curve", "stroke_width_pt": 1.55, "arrowhead_size": "sm", "line_cap": "round", "halo_width_pt": 3.0, "halo_color": "#FFFFFF"}
    if role == "main_flow":
        return {"route_style": "soft_straight", "stroke_width_pt": 2.2, "arrowhead_size": "med", "line_cap": "round"}
    if role == "branch":
        return {"route_style": "bundled_elbow", "stroke_width_pt": 1.55, "arrowhead_size": "sm", "line_cap": "round"}
    if role == "convergence":
        return {"route_style": "bundled_elbow", "stroke_width_pt": 1.55, "arrowhead_size": "sm", "line_cap": "round"}
    if role == "feedback_loop":
        return {"route_style": "dashed_spline_like", "stroke_width_pt": 1.8, "arrowhead_size": "sm", "line_cap": "round", "line_pattern": "dash"}
    if "elbow" in kind:
        return {"route_style": "rounded_elbow", "stroke_width_pt": 1.65, "arrowhead_size": "sm", "line_cap": "round"}
    return {"route_style": "soft_straight", "stroke_width_pt": 1.45, "arrowhead_size": "sm", "line_cap": "round"}


def _reference_locked(arrow: dict) -> bool:
    path = arrow.get("path_percent") if isinstance(arrow.get("path_percent"), list) else []
    if len(path) < 2:
        return False
    source = str(arrow.get("binding_source") or arrow.get("detected_by") or "").lower()
    if any(term in source for term in ("reference", "opencv", "vlm", "explicit", "candidate", "layout")):
        return True
    # In reference-primary mode, existing normalized paths are treated as a
    # reference contract unless explicitly marked as fallback.
    return str(arrow.get("route_policy", "")).lower() != "fallback_reroute_allowed"


def _route_metrics(arrows: list[dict], objects: dict[str, dict]) -> tuple[dict[str, dict], int]:
    metrics: dict[str, dict] = {}
    all_segments: list[tuple[str, list[float], list[float]]] = []
    for arrow in arrows:
        points = arrow.get("path_percent") if isinstance(arrow.get("path_percent"), list) else []
        sid = str(arrow.get("source_id") or arrow.get("source") or "")
        tid = str(arrow.get("target_id") or arrow.get("target") or "")
        obstacles = []
        for obj_id, obj in objects.items():
            if obj_id in {sid, tid} or not isinstance(obj.get("bbox_percent"), dict):
                continue
            if any(_segment_bbox_overlap(a, b, obj["bbox_percent"]) for a, b in _segments(points)):
                obstacles.append(obj_id)
        metrics[str(arrow.get("id"))] = {
            "path_length": _path_length(points),
            "bend_count": max(0, len(points) - 2),
            "obstacle_overlap_count": len(obstacles),
            "obstacle_overlap_ids": obstacles[:12],
            "point_count": len(points),
        }
        for a, b in _segments(points):
            all_segments.append((str(arrow.get("id")), a, b))

    crossing_count = 0
    crossings_by_arrow = {str(arrow.get("id")): 0 for arrow in arrows}
    for idx, (aid, a1, a2) in enumerate(all_segments):
        for bid, b1, b2 in all_segments[idx + 1:]:
            if aid == bid:
                continue
            if _segments_cross(a1, a2, b1, b2):
                crossing_count += 1
                crossings_by_arrow[aid] = crossings_by_arrow.get(aid, 0) + 1
                crossings_by_arrow[bid] = crossings_by_arrow.get(bid, 0) + 1
    for aid, count in crossings_by_arrow.items():
        if aid in metrics:
            metrics[aid]["crossing_count"] = count
    return metrics, crossing_count


def style_and_route_arrows(
    program: dict,
    out_dir: str | Path,
    mode: str = "reference",
) -> dict:
    """Add reference-preserving arrow aesthetics and QA artifacts.

    The reference image remains the hard constraint. Existing reference-derived
    routes are not freely rerouted; this stage mostly adds style, bundling
    metadata, and diagnostics. Only missing/fallback paths are synthesized.
    """
    out = Path(out_dir)
    if str(mode).lower() == "off":
        write_json(out / "arrow_style_profile.json", {"summary": "Arrow styling skipped.", "mode": "off"})
        write_json(out / "selected_arrow_routes.json", {"summary": "Arrow routing skipped.", "mode": "off", "routes": []})
        write_json(out / "arrow_quality_report.json", {"summary": "Arrow quality skipped.", "mode": "off", "status": "skipped"})
        return program

    panels = program.get("panels", []) if isinstance(program.get("panels"), list) else []
    slots = program.get("slots", []) if isinstance(program.get("slots"), list) else []
    objects = {str(item.get("id")): item for item in panels + slots if isinstance(item, dict) and item.get("id")}
    slot_objects = {str(item.get("id")): item for item in slots if isinstance(item, dict) and item.get("id")}
    panel_ids = {str(panel.get("id")) for panel in panels if isinstance(panel, dict)}
    arrows = [dict(item) for item in program.get("arrows", []) if isinstance(item, dict)]
    out_counts: dict[str, int] = {}
    in_counts: dict[str, int] = {}
    for arrow in arrows:
        source = str(arrow.get("source_id") or arrow.get("source") or "")
        target = str(arrow.get("target_id") or arrow.get("target") or "")
        out_counts[source] = out_counts.get(source, 0) + 1
        in_counts[target] = in_counts.get(target, 0) + 1

    reference_segments: list[tuple[list[float], list[float]]] = []
    for original in arrows:
        original_points = original.get("path_percent") if isinstance(original.get("path_percent"), list) else []
        if _reference_locked(original) and len(original_points) >= 2:
            reference_segments.extend(_segments(_clean_path(original_points)))

    grouped: dict[str, list[dict]] = {}
    enriched = []
    committed_fallback_segments: list[tuple[list[float], list[float]]] = []
    for index, arrow in enumerate(arrows, start=1):
        source = str(arrow.get("source_id") or arrow.get("source") or "")
        target = str(arrow.get("target_id") or arrow.get("target") or "")
        arrow["source_id"] = source
        arrow["target_id"] = target
        arrow["source"] = source
        arrow["target"] = target
        points = arrow.get("path_percent") if isinstance(arrow.get("path_percent"), list) else []
        locked = _reference_locked(arrow)
        route_meta: dict[str, Any] = {"routing_algorithm": "preserve_reference_path", "route_generation_status": "reference_locked"}
        fallback_allowed = str(arrow.get("route_policy", "")).lower() == "fallback_reroute_allowed"
        if (len(points) < 2 or (fallback_allowed and not locked)) and mode in {"reference", "aesthetic"}:
            obstacles = {obj_id: obj for obj_id, obj in slot_objects.items() if obj_id not in {source, target}}
            points, route_meta = _best_fallback_path(
                objects.get(source),
                objects.get(target),
                obstacles,
                reference_segments + committed_fallback_segments,
            )
            locked = False
        else:
            points = _clean_path(points)
        arrow["path_percent"] = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in points if isinstance(p, list) and len(p) >= 2]
        role = _infer_role(arrow, out_counts, in_counts, panel_ids)
        style = _style_for_role(role, arrow, mode=mode)
        recompute_generated_style = str(arrow.get("aesthetic_policy", "")).startswith("reference_first")
        for key, value in style.items():
            if recompute_generated_style or key not in arrow or not str(arrow.get(key, "")).strip():
                arrow[key] = value
        if recompute_generated_style or not str(arrow.get("semantic_role", "")).strip():
            arrow["semantic_role"] = role
        arrow.setdefault("aesthetic_policy", "reference_first_soft_editable_ppt_connector")
        arrow.setdefault("reference_locked", locked)
        arrow.setdefault("reference_path_preserved", locked)
        arrow.setdefault("route_policy", "preserve_reference_path" if locked else "synthesize_missing_path_only")
        arrow.setdefault("routing_algorithm", route_meta.get("routing_algorithm", ROUTER_VERSION))
        arrow.setdefault("route_generation_status", route_meta.get("route_generation_status", "fallback_route_selected" if not locked else "reference_locked"))
        if "candidate_count" in route_meta:
            arrow.setdefault("candidate_count", route_meta["candidate_count"])
        if "candidate_score" in route_meta:
            arrow.setdefault("candidate_score", route_meta["candidate_score"])
        arrow.setdefault("corner_radius_percent", 0.018 if arrow.get("route_style") in {"rounded_elbow", "bundled_elbow"} else 0.0)
        if role == "branch":
            bundle_id = f"from_{source}"
        elif role == "convergence":
            bundle_id = f"to_{target}"
        elif role == "feedback_loop":
            bundle_id = f"loop_{source}_{target}"
        else:
            bundle_id = f"flow_{index:02d}"
        arrow.setdefault("bundle_id", bundle_id)
        grouped.setdefault(bundle_id, []).append(arrow)
        enriched.append(arrow)
        if not locked and len(arrow["path_percent"]) >= 2:
            committed_fallback_segments.extend(_segments(arrow["path_percent"]))

    for bundle_id, items in grouped.items():
        items.sort(key=lambda item: (item.get("target_id", ""), item.get("id", "")))
        for lane_index, arrow in enumerate(items):
            arrow["lane_index"] = lane_index
            arrow["lane_count"] = len(items)

    if str(mode).lower() == "aesthetic":
        tunnel_percent = DEFAULT_REFERENCE_TUNNEL_PERCENT
        for arrow in enriched:
            original_path = _clean_path(arrow.get("path_percent") if isinstance(arrow.get("path_percent"), list) else [])
            arrow["reference_original_path_percent"] = original_path
            if arrow.get("reference_locked") and len(original_path) >= 2:
                offset_allowed = bool(arrow.get("aesthetic_offset_allowed")) or str(arrow.get("route_policy", "")).lower() == "aesthetic_tunnel_allowed"
                if offset_allowed:
                    adjusted_path, aesthetic_meta = _aesthetic_tunnel_path(
                        original_path,
                        int(arrow.get("lane_index") or 0),
                        int(arrow.get("lane_count") or 1),
                        str(arrow.get("semantic_role") or ""),
                        tunnel_percent=tunnel_percent,
                    )
                    arrow["path_percent"] = adjusted_path
                    arrow["routing_algorithm"] = aesthetic_meta["routing_algorithm"]
                    arrow["route_generation_status"] = aesthetic_meta["route_generation_status"]
                    arrow["reference_tunnel_percent"] = aesthetic_meta["reference_tunnel_percent"]
                    arrow["reference_path_delta_max"] = aesthetic_meta["reference_path_delta_max"]
                    arrow["reference_tunnel_preserved"] = aesthetic_meta["reference_tunnel_preserved"]
                    arrow["lane_offset_percent"] = aesthetic_meta["lane_offset_percent"]
                    arrow["reference_path_preserved"] = bool(aesthetic_meta["reference_tunnel_preserved"])
                else:
                    arrow["routing_algorithm"] = AESTHETIC_ROUTER_VERSION
                    arrow["route_generation_status"] = "aesthetic_style_only"
                    arrow["reference_tunnel_percent"] = tunnel_percent
                    arrow["reference_path_delta_max"] = 0.0
                    arrow["reference_tunnel_preserved"] = True
                    arrow["lane_offset_percent"] = 0.0
                    arrow["reference_path_preserved"] = True

    metrics, total_crossings = _route_metrics(enriched, slot_objects)
    routes = []
    for arrow in enriched:
        aid = str(arrow.get("id"))
        m = metrics.get(aid, {})
        clutter_score = (
            int(m.get("crossing_count", 0)) * 12
            + int(m.get("bend_count", 0)) * 3
            + int(m.get("obstacle_overlap_count", 0)) * 18
        )
        arrow["aesthetic_score"] = max(0, 100 - clutter_score)
        routes.append({
            "id": aid,
            "source_id": arrow.get("source_id"),
            "target_id": arrow.get("target_id"),
            "semantic_role": arrow.get("semantic_role"),
            "route_style": arrow.get("route_style"),
            "bundle_id": arrow.get("bundle_id"),
            "lane_index": arrow.get("lane_index"),
            "lane_count": arrow.get("lane_count"),
            "reference_locked": arrow.get("reference_locked"),
            "reference_path_preserved": arrow.get("reference_path_preserved"),
            "path_percent": arrow.get("path_percent"),
            "style_token_id": arrow.get("style_token_id"),
            "stroke_width_pt": arrow.get("stroke_width_pt"),
            "arrowhead_size": arrow.get("arrowhead_size"),
            "line_cap": arrow.get("line_cap"),
            "line_pattern": arrow.get("line_pattern", "solid"),
            "routing_algorithm": arrow.get("routing_algorithm"),
            "route_generation_status": arrow.get("route_generation_status"),
            "reference_original_path_percent": arrow.get("reference_original_path_percent"),
            "reference_tunnel_percent": arrow.get("reference_tunnel_percent"),
            "reference_path_delta_max": arrow.get("reference_path_delta_max"),
            "reference_tunnel_preserved": arrow.get("reference_tunnel_preserved"),
            "lane_offset_percent": arrow.get("lane_offset_percent"),
            "halo_width_pt": arrow.get("halo_width_pt"),
            "halo_color": arrow.get("halo_color"),
            "candidate_count": arrow.get("candidate_count"),
            "candidate_score": arrow.get("candidate_score"),
            "metrics": m,
            "aesthetic_score": arrow["aesthetic_score"],
        })

    arrow_style_profile = {
        "summary": "Reference-first arrow styling profile for editable PPT connectors.",
        "mode": mode,
        "reference_priority": "reference_image_hard_constraint",
        "routing_principle": "preserve reference-derived source-target logic and path geometry; only synthesize missing fallback paths",
        "routing_algorithm": ROUTER_VERSION,
        "aesthetic_routing_algorithm": AESTHETIC_ROUTER_VERSION,
        "reference_tunnel_percent": DEFAULT_REFERENCE_TUNNEL_PERCENT,
        "fallback_routing_policy": "only arrows with missing paths or route_policy=fallback_reroute_allowed may use obstacle-aware orthogonal routing",
        "aesthetic_mode_policy": "mode=aesthetic may adjust reference-locked paths only inside the reference tunnel and must keep reference_tunnel_preserved=true",
        "style_rules": {
            "main_flow": {"route_style": "soft_straight", "stroke_width_pt": 2.2, "arrowhead_size": "med"},
            "branch": {"route_style": "bundled_elbow", "stroke_width_pt": 1.55, "arrowhead_size": "sm"},
            "convergence": {"route_style": "bundled_elbow", "stroke_width_pt": 1.55, "arrowhead_size": "sm"},
            "feedback_loop": {"route_style": "dashed_spline_like", "stroke_width_pt": 1.8, "arrowhead_size": "sm"},
            "module_flow": {"route_style": "soft_straight", "stroke_width_pt": 1.45, "arrowhead_size": "sm"},
        },
        "aesthetic_style_rules": {
            "main_flow": {"route_style": "soft_curve", "stroke_width_pt": 2.35, "arrowhead_size": "med", "halo_width_pt": 4.4},
            "branch": {"route_style": "metro_bundle", "stroke_width_pt": 1.45, "arrowhead_size": "sm", "halo_width_pt": 3.2},
            "convergence": {"route_style": "metro_bundle", "stroke_width_pt": 1.45, "arrowhead_size": "sm", "halo_width_pt": 3.2},
            "feedback_loop": {"route_style": "dashed_loop", "stroke_width_pt": 1.75, "arrowhead_size": "sm", "halo_width_pt": 3.0},
            "module_flow": {"route_style": "soft_curve", "stroke_width_pt": 1.55, "arrowhead_size": "sm", "halo_width_pt": 3.0},
        },
        "ppt_editability": "all arrows render as PPT connector shapes, not raster assets",
        "rounded_line_policy": "use round line caps and editable connector segments; reference-locked paths are not geometrically rewritten",
    }
    selected_routes = {
        "summary": "Selected reference-preserving arrow routes and style assignments.",
        "mode": mode,
        "route_count": len(routes),
        "routes": routes,
    }
    tunnel_violations = [route["id"] for route in routes if route.get("reference_tunnel_preserved") is False]
    quality_report = {
        "summary": "Arrow routing and styling quality report.",
        "mode": mode,
        "status": "pass" if all(route["aesthetic_score"] >= 35 for route in routes) and not tunnel_violations else "needs_review",
        "arrow_count": len(routes),
        "total_crossing_count": total_crossings,
        "total_obstacle_overlap_count": sum(int(route["metrics"].get("obstacle_overlap_count", 0)) for route in routes),
        "fallback_route_count": sum(1 for route in routes if route.get("route_generation_status") == "fallback_route_selected"),
        "aesthetic_tunnel_adjusted_count": sum(1 for route in routes if route.get("route_generation_status") == "aesthetic_tunnel_adjusted"),
        "aesthetic_style_only_count": sum(1 for route in routes if route.get("route_generation_status") == "aesthetic_style_only"),
        "reference_tunnel_violations": tunnel_violations,
        "average_aesthetic_score": round(sum(float(route["aesthetic_score"]) for route in routes) / max(len(routes), 1), 2),
        "reference_path_overrides": [route["id"] for route in routes if route.get("reference_locked") and not route.get("reference_path_preserved")],
        "routes": routes,
    }
    program["arrows"] = enriched
    program["control_shapes"] = [dict(item) for item in enriched]
    program.setdefault("style", {})["arrow_style_profile_path"] = "arrow_style_profile.json"
    write_json(out / "arrow_style_profile.json", arrow_style_profile)
    write_json(out / "selected_arrow_routes.json", selected_routes)
    write_json(out / "arrow_quality_report.json", quality_report)
    write_json(out / "figure_program.json", program)
    return program
