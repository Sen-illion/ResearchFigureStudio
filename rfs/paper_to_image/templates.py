from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ..utils import ensure_dir, write_json
from ..vlm_client import call_vlm_json, resolve_vlm_model, vlm_credentials_available


BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "arbor": {
        "summary": "Tree-centered iterative research template.",
        "template_id": "arbor",
        "name": "Arbor tree-loop",
        "aspect_ratio": 1.87,
        "topology": ["tree", "loop", "feedback", "side_inputs", "side_outputs", "top_phase_ribbon"],
        "ideal_module_range": [6, 16],
        "visual_density": "very_high",
        "panels": [
            {"id": "phase_ribbon", "role": "phase_ribbon", "bbox_percent": {"x": 0.13, "y": 0.03, "w": 0.84, "h": 0.14}},
            {"id": "left_inputs", "role": "inputs", "bbox_percent": {"x": 0.02, "y": 0.25, "w": 0.14, "h": 0.55}},
            {"id": "central_tree", "role": "core_method", "bbox_percent": {"x": 0.21, "y": 0.22, "w": 0.61, "h": 0.56}},
            {"id": "right_outputs", "role": "outputs", "bbox_percent": {"x": 0.85, "y": 0.34, "w": 0.13, "h": 0.42}},
            {"id": "bottom_executors", "role": "execution", "bbox_percent": {"x": 0.32, "y": 0.83, "w": 0.43, "h": 0.13}},
        ],
        "connectors": ["large_clockwise_loop", "tree_branches", "left_to_center", "center_to_right"],
        "style": {"background": "white", "panel_fill": "paper_tint", "stroke": "muted_blue", "accent": ["green", "blue", "red"], "corners": "rounded", "shadow": "minimal"},
    },
    "linear": {
        "summary": "Ultra-wide sequential research workflow template.",
        "template_id": "linear",
        "name": "Ultra-wide linear stages",
        "aspect_ratio": 4.366,
        "topology": ["linear", "four_to_six_stages", "local_feedback_loops"],
        "ideal_module_range": [4, 8],
        "visual_density": "high",
        "panels": [
            {"id": "stage_1", "role": "input_problem", "bbox_percent": {"x": 0.01, "y": 0.08, "w": 0.18, "h": 0.82}},
            {"id": "stage_2", "role": "knowledge", "bbox_percent": {"x": 0.20, "y": 0.08, "w": 0.24, "h": 0.82}},
            {"id": "stage_3", "role": "core_method", "bbox_percent": {"x": 0.45, "y": 0.08, "w": 0.27, "h": 0.82}},
            {"id": "stage_4", "role": "output", "bbox_percent": {"x": 0.73, "y": 0.08, "w": 0.26, "h": 0.82}},
        ],
        "connectors": ["left_to_right", "small_feedback_loops"],
        "style": {"background": "white", "panel_fill": "soft_pastel", "stroke": "dark_gray", "accent": ["blue", "yellow"], "corners": "slightly_rounded", "shadow": "soft_cards"},
    },
    "tripanel": {
        "summary": "Three-panel multimodal indexing and retrieval template.",
        "template_id": "tripanel",
        "name": "Three-panel retrieval pipeline",
        "aspect_ratio": 2.903,
        "topology": ["three_panels", "data_to_index_to_query", "parallel_channels"],
        "ideal_module_range": [5, 12],
        "visual_density": "high",
        "panels": [
            {"id": "panel_a", "role": "data_sources", "bbox_percent": {"x": 0.02, "y": 0.05, "w": 0.16, "h": 0.84}},
            {"id": "panel_b", "role": "indexing", "bbox_percent": {"x": 0.20, "y": 0.05, "w": 0.45, "h": 0.84}},
            {"id": "panel_c", "role": "query_and_output", "bbox_percent": {"x": 0.67, "y": 0.05, "w": 0.31, "h": 0.84}},
        ],
        "connectors": ["left_to_right", "parallel_modalities", "retrieval_merge"],
        "style": {"background": "white", "panel_fill": "near_white", "stroke": "dashed_colored", "accent": ["blue", "peach", "purple"], "corners": "rounded", "shadow": "none"},
    },
    "dense-multimodal": {
        "summary": "Dense multimodal parsing, grounding, retrieval, and response template.",
        "template_id": "dense-multimodal",
        "name": "Dense multimodal system",
        "aspect_ratio": 2.3,
        "topology": ["multi_input", "dense_panels", "knowledge_graph", "retrieval", "response"],
        "ideal_module_range": [9, 20],
        "visual_density": "very_high",
        "panels": [
            {"id": "inputs", "role": "multi_source_inputs", "bbox_percent": {"x": 0.01, "y": 0.06, "w": 0.07, "h": 0.86}},
            {"id": "parsing", "role": "content_parsing", "bbox_percent": {"x": 0.09, "y": 0.05, "w": 0.24, "h": 0.87}},
            {"id": "grounding", "role": "knowledge_grounding", "bbox_percent": {"x": 0.34, "y": 0.05, "w": 0.48, "h": 0.87}},
            {"id": "query", "role": "query_retrieval_response", "bbox_percent": {"x": 0.83, "y": 0.05, "w": 0.16, "h": 0.87}},
        ],
        "connectors": ["left_to_right", "parallel_processing", "merge", "query_response"],
        "style": {"background": "white", "panel_fill": "transparent", "stroke": "hand_drawn_dashed_blue", "accent": ["pastel_blue", "peach", "mint", "lavender"], "corners": "rounded", "shadow": "none"},
    },
}


def _dominant_colors(path: Path, count: int = 6) -> list[str]:
    with Image.open(path) as image:
        thumb = image.convert("RGB").resize((96, 96)).quantize(colors=count).convert("RGB")
        colors = sorted(thumb.getcolors(96 * 96) or [], reverse=True)
    return [f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}" for _amount, rgb in colors[:count]]


def _classify_by_ratio(ratio: float) -> str:
    if ratio >= 3.5:
        return "linear"
    if ratio >= 2.55:
        return "tripanel"
    if ratio >= 2.05:
        return "dense-multimodal"
    return "arbor"


def _vlm_template_analysis(path: Path, base: dict, model: str | None) -> dict:
    prompt = f"""
# Summary

Analyze this scientific framework figure only as a reusable architecture and style template. Return JSON only. Do not summarize its scientific content for reuse.

Base archetype:
{json.dumps(base, ensure_ascii=False, indent=2)}

Return:
{{
  "summary": "Reference template analysis.",
  "macro_structure": [],
  "reading_order": [],
  "connector_rhythm": [],
  "visual_focus": [],
  "typography": {{"hierarchy": [], "density": "..."}},
  "style_adjustments": {{}},
  "forbidden_copy_terms": ["all visible paper-specific terms, method names, dataset names, captions, and branded labels found in the image"],
  "forbidden_copy_objects": ["paper-specific logos or uniquely identifying objects"]
}}
""".strip()
    resolved = resolve_vlm_model("RFS_TEMPLATE_ANALYZER_MODEL", "RFS_PAPER_TO_IMAGE_MODEL", explicit_model=model)
    result = call_vlm_json(prompt, [path], model=resolved, timeout=180, retries=1)
    result.setdefault("summary", "Reference template analysis.")
    result["model"] = resolved
    return result


def build_template_profiles(reference_paths: list[str], out_dir: str | Path, mode: str = "vlm", model: str | None = None) -> list[dict]:
    out = ensure_dir(out_dir)
    profiles = []
    for index, value in enumerate(reference_paths):
        path = Path(value).resolve()
        with Image.open(path) as image:
            width, height = image.size
        ratio = width / max(height, 1)
        archetype = _classify_by_ratio(ratio)
        base = json.loads(json.dumps(BUILTIN_TEMPLATES[archetype]))
        profile = {
            **base,
            "summary": "Content-free reference template profile.",
            "profile_id": f"reference_{index + 1:02d}_{archetype}",
            "source_reference": str(path),
            "source_pixels": {"width": width, "height": height},
            "source_aspect_ratio": round(ratio, 6),
            "palette": _dominant_colors(path),
            "analysis_mode": "heuristic",
            "forbidden_copy_terms": [],
            "forbidden_copy_objects": [],
        }
        if mode == "vlm" and vlm_credentials_available():
            try:
                analysis = _vlm_template_analysis(path, base, model)
                profile.update({key: value for key, value in analysis.items() if key not in {"summary"}})
                profile["analysis_mode"] = "vlm"
            except Exception as exc:
                profile["analysis_warning"] = str(exc)
        write_json(out / f"{profile['profile_id']}.json", profile)
        profiles.append(profile)
    if not profiles:
        for archetype, base in BUILTIN_TEMPLATES.items():
            profile = {**json.loads(json.dumps(base)), "profile_id": f"builtin_{archetype}", "source_reference": None, "source_aspect_ratio": base["aspect_ratio"], "palette": [], "analysis_mode": "builtin", "forbidden_copy_terms": [], "forbidden_copy_objects": []}
            write_json(out / f"{profile['profile_id']}.json", profile)
            profiles.append(profile)
    return profiles


def _paper_features(review: dict) -> dict:
    statements = " ".join(str(item.get("statement", "")) for field in ["research_questions", "central_claims", "modules", "relations", "innovations"] for item in review.get(field, [])).lower()
    relation_types = {str(item.get("relation_type") or item.get("type") or "").lower() for item in review.get("relations", [])}
    workflow = review.get("workflows", {})
    return {
        "module_count": len(review.get("modules", [])),
        "input_count": len(review.get("inputs", [])),
        "has_loop": bool(workflow.get("feedback")) or "feedback" in relation_types or any(token in statements for token in ["iterative", "loop", "tree search", "backpropagate"]),
        "has_tree": any(token in statements for token in ["tree", "branch", "prune", "search"]),
        "has_multimodal": any(token in statements for token in ["multimodal", "multi-modal", "image", "video", "audio", "document"]),
        "has_retrieval": any(token in statements for token in ["retrieval", "retrieve", "index", "rag", "knowledge graph"]),
    }


def select_template(profiles: list[dict], review: dict, requested: str = "auto", target_ratio: str = "auto") -> dict:
    if requested != "auto":
        matches = [profile for profile in profiles if profile.get("template_id") == requested or profile.get("profile_id") == requested]
        if not matches:
            builtin = BUILTIN_TEMPLATES.get(requested)
            if not builtin:
                raise ValueError(f"Requested template not found: {requested}")
            matches = [{**json.loads(json.dumps(builtin)), "profile_id": f"builtin_{requested}", "source_reference": None, "source_aspect_ratio": builtin["aspect_ratio"], "palette": [], "analysis_mode": "builtin", "forbidden_copy_terms": [], "forbidden_copy_objects": []}]
        selected = dict(matches[0])
        selected["selection"] = {"mode": "explicit", "score": 1.0, "reasons": ["explicit CLI selection"]}
        return selected
    features = _paper_features(review)
    requested_ratio = None
    if target_ratio != "auto":
        try:
            left, right = target_ratio.split(":", 1)
            requested_ratio = float(left) / float(right)
        except Exception:
            requested_ratio = None
    scored = []
    for profile in profiles:
        template_id = profile["template_id"]
        low, high = profile.get("ideal_module_range", [1, 99])
        module_fit = 1.0 if low <= features["module_count"] <= high else max(0.0, 1.0 - min(abs(features["module_count"] - low), abs(features["module_count"] - high)) / 10)
        topology = 0.0
        reasons = [f"module_fit={module_fit:.2f}"]
        if template_id == "arbor" and (features["has_loop"] or features["has_tree"]):
            topology += 1.0; reasons.append("loop/tree topology")
        if template_id == "linear" and not features["has_loop"] and 4 <= features["module_count"] <= 8:
            topology += 0.9; reasons.append("sequential stage count")
        if template_id == "tripanel" and features["has_retrieval"]:
            topology += 0.9; reasons.append("index/retrieval topology")
        if template_id == "dense-multimodal" and features["has_multimodal"] and features["module_count"] >= 8:
            topology += 1.0; reasons.append("dense multimodal topology")
        ratio_score = 0.5
        if requested_ratio:
            ratio_score = max(0.0, 1.0 - abs(float(profile.get("source_aspect_ratio") or profile["aspect_ratio"]) - requested_ratio) / max(requested_ratio, 0.1))
        score = 0.45 * module_fit + 0.40 * min(topology, 1.0) + 0.15 * ratio_score
        scored.append((score, profile, reasons + [f"ratio_fit={ratio_score:.2f}"]))
    score, profile, reasons = max(scored, key=lambda item: item[0])
    selected = dict(profile)
    selected["selection"] = {"mode": "automatic", "score": round(score, 4), "reasons": reasons, "paper_features": features}
    return selected


def _canvas_size(profile: dict, target_ratio: str) -> tuple[int, int, float]:
    ratio = float(profile.get("source_aspect_ratio") or profile.get("aspect_ratio") or 16 / 9)
    if target_ratio != "auto":
        try:
            left, right = target_ratio.split(":", 1)
            ratio = float(left) / float(right)
        except Exception:
            pass
    if ratio >= 1:
        width = 1536
        height = max(512, round(width / ratio))
    else:
        height = 1536
        width = max(512, round(height * ratio))
    return width, height, ratio


def render_layout_blueprint(profile: dict, out_path: str | Path, target_ratio: str = "auto") -> dict:
    width, height, ratio = _canvas_size(profile, target_ratio)
    image = Image.new("RGB", (width, height), (250, 250, 249))
    draw = ImageDraw.Draw(image)
    panels = profile.get("panels", [])
    centers = []
    for index, panel in enumerate(panels):
        bbox = panel["bbox_percent"]
        x0, y0 = int(bbox["x"] * width), int(bbox["y"] * height)
        x1, y1 = int((bbox["x"] + bbox["w"]) * width), int((bbox["y"] + bbox["h"]) * height)
        fill = (241 + (index % 2) * 4, 246, 247 - (index % 3) * 2)
        dash = profile["template_id"] in {"tripanel", "dense-multimodal"}
        if dash:
            segment = max(8, round(width * 0.006))
            for x in range(x0, x1, segment * 2):
                draw.line((x, y0, min(x + segment, x1), y0), fill=(104, 132, 151), width=3)
                draw.line((x, y1, min(x + segment, x1), y1), fill=(104, 132, 151), width=3)
            for y in range(y0, y1, segment * 2):
                draw.line((x0, y, x0, min(y + segment, y1)), fill=(104, 132, 151), width=3)
                draw.line((x1, y, x1, min(y + segment, y1)), fill=(104, 132, 151), width=3)
            draw.rectangle((x0 + 4, y0 + 4, x1 - 4, y1 - 4), fill=fill)
        else:
            draw.rounded_rectangle((x0, y0, x1, y1), radius=max(10, round(height * 0.025)), fill=fill, outline=(104, 132, 151), width=3)
        centers.append(((x0 + x1) // 2, (y0 + y1) // 2))
        slots = max(2, min(6, round((x1 - x0) / max(width * 0.12, 1))))
        for slot_index in range(slots):
            sx0 = x0 + int((slot_index + 0.2) / slots * (x1 - x0))
            sx1 = x0 + int((slot_index + 0.8) / slots * (x1 - x0))
            sy0 = y0 + int(0.28 * (y1 - y0))
            sy1 = y0 + int(0.70 * (y1 - y0))
            draw.rounded_rectangle((sx0, sy0, sx1, sy1), radius=8, outline=(178, 190, 198), width=2)
    for index in range(len(centers) - 1):
        start = centers[index]
        end = centers[index + 1]
        draw.line((start, end), fill=(80, 111, 134), width=4)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        arrow = 12
        points = [end, (end[0] - arrow * math.cos(angle - 0.45), end[1] - arrow * math.sin(angle - 0.45)), (end[0] - arrow * math.cos(angle + 0.45), end[1] - arrow * math.sin(angle + 0.45))]
        draw.polygon(points, fill=(80, 111, 134))
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return {"summary": "Content-free layout blueprint rendered from selected template.", "path": str(path), "width": width, "height": height, "aspect_ratio_decimal": round(ratio, 6), "template_id": profile["template_id"], "contains_reference_text": False, "contains_reference_objects": False}
