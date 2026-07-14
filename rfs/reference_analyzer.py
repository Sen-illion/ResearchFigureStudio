from __future__ import annotations

import base64
import colorsys
import json
import os
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw

from .utils import ratio_string, write_json


def _round3(value: float) -> float:
    return round(float(value), 3)


def _round4(value: float) -> float:
    return round(float(value), 4)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _lighten(hex_color: str, amount: float = 0.84) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex((
        int(r + (255 - r) * amount),
        int(g + (255 - g) * amount),
        int(b + (255 - b) * amount),
    ))


def _saturation(hex_color: str) -> float:
    r, g, b = [value / 255.0 for value in _hex_to_rgb(hex_color)]
    high = max(r, g, b)
    low = min(r, g, b)
    if high <= 0:
        return 0.0
    return (high - low) / high


def _color_family(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    if max(r, g, b) - min(r, g, b) < 24:
        return "neutral"
    if r >= g and r >= b:
        return "warm"
    if g >= r and g >= b:
        return "green"
    return "blue"


def _hex_to_hsl(hex_color: str) -> dict[str, float]:
    r, g, b = [value / 255.0 for value in _hex_to_rgb(hex_color)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return {"h": _round3(h * 360), "s": _round3(s), "l": _round3(l)}


def _diverse_palette(colors: list[str]) -> list[str]:
    result: list[str] = []
    for color in colors:
        if color not in result and _saturation(color) >= 0.16:
            result.append(color)
    for color in colors:
        if color not in result:
            result.append(color)
    if not result:
        result.append("#8A8F96")
    variant_index = 0
    while len(result) < 4:
        base = result[variant_index % len(result)]
        variant = _lighten(base, 0.30 + 0.14 * (variant_index % 4))
        if variant not in result:
            result.append(variant)
        variant_index += 1
    return result


def _crop_bbox(image: Image.Image, bbox: dict[str, float]) -> Image.Image:
    width, height = image.size
    x0 = max(0, min(width - 1, int(round(float(bbox["x"]) * width))))
    y0 = max(0, min(height - 1, int(round(float(bbox["y"]) * height))))
    x1 = max(x0 + 1, min(width, int(round((float(bbox["x"]) + float(bbox["w"])) * width))))
    y1 = max(y0 + 1, min(height, int(round((float(bbox["y"]) + float(bbox["h"])) * height))))
    return image.crop((x0, y0, x1, y1))


def _dominant_colors(image: Image.Image, limit: int = 6) -> list[str]:
    sample = image.convert("RGB").resize((96, max(1, int(96 * image.height / max(image.width, 1)))))
    colors = sample.quantize(colors=12, method=Image.Quantize.MEDIANCUT).convert("RGB").getcolors(maxcolors=10000) or []
    ranked: list[tuple[int, str]] = []
    for count, rgb in colors:
        r, g, b = rgb
        if r > 242 and g > 242 and b > 242:
            continue
        if r < 25 and g < 25 and b < 25:
            continue
        ranked.append((int(count), _rgb_to_hex((r, g, b))))
    seen = set()
    result = []
    for _count, color in sorted(ranked, reverse=True):
        if color not in seen:
            seen.add(color)
            result.append(color)
        if len(result) >= limit:
            break
    return result


def _geometry_record(item_id: str, bbox: dict[str, float], image_width: int, image_height: int, item_type: str, colors: list[str] | None = None) -> dict:
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    ratio = (w * image_width) / max(h * image_height, 0.001)
    target_pixels = {"width": _round3(image_width * w), "height": _round3(image_height * h)}
    return {
        "id": item_id,
        "type": item_type,
        "bbox_percent": {"x": _round4(x), "y": _round4(y), "w": _round4(w), "h": _round4(h)},
        "center_percent": {"x": _round4(x + w / 2), "y": _round4(y + h / 2)},
        "width_percent": _round4(w),
        "height_percent": _round4(h),
        "aspect_ratio_decimal": _round3(ratio),
        "aspect_ratio_w_h": ratio_string(w * image_width, h * image_height),
        "target_pixels": target_pixels,
        "target_pixels_exact": target_pixels,
        "generation_min_pixels": {"width": max(256, round(image_width * w)), "height": max(256, round(image_height * h))},
        "dominant_colors": colors or [],
    }


CONTROL_ID_TERMS = (
    "arrow",
    "dashed_arc",
    "dashed_arrows",
    "transition",
    "loop_dashed",
    "graph_connector",
)


def _is_control_spec(spec: Any) -> bool:
    slot_id = str(_spec_value(spec, "id") or "").lower()
    composition = str(_spec_value(spec, "composition_type") or "").lower()
    metaphor = str(_spec_value(spec, "visual_metaphor") or "").lower()
    if any(term in slot_id for term in CONTROL_ID_TERMS):
        return True
    if composition == "symbol_cutout" and any(term in metaphor for term in ["arrow", "dashed loop", "connector", "transition arrow"]):
        return True
    return False


def _control_type(control_id: str, metaphor: str = "") -> str:
    text = f"{control_id} {metaphor}".lower()
    if "dashed" in text or "loop" in text or "arc" in text:
        return "dashed_loop"
    if "down" in text:
        return "down_arrow"
    if "connector" in text:
        return "branch_connector"
    if "transition" in text:
        return "transition_arrow"
    return "straight_arrow"


def _control_connection(control_id: str) -> tuple[str, str, list[str]]:
    mapping = {
        "input_to_vlm_arrow_symbol": ("input_text_stack", "vlm_agent_robot", []),
        "vlm_to_blueprint_down_arrow": ("vlm_agent_robot", "initial_blueprint_code_card", []),
        "blueprint_graph_connector": ("initial_blueprint_code_card", "blueprint_node_a", ["blueprint_node_b"]),
        "stage_transition_arrow_1": ("blueprint_node_b", "ai_designer_robot", []),
        "refinement_loop_dashed_arc": ("ai_designer_robot", "ai_critic_robot", []),
        "stage_transition_arrow_2": ("update_banner", "synthesis_magic_wand", []),
        "rendering_loop_dashed_arrows": ("raw_image_card", "final_autofigure_card", ["erase_text_tool", "ocr_verify_magnifier"]),
    }
    return mapping.get(control_id, ("", "", []))


def _control_path_percent(bbox: dict[str, float], control_type: str) -> list[list[float]]:
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    cx = x + w / 2
    cy = y + h / 2
    if control_type == "down_arrow":
        return [[_round4(cx), _round4(y)], [_round4(cx), _round4(y + h)]]
    if control_type == "dashed_loop":
        return [
            [_round4(cx), _round4(y)],
            [_round4(x + w), _round4(cy)],
            [_round4(cx), _round4(y + h)],
            [_round4(x), _round4(cy)],
            [_round4(cx), _round4(y)],
        ]
    if control_type == "branch_connector":
        return [
            [_round4(x), _round4(cy)],
            [_round4(cx), _round4(cy)],
            [_round4(x + w), _round4(y)],
            [_round4(x + w), _round4(y + h)],
        ]
    return [[_round4(x), _round4(cy)], [_round4(x + w), _round4(cy)]]


def _color_token(token_id: str, hex_color: str, source_region: str, usage: str, bbox: dict[str, float] | None = None) -> dict:
    rgb = _hex_to_rgb(hex_color)
    token = {
        "token_id": token_id,
        "hex": hex_color,
        "rgb": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
        "hsl": _hex_to_hsl(hex_color),
        "source_region": source_region,
        "usage": usage,
    }
    if bbox:
        token["bbox_percent"] = {"x": _round4(bbox["x"]), "y": _round4(bbox["y"]), "w": _round4(bbox["w"]), "h": _round4(bbox["h"])}
    return token


def _append_unique_token(tokens: list[dict], token: dict) -> str:
    token_id = str(token["token_id"])
    if not any(str(item.get("token_id")) == token_id for item in tokens):
        tokens.append(token)
    return token_id


def _point_bbox(points: list[list[float]]) -> dict[str, float]:
    xs = [float(point[0]) for point in points if isinstance(point, list) and len(point) >= 2]
    ys = [float(point[1]) for point in points if isinstance(point, list) and len(point) >= 2]
    if not xs or not ys:
        return {"x": 0.0, "y": 0.0, "w": 0.001, "h": 0.001}
    x0, x1 = max(0.0, min(xs)), min(1.0, max(xs))
    y0, y1 = max(0.0, min(ys)), min(1.0, max(ys))
    return {"x": _round4(x0), "y": _round4(y0), "w": _round4(max(0.001, x1 - x0)), "h": _round4(max(0.001, y1 - y0))}


def _object_candidates(slots: list[dict], panel_geometry: list[dict]) -> list[dict]:
    objects: list[dict] = []
    for item in slots:
        if isinstance(item, dict) and isinstance(item.get("bbox_percent"), dict):
            objects.append({"id": item.get("id"), "bbox_percent": item.get("bbox_percent"), "kind": "slot"})
    for item in panel_geometry:
        if isinstance(item, dict) and isinstance(item.get("bbox_percent"), dict):
            objects.append({"id": item.get("id"), "bbox_percent": item.get("bbox_percent"), "kind": "panel"})
    return [item for item in objects if str(item.get("id", "")).strip()]


def _point_to_bbox_distance(point: list[float], bbox: dict[str, float]) -> float:
    px, py = float(point[0]), float(point[1])
    x0, y0 = float(bbox["x"]), float(bbox["y"])
    x1, y1 = x0 + float(bbox["w"]), y0 + float(bbox["h"])
    dx = 0.0 if x0 <= px <= x1 else min(abs(px - x0), abs(px - x1))
    dy = 0.0 if y0 <= py <= y1 else min(abs(py - y0), abs(py - y1))
    return (dx * dx + dy * dy) ** 0.5


def _rank_nearest_objects(point: list[float], objects: list[dict]) -> list[dict]:
    ranked = []
    for obj in objects:
        bbox = obj.get("bbox_percent")
        if isinstance(bbox, dict):
            ranked.append(((_point_to_bbox_distance(point, bbox), 0 if obj.get("kind") == "slot" else 1), obj))
    return [item for _score, item in sorted(ranked, key=lambda pair: pair[0])]


def _anchor_for_point(point: list[float], obj: dict | None) -> str:
    if not obj or not isinstance(obj.get("bbox_percent"), dict):
        return "auto"
    bbox = obj["bbox_percent"]
    px, py = float(point[0]), float(point[1])
    x, y, w, h = float(bbox["x"]), float(bbox["y"]), float(bbox["w"]), float(bbox["h"])
    distances = {
        "left_mid": abs(px - x),
        "right_mid": abs(px - (x + w)),
        "top_mid": abs(py - y),
        "bottom_mid": abs(py - (y + h)),
    }
    return min(distances, key=distances.get)


def _bind_control_to_objects(control: dict, objects: list[dict]) -> dict:
    path = control.get("path_percent") if isinstance(control.get("path_percent"), list) else []
    if len(path) < 2 or not objects:
        control.setdefault("source_id", "")
        control.setdefault("target_id", "")
        control.setdefault("source_anchor", "auto")
        control.setdefault("target_anchor", "auto")
        return control
    source_ranked = _rank_nearest_objects(path[0], objects)
    target_ranked = _rank_nearest_objects(path[-1], objects)
    source_obj = source_ranked[0] if source_ranked else None
    target_obj = target_ranked[0] if target_ranked else None
    if source_obj and target_obj and source_obj.get("id") == target_obj.get("id") and len(target_ranked) > 1:
        target_obj = target_ranked[1]
    control["source_id"] = control.get("source_id") or (str(source_obj.get("id")) if source_obj else "")
    control["target_id"] = control.get("target_id") or (str(target_obj.get("id")) if target_obj else "")
    control["source"] = control.get("source") or control["source_id"]
    control["target"] = control.get("target") or control["target_id"]
    if not str(control.get("source_anchor", "")).strip() or str(control.get("source_anchor")).lower() == "auto":
        control["source_anchor"] = _anchor_for_point(path[0], source_obj)
    if not str(control.get("target_anchor", "")).strip() or str(control.get("target_anchor")).lower() == "auto":
        control["target_anchor"] = _anchor_for_point(path[-1], target_obj)
    return control


def _control_from_path(
    control_id: str,
    path: list[list[float]],
    image_width: int,
    image_height: int,
    control_kind: str,
    colors: list[str],
    style_token_id: str,
    detected_by: str,
    confidence: float,
) -> dict:
    bbox = _point_bbox(path)
    geometry = _geometry_record(control_id, bbox, image_width, image_height, "ppt_control", colors=colors)
    return {
        **geometry,
        "control_kind": control_kind,
        "source_id": "",
        "target_id": "",
        "source": "",
        "target": "",
        "source_anchor": "auto",
        "target_anchor": "auto",
        "path_percent": [[_round4(point[0]), _round4(point[1])] for point in path],
        "style_token_id": style_token_id,
        "color_token_ids": [style_token_id] if style_token_id else [],
        "label": "",
        "editable_in": "pptx",
        "render_policy": "ppt_shape_not_image_asset",
        "slot_exclusion_reason": "arrow_or_connector_rendered_as_editable_ppt_control",
        "detected_by": detected_by,
        "confidence": _round3(confidence),
    }


def _detect_cv_control_candidates(reference_image: Image.Image, image_width: int, image_height: int, max_candidates: int = 24) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as exc:
        return [], [f"opencv_unavailable:{exc}"]

    arr = np.array(reference_image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 60, 160)
    min_dim = min(image_width, image_height)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(35, int(min_dim * 0.04)),
        minLineLength=max(28, int(min_dim * 0.055)),
        maxLineGap=max(8, int(min_dim * 0.018)),
    )
    if lines is None:
        return [], ["opencv_hough_found_no_lines"]

    raw: list[tuple[float, float, list[list[float]]]] = []
    diag = (image_width * image_width + image_height * image_height) ** 0.5
    for line in lines[:, 0, :]:
        x1, y1, x2, y2 = [float(v) for v in line]
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length / max(diag, 1.0) < 0.025:
            continue
        samples = []
        for step in range(12):
            t = step / 11
            sx = int(round(x1 + (x2 - x1) * t))
            sy = int(round(y1 + (y2 - y1) * t))
            sx = max(0, min(image_width - 1, sx))
            sy = max(0, min(image_height - 1, sy))
            r, g, b = [float(v) / 255.0 for v in arr[sy, sx]]
            high, low = max(r, g, b), min(r, g, b)
            saturation = 0.0 if high <= 0 else (high - low) / high
            brightness = (r + g + b) / 3
            samples.append(saturation * (0.55 + min(0.45, abs(brightness - 0.5))))
        color_score = sum(samples) / max(len(samples), 1)
        # Direction is inferred geometrically when arrowheads are unavailable.
        if abs(x2 - x1) >= abs(y2 - y1):
            start, end = ((x1, y1), (x2, y2)) if x1 <= x2 else ((x2, y2), (x1, y1))
        else:
            start, end = ((x1, y1), (x2, y2)) if y1 <= y2 else ((x2, y2), (x1, y1))
        path = [[start[0] / image_width, start[1] / image_height], [end[0] / image_width, end[1] / image_height]]
        raw.append((color_score, length, [[_round4(path[0][0]), _round4(path[0][1])], [_round4(path[1][0]), _round4(path[1][1])]]))

    candidates: list[dict] = []
    seen: list[dict[str, float]] = []
    colored_exists = any(score >= 0.10 for score, _length, _path in raw)
    for color_score, _length, path in sorted(raw, key=lambda item: (item[0], item[1]), reverse=True):
        if colored_exists and color_score < 0.035:
            continue
        bbox = _point_bbox(path)
        if bbox["w"] < 0.012 and bbox["h"] < 0.012:
            continue
        duplicate = False
        for prev in seen:
            center_dist = abs((bbox["x"] + bbox["w"] / 2) - (prev["x"] + prev["w"] / 2)) + abs((bbox["y"] + bbox["h"] / 2) - (prev["y"] + prev["h"] / 2))
            if center_dist < 0.018 and abs(bbox["w"] - prev["w"]) < 0.025 and abs(bbox["h"] - prev["h"]) < 0.025:
                duplicate = True
                break
        if duplicate:
            continue
        seen.append(bbox)
        candidates.append({"path_percent": path, "bbox_percent": bbox, "detected_by": "opencv_hough", "confidence": 0.62})
        if len(candidates) >= max_candidates:
            break
    if not candidates:
        warnings.append("opencv_hough_lines_filtered_to_zero_candidates")
    return candidates, warnings


def _fallback_panel_flow_controls(panel_geometry: list[dict], image_width: int, image_height: int, style_token_id: str) -> list[dict]:
    panels = [panel for panel in panel_geometry if panel.get("id") not in {"legend", "shared_resource_library"}]
    panels = sorted(panels, key=lambda item: (item["bbox_percent"]["y"], item["bbox_percent"]["x"]))
    controls = []
    for index in range(max(0, len(panels) - 1)):
        source = panels[index]
        target = panels[index + 1]
        s = source["bbox_percent"]
        t = target["bbox_percent"]
        path = [
            [_round4(float(s["x"]) + float(s["w"])), _round4(float(s["y"]) + float(s["h"]) / 2)],
            [_round4(float(t["x"])), _round4(float(t["y"]) + float(t["h"]) / 2)],
        ]
        control = _control_from_path(
            f"AR{index + 1:02d}",
            path,
            image_width,
            image_height,
            "straight_arrow",
            [],
            style_token_id,
            "heuristic_panel_flow_fallback",
            0.42,
        )
        control.update({
            "source_id": str(source["id"]),
            "target_id": str(target["id"]),
            "source": str(source["id"]),
            "target": str(target["id"]),
            "source_anchor": "right_mid",
            "target_anchor": "left_mid",
        })
        controls.append(control)
    return controls


def _draw_slot_overlay(reference_image: Image.Image, slots: list[dict], panel_geometry: list[dict], out_dir: Path) -> str:
    image = reference_image.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for panel in panel_geometry:
        bbox = panel.get("bbox_percent")
        if not isinstance(bbox, dict):
            continue
        x0, y0 = int(float(bbox["x"]) * width), int(float(bbox["y"]) * height)
        x1, y1 = int((float(bbox["x"]) + float(bbox["w"])) * width), int((float(bbox["y"]) + float(bbox["h"])) * height)
        draw.rectangle([x0, y0, x1, y1], outline="#2255CC", width=max(2, width // 600))
        draw.text((x0 + 4, y0 + 4), str(panel.get("id")), fill="#2255CC")
    for index, slot in enumerate(slots, start=1):
        bbox = slot.get("bbox_percent")
        if not isinstance(bbox, dict):
            continue
        x0, y0 = int(float(bbox["x"]) * width), int(float(bbox["y"]) * height)
        x1, y1 = int((float(bbox["x"]) + float(bbox["w"])) * width), int((float(bbox["y"]) + float(bbox["h"])) * height)
        label = f"S{index:02d}:{slot.get('id')}"
        draw.rectangle([x0, y0, x1, y1], outline="#00A2FF", width=max(2, width // 700))
        draw.rectangle([x0, max(0, y0 - 14), min(width, x0 + max(50, len(label) * 6)), y0], fill="#00A2FF")
        draw.text((x0 + 2, max(0, y0 - 13)), label, fill="#FFFFFF")
    path = out_dir / "slot_overlay.png"
    image.save(path)
    return path.name


def _draw_control_overlay(reference_image: Image.Image, controls: list[dict], out_dir: Path) -> str:
    image = reference_image.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    line_width = max(3, width // 420)
    for index, control in enumerate(controls, start=1):
        path = control.get("path_percent") if isinstance(control.get("path_percent"), list) else []
        points = [(int(float(point[0]) * width), int(float(point[1]) * height)) for point in path if isinstance(point, list) and len(point) >= 2]
        if len(points) >= 2:
            for a, b in zip(points[:-1], points[1:]):
                draw.line([a, b], fill="#F05A28", width=line_width)
            lx, ly = points[len(points) // 2]
        else:
            bbox = control.get("bbox_percent") if isinstance(control.get("bbox_percent"), dict) else {"x": 0.02, "y": 0.02}
            lx, ly = int(float(bbox["x"]) * width), int(float(bbox["y"]) * height)
        label = str(control.get("candidate_label") or control.get("id") or f"AR{index:02d}")
        draw.ellipse([lx - 12, ly - 12, lx + 12, ly + 12], fill="#F05A28", outline="#FFFFFF", width=2)
        draw.text((lx + 14, ly - 9), label, fill="#F05A28")
    path = out_dir / "reference_control_overlay.png"
    image.save(path)
    return path.name


def _call_vlm_control_binding(reference_path: str | Path, slot_overlay_path: str | Path, control_overlay_path: str | Path, candidates: list[dict], objects: list[dict]) -> tuple[list[dict], list[str]]:
    api_base = os.getenv("API_BASE", "").rstrip("/")
    api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("RFS_CONTROL_LOCALIZER_MODEL") or os.getenv("MODEL_VLM") or os.getenv("RFS_LOCATOR_MODEL") or "gemini-3-pro-preview-thinking"
    if not api_base or not api_key:
        return candidates, ["hybrid_downgraded_to_heuristic:no_api_credentials"]

    def image_part(path: str | Path) -> dict:
        b64 = base64.b64encode(Path(path).read_bytes()).decode("utf-8")
        return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}

    prompt = f"""
You are binding editable PPT arrows/connectors for a scientific figure.
Use image 1 as the original reference, image 2 as slot ID overlay, and image 3 as arrow/control candidate overlay.
Only output JSON. Do not draw a figure.

Rules:
- Arrows/connectors must remain editable PPT controls, never image assets.
- Preserve the reference image flow logic.
- Use only object ids from the provided object list for source_id and target_id.
- Keep path_percent as normalized coordinates.
- If direction is uncertain, choose the most plausible source-target based on arrow direction and layout flow.

Return schema:
{{"summary":"...","controls":[{{"id":"AR01","source_id":"...","target_id":"...","source_anchor":"right_mid","target_anchor":"left_mid","path_percent":[[0.1,0.2],[0.3,0.2]],"control_kind":"straight_arrow|elbow_connector|branch_connector|dashed_loop","confidence":0.0}}]}}

Objects:
{json.dumps([{"id": item.get("id"), "kind": item.get("kind"), "bbox_percent": item.get("bbox_percent")} for item in objects], ensure_ascii=False)}

Candidates:
{json.dumps([{key: item.get(key) for key in ["id", "control_kind", "bbox_percent", "path_percent", "detected_by", "confidence"]} for item in candidates], ensure_ascii=False)}
""".strip()
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, image_part(reference_path), image_part(slot_overlay_path), image_part(control_overlay_path)]}],
        "temperature": 0.1,
    }
    try:
        response = requests.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, data=json.dumps(payload), timeout=180)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        cleaned = content.strip().replace("```json", "```")
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1].strip()
        parsed = json.loads(cleaned[cleaned.find("{"): cleaned.rfind("}") + 1])
        patches = {str(item.get("id")): item for item in parsed.get("controls", []) if isinstance(item, dict)}
    except Exception as exc:
        return candidates, [f"vlm_control_binding_failed:{exc}"]

    object_ids = {str(item.get("id")) for item in objects}
    patched = []
    for item in candidates:
        merged = dict(item)
        patch = patches.get(str(item.get("id")))
        if patch:
            if str(patch.get("source_id")) in object_ids:
                merged["source_id"] = str(patch.get("source_id"))
                merged["source"] = merged["source_id"]
            if str(patch.get("target_id")) in object_ids:
                merged["target_id"] = str(patch.get("target_id"))
                merged["target"] = merged["target_id"]
            if isinstance(patch.get("path_percent"), list) and len(patch["path_percent"]) >= 2:
                merged["path_percent"] = [[_round4(point[0]), _round4(point[1])] for point in patch["path_percent"] if isinstance(point, list) and len(point) >= 2]
            if str(patch.get("source_anchor", "")).strip():
                merged["source_anchor"] = str(patch.get("source_anchor"))
            if str(patch.get("target_anchor", "")).strip():
                merged["target_anchor"] = str(patch.get("target_anchor"))
            if str(patch.get("control_kind", "")).strip():
                merged["control_kind"] = str(patch.get("control_kind"))
            merged["confidence"] = _round3(float(patch.get("confidence", merged.get("confidence", 0.65)) or 0.65))
            merged["binding_source"] = "vlm"
        patched.append(merged)
    return patched, []


def _supplement_reference_slots(slot_specs: list[Any], target_count: int) -> list[Any]:
    """Split large reference cards into detail slots instead of counting arrows."""
    if len(slot_specs) >= target_count:
        return slot_specs
    expandable = [spec for spec in slot_specs if isinstance(spec, dict) and isinstance(spec.get("bbox_percent"), dict)]
    if not expandable:
        if not slot_specs:
            return slot_specs
        supplemented = list(slot_specs)
        detail_index = 1
        while len(supplemented) < target_count:
            base = slot_specs[(detail_index - 1) % len(slot_specs)]
            base_id = str(_spec_value(base, "id") or f"slot_{detail_index:02d}")
            panel = str(_spec_value(base, "macro_panel") or "Paper Method")
            concept = str(_spec_value(base, "paper_concept") or base_id)
            composition = str(_spec_value(base, "composition_type") or "full_bleed_card")
            supplemented.append({
                "id": f"{base_id}_detail_{detail_index:02d}",
                "macro_panel": panel,
                "paper_concept": f"{concept} local detail {detail_index}",
                "composition_type": "scene_thumbnail" if composition != "symbol_cutout" else "full_frame_icon",
                "visual_metaphor": str(_spec_value(base, "visual_metaphor") or ""),
                "must_show": _spec_value(base, "must_show") if isinstance(_spec_value(base, "must_show"), list) else [],
                "avoid_showing": _spec_value(base, "avoid_showing") if isinstance(_spec_value(base, "avoid_showing"), list) else [],
                "display_label": "",
                "show_slot_caption": False,
            })
            detail_index += 1
        return supplemented
    supplemented = list(slot_specs)
    detail_index = 1
    while len(supplemented) < target_count:
        base = expandable[(detail_index - 1) % len(expandable)]
        bbox = base["bbox_percent"]
        quad = (detail_index - 1) % 4
        col = quad % 2
        row = quad // 2
        new_spec = dict(base)
        new_spec["id"] = f"{base['id']}_detail_{detail_index:02d}"
        new_spec["paper_concept"] = f"{base.get('paper_concept', base['id'])} local detail {detail_index}"
        new_spec["composition_type"] = "scene_thumbnail" if base.get("composition_type") != "symbol_cutout" else "full_frame_icon"
        new_spec["bbox_percent"] = {
            "x": _round4(float(bbox["x"]) + float(bbox["w"]) * (0.04 + col * 0.50)),
            "y": _round4(float(bbox["y"]) + float(bbox["h"]) * (0.04 + row * 0.50)),
            "w": _round4(float(bbox["w"]) * 0.46),
            "h": _round4(float(bbox["h"]) * 0.46),
        }
        new_spec["display_label"] = ""
        new_spec["show_slot_caption"] = False
        supplemented.append(new_spec)
        detail_index += 1
    return supplemented


MASTER_SLOT_SPECS = [
    ("current_player_action", "Current Turn Context", "player action card", "full_frame_icon"),
    ("current_dialogue", "Current Turn Context", "recent dialogue card", "full_bleed_card"),
    ("current_options", "Current Turn Context", "player options card", "full_bleed_card"),
    ("current_scene", "Current Turn Context", "current scene thumbnail", "scene_thumbnail"),
    ("world_book", "Worldline Conditioning", "persistent world book W_p", "full_bleed_card"),
    ("state_board", "Worldline Conditioning", "closed-loop state board S_t", "full_bleed_card"),
    ("scene_anchor", "Worldline Conditioning", "scene anchor A_t", "symbol_cutout"),
    ("conditioning_cue", "Worldline Conditioning", "Omega_t=(W_p,S_t,A_t) conditioning cue", "full_frame_icon"),
    ("displayed_options", "Reading-Time Speculation", "displayed options card", "full_bleed_card"),
    ("branch_a", "Reading-Time Speculation", "candidate branch A card", "scene_thumbnail"),
    ("branch_b", "Reading-Time Speculation", "candidate branch B card", "scene_thumbnail"),
    ("branch_c", "Reading-Time Speculation", "candidate branch C card", "scene_thumbnail"),
    ("parallel_generation", "Reading-Time Speculation", "parallel generation cue", "full_frame_icon"),
    ("fast_lane", "Priority Gate", "user-facing fast lane", "full_bleed_card"),
    ("spec_queue", "Priority Gate", "speculative queue", "full_bleed_card"),
    ("gate_controller", "Priority Gate", "priority gate controller", "full_frame_icon"),
    ("cache_box", "Full-Ready Cache", "full-ready cache box", "full_frame_icon"),
    ("narrative_doc", "Full-Ready Cache", "pre-generated narrative N_t", "full_bleed_card"),
    ("scene_image", "Full-Ready Cache", "generated scene image I_t", "scene_thumbnail"),
    ("updated_state", "Full-Ready Cache", "updated state S_t", "full_bleed_card"),
    ("next_options", "Full-Ready Cache", "next options", "full_bleed_card"),
    ("llm_icon", "Shared Resource Library", "LLM", "full_frame_icon"),
    ("image_model_icon", "Shared Resource Library", "image model", "full_frame_icon"),
    ("character_archive", "Shared Resource Library", "character archive", "full_frame_icon"),
    ("cache_memory", "Shared Resource Library", "world/image cache", "full_frame_icon"),
    ("eval_monitor", "Shared Resource Library", "evaluation monitor", "full_frame_icon"),
    ("player_profile", "Current Turn Context", "player profile/status", "full_frame_icon"),
    ("history_window", "Current Turn Context", "recent interaction history", "full_bleed_card"),
    ("turn_timer", "Current Turn Context", "current turn timing cue", "full_frame_icon"),
    ("world_graph", "Worldline Conditioning", "world graph", "full_bleed_card"),
    ("character_relation", "Worldline Conditioning", "character relation board", "full_bleed_card"),
    ("constraint_checklist", "Worldline Conditioning", "consistency constraints", "full_bleed_card"),
    ("multimodal_bridge", "Worldline Conditioning", "text-image conditioning bridge", "full_frame_icon"),
    ("branch_ranker", "Reading-Time Speculation", "candidate branch ranker", "full_frame_icon"),
    ("finite_frontier", "Reading-Time Speculation", "finite frontier", "full_bleed_card"),
    ("background_worker", "Reading-Time Speculation", "background worker generation", "full_frame_icon"),
    ("story_draft", "Reading-Time Speculation", "draft narrative branch", "full_bleed_card"),
    ("image_draft", "Reading-Time Speculation", "draft image branch", "scene_thumbnail"),
    ("priority_score", "Priority Gate", "priority score", "full_frame_icon"),
    ("interrupt_signal", "Priority Gate", "user interrupt signal", "full_frame_icon"),
    ("resource_meter", "Priority Gate", "resource budget meter", "full_bleed_card"),
    ("cancel_token", "Priority Gate", "cancel speculative job", "full_frame_icon"),
    ("resume_marker", "Priority Gate", "resume queued job", "full_frame_icon"),
    ("cache_key", "Full-Ready Cache", "cache key", "full_frame_icon"),
    ("validation_stamp", "Full-Ready Cache", "cache validation stamp", "full_frame_icon"),
    ("cache_hit_path", "Full-Ready Cache", "cache hit path", "full_bleed_card"),
    ("refresh_loop", "Full-Ready Cache", "cache refresh loop", "full_frame_icon"),
    ("pre_generation_cache", "Shared Resource Library", "pre-generation cache", "full_frame_icon"),
    ("resource_scheduler", "Shared Resource Library", "resource scheduler", "full_frame_icon"),
    ("quality_metric", "Shared Resource Library", "quality metric", "full_frame_icon"),
    ("latency_metric", "Shared Resource Library", "latency metric", "full_frame_icon"),
    ("cost_metric", "Shared Resource Library", "cost metric", "full_frame_icon"),
]

PANEL_LAYOUT = {
    "Current Turn Context": {"x": 0.045, "y": 0.16, "w": 0.145, "h": 0.42},
    "Worldline Conditioning": {"x": 0.215, "y": 0.16, "w": 0.145, "h": 0.42},
    "Reading-Time Speculation": {"x": 0.385, "y": 0.16, "w": 0.145, "h": 0.42},
    "Priority Gate": {"x": 0.555, "y": 0.16, "w": 0.145, "h": 0.42},
    "Full-Ready Cache": {"x": 0.725, "y": 0.16, "w": 0.165, "h": 0.42},
    "Shared Resource Library": {"x": 0.08, "y": 0.68, "w": 0.70, "h": 0.17},
}

PERSONALITY_SLOT_SPECS = [
    ("setup_participant_screen", "Virtual Interview Setup", "participant seated before 49-inch screen", "scene_thumbnail"),
    ("setup_virtual_interviewer", "Virtual Interview Setup", "3D virtual interviewer on screen", "scene_thumbnail"),
    ("setup_camera_full_body", "Virtual Interview Setup", "wide-angle camera capturing full body", "scene_thumbnail"),
    ("setup_interview_room", "Virtual Interview Setup", "virtual interview room setup", "scene_thumbnail"),
    ("setup_question_prompt", "Virtual Interview Setup", "interview question prompt on screen", "full_bleed_card"),
    ("raw_video_file", "Raw Video Collection", "raw interview video recording", "full_bleed_card"),
    ("raw_participants", "Raw Video Collection", "287 participant video collection", "full_bleed_card"),
    ("raw_questions", "Raw Video Collection", "36 interview questions", "full_bleed_card"),
    ("raw_full_body_frames", "Raw Video Collection", "full-body video thumbnails", "scene_thumbnail"),
    ("raw_clip_grid", "Raw Video Collection", "participant clip grid", "full_bleed_card"),
    ("ffmpeg_video_to_audio", "Preprocessing Modules", "FFmpeg extracts audio from video", "full_bleed_card"),
    ("audio_waveform_stream", "Preprocessing Modules", "audio waveform stream", "full_frame_icon"),
    ("funasr_speech_recognition", "Preprocessing Modules", "FunASR speech recognition", "full_bleed_card"),
    ("spoken_text_timestamps", "Preprocessing Modules", "spoken text with timestamps", "full_bleed_card"),
    ("mtcnn_face_detection", "Preprocessing Modules", "MTCNN face detection", "full_frame_icon"),
    ("face_clip_sequence", "Preprocessing Modules", "face clips", "scene_thumbnail"),
    ("alphapose_skeleton_extraction", "Preprocessing Modules", "AlphaPose full-body skeleton extraction", "full_frame_icon"),
    ("pose_skeleton_stream", "Preprocessing Modules", "full-body pose skeleton stream", "full_bleed_card"),
    ("frame_sampling_stack", "Preprocessing Modules", "frame sampling from video", "full_bleed_card"),
    ("sampled_video_frames", "Preprocessing Modules", "sampled video frames", "scene_thumbnail"),
    ("timestamp_clock", "Timestamp Alignment", "timestamp alignment clock", "full_frame_icon"),
    ("timeline_audio_text", "Timestamp Alignment", "aligned audio and text streams", "full_bleed_card"),
    ("timeline_face_pose", "Timestamp Alignment", "aligned face and pose streams", "full_bleed_card"),
    ("timeline_frame_stream", "Timestamp Alignment", "aligned frame stream", "full_bleed_card"),
    ("modality_face", "Five Modalities", "face modality", "full_frame_icon"),
    ("modality_frame", "Five Modalities", "frame modality", "scene_thumbnail"),
    ("modality_pose", "Five Modalities", "pose modality", "full_frame_icon"),
    ("modality_audio", "Five Modalities", "audio modality", "full_frame_icon"),
    ("modality_text", "Five Modalities", "text modality", "full_frame_icon"),
    ("neo_questionnaire", "NEO-FFI-3 Self-report Labels", "NEO-FFI-3 questionnaire", "full_bleed_card"),
    ("ocean_score_vector", "NEO-FFI-3 Self-report Labels", "OCEAN score vector", "full_bleed_card"),
    ("openness_label", "NEO-FFI-3 Self-report Labels", "Openness score", "full_frame_icon"),
    ("conscientiousness_label", "NEO-FFI-3 Self-report Labels", "Conscientiousness score", "full_frame_icon"),
    ("extraversion_label", "NEO-FFI-3 Self-report Labels", "Extraversion score", "full_frame_icon"),
    ("agreeableness_label", "NEO-FFI-3 Self-report Labels", "Agreeableness score", "full_frame_icon"),
    ("neuroticism_label", "NEO-FFI-3 Self-report Labels", "Neuroticism score", "full_frame_icon"),
    ("dataset_database", "Multimodal Personality Dataset", "multimodal personality dataset database", "full_frame_icon"),
    ("dataset_aligned_samples", "Multimodal Personality Dataset", "videos aligned across five modalities", "full_bleed_card"),
    ("dataset_participant_index", "Multimodal Personality Dataset", "participant identity index", "full_frame_icon"),
    ("dataset_label_binding", "Multimodal Personality Dataset", "modality streams bound to OCEAN labels", "full_bleed_card"),
    ("legend_video", "Legend", "video icon", "full_frame_icon"),
    ("legend_audio", "Legend", "audio icon", "full_frame_icon"),
    ("legend_text", "Legend", "text icon", "full_frame_icon"),
    ("legend_face", "Legend", "face icon", "full_frame_icon"),
    ("legend_pose", "Legend", "pose icon", "full_frame_icon"),
    ("legend_frames", "Legend", "frames icon", "full_frame_icon"),
]

PERSONALITY_PANEL_LAYOUT = {
    "Virtual Interview Setup": {"x": 0.02, "y": 0.11, "w": 0.125, "h": 0.62},
    "Raw Video Collection": {"x": 0.17, "y": 0.24, "w": 0.13, "h": 0.42},
    "Preprocessing Modules": {"x": 0.335, "y": 0.08, "w": 0.23, "h": 0.66},
    "Timestamp Alignment": {"x": 0.595, "y": 0.24, "w": 0.085, "h": 0.43},
    "Five Modalities": {"x": 0.700, "y": 0.17, "w": 0.105, "h": 0.58},
    "NEO-FFI-3 Self-report Labels": {"x": 0.815, "y": 0.17, "w": 0.100, "h": 0.58},
    "Multimodal Personality Dataset": {"x": 0.930, "y": 0.29, "w": 0.065, "h": 0.36},
    "Legend": {"x": 0.03, "y": 0.82, "w": 0.52, "h": 0.10},
}

PERSONALITY_REFERENCE_PANEL_LAYOUT = {
    "Virtual Interview Setup": {"x": 0.005, "y": 0.050, "w": 0.137, "h": 0.735},
    "Raw Video Collection": {"x": 0.167, "y": 0.190, "w": 0.119, "h": 0.495},
    "Preprocessing Modules": {"x": 0.323, "y": 0.050, "w": 0.217, "h": 0.765},
    "Timestamp Alignment": {"x": 0.565, "y": 0.215, "w": 0.085, "h": 0.495},
    "Five Modalities": {"x": 0.665, "y": 0.150, "w": 0.106, "h": 0.625},
    "NEO-FFI-3 Self-report Labels": {"x": 0.790, "y": 0.150, "w": 0.105, "h": 0.625},
    "Multimodal Personality Dataset": {"x": 0.914, "y": 0.270, "w": 0.084, "h": 0.400},
    "Legend": {"x": 0.010, "y": 0.840, "w": 0.520, "h": 0.100},
}

PERSONALITY_REFERENCE_SLOT_SPECS = [
    {"id": "setup_participant_screen", "macro_panel": "Virtual Interview Setup", "paper_concept": "participant in front of 49-inch screen", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.014, "y": 0.135, "w": 0.118, "h": 0.180}},
    {"id": "setup_virtual_interviewer", "macro_panel": "Virtual Interview Setup", "paper_concept": "3D virtual interviewer on screen", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.016, "y": 0.390, "w": 0.116, "h": 0.135}},
    {"id": "setup_camera_full_body", "macro_panel": "Virtual Interview Setup", "paper_concept": "wide-angle camera capturing full body", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.015, "y": 0.585, "w": 0.117, "h": 0.170}},
    {"id": "raw_video_file", "macro_panel": "Raw Video Collection", "paper_concept": "raw interview video recording", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.184, "y": 0.315, "w": 0.082, "h": 0.135}},
    {"id": "raw_clip_grid", "macro_panel": "Raw Video Collection", "paper_concept": "participant full-body video thumbnail grid", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.178, "y": 0.490, "w": 0.092, "h": 0.165}},
    {"id": "ffmpeg_video_to_audio", "macro_panel": "Preprocessing Modules", "paper_concept": "FFmpeg video-to-audio extraction", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.338, "y": 0.118, "w": 0.042, "h": 0.078}},
    {"id": "audio_waveform_stream", "macro_panel": "Preprocessing Modules", "paper_concept": "audio waveform output", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.448, "y": 0.120, "w": 0.050, "h": 0.075}},
    {"id": "funasr_speech_recognition", "macro_panel": "Preprocessing Modules", "paper_concept": "FunASR speech recognition microphone", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.340, "y": 0.255, "w": 0.040, "h": 0.082}},
    {"id": "spoken_text_timestamps", "macro_panel": "Preprocessing Modules", "paper_concept": "spoken text with timestamps", "composition_type": "full_bleed_card", "bbox_percent": {"x": 0.444, "y": 0.253, "w": 0.064, "h": 0.090}},
    {"id": "mtcnn_face_detection", "macro_panel": "Preprocessing Modules", "paper_concept": "MTCNN face detection", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.340, "y": 0.395, "w": 0.042, "h": 0.082}},
    {"id": "face_clip_sequence", "macro_panel": "Preprocessing Modules", "paper_concept": "face clips", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.445, "y": 0.395, "w": 0.060, "h": 0.090}},
    {"id": "alphapose_skeleton_extraction", "macro_panel": "Preprocessing Modules", "paper_concept": "AlphaPose full-body skeleton extraction", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.338, "y": 0.535, "w": 0.042, "h": 0.088}},
    {"id": "pose_skeleton_stream", "macro_panel": "Preprocessing Modules", "paper_concept": "full-body pose skeletons", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.443, "y": 0.532, "w": 0.060, "h": 0.092}},
    {"id": "frame_sampling_stack", "macro_panel": "Preprocessing Modules", "paper_concept": "frame sampling stack", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.336, "y": 0.665, "w": 0.052, "h": 0.095}},
    {"id": "sampled_video_frames", "macro_panel": "Preprocessing Modules", "paper_concept": "sampled video frames", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.450, "y": 0.672, "w": 0.050, "h": 0.085}},
    {"id": "timestamp_clock", "macro_panel": "Timestamp Alignment", "paper_concept": "timestamp alignment clock", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.585, "y": 0.340, "w": 0.050, "h": 0.120}},
    {"id": "modality_face", "macro_panel": "Five Modalities", "paper_concept": "face modality", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.678, "y": 0.215, "w": 0.080, "h": 0.095}},
    {"id": "modality_frame", "macro_panel": "Five Modalities", "paper_concept": "frame modality", "composition_type": "scene_thumbnail", "bbox_percent": {"x": 0.678, "y": 0.340, "w": 0.080, "h": 0.095}},
    {"id": "modality_pose", "macro_panel": "Five Modalities", "paper_concept": "pose modality", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.678, "y": 0.465, "w": 0.080, "h": 0.095}},
    {"id": "modality_audio", "macro_panel": "Five Modalities", "paper_concept": "audio modality", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.678, "y": 0.590, "w": 0.080, "h": 0.095}},
    {"id": "modality_text", "macro_panel": "Five Modalities", "paper_concept": "text modality", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.678, "y": 0.708, "w": 0.080, "h": 0.095}},
    {"id": "neo_questionnaire", "macro_panel": "NEO-FFI-3 Self-report Labels", "paper_concept": "NEO-FFI-3 questionnaire checklist", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.815, "y": 0.220, "w": 0.065, "h": 0.120}},
    {"id": "openness_label", "macro_panel": "NEO-FFI-3 Self-report Labels", "paper_concept": "Openness score badge", "composition_type": "symbol_cutout", "bbox_percent": {"x": 0.800, "y": 0.425, "w": 0.025, "h": 0.055}},
    {"id": "conscientiousness_label", "macro_panel": "NEO-FFI-3 Self-report Labels", "paper_concept": "Conscientiousness score badge", "composition_type": "symbol_cutout", "bbox_percent": {"x": 0.800, "y": 0.495, "w": 0.025, "h": 0.055}},
    {"id": "extraversion_label", "macro_panel": "NEO-FFI-3 Self-report Labels", "paper_concept": "Extraversion score badge", "composition_type": "symbol_cutout", "bbox_percent": {"x": 0.800, "y": 0.565, "w": 0.025, "h": 0.055}},
    {"id": "agreeableness_label", "macro_panel": "NEO-FFI-3 Self-report Labels", "paper_concept": "Agreeableness score badge", "composition_type": "symbol_cutout", "bbox_percent": {"x": 0.800, "y": 0.635, "w": 0.025, "h": 0.055}},
    {"id": "neuroticism_label", "macro_panel": "NEO-FFI-3 Self-report Labels", "paper_concept": "Neuroticism score badge", "composition_type": "symbol_cutout", "bbox_percent": {"x": 0.800, "y": 0.705, "w": 0.025, "h": 0.055}},
    {"id": "dataset_database", "macro_panel": "Multimodal Personality Dataset", "paper_concept": "multimodal personality dataset database", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.932, "y": 0.390, "w": 0.050, "h": 0.130}},
    {"id": "legend_video", "macro_panel": "Legend", "paper_concept": "legend video icon", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.030, "y": 0.870, "w": 0.035, "h": 0.050}},
    {"id": "legend_audio", "macro_panel": "Legend", "paper_concept": "legend audio icon", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.120, "y": 0.870, "w": 0.040, "h": 0.050}},
    {"id": "legend_text", "macro_panel": "Legend", "paper_concept": "legend text icon", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.215, "y": 0.865, "w": 0.035, "h": 0.055}},
    {"id": "legend_face", "macro_panel": "Legend", "paper_concept": "legend face icon", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.288, "y": 0.865, "w": 0.035, "h": 0.055}},
    {"id": "legend_pose", "macro_panel": "Legend", "paper_concept": "legend pose icon", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.360, "y": 0.865, "w": 0.035, "h": 0.055}},
    {"id": "legend_frames", "macro_panel": "Legend", "paper_concept": "legend frames icon", "composition_type": "full_frame_icon", "bbox_percent": {"x": 0.435, "y": 0.865, "w": 0.050, "h": 0.055}},
]

AUTOFIGURE_REFERENCE_PANEL_LAYOUT = {
    "Stage I: Concept Extraction": {"x": 0.022, "y": 0.173, "w": 0.302, "h": 0.671},
    "Stage II: Critique-and-Refine": {"x": 0.344, "y": 0.174, "w": 0.337, "h": 0.675},
    "Stage III: Rendering Strategy": {"x": 0.704, "y": 0.049, "w": 0.277, "h": 0.914},
    "Key Methodology": {"x": 0.023, "y": 0.881, "w": 0.657, "h": 0.084},
}

AUTOFIGURE_REFERENCE_SLOT_SPECS = [
    {
        "id": "input_text_stack",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "unstructured paper text input",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.041, "y": 0.264, "w": 0.085, "h": 0.169},
        "display_label": "Input Text",
        "show_slot_caption": True,
        "visual_metaphor": "stack of manuscript pages with tiny decorative text lines",
        "must_show": ["paper stack", "abstract text lines", "scientific manuscript input"],
        "avoid_showing": ["real readable paragraphs", "fake formula-heavy page"],
    },
    {
        "id": "input_to_vlm_arrow_symbol",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "input text passed to VLM agent",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.125, "y": 0.326, "w": 0.031, "h": 0.058},
        "visual_metaphor": "thick rightward process arrow matching the reference figure",
        "must_show": ["single right arrow", "rounded scientific diagram style"],
        "avoid_showing": ["text", "large blank canvas"],
    },
    {
        "id": "vlm_agent_robot",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "VLM agent parses scientific figure concepts",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.165, "y": 0.258, "w": 0.082, "h": 0.189},
        "display_label": "VLM Agent",
        "show_slot_caption": True,
        "visual_metaphor": "cute but detailed VLM robot head with antenna and multimodal swirls",
        "must_show": ["robot agent", "multimodal reasoning swirls", "academic flat illustration"],
        "avoid_showing": ["generic brain", "sci-fi neon robot"],
    },
    {
        "id": "entities_bubble",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "extracted entity set",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.262, "y": 0.260, "w": 0.054, "h": 0.092},
        "display_label": "Entities",
        "visual_metaphor": "circular entity bubble containing small connected object glyphs",
        "must_show": ["round bubble", "several entity glyphs", "high fill"],
        "avoid_showing": ["empty circle", "readable labels"],
    },
    {
        "id": "relations_bubble",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "extracted relation set",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.262, "y": 0.363, "w": 0.054, "h": 0.092},
        "display_label": "Relations",
        "visual_metaphor": "circular relation bubble with linked nodes and arrows",
        "must_show": ["round bubble", "node links", "relation arrows"],
        "avoid_showing": ["readable graph labels", "empty circle"],
    },
    {
        "id": "vlm_to_blueprint_down_arrow",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "VLM output becomes initial symbolic blueprint",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.196, "y": 0.462, "w": 0.030, "h": 0.063},
        "visual_metaphor": "thick downward arrow matching soft academic diagram style",
        "must_show": ["single down arrow", "blue-gray fill", "rounded arrowhead"],
        "avoid_showing": ["text", "thin line arrow"],
    },
    {
        "id": "initial_blueprint_code_card",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "initial blueprint symbolic graph S0 A0",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.049, "y": 0.525, "w": 0.180, "h": 0.233},
        "display_label": "Initial Blueprint",
        "visual_metaphor": "dashed code card showing abstract JSON-like symbolic graph",
        "must_show": ["dashed rounded card", "abstract code lines", "blueprint graph structure"],
        "avoid_showing": ["readable fake code", "fake numeric coordinates as facts"],
    },
    {
        "id": "blueprint_graph_connector",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "symbolic graph connects blueprint entries to visual nodes",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.191, "y": 0.610, "w": 0.061, "h": 0.089},
        "visual_metaphor": "blue bracket connector branching from code to two nodes",
        "must_show": ["curly connector", "two output branches", "dense linework"],
        "avoid_showing": ["readable text", "blank diagram"],
    },
    {
        "id": "blueprint_node_a",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "blueprint node A visual element",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.239, "y": 0.564, "w": 0.065, "h": 0.064},
        "display_label": "Node A",
        "visual_metaphor": "rounded graph node card with one tiny visual glyph",
        "must_show": ["rounded node card", "small visual glyph", "full-frame card"],
        "avoid_showing": ["large empty margins", "readable fake text"],
    },
    {
        "id": "blueprint_node_b",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "blueprint node B visual element",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.240, "y": 0.671, "w": 0.065, "h": 0.063},
        "display_label": "Node B",
        "visual_metaphor": "rounded graph node card with expressive tiny glyph",
        "must_show": ["rounded node card", "small visual glyph", "full-frame card"],
        "avoid_showing": ["large empty margins", "readable fake text"],
    },
    {
        "id": "stage_transition_arrow_1",
        "macro_panel": "Stage I: Concept Extraction",
        "paper_concept": "concept extraction output feeds critique-and-refine stage",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.315, "y": 0.497, "w": 0.036, "h": 0.066},
        "visual_metaphor": "large rightward transition arrow between architecture stages",
        "must_show": ["single thick arrow", "gray-blue fill", "rounded arrowhead"],
        "avoid_showing": ["text", "many small arrows"],
    },
    {
        "id": "critique_banner",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "critic checks alignment overlap and balance",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.391, "y": 0.267, "w": 0.245, "h": 0.057},
        "display_label": "Critique",
        "visual_metaphor": "rounded speech banner for visual critique criteria",
        "must_show": ["speech banner", "three compact abstract checklist marks", "orange style"],
        "avoid_showing": ["long readable sentence", "empty banner"],
    },
    {
        "id": "refine_layout_bubble",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "AI designer receives refine-layout instruction",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.357, "y": 0.360, "w": 0.063, "h": 0.070},
        "display_label": "Refine Layout",
        "visual_metaphor": "small speech bubble pointing to designer with layout grid glyph",
        "must_show": ["speech bubble", "layout grid glyph", "orange outline"],
        "avoid_showing": ["large blank bubble", "readable paragraphs"],
    },
    {
        "id": "ai_designer_robot",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "AI designer proposes layout improvements",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.366, "y": 0.450, "w": 0.092, "h": 0.186},
        "display_label": "AI Designer",
        "show_slot_caption": True,
        "visual_metaphor": "designer robot holding a blueprint tablet",
        "must_show": ["robot designer", "blueprint tablet", "creative layout planning"],
        "avoid_showing": ["generic humanoid", "office worker photo"],
    },
    {
        "id": "designer_blueprint_tablet",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "designer edits candidate figure blueprint",
        "composition_type": "scene_thumbnail",
        "bbox_percent": {"x": 0.409, "y": 0.527, "w": 0.050, "h": 0.078},
        "visual_metaphor": "close-up blue tablet with dense layout boxes and arrows",
        "must_show": ["tablet", "dense layout boxes", "diagram editing"],
        "avoid_showing": ["readable words", "empty screen"],
    },
    {
        "id": "score_comparison_card",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "score comparison chooses better candidate q cand greater than q best",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.448, "y": 0.490, "w": 0.129, "h": 0.093},
        "display_label": "Score Comparison",
        "visual_metaphor": "compact comparison card with abstract score bars and checkmark",
        "must_show": ["rounded comparison card", "two candidate bars", "winner indicator"],
        "avoid_showing": ["fake exact numbers", "readable equations"],
    },
    {
        "id": "feedback_bubble",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "AI critic emits feedback F i",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.611, "y": 0.359, "w": 0.063, "h": 0.071},
        "display_label": "Feedback",
        "visual_metaphor": "speech bubble with clipboard feedback glyphs",
        "must_show": ["speech bubble", "feedback marks", "orange outline"],
        "avoid_showing": ["long text", "empty bubble"],
    },
    {
        "id": "ai_critic_robot",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "AI critic evaluates visual alignment and errors",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.597, "y": 0.451, "w": 0.093, "h": 0.188},
        "display_label": "AI Critic",
        "show_slot_caption": True,
        "visual_metaphor": "critic robot with glasses holding a checklist clipboard",
        "must_show": ["robot critic", "glasses", "checklist clipboard", "review posture"],
        "avoid_showing": ["generic robot only", "scientist portrait"],
    },
    {
        "id": "critic_clipboard_detail",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "critic checklist records visual diagnostics",
        "composition_type": "scene_thumbnail",
        "bbox_percent": {"x": 0.629, "y": 0.515, "w": 0.047, "h": 0.087},
        "visual_metaphor": "clipboard close-up with dense check marks and visual diagnostic rows",
        "must_show": ["clipboard", "check marks", "diagnostic rows"],
        "avoid_showing": ["readable fake metrics", "empty clipboard"],
    },
    {
        "id": "refinement_loop_dashed_arc",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "self-refinement loop between designer and critic",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.420, "y": 0.340, "w": 0.197, "h": 0.371},
        "visual_metaphor": "large dashed circular feedback loop arrows, transparent center",
        "must_show": ["dashed circular arrows", "loop motion", "orange color"],
        "avoid_showing": ["solid filled circle", "text labels"],
    },
    {
        "id": "update_banner",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "updated design re-interprets method and improves figure",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.385, "y": 0.772, "w": 0.232, "h": 0.058},
        "display_label": "Update",
        "visual_metaphor": "rounded update banner with revision arrows and improvement sparkles",
        "must_show": ["rounded banner", "revision arrows", "improvement marks"],
        "avoid_showing": ["long readable instruction", "empty rectangle"],
    },
    {
        "id": "stage_transition_arrow_2",
        "macro_panel": "Stage II: Critique-and-Refine",
        "paper_concept": "refined plan feeds rendering strategy",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.681, "y": 0.497, "w": 0.036, "h": 0.066},
        "visual_metaphor": "large rightward transition arrow into rendering stage",
        "must_show": ["single thick arrow", "gray-blue fill", "rounded arrowhead"],
        "avoid_showing": ["text", "many arrows"],
    },
    {
        "id": "synthesis_magic_wand",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "image synthesis generates raw scientific illustration",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.781, "y": 0.133, "w": 0.060, "h": 0.096},
        "display_label": "Synthesis",
        "visual_metaphor": "magic wand with sparkles for image synthesis",
        "must_show": ["magic wand", "sparkles", "soft academic illustration"],
        "avoid_showing": ["text", "large blank background"],
    },
    {
        "id": "synthesis_palette",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "aesthetic rendering style palette",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.856, "y": 0.132, "w": 0.072, "h": 0.105},
        "visual_metaphor": "cute color palette with rich paint dots",
        "must_show": ["paint palette", "multiple colors", "dense details"],
        "avoid_showing": ["monochrome", "large white margins"],
    },
    {
        "id": "raw_image_card",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "raw generated image before text correction",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.802, "y": 0.355, "w": 0.091, "h": 0.113},
        "display_label": "Raw Image",
        "visual_metaphor": "raw image card with blurred decorative text marks",
        "must_show": ["rounded image card", "blurred red text mark", "raw output feel"],
        "avoid_showing": ["readable fake text", "blank card"],
    },
    {
        "id": "erase_text_tool",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "erase-and-correct removes malformed text",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.739, "y": 0.495, "w": 0.070, "h": 0.129},
        "display_label": "Erase Text",
        "show_slot_caption": True,
        "visual_metaphor": "pink eraser actively removing blurred ABC marks",
        "must_show": ["eraser", "blurred letters being removed", "motion particles"],
        "avoid_showing": ["readable words", "empty eraser icon"],
    },
    {
        "id": "ocr_verify_magnifier",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "OCR verifies rendered text correctness",
        "composition_type": "full_frame_icon",
        "bbox_percent": {"x": 0.884, "y": 0.490, "w": 0.081, "h": 0.137},
        "display_label": "OCR + Verify",
        "show_slot_caption": True,
        "visual_metaphor": "magnifying glass checking tiny decorative numbers and lines with green check badge",
        "must_show": ["magnifier", "green verification check", "document line details"],
        "avoid_showing": ["fake exact metrics", "large blank background"],
    },
    {
        "id": "rendering_loop_dashed_arrows",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "render erase OCR verification loop",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.760, "y": 0.411, "w": 0.183, "h": 0.332},
        "visual_metaphor": "green dashed loop arrows connecting raw image, erase, OCR, final output",
        "must_show": ["dashed loop arrows", "green arrowheads", "transparent center"],
        "avoid_showing": ["text", "solid filled blob"],
    },
    {
        "id": "final_autofigure_card",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "publication-ready final AutoFigure output",
        "composition_type": "scene_thumbnail",
        "bbox_percent": {"x": 0.790, "y": 0.695, "w": 0.111, "h": 0.133},
        "display_label": "Final AutoFigure",
        "show_slot_caption": True,
        "visual_metaphor": "final polished scientific illustration card with charts and soft geometric panels",
        "must_show": ["rounded final figure card", "small chart shapes", "crisp high-resolution look"],
        "avoid_showing": ["fake axes labels", "readable metric numbers"],
    },
    {
        "id": "final_card_chart_detail",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "final figure contains polished chart and schematic details",
        "composition_type": "scene_thumbnail",
        "bbox_percent": {"x": 0.808, "y": 0.719, "w": 0.078, "h": 0.074},
        "visual_metaphor": "close-up miniature scientific chart shapes with crisp colored components",
        "must_show": ["mini chart", "geometric diagram pieces", "high detail density"],
        "avoid_showing": ["readable axes", "fake numbers"],
    },
    {
        "id": "green_quality_badge",
        "macro_panel": "Stage III: Rendering Strategy",
        "paper_concept": "verified output quality badge",
        "composition_type": "symbol_cutout",
        "bbox_percent": {"x": 0.947, "y": 0.493, "w": 0.032, "h": 0.052},
        "visual_metaphor": "green circular verification badge with checkmark",
        "must_show": ["green badge", "check mark", "filled icon"],
        "avoid_showing": ["text", "empty circle"],
    },
    {
        "id": "legend_concept_extraction_pill",
        "macro_panel": "Key Methodology",
        "paper_concept": "legend color for concept extraction stage",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.184, "y": 0.899, "w": 0.155, "h": 0.054},
        "display_label": "Concept Extraction",
        "visual_metaphor": "blue rounded legend pill with abstract concept extraction glyphs",
        "must_show": ["blue rounded pill", "tiny entity-relation glyphs", "dense fill"],
        "avoid_showing": ["large white card", "readable paragraph"],
    },
    {
        "id": "legend_critique_refine_pill",
        "macro_panel": "Key Methodology",
        "paper_concept": "legend color for critique-and-refine stage",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.350, "y": 0.899, "w": 0.155, "h": 0.054},
        "display_label": "Critique-and-Refine",
        "visual_metaphor": "orange rounded legend pill with loop and critic glyphs",
        "must_show": ["orange rounded pill", "feedback loop glyph", "dense fill"],
        "avoid_showing": ["large white card", "readable paragraph"],
    },
    {
        "id": "legend_rendering_strategy_pill",
        "macro_panel": "Key Methodology",
        "paper_concept": "legend color for rendering strategy stage",
        "composition_type": "full_bleed_card",
        "bbox_percent": {"x": 0.516, "y": 0.899, "w": 0.155, "h": 0.054},
        "display_label": "Rendering Strategy",
        "visual_metaphor": "green rounded legend pill with rendering palette glyph",
        "must_show": ["green rounded pill", "palette glyph", "dense fill"],
        "avoid_showing": ["large white card", "readable paragraph"],
    },
]

FORA_UA_SLOT_SPECS = [
    ("frozen_weight_matrix", "Extreme-Budget PEFT Problem", "frozen pretrained weight matrix W", "full_bleed_card"),
    ("lora_update_baseline", "Extreme-Budget PEFT Problem", "LoRA low-rank update Delta W equals B A", "full_bleed_card"),
    ("standard_lora_budget", "Extreme-Budget PEFT Problem", "standard LoRA trainable parameter budget", "full_frame_icon"),
    ("tiny_budget_constraint", "Extreme-Budget PEFT Problem", "extreme 1-5 percent LoRA parameter budget", "full_frame_icon"),
    ("direct_fourierft", "Baseline Approximation Study", "FourierFT direct sparse IFT approximation", "full_bleed_card"),
    ("small_matrix_finding", "Baseline Approximation Study", "Finding 1: smaller matrices improve fixed-sparse approximation", "full_bleed_card"),
    ("intermediate_finding", "Baseline Approximation Study", "Finding 2: intermediate representation reduces reconstruction error", "full_bleed_card"),
    ("split_theorem", "Baseline Approximation Study", "Finding 3: split matrices are lossless and useful", "full_bleed_card"),
    ("frozen_projection_a", "FoRA-UA Construction", "frozen random projection matrix A", "full_frame_icon"),
    ("sparse_frequency_b", "FoRA-UA Construction", "sparse frequency-domain matrix B", "full_bleed_card"),
    ("trainable_index_set", "FoRA-UA Construction", "random nonzero trainable index set S", "full_frame_icon"),
    ("empty_zero_entries", "FoRA-UA Construction", "empty zero entries left untrained", "full_frame_icon"),
    ("split_b_matrices", "FoRA-UA Construction", "split B into B_1 through B_M", "full_bleed_card"),
    ("ift_block_one", "IFT Split Projection", "inverse Fourier transform IFT(B_1)", "full_frame_icon"),
    ("ift_block_many", "IFT Split Projection", "parallel IFT over split B_m matrices", "full_frame_icon"),
    ("concat_blocks", "IFT Split Projection", "concatenate transformed split blocks", "full_bleed_card"),
    ("delta_w_formula_visual", "IFT Split Projection", "Delta W equals concatenated IFT blocks times A", "full_bleed_card"),
    ("adapter_delta_w", "Adapter Injection", "FoRA-UA update Delta W", "full_frame_icon"),
    ("frozen_w_plus_delta", "Adapter Injection", "pretrained W remains frozen while Delta W is added", "full_bleed_card"),
    ("target_qv_modules", "Adapter Injection", "insert update into query and value target modules", "full_bleed_card"),
    ("train_only_sparse_b", "Adapter Injection", "only nonzero entries of B_m are updated", "full_frame_icon"),
    ("glue_evaluation", "Multi-Task Evaluation", "GLUE natural language understanding evaluation", "full_frame_icon"),
    ("e2e_generation_eval", "Multi-Task Evaluation", "E2E natural language generation evaluation", "full_frame_icon"),
    ("math_reasoning_eval", "Multi-Task Evaluation", "math reasoning with LLaMA evaluation", "full_frame_icon"),
    ("vision_classification_eval", "Multi-Task Evaluation", "vision classification with ViT evaluation", "full_frame_icon"),
    ("parameter_count_gain", "Tiny-Budget Gains", "1-5 percent of LoRA trainable parameters", "full_frame_icon"),
    ("performance_tradeoff", "Tiny-Budget Gains", "best tradeoff between performance and trainable parameters", "full_bleed_card"),
    ("rank_ablation", "Tiny-Budget Gains", "rank ablation and split-count sensitivity", "full_bleed_card"),
    ("flops_tradeoff", "Tiny-Budget Gains", "FLOPs tradeoff analysis", "full_frame_icon"),
    ("legend_frozen", "Legend", "frozen parameter icon", "full_frame_icon"),
    ("legend_trainable", "Legend", "trainable sparse parameter icon", "full_frame_icon"),
    ("legend_ift", "Legend", "inverse Fourier transform icon", "full_frame_icon"),
    ("legend_concat", "Legend", "concatenation icon", "full_frame_icon"),
    ("legend_eval", "Legend", "evaluation benchmark icon", "full_frame_icon"),
]

FORA_UA_PANEL_LAYOUT = {
    "Extreme-Budget PEFT Problem": {"x": 0.02, "y": 0.11, "w": 0.125, "h": 0.62},
    "Baseline Approximation Study": {"x": 0.17, "y": 0.24, "w": 0.13, "h": 0.42},
    "FoRA-UA Construction": {"x": 0.335, "y": 0.08, "w": 0.23, "h": 0.66},
    "IFT Split Projection": {"x": 0.595, "y": 0.24, "w": 0.085, "h": 0.43},
    "Adapter Injection": {"x": 0.700, "y": 0.17, "w": 0.105, "h": 0.58},
    "Multi-Task Evaluation": {"x": 0.815, "y": 0.17, "w": 0.100, "h": 0.58},
    "Tiny-Budget Gains": {"x": 0.930, "y": 0.29, "w": 0.065, "h": 0.36},
    "Legend": {"x": 0.03, "y": 0.82, "w": 0.52, "h": 0.10},
}


def _spec_value(spec: Any, key: str, index: int | None = None):
    if isinstance(spec, dict):
        return spec.get(key)
    if isinstance(spec, (tuple, list)):
        mapping = {"id": 0, "macro_panel": 1, "paper_concept": 2, "composition_type": 3}
        pos = mapping.get(key) if index is None else index
        if pos is not None and pos < len(spec):
            return spec[pos]
    return None


def _generic_slot_specs(paper_brief: dict, slot_count: int) -> tuple[list[dict], dict[str, dict]]:
    modules = [str(item) for item in paper_brief.get("modules", []) if str(item).strip()]
    if not modules:
        modules = ["Paper Problem", "Method Core", "Training or Inference Flow", "Outputs", "Evaluation"]
    modules = modules[:7]
    layout_template = [
        {"x": 0.02, "y": 0.11, "w": 0.125, "h": 0.62},
        {"x": 0.17, "y": 0.24, "w": 0.13, "h": 0.42},
        {"x": 0.335, "y": 0.08, "w": 0.23, "h": 0.66},
        {"x": 0.595, "y": 0.24, "w": 0.085, "h": 0.43},
        {"x": 0.700, "y": 0.17, "w": 0.105, "h": 0.58},
        {"x": 0.815, "y": 0.17, "w": 0.100, "h": 0.58},
        {"x": 0.930, "y": 0.29, "w": 0.065, "h": 0.36},
    ]
    panel_layout = {module: layout_template[index] for index, module in enumerate(modules)}
    panel_layout["Legend"] = {"x": 0.03, "y": 0.82, "w": 0.52, "h": 0.10}
    suggestions = paper_brief.get("slot_suggestions", [])
    specs: list[dict] = []
    if isinstance(suggestions, list):
        for index, item in enumerate(suggestions[:slot_count]):
            if not isinstance(item, dict):
                continue
            panel = str(item.get("macro_panel") or modules[index % len(modules)]).strip()
            if panel not in panel_layout:
                panel = modules[index % len(modules)]
            concept = str(item.get("paper_concept") or panel).strip()
            slot_id = str(item.get("id") or concept).strip()
            slot_id = "".join(ch if ch.isalnum() else "_" for ch in slot_id.lower()).strip("_")[:52] or f"slot_{index+1:02d}"
            composition = str(item.get("composition_type") or "full_bleed_card")
            if composition not in {"full_frame_icon", "full_bleed_card", "scene_thumbnail", "symbol_cutout"}:
                composition = "full_bleed_card"
            specs.append({
                "id": slot_id,
                "macro_panel": panel,
                "paper_concept": concept,
                "composition_type": composition,
                "visual_metaphor": str(item.get("visual_metaphor") or "").strip(),
                "must_show": item.get("must_show") if isinstance(item.get("must_show"), list) else [],
                "avoid_showing": item.get("avoid_showing") if isinstance(item.get("avoid_showing"), list) else [],
            })
    if len(specs) >= min(25, slot_count):
        return specs[:slot_count], panel_layout

    concepts = [str(item) for item in paper_brief.get("concepts", []) if str(item).strip()]
    for index in range(slot_count):
        panel = modules[index % len(modules)]
        concept = concepts[index] if index < len(concepts) else f"{panel} visual unit {index + 1}"
        slot_id = "".join(ch if ch.isalnum() else "_" for ch in concept.lower()).strip("_")[:44] or f"slot_{index+1:02d}"
        composition = "scene_thumbnail" if any(word in concept.lower() for word in ["example", "input", "output", "dataset", "task"]) else ("full_bleed_card" if index % 3 else "full_frame_icon")
        specs.append({
            "id": f"{slot_id}_{index+1:02d}",
            "macro_panel": panel,
            "paper_concept": concept,
            "composition_type": composition,
            "visual_metaphor": "",
            "must_show": [],
            "avoid_showing": [],
        })
    return specs, panel_layout


def _slot_bbox(panel: str, index_in_panel: int, count_in_panel: int, panel_layout: dict[str, dict] | None = None) -> dict[str, float]:
    layout = panel_layout or PANEL_LAYOUT
    p = layout[panel]
    if panel == "Shared Resource Library":
        gap = 0.012
        inner_x = p["x"] + 0.018
        inner_y = p["y"] + 0.062
        cell_w = (p["w"] - 0.036 - gap * (count_in_panel - 1)) / count_in_panel
        return {"x": inner_x + index_in_panel * (cell_w + gap), "y": inner_y, "w": cell_w, "h": p["h"] * 0.46}
    if panel == "Legend":
        gap = 0.012
        inner_x = p["x"] + 0.012
        inner_y = p["y"] + 0.03
        cell_w = (p["w"] - 0.024 - gap * (count_in_panel - 1)) / max(count_in_panel, 1)
        return {"x": inner_x + index_in_panel * (cell_w + gap), "y": inner_y, "w": cell_w, "h": p["h"] * 0.48}
    if panel in {
        "Five Modalities", "NEO-FFI-3 Self-report Labels", "Timestamp Alignment", "Multimodal Personality Dataset",
        "IFT Split Projection", "Adapter Injection", "Multi-Task Evaluation", "Tiny-Budget Gains",
    }:
        inner_x = p["x"] + p["w"] * 0.10
        inner_y = p["y"] + p["h"] * 0.16
        inner_w = p["w"] * 0.80
        inner_h = p["h"] * 0.76
        gap = inner_h * 0.045
        cell_h = (inner_h - gap * (count_in_panel - 1)) / max(count_in_panel, 1)
        return {"x": inner_x, "y": inner_y + index_in_panel * (cell_h + gap), "w": inner_w, "h": cell_h}

    inner_x = p["x"] + 0.014
    inner_y = p["y"] + 0.085
    inner_w = p["w"] - 0.028
    inner_h = p["h"] - 0.115
    if count_in_panel <= 3:
        cell_h = inner_h / count_in_panel
        return {"x": inner_x, "y": inner_y + index_in_panel * cell_h, "w": inner_w, "h": cell_h * 0.78}
    col = index_in_panel % 2
    row = index_in_panel // 2
    import math
    rows = max(1, math.ceil(count_in_panel / 2))
    cell_h = inner_h / rows
    return {
        "x": inner_x + col * inner_w * 0.52,
        "y": inner_y + row * cell_h,
        "w": inner_w * 0.44,
        "h": cell_h * 0.78,
    }


def analyze_reference(
    reference_path: str | Path,
    paper_brief: dict,
    out_dir: str | Path,
    slot_count: int = 36,
    slot_source: str | None = None,
    control_localizer_mode: str = "hybrid",
) -> dict:
    p = Path(reference_path)
    with Image.open(p) as img:
        width, height = img.size
        reference_image = img.convert("RGB").copy()

    out_path = Path(out_dir)
    slot_count = max(25, min(50, int(slot_count)))
    requested_control_mode = str(control_localizer_mode or "hybrid").lower().replace("_", "-")
    if requested_control_mode not in {"off", "heuristic", "hybrid"}:
        requested_control_mode = "hybrid"
    effective_control_mode = requested_control_mode
    control_warnings: list[str] = []
    if requested_control_mode == "hybrid" and not ((os.getenv("API_BASE", "").strip()) and (os.getenv("API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip())):
        effective_control_mode = "heuristic"
        control_warnings.append("hybrid_downgraded_to_heuristic:no_api_credentials")
    allow_legacy_templates = False
    try:
        import os
        allow_legacy_templates = os.getenv("RFS_ALLOW_LEGACY_TEMPLATES", "").lower() in {"1", "true", "yes"}
    except Exception:
        allow_legacy_templates = False

    reference_slot_source = str(slot_source or "").lower() or "paper"
    try:
        import os
        reference_slot_source = str(slot_source or os.getenv("RFS_SLOT_SOURCE", "paper")).lower()
    except Exception:
        reference_slot_source = str(slot_source or "paper").lower()

    paper_text = " ".join(
        [
            str(paper_brief.get("title_guess", "")),
            str(paper_brief.get("figure_goal", "")),
            " ".join(str(item) for item in paper_brief.get("modules", [])),
            " ".join(str(item) for item in paper_brief.get("concepts", [])),
        ]
    ).lower()
    reference_primary_personality = (
        reference_slot_source in {"reference", "reference-primary", "reference_primary"}
        and "personality" in paper_text
        and ("multimodal" in paper_text or "neo" in paper_text or "ocean" in paper_text)
    )
    reference_primary_autofigure = (
        reference_slot_source in {"reference", "reference-primary", "reference_primary"}
        and "autofigure" in paper_text
        and ("scientific illustration" in paper_text or "figurebench" in paper_text or "critique" in paper_text)
    )

    strict_reference_bboxes = False
    if reference_primary_autofigure:
        all_specs = AUTOFIGURE_REFERENCE_SLOT_SPECS
        panel_layout = AUTOFIGURE_REFERENCE_PANEL_LAYOUT
        strict_reference_bboxes = True
    elif reference_primary_personality:
        all_specs = PERSONALITY_REFERENCE_SLOT_SPECS
        panel_layout = PERSONALITY_REFERENCE_PANEL_LAYOUT
        strict_reference_bboxes = True
    elif allow_legacy_templates and paper_brief.get("figure_kind") == "multimodal_personality_dataset":
        all_specs = PERSONALITY_SLOT_SPECS
        panel_layout = PERSONALITY_PANEL_LAYOUT
    elif allow_legacy_templates and paper_brief.get("figure_kind") == "fora_ua":
        all_specs = FORA_UA_SLOT_SPECS
        panel_layout = FORA_UA_PANEL_LAYOUT
    elif allow_legacy_templates and paper_brief.get("figure_kind") == "banana_game":
        all_specs = MASTER_SLOT_SPECS
        panel_layout = PANEL_LAYOUT
    else:
        all_specs, panel_layout = _generic_slot_specs(paper_brief, slot_count)
    control_specs = [spec for spec in all_specs if _is_control_spec(spec)]
    image_slot_specs = [spec for spec in all_specs if not _is_control_spec(spec)]
    if reference_slot_source in {"reference", "reference-primary", "reference_primary"}:
        image_slot_specs = _supplement_reference_slots(image_slot_specs, min(slot_count, 25))
    specs = image_slot_specs[:slot_count]
    panel_counts: dict[str, int] = {}
    for spec in specs:
        panel = str(_spec_value(spec, "macro_panel"))
        panel_counts[panel] = panel_counts.get(panel, 0) + 1
    panel_seen: dict[str, int] = {}

    slots = []
    for spec in specs:
        slot_id = str(_spec_value(spec, "id"))
        panel = str(_spec_value(spec, "macro_panel"))
        concept = str(_spec_value(spec, "paper_concept"))
        composition_type = str(_spec_value(spec, "composition_type") or "full_bleed_card")
        index = panel_seen.get(panel, 0)
        panel_seen[panel] = index + 1
        explicit_bbox = _spec_value(spec, "bbox_percent")
        if strict_reference_bboxes and isinstance(explicit_bbox, dict):
            bbox = {
                "x": float(explicit_bbox["x"]),
                "y": float(explicit_bbox["y"]),
                "w": float(explicit_bbox["w"]),
                "h": float(explicit_bbox["h"]),
            }
        else:
            bbox = _slot_bbox(panel, index, panel_counts[panel], panel_layout=panel_layout)
        slot_colors = _dominant_colors(_crop_bbox(reference_image, bbox), limit=5)
        geometry = _geometry_record(slot_id, bbox, width, height, "slot", colors=slot_colors)
        target_px = geometry["target_pixels_exact"]
        generation_min_px = {"width": max(256, round(width * bbox["w"])), "height": max(256, round(height * bbox["h"]))}
        slots.append({
            "id": slot_id,
            "panel_id": panel.lower().replace(" ", "_"),
            "macro_panel": panel,
            "paper_concept": concept,
            "bbox_percent": geometry["bbox_percent"],
            "center_percent": geometry["center_percent"],
            "width_percent": geometry["width_percent"],
            "height_percent": geometry["height_percent"],
            "aspect_ratio": geometry["aspect_ratio_decimal"],
            "aspect_ratio_decimal": geometry["aspect_ratio_decimal"],
            "aspect_ratio_w_h": geometry["aspect_ratio_w_h"],
            "target_canvas_ratio": geometry["aspect_ratio_w_h"],
            "target_pixels": target_px,
            "target_pixels_exact": geometry["target_pixels_exact"],
            "generation_min_pixels": generation_min_px,
            "safe_area_percent": 92,
            "fit_policy": "contain_no_crop",
            "text_policy": "very_small_decorative_text_only; critical labels in pptx",
            "asset_id": f"asset_{slot_id}",
            "target_content_fill_percent": 93,
            "min_content_fill_percent": 85,
            "max_empty_margin_percent": 10,
            "composition_type": composition_type,
            "slot_frame_policy": "frameless_slot",
            "picture_fill_policy": "direct_full_slot_contain_no_tile",
            "blank_space_policy": "full-frame composition; no tiny centered subject; no large blank canvas",
            "reference_dominant_colors": slot_colors,
            "visual_metaphor": str(_spec_value(spec, "visual_metaphor") or "").strip(),
            "must_show": _spec_value(spec, "must_show") if isinstance(_spec_value(spec, "must_show"), list) else [],
            "avoid_showing": _spec_value(spec, "avoid_showing") if isinstance(_spec_value(spec, "avoid_showing"), list) else [],
            "display_label": str(_spec_value(spec, "display_label") or "").strip(),
            "show_slot_caption": bool(_spec_value(spec, "show_slot_caption")),
        })

    panel_geometry = []
    panel_styles = {}
    reference_palette: list[str] = []
    color_tokens: list[dict] = []
    for panel_name, panel_bbox in panel_layout.items():
        panel_id = panel_name.lower().replace(" ", "_")
        panel_crop = _crop_bbox(reference_image, panel_bbox)
        header_bbox = {
            "x": panel_bbox["x"],
            "y": panel_bbox["y"],
            "w": panel_bbox["w"],
            "h": max(0.025, min(panel_bbox["h"], panel_bbox["h"] * 0.16)),
        }
        header_colors = _dominant_colors(_crop_bbox(reference_image, header_bbox), limit=4)
        panel_colors = _dominant_colors(panel_crop, limit=6)
        header_color = (header_colors or panel_colors or ["#4B86C5"])[0]
        fill_color = _lighten(header_color, 0.86)
        stroke_color = header_color
        header_token_id = _append_unique_token(
            color_tokens,
            _color_token(f"{panel_id}_header_001", header_color, f"panel:{panel_id}:header", "header_fill", header_bbox),
        )
        fill_token_id = _append_unique_token(
            color_tokens,
            _color_token(f"{panel_id}_fill_001", fill_color, f"panel:{panel_id}:body", "panel_fill", panel_bbox),
        )
        stroke_token_id = _append_unique_token(
            color_tokens,
            _color_token(f"{panel_id}_stroke_001", stroke_color, f"panel:{panel_id}:border", "panel_stroke", panel_bbox),
        )
        panel_geometry.append(_geometry_record(panel_id, panel_bbox, width, height, "panel", colors=panel_colors))
        panel_styles[panel_id] = {
            "header_color": header_color,
            "fill_color": fill_color,
            "stroke_color": stroke_color,
            "header_token_id": header_token_id,
            "fill_token_id": fill_token_id,
            "stroke_token_id": stroke_token_id,
            "dominant_colors": panel_colors,
        }
        for color in header_colors + panel_colors:
            if color not in reference_palette:
                reference_palette.append(color)
    for slot in slots:
        for color in slot.get("reference_dominant_colors", []):
            if color not in reference_palette:
                reference_palette.append(color)
    reference_palette = _diverse_palette(reference_palette)
    for slot in slots:
        token_ids = []
        for color_index, color in enumerate(slot.get("reference_dominant_colors", [])[:3], start=1):
            token_ids.append(
                _append_unique_token(
                    color_tokens,
                    _color_token(
                        f"{slot['id']}_local_{color_index:03d}",
                        color,
                        f"slot:{slot['id']}",
                        "slot_local_palette",
                        slot["bbox_percent"],
                    ),
                )
            )
        slot["local_color_token_ids"] = token_ids
        slot["reference_color_token_ids"] = token_ids

    objects = _object_candidates(slots, panel_geometry)
    controls = []
    for spec in control_specs:
        control_id = str(_spec_value(spec, "id"))
        explicit_bbox = _spec_value(spec, "bbox_percent")
        if not isinstance(explicit_bbox, dict):
            continue
        bbox = {
            "x": float(explicit_bbox["x"]),
            "y": float(explicit_bbox["y"]),
            "w": float(explicit_bbox["w"]),
            "h": float(explicit_bbox["h"]),
        }
        control_colors = _dominant_colors(_crop_bbox(reference_image, bbox), limit=4)
        control_type = _control_type(control_id, str(_spec_value(spec, "visual_metaphor") or ""))
        source_id, target_id, target_ids = _control_connection(control_id)
        style_color = (control_colors or reference_palette or ["#666666"])[0]
        style_token_id = _append_unique_token(
            color_tokens,
            _color_token(f"{control_id}_stroke_001", style_color, f"control:{control_id}", "arrow_or_connector_stroke", bbox),
        )
        path = _control_path_percent(bbox, control_type)
        control = _control_from_path(
            control_id,
            path,
            width,
            height,
            control_type,
            control_colors,
            style_token_id,
            "explicit_reference_template",
            0.90,
        )
        control.update({
            "source_id": source_id,
            "target_id": target_id,
            "target_ids": target_ids,
            "source": source_id,
            "target": target_id,
            "binding_source": "explicit_template_mapping" if source_id and target_id else "nearest_object_heuristic",
        })
        controls.append(_bind_control_to_objects(control, objects))

    if requested_control_mode != "off" and not controls:
        detected, warnings = _detect_cv_control_candidates(reference_image, width, height)
        control_warnings.extend(warnings)
        for index, candidate in enumerate(detected, start=1):
            bbox = candidate["bbox_percent"]
            colors = _dominant_colors(_crop_bbox(reference_image, bbox), limit=4)
            style_color = (colors or reference_palette or ["#666666"])[0]
            control_id = f"AR{index:02d}"
            style_token_id = _append_unique_token(
                color_tokens,
                _color_token(f"{control_id}_stroke_001", style_color, f"control:{control_id}", "arrow_or_connector_stroke", bbox),
            )
            control = _control_from_path(
                control_id,
                candidate["path_percent"],
                width,
                height,
                "straight_arrow",
                colors,
                style_token_id,
                str(candidate.get("detected_by") or "opencv_hough"),
                float(candidate.get("confidence", 0.62)),
            )
            control["binding_source"] = "nearest_object_heuristic"
            controls.append(_bind_control_to_objects(control, objects))
        if not controls:
            default_token = next((str(item.get("token_id")) for item in color_tokens if item.get("token_id")), "")
            controls = _fallback_panel_flow_controls(panel_geometry, width, height, default_token)
            control_warnings.append("control_candidates_fell_back_to_panel_flow")

    for index, control in enumerate(controls, start=1):
        control["candidate_label"] = control.get("candidate_label") or f"AR{index:02d}"
        control.setdefault("source_anchor", "auto")
        control.setdefault("target_anchor", "auto")
        control.setdefault("editable_in", "pptx")
        control.setdefault("render_policy", "ppt_shape_not_image_asset")

    slot_overlay_path = _draw_slot_overlay(reference_image, slots, panel_geometry, out_path)
    control_overlay_path = _draw_control_overlay(reference_image, controls, out_path)
    if requested_control_mode == "hybrid" and effective_control_mode == "hybrid" and controls:
        controls, vlm_warnings = _call_vlm_control_binding(p, out_path / slot_overlay_path, out_path / control_overlay_path, controls, objects)
        control_warnings.extend(vlm_warnings)
        control_overlay_path = _draw_control_overlay(reference_image, controls, out_path)

    slot_geometry = []
    for slot in slots:
        geometry = _geometry_record(slot["id"], slot["bbox_percent"], width, height, "slot", colors=slot.get("reference_dominant_colors", []))
        geometry["local_color_token_ids"] = slot.get("local_color_token_ids", [])
        geometry["reference_color_token_ids"] = slot.get("reference_color_token_ids", [])
        slot_geometry.append(geometry)
    reference_geometry = {
        "summary": "Precise reference-image geometry used as the source of truth for reference-primary layout, prompts, and PPT placement.",
        "reference_path": str(p),
        "reference_size_px": {"width": width, "height": height},
        "canvas_aspect_ratio_decimal": _round3(width / max(height, 1)),
        "canvas_aspect_ratio_w_h": ratio_string(width, height),
        "layout_strategy": "strict_reference_bbox" if strict_reference_bboxes else "derived_panel_layout",
        "panels": panel_geometry,
        "slots": slot_geometry,
        "controls": controls,
        "control_localizer": {
            "requested_mode": requested_control_mode,
            "effective_mode": effective_control_mode,
            "candidate_count": len(controls),
            "candidate_path": "reference_control_candidates.json",
            "slot_overlay_path": slot_overlay_path,
            "control_overlay_path": control_overlay_path,
            "warnings": control_warnings,
        },
        "panel_styles": panel_styles,
        "reference_palette": reference_palette[:12],
        "color_tokens": color_tokens,
        "geometry_precision": "normalized coordinates and ratios preserve at least three decimals",
    }
    reference_control_candidates = {
        "summary": "AutoFigure-Edit-inspired control candidate boxlib for editable PPT arrows, connectors, loops, and branch routes.",
        "reference_path": str(p),
        "reference_size_px": {"width": width, "height": height},
        "requested_mode": requested_control_mode,
        "effective_mode": effective_control_mode,
        "slot_overlay_path": slot_overlay_path,
        "control_overlay_path": control_overlay_path,
        "candidate_count": len(controls),
        "candidates": controls,
        "object_ids": [str(item.get("id")) for item in objects],
        "warnings": control_warnings,
    }
    reference_controls = {
        "summary": "Reference arrows, connectors, loops, and other non-image controls measured from the reference image for editable PPT rendering.",
        "reference_path": str(p),
        "reference_size_px": {"width": width, "height": height},
        "requested_mode": requested_control_mode,
        "effective_mode": effective_control_mode,
        "candidate_path": "reference_control_candidates.json",
        "slot_overlay_path": slot_overlay_path,
        "control_overlay_path": control_overlay_path,
        "controls": controls,
        "ppt_arrows": controls,
        "render_policy": "ppt_shape_not_image_asset",
    }

    inventory = {
        "summary": "Reference image parameter analysis converted into slot-level layout targets.",
        "reference_path": str(p),
        "slot_source": reference_slot_source,
        "layout_strategy": "strict_reference_bbox" if strict_reference_bboxes else "derived_panel_layout",
        "reference_alignment_priority": "reference_bbox_is_source_of_truth" if strict_reference_bboxes else "paper_slots_with_reference_guidance",
        "reference_size_px": {"width": width, "height": height},
        "canvas_aspect_ratio": round(width / max(height, 1), 4),
        "canvas_aspect_ratio_w_h": ratio_string(width, height),
        "reference_palette": reference_palette[:12],
        "color_tokens": color_tokens,
        "control_localizer": {
            "requested_mode": requested_control_mode,
            "effective_mode": effective_control_mode,
            "candidate_path": "reference_control_candidates.json",
            "slot_overlay_path": slot_overlay_path,
            "control_overlay_path": control_overlay_path,
            "warnings": control_warnings,
        },
        "reference_control_candidates_path": "reference_control_candidates.json",
        "slot_overlay_path": slot_overlay_path,
        "reference_control_overlay_path": control_overlay_path,
        "reference_controls_path": "reference_controls.json",
        "panel_styles": panel_styles,
        "controls": controls,
        "ppt_arrows": controls,
        "ppt_shapes": [],
        "text_regions": [],
        "reference_geometry_path": "reference_geometry.json",
        "panel_layout": {key.lower().replace(" ", "_"): value for key, value in panel_layout.items()},
        "paper_title_guess": paper_brief.get("title_guess"),
        "slot_count": len(slots),
        "slots": slots,
    }
    write_json(Path(out_dir) / "reference_control_candidates.json", reference_control_candidates)
    write_json(Path(out_dir) / "reference_geometry.json", reference_geometry)
    write_json(Path(out_dir) / "reference_controls.json", reference_controls)
    write_json(Path(out_dir) / "slot_inventory.json", inventory)
    return inventory


