from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .vlm_client import call_vlm_json, resolve_vlm_model, vlm_credentials_available


def _brief_slots(slots: list[dict]) -> list[dict]:
    return [{
        "id": item.get("id"),
        "bbox_percent": item.get("bbox_percent"),
        "paper_concept": item.get("paper_concept"),
        "display_label": item.get("display_label"),
        "semantic_role": item.get("semantic_role"),
        "asset_type": item.get("asset_type"),
    } for item in slots]


def _brief_panels(panels: list[dict]) -> list[dict]:
    return [{
        "id": item.get("id"),
        "title": item.get("title"),
        "bbox_percent": item.get("bbox_percent"),
    } for item in panels]


def _brief_controls(controls: list[dict]) -> list[dict]:
    return [{
        "id": item.get("id"),
        "source_id": item.get("source_id") or item.get("source"),
        "target_id": item.get("target_id") or item.get("target"),
        "control_kind": item.get("control_kind"),
        "path_percent": item.get("path_percent"),
        "arrowhead_direction": item.get("arrowhead_direction"),
        "stroke_color": item.get("stroke_color"),
        "stroke_width_pt": item.get("stroke_width_pt"),
        "dash_style": item.get("dash_style") or item.get("line_pattern"),
        "confidence": item.get("confidence"),
    } for item in controls]


def vlm_layout_adapter(reference_path: str | Path, base_layout: dict) -> dict:
    model = resolve_vlm_model("RFS_REBUILD_LAYOUT_MODEL", "RFS_LOCATOR_MODEL")
    prompt = f"""
You are reconstructing a diagram image as editable PowerPoint objects.
Inspect the reference image and improve the detected layout.
Only output JSON. Do not include markdown or explanations.

Use normalized bbox_percent coordinates in [0,1].
Prefer structural regions that should become editable PPT objects:
- panels: large stage/section containers
- cards: smaller editable boxes inside panels
- slots: non-text visual assets such as icons, illustrations, screenshots, tools, characters, charts
- legend_regions: legend markers or legend label areas

Rules:
- Do not create a slot for pure text, arrows, or panel borders.
- Keep ids short, stable, lowercase snake_case.
- Each slot must include id, asset_id, bbox_percent, prompt_subject if recognizable, and panel_id if inside a panel.
- Include confidence in 0..1.

Return schema:
{{
  "summary": "...",
  "confidence": 0.0,
  "panels": [{{"id":"stage_1","title":"...","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"confidence":0.0}}],
  "cards": [{{"id":"card_1","title":"...","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"panel_id":"stage_1","confidence":0.0}}],
  "slots": [{{"id":"slot_1","asset_id":"slot_1","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"panel_id":"stage_1","prompt_subject":"...","confidence":0.0}}],
  "legend_regions": [{{"id":"legend_1","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"confidence":0.0}}]
}}

Heuristic base layout:
{json.dumps(base_layout, ensure_ascii=False)}
""".strip()
    result = call_vlm_json(prompt, [reference_path], model=model)
    result["_vlm_model"] = model
    return result


def vlm_control_adapter_factory(out_dir: str | Path) -> Callable[[str | Path, list[dict], list[dict]], dict]:
    out = Path(out_dir)

    def adapter(reference_path: str | Path, slots: list[dict], heuristic_controls: list[dict]) -> dict:
        model = resolve_vlm_model("RFS_REBUILD_CONTROL_MODEL", "RFS_CONTROL_LOCALIZER_MODEL", "RFS_LOCATOR_MODEL")
        image_paths = [reference_path]
        for overlay in [out / "reference_geometry_overlay.png", out / "reference_controls_candidates_overlay.png"]:
            if overlay.exists():
                image_paths.append(overlay)
        prompt = f"""
You are binding and refining editable PPT arrows/connectors for a diagram.
Image 1 is the original reference. Additional images may show detected layout/control overlays.
Only output JSON. Do not include markdown or explanations.

Rules:
- Preserve arrow position, direction, path shape, line width, color, and dashed/solid style from the reference.
- Use only source_id and target_id from the slot list.
- Keep path_percent as normalized [x,y] points in [0,1].
- If a line is curved, approximate with 3-6 path points.
- If source/target is uncertain, choose the most plausible objects based on arrow direction and layout.
- Also choose editable render intent when visible: render_style can be filled_block_arrow, line_connector, elbow_connector, branch_line_connector, or dashed_loop_connector.
- Use route_intent straight for normal arrows, orthogonal for turning arrows, branch for one-to-many connectors, and loop for dashed feedback loops.
- Use visual_weight chunky for short thick/block arrows, normal for ordinary arrows, and thin for subtle helper connectors.
- Use preferred_axis/bend_side only as coarse routing hints; code will compute final PPT geometry from source/target boxes.
- path_percent is a reference-path hint for auditing/routing, not the sole final geometry authority.

Return schema:
{{
  "summary": "...",
  "arrows": [
    {{"id":"arrow_1","source_id":"slot_a","target_id":"slot_b","target_ids":["slot_b"],"control_kind":"straight_arrow|elbow_connector|branch_connector|dashed_loop","render_style":"filled_block_arrow|line_connector|elbow_connector|branch_line_connector|dashed_loop_connector","route_intent":"straight|orthogonal|branch|loop","visual_weight":"chunky|normal|thin","preferred_axis":"horizontal|vertical|horizontal_first|vertical_first","bend_side":"above|below|left|right","path_percent":[[0.1,0.2],[0.3,0.2]],"arrowhead_direction":0,"stroke_color":"#333333","stroke_width_pt":1.5,"dash_style":"solid|dashed","line_pattern":"solid|dash","confidence":0.0}}
  ]
}}

Slots:
{json.dumps(_brief_slots(slots), ensure_ascii=False)}

Heuristic control candidates:
{json.dumps(_brief_controls(heuristic_controls), ensure_ascii=False)}
""".strip()
        result = call_vlm_json(prompt, image_paths, model=model)
        result["_vlm_model"] = model
        return result

    return adapter


def vlm_semantic_adapter(reference_path: str | Path, slots: list[dict], panels: list[dict], controls: list[dict], text_geometry: dict | None) -> dict:
    model = resolve_vlm_model("RFS_REBUILD_SEMANTIC_MODEL", "RFS_PROMPT_PLANNER_MODEL")
    prompt = f"""
You are planning slot-level visual assets for an editable PowerPoint rebuild.
Use the reference image plus OCR/layout/control metadata to assign semantics to each slot.
Only output JSON. Do not include markdown or explanations.

Allowed asset_type values:
character, document_stack, chart_card, tool_icon, tool_combo, device, screenshot_card, legend_marker, thin_tool, generic

Rules:
- Use nearby OCR text as the highest-priority semantic clue.
- If OCR text geometry includes text_relations/text_intelligence, use label_for_visual_object and caption_for relations before pure distance.
- Do not put readable text into generated image assets; text will be editable PPT text.
- prompt_subject must describe the visual subject for image generation, not the whole diagram.
- Keep ids exactly matching input slot ids.

Return schema:
{{
  "summary": "...",
  "slots": [
    {{"slot_id":"slot_1","asset_type":"character","semantic_role":"ai_critic","prompt_subject":"AI critic robot character","nearby_text":["AI Critic"]}}
  ]
}}

Panels:
{json.dumps(_brief_panels(panels), ensure_ascii=False)}

Slots:
{json.dumps(_brief_slots(slots), ensure_ascii=False)}

Controls:
{json.dumps(_brief_controls(controls), ensure_ascii=False)}

OCR text geometry:
{json.dumps(text_geometry or {}, ensure_ascii=False)}
""".strip()
    result = call_vlm_json(prompt, [reference_path], model=model)
    result["_vlm_model"] = model
    return result


def vlm_text_intelligence_adapter(reference_path: str | Path, program: dict, text_geometry: dict, text_program: dict, explicit_model: str | None = None) -> dict:
    model = resolve_vlm_model("RFS_REBUILD_TEXT_MODEL", "RFS_TEXT_ROLE_MODEL", explicit_model=explicit_model)
    text_regions = text_geometry.get("text_regions") if isinstance(text_geometry, dict) else []
    text_items = text_program.get("items") if isinstance(text_program, dict) else []
    prompt = f"""
You are analyzing editable text in a reference diagram for a PowerPoint rebuild.
Use the reference image plus OCR/PPT text metadata to judge font style, semantic relationships, and layout intent.
Only output JSON. Do not include markdown or explanations.

Rules:
- Do not write PowerPoint code.
- Do not output corrected bbox coordinates.
- Do not change text content, font size, or position.
- family_class must be one of: sans_serif, serif, monospace, display, handwriting, unknown.
- weight must be one of: regular, medium, bold.
- case_style must be one of: uppercase, title_case, sentence_case, mixed, unknown.
- alignment must be left, center, or right.
- anchor must be top_left, top_center, center, bottom_center, or custom.
- relation must be one of: title_subtitle, panel_title_of, label_for_visual_object, arrow_label_for, legend_label_for, caption_for, continuation_of.

Return schema:
{{
  "summary": "...",
  "items": [
    {{
      "text_id": "reference text id",
      "font_style_guess": {{"family_class":"sans_serif","weight":"bold","italic":false,"case_style":"title_case","visual_style":"short description"}},
      "layout_intent": {{"alignment":"center","anchor":"top_center","belongs_to":"panel_or_slot_or_control_id_or_canvas","row_group":"stable row group","column_group":"stable column group"}},
      "confidence": 0.0,
      "reason": "short reason"
    }}
  ],
  "text_relations": [
    {{"source_text_id":"text id","target_text_id":"text id","target_object_id":"slot_or_panel_or_control id","relation":"label_for_visual_object","confidence":0.0,"reason":"short reason"}}
  ]
}}

Panels:
{json.dumps(_brief_panels(program.get("panels", [])), ensure_ascii=False)}

Slots:
{json.dumps(_brief_slots(program.get("slots", [])), ensure_ascii=False)}

Controls:
{json.dumps(_brief_controls(program.get("arrows", [])), ensure_ascii=False)}

Text regions:
{json.dumps(text_regions, ensure_ascii=False)}

Text program:
{json.dumps(text_items, ensure_ascii=False)}
""".strip()
    result = call_vlm_json(prompt, [reference_path], model=model)
    result["_vlm_model"] = model
    return result


def build_rebuild_vlm_adapters(out_dir: str | Path) -> dict[str, Callable | None]:
    if not vlm_credentials_available():
        return {"layout": None, "control": None, "semantic": None, "text_intelligence": None}
    return {
        "layout": vlm_layout_adapter,
        "control": vlm_control_adapter_factory(out_dir),
        "semantic": vlm_semantic_adapter,
        "text_intelligence": vlm_text_intelligence_adapter,
    }
