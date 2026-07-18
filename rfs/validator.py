from __future__ import annotations

import json
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
REQUIRED = [
    "input_manifest.json",
    "reference_geometry.json",
    "reference_control_candidates.json",
    "slot_overlay.png",
    "reference_control_overlay.png",
    "reference_controls.json",
    "arrow_style_profile.json",
    "selected_arrow_routes.json",
    "arrow_quality_report.json",
    "slot_inventory.json",
    "reference_style_profile.json",
    "style_sheet.md",
    "layout_plan.json",
    "figure_program.json",
    "reference_text_geometry.json",
    "text_program.json",
    "ocr_text_quality_report.json",
    "text_alignment_report.json",
    "slot_visual_spec.json",
    "reference_slot_prompt_brief.json",
    "slot_prompt_plan.json",
    "prompts.md",
    "asset_quality_report.json",
    "asset_complexity_report.json",
    "composition_quality_report.json",
    "asset_visual_review.json",
    "asset_contact_sheet.png",
    "asset_candidate_contact_sheet.png",
    "editable_composition.pptx",
    "alignment_review.md",
    "critic_report.md",
    "visual_critic_iter_0.json",
]
FORBIDDEN_MARKERS = ["ok_after_crop", "cover-crop", "fill-crop", "forced crop", "crop-to-ratio", "single full diagram", "vector-only", "svg-only", "baked labels"]
COARSE_RATIO_PRESETS = {"1:1", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "3:2", "2:3"}
ARROW_ASSET_ID_TERMS = ("arrow", "dashed_arc", "dashed_arrows", "transition_arrow", "loop_dashed", "graph_connector")
COMPLEXITY_BLOCKERS = {"too_simple", "generic_icon", "reference_crop_ignored", "single_object_on_blank_background", "style_drift"}


def _front_summary(path: Path) -> bool:
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return isinstance(data, dict) and bool(str(data.get("summary", "")).strip())
        except Exception:
            return False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text:
            continue
        return text.lstrip("#").strip().lower() == "summary"
    return False


def _is_precise_ratio(value: object) -> bool:
    text = str(value or "").strip()
    if text in COARSE_RATIO_PRESETS:
        return False
    parts = text.split(":")
    if len(parts) != 2:
        return False
    try:
        return all("." in part and len(part.split(".", 1)[1]) >= 3 and float(part) > 0 for part in parts)
    except Exception:
        return False


def _validate_geometry_item(item: dict, label: str, errors: list[str]) -> None:
    for key in ["bbox_percent", "center_percent", "width_percent", "height_percent", "aspect_ratio_decimal", "aspect_ratio_w_h", "target_pixels_exact"]:
        if key not in item:
            errors.append(f"{label} missing {key}")
    if not _is_precise_ratio(item.get("aspect_ratio_w_h")):
        errors.append(f"{label} must use precise decimal aspect_ratio_w_h")
    try:
        if float(item.get("aspect_ratio_decimal", 0)) <= 0:
            errors.append(f"{label} aspect_ratio_decimal must be positive")
    except Exception:
        errors.append(f"{label} aspect_ratio_decimal must be numeric")


def _pixel_pair(value: object) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        return float(value["width"]), float(value["height"])
    except Exception:
        return None


def _color_family(hex_color: str) -> str:
    text = str(hex_color).strip().lstrip("#")
    if len(text) < 6:
        return "unknown"
    try:
        r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except Exception:
        return "unknown"
    if max(r, g, b) - min(r, g, b) < 24:
        return "neutral"
    if r >= g and r >= b:
        return "warm"
    if g >= r and g >= b:
        return "green"
    return "blue"


def _arrow_like_asset_id(value: object) -> bool:
    text = str(value or "").lower()
    return any(term in text for term in ARROW_ASSET_ID_TERMS)


def validate_output(out_dir: str | Path) -> dict:
    root = Path(out_dir)
    errors = []
    warnings = []
    if not root.exists():
        return {"summary": "Framework output validation result.", "ok": False, "errors": [f"Missing output directory: {root}"], "warnings": []}

    for name in REQUIRED:
        path = root / name
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"Missing non-empty {name}")
        elif path.suffix.lower() in {".md", ".json"} and not _front_summary(path):
            errors.append(f"{name} must start with Summary or top-level summary")

    try:
        manifest = json.loads((root / "input_manifest.json").read_text(encoding="utf-8"))
        if not manifest.get("paper_archived"):
            errors.append("input_manifest.json missing archived paper path")
        if not manifest.get("reference_archived"):
            errors.append("input_manifest.json missing archived reference path")
    except Exception as exc:
        errors.append(f"Invalid input_manifest.json: {exc}")

    try:
        geometry = json.loads((root / "reference_geometry.json").read_text(encoding="utf-8"))
        if not isinstance(geometry.get("slots"), list) or len(geometry.get("slots", [])) < 25:
            errors.append("reference_geometry.json must contain at least 25 slot geometry entries")
        if not isinstance(geometry.get("panels"), list) or not geometry.get("panels"):
            errors.append("reference_geometry.json must contain panel geometry entries")
        for item in geometry.get("slots", []):
            if isinstance(item, dict):
                _validate_geometry_item(item, f"reference_geometry slot {item.get('id')}", errors)
                if _arrow_like_asset_id(item.get("id")):
                    errors.append(f"reference_geometry slot {item.get('id')} looks like an arrow/control and must be moved to reference_controls.json")
        for item in geometry.get("panels", []):
            if isinstance(item, dict):
                _validate_geometry_item(item, f"reference_geometry panel {item.get('id')}", errors)
        for item in geometry.get("controls", []):
            if isinstance(item, dict):
                _validate_geometry_item(item, f"reference_geometry control {item.get('id')}", errors)
                if not str(item.get("source_id", "")).strip():
                    errors.append(f"reference_geometry control {item.get('id')} missing source_id")
                if not str(item.get("target_id", "")).strip():
                    errors.append(f"reference_geometry control {item.get('id')} missing target_id")
                if not str(item.get("source_anchor", "")).strip():
                    errors.append(f"reference_geometry control {item.get('id')} missing source_anchor")
                if not str(item.get("target_anchor", "")).strip():
                    errors.append(f"reference_geometry control {item.get('id')} missing target_anchor")
                if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
                    errors.append(f"reference_geometry control {item.get('id')} must render as a PPT shape, not an image asset")
        palette = geometry.get("reference_palette", [])
        if not isinstance(palette, list) or len({str(c).upper() for c in palette}) < 4:
            errors.append("reference_geometry.json reference_palette must contain at least 4 distinct colors")
        if not isinstance(geometry.get("color_tokens"), list) or not geometry.get("color_tokens"):
            errors.append("reference_geometry.json must contain color_tokens")
    except Exception as exc:
        errors.append(f"Invalid reference_geometry.json: {exc}")

    try:
        candidates_doc = json.loads((root / "reference_control_candidates.json").read_text(encoding="utf-8"))
        if not str(candidates_doc.get("effective_mode", "")).strip():
            errors.append("reference_control_candidates.json missing effective_mode")
        if not isinstance(candidates_doc.get("candidates"), list):
            errors.append("reference_control_candidates.json candidates must be a list")
        if str(candidates_doc.get("slot_overlay_path", "")).strip() and not (root / str(candidates_doc.get("slot_overlay_path"))).exists():
            errors.append("reference_control_candidates.json slot_overlay_path does not exist")
        if str(candidates_doc.get("control_overlay_path", "")).strip() and not (root / str(candidates_doc.get("control_overlay_path"))).exists():
            errors.append("reference_control_candidates.json control_overlay_path does not exist")
        for item in candidates_doc.get("candidates", []) if isinstance(candidates_doc.get("candidates"), list) else []:
            cid = item.get("id")
            for key in ["bbox_percent", "center_percent", "width_percent", "height_percent", "path_percent", "editable_in", "render_policy"]:
                if key not in item:
                    errors.append(f"reference_control_candidates item {cid} missing {key}")
            if _arrow_like_asset_id(item.get("asset_id")):
                errors.append(f"reference_control_candidates item {cid} must not bind to an image asset")
    except Exception as exc:
        errors.append(f"Invalid reference_control_candidates.json: {exc}")

    try:
        controls_doc = json.loads((root / "reference_controls.json").read_text(encoding="utf-8"))
        controls = controls_doc.get("controls", [])
        if not isinstance(controls, list):
            errors.append("reference_controls.json controls must be a list")
        for item in controls if isinstance(controls, list) else []:
            cid = item.get("id")
            for key in ["bbox_percent", "center_percent", "width_percent", "height_percent", "source_id", "target_id", "source_anchor", "target_anchor", "path_percent", "style_token_id", "editable_in", "render_policy"]:
                if key not in item:
                    errors.append(f"reference_controls item {cid} missing {key}")
            if not str(item.get("source_id", "")).strip():
                errors.append(f"reference_controls item {cid} missing non-empty source_id")
            if not str(item.get("target_id", "")).strip():
                errors.append(f"reference_controls item {cid} missing non-empty target_id")
            if not isinstance(item.get("path_percent"), list) or len(item.get("path_percent", [])) < 2:
                errors.append(f"reference_controls item {cid} must have at least 2 path_percent points")
            if str(item.get("editable_in", "")).lower() != "pptx":
                errors.append(f"reference_controls item {cid} must be editable in PPTX")
            if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
                errors.append(f"reference_controls item {cid} must use ppt_shape_not_image_asset")
    except Exception as exc:
        errors.append(f"Invalid reference_controls.json: {exc}")

    try:
        arrow_style = json.loads((root / "arrow_style_profile.json").read_text(encoding="utf-8"))
        if str(arrow_style.get("reference_priority", "")).lower() != "reference_image_hard_constraint":
            errors.append("arrow_style_profile.json must keep reference_image_hard_constraint")
        if not isinstance(arrow_style.get("style_rules"), dict) or not arrow_style.get("style_rules"):
            errors.append("arrow_style_profile.json must contain style_rules")
        if "reference" not in str(arrow_style.get("routing_principle", "")).lower():
            errors.append("arrow_style_profile.json routing_principle must explicitly preserve the reference image")
        if not str(arrow_style.get("routing_algorithm", "")).strip():
            errors.append("arrow_style_profile.json must record routing_algorithm")
        if "fallback" not in str(arrow_style.get("fallback_routing_policy", "")).lower():
            errors.append("arrow_style_profile.json must record fallback_routing_policy")
    except Exception as exc:
        errors.append(f"Invalid arrow_style_profile.json: {exc}")

    try:
        routes_doc = json.loads((root / "selected_arrow_routes.json").read_text(encoding="utf-8"))
        routes = routes_doc.get("routes", [])
        if not isinstance(routes, list):
            errors.append("selected_arrow_routes.json routes must be a list")
        for item in routes if isinstance(routes, list) else []:
            rid = item.get("id")
            for key in ["source_id", "target_id", "semantic_role", "route_style", "path_percent", "style_token_id", "stroke_width_pt", "arrowhead_size", "line_cap", "routing_algorithm", "route_generation_status"]:
                if key not in item or not str(item.get(key, "")).strip():
                    errors.append(f"selected_arrow_routes item {rid} missing {key}")
            if item.get("reference_locked") and item.get("reference_path_preserved") is not True:
                errors.append(f"selected_arrow_routes item {rid} overrides a locked reference path")
            if not isinstance(item.get("path_percent"), list) or len(item.get("path_percent", [])) < 2:
                errors.append(f"selected_arrow_routes item {rid} must have at least 2 path_percent points")
            if str(item.get("route_generation_status", "")).lower() == "aesthetic_tunnel_adjusted":
                if not isinstance(item.get("reference_original_path_percent"), list) or len(item.get("reference_original_path_percent", [])) < 2:
                    errors.append(f"selected_arrow_routes item {rid} missing reference_original_path_percent for aesthetic adjustment")
                if item.get("reference_tunnel_preserved") is not True:
                    errors.append(f"selected_arrow_routes item {rid} left its reference tunnel")
    except Exception as exc:
        errors.append(f"Invalid selected_arrow_routes.json: {exc}")

    try:
        arrow_quality = json.loads((root / "arrow_quality_report.json").read_text(encoding="utf-8"))
        if str(arrow_quality.get("status", "")).lower() in {"fail", "failed", "blocked"}:
            errors.append("arrow_quality_report.json reports failed arrow quality")
        if arrow_quality.get("reference_path_overrides"):
            errors.append("arrow_quality_report.json contains reference_path_overrides")
        if arrow_quality.get("reference_tunnel_violations"):
            errors.append("arrow_quality_report.json contains reference_tunnel_violations")
        if "total_crossing_count" not in arrow_quality:
            errors.append("arrow_quality_report.json missing total_crossing_count")
        if "average_aesthetic_score" not in arrow_quality:
            errors.append("arrow_quality_report.json missing average_aesthetic_score")
    except Exception as exc:
        errors.append(f"Invalid arrow_quality_report.json: {exc}")

    try:
        style_profile = json.loads((root / "reference_style_profile.json").read_text(encoding="utf-8"))
        if not isinstance(style_profile.get("color_tokens"), list) or not style_profile.get("color_tokens"):
            errors.append("reference_style_profile.json must contain color_tokens")
        for key in ["style_summary", "illustration_style", "line_weight", "shadow_style", "corner_radius", "icon_detail_level", "visual_density", "text_policy", "reference_priority"]:
            if not str(style_profile.get(key, "")).strip():
                errors.append(f"reference_style_profile.json missing {key}")
    except Exception as exc:
        errors.append(f"Invalid reference_style_profile.json: {exc}")

    try:
        layout_plan = json.loads((root / "layout_plan.json").read_text(encoding="utf-8"))
        if not isinstance(layout_plan.get("slots"), list) or len(layout_plan.get("slots", [])) < 25:
            errors.append("layout_plan.json must contain at least 25 located slots")
        if not isinstance(layout_plan.get("panels"), list) or not layout_plan.get("panels"):
            errors.append("layout_plan.json must contain located panels")
    except Exception as exc:
        errors.append(f"Invalid layout_plan.json: {exc}")

    try:
        program = json.loads((root / "figure_program.json").read_text(encoding="utf-8"))
        for key in ["canvas", "panels", "slots", "assets", "labels", "arrows", "groups", "export_targets"]:
            if key not in program:
                errors.append(f"figure_program.json missing {key}")
        slots = program.get("slots", [])
        if len(slots) < 25:
            errors.append(f"Too few slots: {len(slots)}")
        if not any(str(t.get("type", "")).lower() == "pptx" or str(t.get("path", "")).lower().endswith(".pptx") for t in program.get("export_targets", []) if isinstance(t, dict)):
            errors.append("figure_program.json export_targets must include pptx")
        for slot in slots:
            if _arrow_like_asset_id(slot.get("id")) or _arrow_like_asset_id(slot.get("asset_id")):
                errors.append(f"Slot {slot.get('id')} looks like an arrow/control and must not be generated as an image asset")
            fit_policy = str(slot.get("fit_policy", "")).lower()
            if "crop" in fit_policy and "no_crop" not in fit_policy and "without_crop" not in fit_policy:
                errors.append(f"Slot {slot.get('id')} uses a crop fit policy")
            if not _is_precise_ratio(slot.get("target_canvas_ratio")):
                errors.append(f"Slot {slot.get('id')} uses a coarse or non-decimal target_canvas_ratio")
            for key in ["center_percent", "width_percent", "height_percent", "aspect_ratio_decimal", "aspect_ratio_w_h", "target_pixels", "target_pixels_exact", "generation_min_pixels"]:
                if key not in slot:
                    errors.append(f"Slot {slot.get('id')} missing precise geometry key {key}")
            target_pixels = _pixel_pair(slot.get("target_pixels"))
            exact_pixels = _pixel_pair(slot.get("target_pixels_exact"))
            if target_pixels and exact_pixels:
                if abs(target_pixels[0] - exact_pixels[0]) > 0.01 or abs(target_pixels[1] - exact_pixels[1]) > 0.01:
                    errors.append(f"Slot {slot.get('id')} target_pixels must equal target_pixels_exact; use generation_min_pixels for minimum generation size")
            if float(slot.get("min_content_fill_percent", 0)) < 85:
                errors.append(f"Slot {slot.get('id')} has min fill below 85")
            if float(slot.get("max_empty_margin_percent", 99)) > 10:
                errors.append(f"Slot {slot.get('id')} allows too much empty margin")
            if str(slot.get("slot_frame_policy", "")).lower() != "frameless_slot":
                errors.append(f"Slot {slot.get('id')} must use frameless_slot")
            crop_path = str(slot.get("reference_crop_path", "")).strip()
            if not crop_path:
                errors.append(f"Slot {slot.get('id')} missing reference_crop_path")
            elif not (root / crop_path).exists():
                errors.append(f"Slot {slot.get('id')} reference crop does not exist: {crop_path}")
            if not str(slot.get("reference_style_profile_path", "")).strip():
                errors.append(f"Slot {slot.get('id')} missing reference_style_profile_path")
            if not isinstance(slot.get("local_color_token_ids"), list) or not slot.get("local_color_token_ids"):
                errors.append(f"Slot {slot.get('id')} missing local_color_token_ids")
            for key in ["visual_spec_id", "complexity_profile", "complexity_kind", "foreground_subject", "secondary_objects", "micro_details", "background_fill_elements", "scientific_mechanism_detail", "required_visual_complexity", "forbidden_simplification"]:
                if key not in slot:
                    errors.append(f"Slot {slot.get('id')} missing visual complexity key {key}")
            if str(slot.get("complexity_kind", "")).lower() != "legend_icon":
                if not isinstance(slot.get("secondary_objects"), list) or len(slot.get("secondary_objects", [])) < 2:
                    errors.append(f"Slot {slot.get('id')} needs at least 2 secondary_objects")
                if not isinstance(slot.get("micro_details"), list) or len(slot.get("micro_details", [])) < 2:
                    errors.append(f"Slot {slot.get('id')} needs at least 2 micro_details")
            safe_area = float(slot.get("safe_area_percent", 0))
            if safe_area < 88:
                errors.append(f"Slot {slot.get('id')} safe area below 88")
        for asset in program.get("assets", []):
            if _arrow_like_asset_id(asset.get("id")) or _arrow_like_asset_id(asset.get("slot_id")):
                errors.append(f"Asset {asset.get('id')} looks like an arrow/control and must not be generated by image2")
            if not str(asset.get("reference_crop_path", "")).strip():
                errors.append(f"Asset {asset.get('id')} missing reference_crop_path")
            if not str(asset.get("visual_spec_id", "")).strip():
                errors.append(f"Asset {asset.get('id')} missing visual_spec_id")
        for key in ["panels", "labels", "arrows", "groups"]:
            for item in program.get(key, []):
                if isinstance(item, dict) and str(item.get("editable_in", "")).lower() != "pptx":
                    errors.append(f"{key} item {item.get('id')} is not marked editable in PPTX")
        for arrow in program.get("arrows", []):
            if not str(arrow.get("source_id") or arrow.get("source") or "").strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing source_id")
            if not str(arrow.get("target_id") or arrow.get("target") or "").strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing target_id")
            if not isinstance(arrow.get("path_percent"), list) or len(arrow.get("path_percent", [])) < 2:
                errors.append(f"Arrow/control {arrow.get('id')} must have at least 2 path_percent points")
            if not str(arrow.get("source_anchor", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing source_anchor")
            if not str(arrow.get("target_anchor", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing target_anchor")
            if not str(arrow.get("style_token_id", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing style_token_id")
            if str(arrow.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
                errors.append(f"Arrow/control {arrow.get('id')} must render as PPT shape, not image asset")
            if not str(arrow.get("semantic_role", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing semantic_role")
            if not str(arrow.get("route_style", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing route_style")
            if not str(arrow.get("routing_algorithm", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing routing_algorithm")
            if not str(arrow.get("route_generation_status", "")).strip():
                errors.append(f"Arrow/control {arrow.get('id')} missing route_generation_status")
            if arrow.get("reference_locked") and arrow.get("reference_path_preserved") is not True:
                errors.append(f"Arrow/control {arrow.get('id')} overrides a locked reference path")
        style = program.get("style", {}) if isinstance(program.get("style"), dict) else {}
        if not isinstance(style.get("color_tokens"), list) or not style.get("color_tokens"):
            errors.append("figure_program.json style must include color_tokens")
        if not str(style.get("reference_style_profile_path", "")).strip():
            errors.append("figure_program.json style must include reference_style_profile_path")
        if not str(style.get("arrow_style_profile_path", "")).strip():
            errors.append("figure_program.json style must include arrow_style_profile_path")
        if not str(program.get("text_program_path", "")).strip():
            errors.append("figure_program.json must include text_program_path")
        if not str(program.get("reference_text_geometry_path", "")).strip():
            errors.append("figure_program.json must include reference_text_geometry_path")
        if not str(program.get("text_alignment_report_path", "")).strip():
            errors.append("figure_program.json must include text_alignment_report_path")
        text_program_inline = program.get("text_program")
        if not isinstance(text_program_inline, dict) or not isinstance(text_program_inline.get("items"), list) or not text_program_inline.get("items"):
            errors.append("figure_program.json must embed non-empty text_program items for PPT text rendering")
        palette = style.get("reference_palette") or style.get("palette") or []
        distinct = {str(c).upper() for c in palette if str(c).strip()}
        if len(distinct) < 4:
            errors.append("figure_program.json style must preserve reference-derived palette tokens, not a hardcoded fallback template")
        token_ids = {str(item.get("token_id")) for item in style.get("color_tokens", []) if isinstance(item, dict)}
        for arrow in program.get("arrows", []):
            if str(arrow.get("style_token_id")) not in token_ids:
                errors.append(f"Arrow/control {arrow.get('id')} style_token_id is not present in reference color_tokens")
    except Exception as exc:
        errors.append(f"Invalid figure_program.json: {exc}")

    reference_text_ids: set[str] = set()
    try:
        text_geometry = json.loads((root / "reference_text_geometry.json").read_text(encoding="utf-8"))
        if "publication" in str(text_geometry.get("policy", "")).lower() and "reference" not in str(text_geometry.get("policy", "")).lower():
            errors.append("reference_text_geometry.json policy must be reference-first, not publication-scale-first")
        regions = text_geometry.get("text_regions", [])
        if not isinstance(regions, list) or not regions:
            errors.append("reference_text_geometry.json must contain non-empty text_regions")
        for item in regions if isinstance(regions, list) else []:
            rid = str(item.get("id") or "")
            reference_text_ids.add(rid)
            for key in ["bbox_percent", "center_percent", "width_percent", "height_percent", "estimated_font_ratio", "color_hex", "role", "target_id"]:
                if key not in item:
                    errors.append(f"reference_text_geometry item {rid} missing {key}")
            try:
                if float(item.get("width_percent", 0)) <= 0 or float(item.get("height_percent", 0)) <= 0:
                    errors.append(f"reference_text_geometry item {rid} has non-positive size")
                if float(item.get("estimated_font_ratio", 0)) <= 0:
                    errors.append(f"reference_text_geometry item {rid} has non-positive estimated_font_ratio")
            except Exception:
                errors.append(f"reference_text_geometry item {rid} size/font fields must be numeric")
            if str(item.get("editable_in", "")).lower() != "pptx":
                errors.append(f"reference_text_geometry item {rid} must be intended for editable PPTX text")
            color = str(item.get("color_hex", ""))
            if not color.startswith("#") or len(color.strip()) < 7:
                errors.append(f"reference_text_geometry item {rid} must record reference color_hex")
            if str(text_geometry.get("detection_mode", "")).lower() == "ocr":
                if "confidence" not in item:
                    errors.append(f"reference_text_geometry OCR item {rid} missing confidence")
                if not str(item.get("raw_text", "")).strip():
                    errors.append(f"reference_text_geometry OCR item {rid} missing raw_text")
    except Exception as exc:
        errors.append(f"Invalid reference_text_geometry.json: {exc}")

    try:
        ocr_report = json.loads((root / "ocr_text_quality_report.json").read_text(encoding="utf-8"))
        if not str(ocr_report.get("mode", "")).strip():
            errors.append("ocr_text_quality_report.json missing mode")
        if not str(ocr_report.get("status", "")).strip():
            errors.append("ocr_text_quality_report.json missing status")
        if str(ocr_report.get("status", "")).lower() not in {"pass", "fallback", "not_run"}:
            errors.append("ocr_text_quality_report.json status must be pass, fallback, or not_run")
        if "text_region_count" not in ocr_report:
            errors.append("ocr_text_quality_report.json missing text_region_count")
    except Exception as exc:
        errors.append(f"Invalid ocr_text_quality_report.json: {exc}")

    text_role_path = root / "text_role_classification.json"
    if text_role_path.exists():
        try:
            text_roles = json.loads(text_role_path.read_text(encoding="utf-8"))
            if not str(text_roles.get("summary", "")).strip():
                errors.append("text_role_classification.json missing summary")
            if str(text_roles.get("mode", "")).lower() not in {"heuristic", "vlm"}:
                errors.append("text_role_classification.json mode must be heuristic or vlm")
            if not isinstance(text_roles.get("items"), list):
                errors.append("text_role_classification.json must contain items list")
            for item in text_roles.get("items", []) if isinstance(text_roles.get("items"), list) else []:
                tid = str(item.get("text_id") or "")
                for key in ["role", "hierarchy_level", "size_class", "group_hint", "source"]:
                    if key not in item:
                        errors.append(f"text_role_classification item {tid} missing {key}")
        except Exception as exc:
            errors.append(f"Invalid text_role_classification.json: {exc}")

    text_size_path = root / "text_size_normalization_report.json"
    if text_size_path.exists():
        try:
            text_sizes = json.loads(text_size_path.read_text(encoding="utf-8"))
            if not str(text_sizes.get("summary", "")).strip():
                errors.append("text_size_normalization_report.json missing summary")
            if str(text_sizes.get("method", "")).lower() != "role_aware_median_cluster":
                errors.append("text_size_normalization_report.json method must be role_aware_median_cluster")
            if not isinstance(text_sizes.get("text_size_levels"), list) or not text_sizes.get("text_size_levels"):
                errors.append("text_size_normalization_report.json must contain non-empty text_size_levels")
            if not isinstance(text_sizes.get("items"), list) or not text_sizes.get("items"):
                errors.append("text_size_normalization_report.json must contain non-empty items")
            for item in text_sizes.get("items", []) if isinstance(text_sizes.get("items"), list) else []:
                tid = str(item.get("text_id") or "")
                for key in ["raw_font_size_pt", "final_font_size_pt", "text_size_level_id", "final_role"]:
                    if key not in item:
                        errors.append(f"text_size_normalization_report item {tid} missing {key}")
        except Exception as exc:
            errors.append(f"Invalid text_size_normalization_report.json: {exc}")

    try:
        text_program = json.loads((root / "text_program.json").read_text(encoding="utf-8"))
        policy = str(text_program.get("policy", "")).lower()
        if "paper_double_column" in policy or "minimum_effective_font" in policy:
            errors.append("text_program.json must not apply fixed publication-scale font thresholds by default")
        items = text_program.get("items", [])
        if not isinstance(items, list) or not items:
            errors.append("text_program.json must contain non-empty items")
        for item in items if isinstance(items, list) else []:
            tid = str(item.get("id") or "")
            for key in ["text", "role", "target_id", "source_reference_text_id", "reference_binding", "bbox_percent", "center_percent", "width_percent", "height_percent", "estimated_font_ratio", "font_size_pt", "color_hex", "editable_in"]:
                if key not in item:
                    errors.append(f"text_program item {tid} missing {key}")
            for key in ["font_family_guess", "font_weight_guess", "fit_strategy"]:
                if key not in item:
                    errors.append(f"text_program item {tid} missing {key}")
            source_id = str(item.get("source_reference_text_id") or "")
            if source_id not in reference_text_ids:
                errors.append(f"text_program item {tid} source_reference_text_id does not exist in reference_text_geometry.json")
            if str(item.get("editable_in", "")).lower() != "pptx":
                errors.append(f"text_program item {tid} must render as editable PPTX text")
            try:
                if float(item.get("font_size_pt", 0)) <= 0:
                    errors.append(f"text_program item {tid} font_size_pt must be positive")
                if float(item.get("estimated_font_ratio", 0)) <= 0:
                    errors.append(f"text_program item {tid} estimated_font_ratio must be positive")
            except Exception:
                errors.append(f"text_program item {tid} font fields must be numeric")
            binding = str(item.get("reference_binding", "")).lower()
            if "reference" not in binding:
                errors.append(f"text_program item {tid} must bind to a reference-derived text region")
    except Exception as exc:
        errors.append(f"Invalid text_program.json: {exc}")

    try:
        text_alignment = json.loads((root / "text_alignment_report.json").read_text(encoding="utf-8"))
        policy = str(text_alignment.get("policy", "")).lower()
        if "fixed publication" in policy or "paper_double_column" in policy:
            errors.append("text_alignment_report.json must check reference alignment, not fixed publication font thresholds")
        if str(text_alignment.get("status", "")).lower() in {"fail", "failed", "blocked"}:
            errors.append("text_alignment_report.json reports failed text alignment")
        items = text_alignment.get("items", [])
        if not isinstance(items, list) or not items:
            errors.append("text_alignment_report.json must contain non-empty items")
        for item in items if isinstance(items, list) else []:
            tid = str(item.get("label_id") or "")
            if str(item.get("editable_in", "")).lower() != "pptx":
                errors.append(f"text_alignment_report item {tid} is not editable in PPTX")
            if str(item.get("status", "")).lower() in {"fail", "failed", "blocked"}:
                errors.append(f"text_alignment_report item {tid} failed reference alignment")
            try:
                if float(item.get("center_delta_percent", 0)) > 0.05:
                    errors.append(f"text_alignment_report item {tid} center drift exceeds reference tolerance")
                if float(item.get("width_delta_percent", 0)) > 0.08:
                    errors.append(f"text_alignment_report item {tid} width drift exceeds reference tolerance")
                if float(item.get("height_delta_percent", 0)) > 0.06:
                    errors.append(f"text_alignment_report item {tid} height drift exceeds reference tolerance")
            except Exception:
                errors.append(f"text_alignment_report item {tid} delta fields must be numeric")
            if not str(item.get("source_reference_text_id", "")).strip():
                errors.append(f"text_alignment_report item {tid} missing source_reference_text_id")
    except Exception as exc:
        errors.append(f"Invalid text_alignment_report.json: {exc}")

    try:
        visual_spec = json.loads((root / "slot_visual_spec.json").read_text(encoding="utf-8"))
        items = visual_spec.get("slots", [])
        if not isinstance(items, list) or len(items) < 25:
            errors.append("slot_visual_spec.json must contain at least 25 slot entries")
        for item in items:
            sid = item.get("slot_id")
            for key in ["reference_crop_objects", "foreground_subject", "secondary_objects", "micro_details", "background_fill_elements", "scientific_mechanism_detail", "required_visual_complexity", "forbidden_simplification"]:
                if key not in item:
                    errors.append(f"slot_visual_spec item {sid} missing {key}")
            if str(item.get("complexity_kind", "")).lower() != "legend_icon":
                if not isinstance(item.get("secondary_objects"), list) or len(item.get("secondary_objects", [])) < 2:
                    errors.append(f"slot_visual_spec item {sid} needs at least 2 secondary_objects")
                if not isinstance(item.get("micro_details"), list) or len(item.get("micro_details", [])) < 2:
                    errors.append(f"slot_visual_spec item {sid} needs at least 2 micro_details")
            forbidden_items = item.get("forbidden_simplification", []) if isinstance(item.get("forbidden_simplification"), list) else []
            forbidden = " ".join(str(x).lower() for x in forbidden_items)
            if str(item.get("complexity_kind", "")).lower() != "legend_icon" and "simple icon" not in forbidden:
                errors.append(f"slot_visual_spec item {sid} must forbid simple icon simplification")
    except Exception as exc:
        errors.append(f"Invalid slot_visual_spec.json: {exc}")

    try:
        prompt_brief = json.loads((root / "reference_slot_prompt_brief.json").read_text(encoding="utf-8"))
        brief_items = prompt_brief.get("slots", [])
        if not isinstance(brief_items, list) or len(brief_items) < 25:
            errors.append("reference_slot_prompt_brief.json must contain at least 25 slot brief entries")
        for item in brief_items:
            sid = item.get("slot_id")
            if not str(item.get("slot_function", "")).strip():
                errors.append(f"reference_slot_prompt_brief item {sid} missing slot_function")
            crop_path = str(item.get("reference_crop_path", "")).strip()
            if not crop_path:
                errors.append(f"reference_slot_prompt_brief item {sid} missing reference_crop_path")
            elif not (root / crop_path).exists():
                errors.append(f"reference_slot_prompt_brief item {sid} crop file missing: {crop_path}")
            if not str(item.get("reference_style_profile_path", "")).strip():
                errors.append(f"reference_slot_prompt_brief item {sid} missing reference_style_profile_path")
    except Exception as exc:
        errors.append(f"Invalid reference_slot_prompt_brief.json: {exc}")

    try:
        prompt_plan = json.loads((root / "slot_prompt_plan.json").read_text(encoding="utf-8"))
        items = prompt_plan.get("slots", [])
        if not isinstance(items, list) or len(items) < 25:
            errors.append("slot_prompt_plan.json must contain at least 25 slot prompt plans")
        for item in items:
            sid = item.get("slot_id")
            for key in ["slot_function", "reference_slot_role", "reference_shape_language", "reference_local_style", "reference_prompt_hint", "visual_metaphor", "image_prompt_core"]:
                if not str(item.get(key, "")).strip():
                    errors.append(f"slot_prompt_plan item {sid} missing {key}")
            for key in ["center_percent", "width_percent", "height_percent", "aspect_ratio_decimal", "aspect_ratio_w_h", "target_canvas_ratio", "target_pixels", "target_pixels_exact", "generation_min_pixels"]:
                if key not in item:
                    errors.append(f"slot_prompt_plan item {sid} missing precise geometry key {key}")
            crop_path = str(item.get("reference_crop_path", "")).strip()
            if not crop_path:
                errors.append(f"slot_prompt_plan item {sid} missing reference_crop_path")
            elif not (root / crop_path).exists():
                errors.append(f"slot_prompt_plan item {sid} crop file missing: {crop_path}")
            if not item.get("reference_crop_used"):
                errors.append(f"slot_prompt_plan item {sid} must record reference_crop_used=true")
            if not str(item.get("reference_style_profile_path", "")).strip():
                errors.append(f"slot_prompt_plan item {sid} missing reference_style_profile_path")
            if not isinstance(item.get("local_color_token_ids"), list) or not item.get("local_color_token_ids"):
                errors.append(f"slot_prompt_plan item {sid} missing local_color_token_ids")
            for key in ["visual_spec_id", "complexity_kind", "foreground_subject", "secondary_objects", "micro_details", "background_fill_elements", "scientific_mechanism_detail", "required_visual_complexity", "forbidden_simplification"]:
                if key not in item:
                    errors.append(f"slot_prompt_plan item {sid} missing visual complexity key {key}")
            if not _is_precise_ratio(item.get("target_canvas_ratio")):
                errors.append(f"slot_prompt_plan item {sid} uses coarse target_canvas_ratio")
            core = str(item.get("image_prompt_core", "")).lower()
            if "90-97" not in core or "10%" not in core:
                errors.append(f"slot_prompt_plan item {sid} image_prompt_core must mention 90-97% fill and 10% margin")
            if "reference_style_profile" not in core or "crop" not in core:
                errors.append(f"slot_prompt_plan item {sid} image_prompt_core must mention reference_style_profile and local crop grounding")
            if str(item.get("complexity_kind", "")).lower() != "legend_icon":
                for phrase in ["dense mini scientific", "2-5", "standalone pictogram"]:
                    if phrase not in core:
                        errors.append(f"slot_prompt_plan item {sid} image_prompt_core must mention {phrase}")
            if not isinstance(item.get("must_show"), list) or not item.get("must_show"):
                errors.append(f"slot_prompt_plan item {sid} missing must_show")
    except Exception as exc:
        errors.append(f"Invalid slot_prompt_plan.json: {exc}")

    try:
        report = json.loads((root / "asset_quality_report.json").read_text(encoding="utf-8"))
        items = report.get("assets", [])
        if len(items) < 25:
            errors.append(f"Too few asset QA entries: {len(items)}")
        for item in items:
            aid = item.get("asset_id") or item.get("slot_id")
            if "selected_candidate_index" not in item:
                errors.append(f"Asset {aid} missing selected_candidate_index")
            fill = float(item.get("content_fill_percent", 0))
            min_fill = float(item.get("min_content_fill_percent", 85))
            margin = float(item.get("empty_margin_percent", 100))
            max_margin = float(item.get("max_empty_margin_percent", 10))
            if fill < min_fill:
                errors.append(f"Asset {aid} fill {fill} below {min_fill}")
            if margin > max_margin:
                errors.append(f"Asset {aid} margin {margin} above {max_margin}")
            if str(item.get("edge_cutoff_status", "")).lower() not in {"ok", "none", "complete", "no_cutoff"}:
                errors.append(f"Asset {aid} edge cutoff status is not ok")
    except Exception as exc:
        errors.append(f"Invalid asset_quality_report.json: {exc}")

    try:
        complexity = json.loads((root / "asset_complexity_report.json").read_text(encoding="utf-8"))
        items = complexity.get("assets", [])
        if len(items) < 25:
            errors.append(f"Too few asset complexity entries: {len(items)}")
        for item in items:
            aid = item.get("asset_id") or item.get("slot_id")
            for key in ["detail_score", "detail_score_target", "object_count_estimate", "object_count_target", "simple_icon_risk", "reference_crop_match", "style_match", "selected_reason"]:
                if key not in item:
                    errors.append(f"Asset complexity {aid} missing {key}")
            try:
                if float(item.get("detail_score", 0)) < float(item.get("detail_score_target", 0)):
                    errors.append(f"Asset complexity {aid} detail_score below target")
            except Exception:
                errors.append(f"Asset complexity {aid} detail_score fields must be numeric")
            if item.get("simple_icon_risk") is True:
                errors.append(f"Asset complexity {aid} has simple_icon_risk=true")
            tags = item.get("complexity_issue_tags", []) if isinstance(item.get("complexity_issue_tags"), list) else []
            unresolved = sorted(COMPLEXITY_BLOCKERS.intersection(str(tag) for tag in tags))
            if unresolved:
                errors.append(f"Asset complexity {aid} has unresolved complexity issue(s): {', '.join(unresolved)}")
            if str(item.get("reference_crop_match", "")).startswith("missing"):
                errors.append(f"Asset complexity {aid} missing reference crop match")
            if str(item.get("style_match", "")).startswith("missing"):
                errors.append(f"Asset complexity {aid} missing style match")
    except Exception as exc:
        errors.append(f"Invalid asset_complexity_report.json: {exc}")

    try:
        comp = json.loads((root / "composition_quality_report.json").read_text(encoding="utf-8"))
        items = comp.get("slots", [])
        if not isinstance(items, list) or len(items) < 25:
            errors.append("composition_quality_report.json must contain at least 25 slot entries")
        for item in items:
            sid = item.get("slot_id")
            if item.get("tile_frame_added") is not False:
                errors.append(f"Composition slot {sid} added an extra tile frame")
            if item.get("caption_inside_image_slot") is not False:
                errors.append(f"Composition slot {sid} has caption inside image slot")
            if str(item.get("slot_frame_policy", "")).lower() != "frameless_slot":
                errors.append(f"Composition slot {sid} must use frameless_slot")
            fill = float(item.get("image_slot_area_fill_percent", 0))
            if fill < 95:
                errors.append(f"Composition slot {sid} image fills {fill}% of slot, below 95%")
        for item in comp.get("arrows", []) if isinstance(comp.get("arrows"), list) else []:
            aid = item.get("arrow_id")
            if str(item.get("editable_in", "")).lower() != "pptx":
                errors.append(f"Composition arrow {aid} is not editable in PPTX")
            if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
                errors.append(f"Composition arrow {aid} must render as a PPT shape")
            if int(item.get("segment_count", 0)) < 1:
                errors.append(f"Composition arrow {aid} rendered no connector segments")
            if not str(item.get("route_style", "")).strip():
                errors.append(f"Composition arrow {aid} missing route_style")
            if not str(item.get("line_cap", "")).strip():
                errors.append(f"Composition arrow {aid} missing line_cap")
            if not str(item.get("routing_algorithm", "")).strip():
                errors.append(f"Composition arrow {aid} missing routing_algorithm")
    except Exception as exc:
        errors.append(f"Invalid composition_quality_report.json: {exc}")

    try:
        asset_review = json.loads((root / "asset_visual_review.json").read_text(encoding="utf-8"))
        if str(asset_review.get("status", "")).lower() in {"needs_regeneration", "blocked", "fail", "failed"}:
            issues = asset_review.get("issues", [])
            errors.append(f"asset_visual_review.json has unresolved asset issues: {len(issues)}")
    except Exception as exc:
        errors.append(f"Invalid asset_visual_review.json: {exc}")

    try:
        visual_critic = json.loads((root / "visual_critic_iter_0.json").read_text(encoding="utf-8"))
        if str(visual_critic.get("status", "")).lower() in {"blocked", "needs_layout_refinement", "fail", "failed"}:
            errors.append("visual_critic_iter_0.json reports unresolved layout or blocking issues")
        if visual_critic.get("blocking_issues"):
            errors.append(f"visual_critic_iter_0.json has blocking issues: {len(visual_critic.get('blocking_issues', []))}")
    except Exception as exc:
        errors.append(f"Invalid visual_critic_iter_0.json: {exc}")

    asset_count = len([p for p in (root / "assets").glob("*") if p.suffix.lower() in IMAGE_EXTS]) if (root / "assets").exists() else 0
    if asset_count < 25:
        errors.append(f"Too few generated assets: {asset_count}")

    text_blob = ""
    for name in ["prompts.md", "style_sheet.md", "reference_style_profile.json", "arrow_style_profile.json", "selected_arrow_routes.json", "arrow_quality_report.json", "figure_program.json", "reference_geometry.json", "reference_controls.json", "reference_text_geometry.json", "text_program.json", "ocr_text_quality_report.json", "text_role_classification.json", "text_size_normalization_report.json", "text_size_decisions.md", "text_alignment_report.json", "slot_visual_spec.json", "reference_slot_prompt_brief.json", "slot_prompt_plan.json", "asset_quality_report.json", "asset_complexity_report.json", "composition_quality_report.json", "asset_visual_review.json", "alignment_review.md", "critic_report.md", "visual_critic_iter_0.json"]:
        path = root / name
        if path.exists():
            text_blob += "\n" + path.read_text(encoding="utf-8", errors="ignore").lower()
    hits = [m for m in FORBIDDEN_MARKERS if m in text_blob]
    if hits:
        errors.append("Forbidden marker(s) found: " + ", ".join(hits))

    if not (root / "review.pdf").exists():
        warnings.append("review.pdf missing; PPTX may still be editable but export failed")
    if not (root / "final_600dpi.png").exists():
        warnings.append("final_600dpi.png missing; PDF-to-PNG export may have failed")

    return {"summary": "Framework output validation result.", "ok": not errors, "errors": errors, "warnings": warnings, "asset_count": asset_count}
