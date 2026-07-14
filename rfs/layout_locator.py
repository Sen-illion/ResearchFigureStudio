from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from .utils import ratio_string, write_json


REQUIRED_SLOT_KEYS = {
    "id",
    "paper_concept",
    "bbox_percent",
    "target_canvas_ratio",
    "safe_area_percent",
    "fit_policy",
    "text_policy",
    "asset_id",
    "target_content_fill_percent",
    "min_content_fill_percent",
    "max_empty_margin_percent",
    "composition_type",
    "blank_space_policy",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_bbox(bbox: dict[str, Any]) -> dict[str, float]:
    x = _clamp(float(bbox.get("x", 0.05)))
    y = _clamp(float(bbox.get("y", 0.10)))
    w = _clamp(float(bbox.get("w", 0.08)), 0.02, 0.40)
    h = _clamp(float(bbox.get("h", 0.08)), 0.02, 0.40)
    if x + w > 0.98:
        x = max(0.0, 0.98 - w)
    if y + h > 0.96:
        y = max(0.0, 0.96 - h)
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _clean_panel_bbox(bbox: dict[str, Any]) -> dict[str, float]:
    x = _clamp(float(bbox.get("x", 0.05)))
    y = _clamp(float(bbox.get("y", 0.10)))
    w = _clamp(float(bbox.get("w", 0.2)), 0.03, 0.95)
    h = _clamp(float(bbox.get("h", 0.2)), 0.03, 0.95)
    if x + w > 0.995:
        x = max(0.0, 0.995 - w)
    if y + h > 0.985:
        y = max(0.0, 0.985 - h)
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _slot_from_inventory(slot: dict, bbox: dict | None = None) -> dict:
    merged = dict(slot)
    if bbox is not None:
        clean = _clean_bbox(bbox)
        merged["bbox_percent"] = clean
        ratio = round(clean["w"] / max(clean["h"], 0.001), 3)
        merged["center_percent"] = {"x": round(clean["x"] + clean["w"] / 2, 4), "y": round(clean["y"] + clean["h"] / 2, 4)}
        merged["width_percent"] = round(clean["w"], 4)
        merged["height_percent"] = round(clean["h"], 4)
        merged["aspect_ratio"] = ratio
        merged["aspect_ratio_decimal"] = ratio
        merged["aspect_ratio_w_h"] = ratio_string(clean["w"], clean["h"])
        merged["target_canvas_ratio"] = ratio_string(clean["w"], clean["h"])
    merged["fit_policy"] = "contain_no_crop"
    merged["safe_area_percent"] = int(merged.get("safe_area_percent", 92))
    merged["target_content_fill_percent"] = int(merged.get("target_content_fill_percent", 93))
    merged["min_content_fill_percent"] = int(merged.get("min_content_fill_percent", 85))
    merged["max_empty_margin_percent"] = int(merged.get("max_empty_margin_percent", 10))
    merged["text_policy"] = merged.get("text_policy") or "very_small_decorative_text_only; critical labels in pptx"
    merged["blank_space_policy"] = merged.get("blank_space_policy") or "full-frame composition; no tiny centered subject"
    merged["slot_frame_policy"] = merged.get("slot_frame_policy") or "frameless_slot"
    merged["picture_fill_policy"] = merged.get("picture_fill_policy") or "direct_full_slot_contain_no_tile"
    return merged


def _heuristic_layout(inventory: dict) -> dict:
    panels: dict[str, dict] = {}
    explicit_panel_layout = inventory.get("panel_layout") if isinstance(inventory.get("panel_layout"), dict) else {}
    for slot in inventory["slots"]:
        panel = slot["macro_panel"]
        panel_id = slot["panel_id"]
        bbox = slot["bbox_percent"]
        if panel_id in explicit_panel_layout and isinstance(explicit_panel_layout[panel_id], dict):
            panels[panel_id] = {
                "x1": explicit_panel_layout[panel_id]["x"],
                "y1": explicit_panel_layout[panel_id]["y"],
                "x2": explicit_panel_layout[panel_id]["x"] + explicit_panel_layout[panel_id]["w"],
                "y2": explicit_panel_layout[panel_id]["y"] + explicit_panel_layout[panel_id]["h"],
                "title": panel,
                "explicit": True,
            }
        elif panel_id not in panels:
            panels[panel_id] = {"x1": bbox["x"], "y1": bbox["y"], "x2": bbox["x"] + bbox["w"], "y2": bbox["y"] + bbox["h"], "title": panel}
        else:
            panels[panel_id]["x1"] = min(panels[panel_id]["x1"], bbox["x"])
            panels[panel_id]["y1"] = min(panels[panel_id]["y1"], bbox["y"])
            panels[panel_id]["x2"] = max(panels[panel_id]["x2"], bbox["x"] + bbox["w"])
            panels[panel_id]["y2"] = max(panels[panel_id]["y2"], bbox["y"] + bbox["h"])
    panel_items = []
    for panel_id, raw in panels.items():
        if raw.get("explicit"):
            bbox = _clean_panel_bbox({"x": raw["x1"], "y": raw["y1"], "w": raw["x2"] - raw["x1"], "h": raw["y2"] - raw["y1"]})
        else:
            pad_x, pad_y = 0.025, 0.065
            bbox = _clean_panel_bbox({
                "x": raw["x1"] - pad_x,
                "y": raw["y1"] - pad_y,
                "w": raw["x2"] - raw["x1"] + pad_x * 2,
                "h": raw["y2"] - raw["y1"] + pad_y * 1.7,
            })
        panel_items.append({"id": panel_id, "title": raw["title"], "bbox_percent": bbox, "editable_in": "pptx"})
    return {
        "summary": "Heuristic layout plan generated by the self-owned locator fallback.",
        "locator_mode": "heuristic",
        "control_localizer": inventory.get("control_localizer"),
        "reference_path": inventory.get("reference_path"),
        "panels": sorted(panel_items, key=lambda item: (item["bbox_percent"]["y"], item["bbox_percent"]["x"])),
        "slots": [_slot_from_inventory(slot) for slot in inventory["slots"]],
        "arrows": inventory.get("controls") or inventory.get("ppt_arrows") or _default_arrows(panel_items),
        "control_shapes": inventory.get("controls") or [],
        "ppt_shapes": inventory.get("ppt_shapes") or [],
        "text_regions": inventory.get("text_regions") or [],
        "layer_order": [slot["id"] for slot in inventory["slots"]],
    }


def _default_arrows(panels: list[dict]) -> list[dict]:
    top = [p for p in panels if p["id"] not in {"shared_resource_library", "legend"}]
    top = sorted(top, key=lambda p: p["bbox_percent"]["x"])
    arrows = []
    for index in range(len(top) - 1):
        arrows.append({
            "id": f"main_flow_{index+1}",
            "source": top[index]["id"],
            "target": top[index + 1]["id"],
            "type": "straight",
            "path_percent": [],
            "label": "",
            "editable_in": "pptx",
        })
    if any(p["id"] == "shared_resource_library" for p in panels):
        arrows.append({
            "id": "resource_bus",
            "source": "shared_resource_library",
            "target": "top_pipeline",
            "type": "custom_bus",
            "path_percent": [],
            "label": "shared resources",
            "editable_in": "pptx",
        })
    return arrows


def _reference_primary_panel_titles(plan: dict) -> None:
    titles = {
        "virtual_interview_setup": "1. Virtual Interview Setup",
        "raw_video_collection": "2. Raw Video",
        "preprocessing_modules": "3. Preprocessing Modules",
        "timestamp_alignment": "4. Timestamp Alignment",
        "five_modalities": "5. Five Modalities",
        "neo-ffi-3_self-report_labels": "6. NEO-FFI-3 Self-report Labels",
        "neo_ffi_3_self_report_labels": "6. NEO-FFI-3 Self-report Labels",
        "multimodal_personality_dataset": "7. Multimodal Personality Dataset",
        "legend": "Legend",
    }
    for panel in plan.get("panels", []):
        panel_id = str(panel.get("id", ""))
        if panel_id in titles:
            panel["title"] = titles[panel_id]


def _personality_reference_arrows() -> list[dict]:
    pairs = [
        ("setup_virtual_interviewer", "raw_video_file"),
        ("setup_camera_full_body", "raw_clip_grid"),
        ("raw_video_file", "ffmpeg_video_to_audio"),
        ("raw_video_file", "funasr_speech_recognition"),
        ("raw_clip_grid", "mtcnn_face_detection"),
        ("raw_clip_grid", "alphapose_skeleton_extraction"),
        ("raw_clip_grid", "frame_sampling_stack"),
        ("ffmpeg_video_to_audio", "audio_waveform_stream"),
        ("funasr_speech_recognition", "spoken_text_timestamps"),
        ("mtcnn_face_detection", "face_clip_sequence"),
        ("alphapose_skeleton_extraction", "pose_skeleton_stream"),
        ("frame_sampling_stack", "sampled_video_frames"),
        ("audio_waveform_stream", "timestamp_clock"),
        ("spoken_text_timestamps", "timestamp_clock"),
        ("face_clip_sequence", "timestamp_clock"),
        ("pose_skeleton_stream", "timestamp_clock"),
        ("sampled_video_frames", "timestamp_clock"),
        ("timestamp_clock", "five_modalities"),
        ("five_modalities", "neo-ffi-3_self-report_labels"),
        ("neo-ffi-3_self-report_labels", "dataset_database"),
    ]
    return [
        {
            "id": f"reference_flow_{index+1:02d}",
            "source": source,
            "target": target,
            "type": "straight",
            "path_percent": [],
            "label": "",
            "editable_in": "pptx",
        }
        for index, (source, target) in enumerate(pairs)
    ]


def _autofigure_reference_arrows() -> list[dict]:
    pairs = [
        ("input_text_stack", "input_to_vlm_arrow_symbol"),
        ("input_to_vlm_arrow_symbol", "vlm_agent_robot"),
        ("vlm_agent_robot", "entities_bubble"),
        ("vlm_agent_robot", "relations_bubble"),
        ("vlm_agent_robot", "vlm_to_blueprint_down_arrow"),
        ("vlm_to_blueprint_down_arrow", "initial_blueprint_code_card"),
        ("initial_blueprint_code_card", "blueprint_graph_connector"),
        ("blueprint_graph_connector", "blueprint_node_a"),
        ("blueprint_graph_connector", "blueprint_node_b"),
        ("stage_transition_arrow_1", "ai_designer_robot"),
        ("critique_banner", "feedback_bubble"),
        ("feedback_bubble", "ai_critic_robot"),
        ("ai_critic_robot", "score_comparison_card"),
        ("score_comparison_card", "ai_designer_robot"),
        ("ai_designer_robot", "update_banner"),
        ("update_banner", "stage_transition_arrow_2"),
        ("synthesis_magic_wand", "raw_image_card"),
        ("synthesis_palette", "raw_image_card"),
        ("raw_image_card", "erase_text_tool"),
        ("raw_image_card", "ocr_verify_magnifier"),
        ("erase_text_tool", "final_autofigure_card"),
        ("ocr_verify_magnifier", "final_autofigure_card"),
        ("final_autofigure_card", "green_quality_badge"),
    ]
    arrows = [
        {
            "id": f"autofigure_flow_{index+1:02d}",
            "source": source,
            "target": target,
            "type": "straight",
            "path_percent": [],
            "label": "",
            "editable_in": "pptx",
        }
        for index, (source, target) in enumerate(pairs)
    ]
    arrows.extend([
        {
            "id": "autofigure_stage_i_to_ii",
            "source": "stage_transition_arrow_1",
            "target": "critique_banner",
            "type": "straight",
            "path_percent": [],
            "label": "",
            "editable_in": "pptx",
        },
        {
            "id": "autofigure_stage_ii_to_iii",
            "source": "stage_transition_arrow_2",
            "target": "synthesis_magic_wand",
            "type": "straight",
            "path_percent": [],
            "label": "",
            "editable_in": "pptx",
        },
    ])
    return arrows


def _extract_json(text: str) -> dict:
    cleaned = text.strip().replace("```json", "```")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_vlm_locator(reference_path: str | Path, inventory: dict, style: dict, model: str | None = None) -> dict:
    api_base = os.getenv("API_BASE", "").rstrip("/")
    api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
    model_name = model or os.getenv("RFS_LOCATOR_MODEL") or os.getenv("MODEL_VLM") or "gemini-3-pro-preview-thinking"
    if not api_base or not api_key:
        raise RuntimeError("VLM locator requires API_BASE and API_KEY/GEMINI_API_KEY environment variables")

    ref = Path(reference_path)
    b64 = base64.b64encode(ref.read_bytes()).decode("utf-8")
    slots_brief = [
        {
            "id": slot["id"],
            "macro_panel": slot["macro_panel"],
            "paper_concept": slot["paper_concept"],
            "composition_type": slot["composition_type"],
        }
        for slot in inventory["slots"]
    ]
    prompt = f"""
You are a layout locator for editable scientific PowerPoint figures.

Task: inspect the provided reference image and place the given slot list onto it.
Only output JSON. Do not output Python, SVG, markdown, or explanations.

Important constraints:
- You only decide layout coordinates, arrow routes, z order, and panel grouping.
- Scientific content and generated images are produced by another system.
- Use bbox_percent values in normalized coordinates: x,y,w,h in [0,1].
- Use 25-50 slots; keep all slots from the input list.
- Preserve the reference image's main flow direction, macro panel positions, resource library position, branch layout, and visual density.
- Labels, formulas, arrows, panels, and groups must be editable in pptx.
- Fit policy must be contain_no_crop for every image slot.

Return schema:
{{
  "summary": "...",
  "locator_mode": "vlm",
  "panels": [{{"id":"...","title":"...","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"editable_in":"pptx"}}],
  "slots": [{{"id":"input slot id","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"z_index":20}}],
  "arrows": [{{"id":"...","source":"slot or panel id","target":"slot or panel id","type":"straight|elbow|custom_bus","path_percent":[[0.1,0.2],[0.3,0.2]],"label":"","editable_in":"pptx"}}],
  "layer_order": ["slot id", "slot id"]
}}

Slot list:
{json.dumps(slots_brief, ensure_ascii=False)}

Style constraints:
{json.dumps(style, ensure_ascii=False)}
""".strip()

    payload = {
        "model": model_name,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "temperature": 0.1,
    }
    response = requests.post(f"{api_base}/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, data=json.dumps(payload), timeout=180)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _extract_json(content)


def _merge_locator_output(raw_plan: dict, inventory: dict) -> dict:
    by_id = {slot["id"]: slot for slot in inventory["slots"]}
    raw_slots = {slot.get("id"): slot for slot in raw_plan.get("slots", []) if isinstance(slot, dict)}
    strict_reference_bboxes = inventory.get("layout_strategy") == "strict_reference_bbox"
    slots = []
    for slot_id, base in by_id.items():
        raw = raw_slots.get(slot_id, {})
        bbox = None if strict_reference_bboxes else (raw.get("bbox_percent") if isinstance(raw.get("bbox_percent"), dict) else None)
        merged = _slot_from_inventory(base, bbox=bbox)
        merged["z_index"] = int(raw.get("z_index", 20)) if isinstance(raw, dict) else 20
        slots.append(merged)

    panels = []
    if not strict_reference_bboxes:
        for panel in raw_plan.get("panels", []):
            if not isinstance(panel, dict) or not panel.get("id") or not isinstance(panel.get("bbox_percent"), dict):
                continue
            panels.append({
                "id": str(panel["id"]),
                "title": str(panel.get("title") or panel["id"]).replace("_", " ").title(),
                "bbox_percent": _clean_panel_bbox(panel["bbox_percent"]),
                "editable_in": "pptx",
            })
    if not panels:
        panels = _heuristic_layout(inventory)["panels"]

    arrows = []
    for arrow in raw_plan.get("arrows", []):
        if not isinstance(arrow, dict):
            continue
        arrows.append({
            "id": str(arrow.get("id") or f"arrow_{len(arrows)+1}"),
            "source": str(arrow.get("source", "")),
            "target": str(arrow.get("target", "")),
            "type": str(arrow.get("type") or "straight"),
            "path_percent": arrow.get("path_percent", []) if isinstance(arrow.get("path_percent", []), list) else [],
            "label": str(arrow.get("label", "")),
            "editable_in": "pptx",
        })
    if inventory.get("controls"):
        arrows = inventory.get("controls") or []
    elif not arrows:
        arrows = _default_arrows(panels)

    return {
        "summary": raw_plan.get("summary") or "VLM layout locator output normalized into a valid layout plan.",
        "locator_mode": raw_plan.get("locator_mode") or "vlm",
        "control_localizer": inventory.get("control_localizer"),
        "reference_path": inventory.get("reference_path"),
        "panels": panels,
        "slots": slots,
        "arrows": arrows,
        "control_shapes": inventory.get("controls") or [],
        "ppt_shapes": inventory.get("ppt_shapes") or [],
        "text_regions": inventory.get("text_regions") or [],
        "layer_order": [slot["id"] for slot in slots],
    }


def locate_layout(reference_path: str | Path, inventory: dict, style: dict, out_dir: str | Path, mode: str = "heuristic", model: str | None = None) -> dict:
    if inventory.get("layout_strategy") == "strict_reference_bbox":
        plan = _heuristic_layout(inventory)
        plan["summary"] = "Strict reference-primary layout plan generated from explicit reference-image bboxes; VLM/PPT code cannot override slot positions."
        plan["locator_mode"] = "strict_reference_bbox"
        plan["layout_strategy"] = "strict_reference_bbox"
        _reference_primary_panel_titles(plan)
        if not inventory.get("controls") and "personality" in " ".join(str(slot.get("paper_concept", "")).lower() for slot in inventory.get("slots", [])):
            plan["arrows"] = _personality_reference_arrows()
        if not inventory.get("controls") and any(str(slot.get("id", "")) == "vlm_agent_robot" for slot in inventory.get("slots", [])):
            plan["arrows"] = _autofigure_reference_arrows()
    elif mode == "heuristic":
        plan = _heuristic_layout(inventory)
    elif mode == "vlm":
        raw_plan = _call_vlm_locator(reference_path, inventory, style, model=model)
        plan = _merge_locator_output(raw_plan, inventory)
    else:
        raise ValueError(f"Unsupported locator mode: {mode}")
    write_json(Path(out_dir) / "layout_plan.json", plan)
    return plan
