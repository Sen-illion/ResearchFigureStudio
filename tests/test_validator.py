import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rfs.validator import validate_output


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _make_valid_output(root: Path, asset_count: int = 25) -> None:
    assets = root / "assets"
    assets.mkdir(parents=True)
    crop_dir = root / "reference_slot_crops"
    crop_dir.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(root / "asset_contact_sheet.png")
    Image.new("RGB", (64, 64), "white").save(root / "asset_candidate_contact_sheet.png")
    Image.new("RGB", (64, 64), "white").save(root / "slot_overlay.png")
    Image.new("RGB", (64, 64), "white").save(root / "reference_control_overlay.png")
    (root / "editable_composition.pptx").write_bytes(b"pptx-placeholder")
    (root / "review.pdf").write_bytes(b"pdf-placeholder")
    Image.new("RGB", (64, 64), "white").save(root / "final_600dpi.png")

    slots = []
    geometry_slots = []
    asset_items = []
    complexity_items = []
    composition_items = []
    prompt_brief_items = []
    prompt_plan_items = []
    color_tokens = [{
        "token_id": "panel_a_header_001",
        "hex": "#2D6FB7",
        "rgb": {"r": 45, "g": 111, "b": 183},
        "hsl": {"h": 211.0, "s": 0.606, "l": 0.447},
        "source_region": "panel:panel_a:header",
        "usage": "header_fill",
    }]
    for index in range(asset_count):
        slot_id = f"slot_{index:02d}"
        asset_id = f"asset_{index:02d}"
        crop_path = f"reference_slot_crops/{slot_id}.png"
        Image.new("RGB", (64, 64), (50, 160, 190)).save(assets / f"{asset_id}.png")
        Image.new("RGB", (64, 64), (50, 160, 190)).save(root / crop_path)
        slot = {
            "id": slot_id,
            "parent_panel": "panel_a",
            "paper_concept": f"concept {index}",
            "bbox_percent": {"x": 0.05, "y": 0.05, "w": 0.08, "h": 0.08},
            "center_percent": {"x": 0.09, "y": 0.09},
            "width_percent": 0.08,
            "height_percent": 0.08,
            "aspect_ratio_decimal": 1.0,
            "aspect_ratio_w_h": "1.000:1.000",
            "target_canvas_ratio": "1.000:1.000",
            "target_pixels": {"width": 64.0, "height": 64.0},
            "target_pixels_exact": {"width": 64.0, "height": 64.0},
            "generation_min_pixels": {"width": 256, "height": 256},
            "safe_area_percent": 92,
            "fit_policy": "contain_no_crop",
            "text_policy": "very_small_decorative_text_only; critical labels in pptx",
            "asset_id": asset_id,
            "target_content_fill_percent": 93,
            "min_content_fill_percent": 85,
            "max_empty_margin_percent": 10,
            "composition_type": "full_frame_icon",
            "slot_frame_policy": "frameless_slot",
            "picture_fill_policy": "direct_full_slot_contain_no_tile",
            "blank_space_policy": "full-frame composition; no tiny centered subject",
            "reference_crop_path": crop_path,
            "reference_style_profile_path": "reference_style_profile.json",
            "local_color_token_ids": ["panel_a_header_001"],
            "visual_spec_id": f"visual_spec_{slot_id}",
            "complexity_profile": "reference-dense",
            "complexity_kind": "pipeline_module",
            "reference_crop_objects": ["paper-specific object", "visible relation"],
            "foreground_subject": "paper-specific object",
            "secondary_objects": ["supporting object", "input-output cue"],
            "micro_details": ["small glyph texture", "internal line detail"],
            "background_fill_elements": ["edge-to-edge colored support", "subtle texture"],
            "scientific_mechanism_detail": "show the concept as a layered mechanism",
            "required_visual_complexity": "dense",
            "forbidden_simplification": ["simple icon", "centered icon", "clean blank background", "single object on white canvas"],
            "object_count_target": 3,
            "detail_score_target": 65,
        }
        slots.append(slot)
        geometry_slots.append({
            "id": slot_id,
            "type": "slot",
            "bbox_percent": slot["bbox_percent"],
            "center_percent": slot["center_percent"],
            "width_percent": slot["width_percent"],
            "height_percent": slot["height_percent"],
            "aspect_ratio_decimal": slot["aspect_ratio_decimal"],
            "aspect_ratio_w_h": slot["aspect_ratio_w_h"],
            "target_pixels_exact": slot["target_pixels_exact"],
            "local_color_token_ids": ["panel_a_header_001"],
        })
        asset_items.append({
            "asset_id": asset_id,
            "slot_id": slot_id,
            "selected_candidate_index": 1,
            "content_fill_percent": 90,
            "min_content_fill_percent": 85,
            "empty_margin_percent": 8,
            "max_empty_margin_percent": 10,
            "edge_cutoff_status": "ok",
            "ratio_status": "ok",
            "issue_tags": [],
            "action": "ok_no_crop",
            "detail_score": 75,
            "detail_score_target": 65,
            "object_count_estimate": 4,
            "object_count_target": 3,
            "simple_icon_risk": False,
            "reference_crop_match": "planned_reference_crop_grounded",
            "style_match": "planned_reference_style_grounded",
            "complexity_issue_tags": [],
            "selected_reason": "Selected because it had the best combined fill, margin, ratio, and visual-complexity score.",
        })
        complexity_items.append({
            "asset_id": asset_id,
            "slot_id": slot_id,
            "selected_candidate_index": 1,
            "selected_candidate_path": f"asset_candidates/{slot_id}/candidate_01.png",
            "complexity_kind": "pipeline_module",
            "required_visual_complexity": "dense",
            "detail_score": 75,
            "detail_score_target": 65,
            "object_count_estimate": 4,
            "object_count_target": 3,
            "simple_icon_risk": False,
            "reference_crop_match": "planned_reference_crop_grounded",
            "style_match": "planned_reference_style_grounded",
            "complexity_issue_tags": [],
            "selected_reason": "Selected because it had the best combined fill, margin, ratio, and visual-complexity score.",
        })
        composition_items.append({
            "slot_id": slot_id,
            "asset_id": asset_id,
            "slot_frame_policy": "frameless_slot",
            "picture_fill_policy": "direct_full_slot_contain_no_tile",
            "tile_frame_added": False,
            "caption_inside_image_slot": False,
            "image_slot_area_fill_percent": 100,
        })
        prompt_brief_items.append({
            "slot_id": slot_id,
            "paper_concept": f"concept {index}",
            "slot_function": f"visualize concept {index} in its local reference slot",
            "bbox_percent": slot["bbox_percent"],
            "center_percent": slot["center_percent"],
            "width_percent": slot["width_percent"],
            "height_percent": slot["height_percent"],
            "aspect_ratio_decimal": slot["aspect_ratio_decimal"],
            "aspect_ratio_w_h": slot["aspect_ratio_w_h"],
            "target_canvas_ratio": slot["target_canvas_ratio"],
            "target_pixels": slot["target_pixels"],
            "target_pixels_exact": slot["target_pixels_exact"],
            "generation_min_pixels": slot["generation_min_pixels"],
            "composition_type": "full_frame_icon",
            "visual_metaphor": "concrete scientific object",
            "must_show": ["paper-specific object", "visible relation"],
            "avoid_showing": ["generic sci-fi dashboard"],
            "reference_crop_path": crop_path,
            "reference_style_profile_path": "reference_style_profile.json",
            "local_color_token_ids": ["panel_a_header_001"],
            "visual_spec_id": f"visual_spec_{slot_id}",
            "complexity_profile": "reference-dense",
            "complexity_kind": "pipeline_module",
            "reference_crop_objects": ["paper-specific object", "visible relation"],
            "foreground_subject": "paper-specific object",
            "secondary_objects": ["supporting object", "input-output cue"],
            "micro_details": ["small glyph texture", "internal line detail"],
            "background_fill_elements": ["edge-to-edge colored support", "subtle texture"],
            "scientific_mechanism_detail": "show the concept as a layered mechanism",
            "required_visual_complexity": "dense",
            "forbidden_simplification": ["simple icon", "centered icon", "clean blank background", "single object on white canvas"],
            "object_count_target": 3,
            "detail_score_target": 65,
        })
        prompt_plan_items.append({
            "slot_id": slot_id,
            "paper_concept": f"concept {index}",
            "slot_function": f"visualize concept {index} in its local reference slot",
            "bbox_percent": slot["bbox_percent"],
            "center_percent": slot["center_percent"],
            "width_percent": slot["width_percent"],
            "height_percent": slot["height_percent"],
            "aspect_ratio_decimal": slot["aspect_ratio_decimal"],
            "aspect_ratio_w_h": slot["aspect_ratio_w_h"],
            "target_canvas_ratio": slot["target_canvas_ratio"],
            "target_pixels": slot["target_pixels"],
            "target_pixels_exact": slot["target_pixels_exact"],
            "generation_min_pixels": slot["generation_min_pixels"],
            "target_content_fill_percent": 93,
            "min_content_fill_percent": 85,
            "max_empty_margin_percent": 10,
            "reference_crop_path": crop_path,
            "reference_crop_used": True,
            "reference_style_profile_path": "reference_style_profile.json",
            "local_color_token_ids": ["panel_a_header_001"],
            "visual_spec_id": f"visual_spec_{slot_id}",
            "complexity_profile": "reference-dense",
            "complexity_kind": "pipeline_module",
            "reference_crop_objects": ["paper-specific object", "visible relation"],
            "foreground_subject": "paper-specific object",
            "secondary_objects": ["supporting object", "input-output cue"],
            "micro_details": ["small glyph texture", "internal line detail"],
            "background_fill_elements": ["edge-to-edge colored support", "subtle texture"],
            "scientific_mechanism_detail": "show the concept as a layered mechanism",
            "required_visual_complexity": "dense",
            "forbidden_simplification": ["simple icon", "centered icon", "clean blank background", "single object on white canvas"],
            "object_count_target": 3,
            "detail_score_target": 65,
            "reference_slot_role": "near-square icon/card in the reference layout",
            "reference_shape_language": "near-square icon/card",
            "reference_local_style": "rounded scientific card with compact visual density",
            "reference_density": "high",
            "reference_prompt_hint": "match the local reference slot while drawing the paper concept",
            "visual_metaphor": "concrete scientific object",
            "must_show": ["paper-specific object", "visible relation"],
            "avoid_showing": ["generic sci-fi dashboard"],
            "image_prompt_core": "Draw a dense mini scientific scene/card from the local crop that visibly represents this paper-specific relation with foreground_subject, 2-5 layered objects, micro details, edge-to-edge support detail, and not a standalone pictogram. Use reference_style_profile.json, exact aspect ratio 1.000:1, content fill 90-97%, empty margin below 10% on every edge.",
        })

    panels = [{"id": "panel_a", "title": "Panel A", "bbox_percent": {"x": 0.03, "y": 0.03, "w": 0.9, "h": 0.5}, "editable_in": "pptx"}]
    arrows = [
        {
            "id": "flow_a",
            "source": "slot_00",
            "target": "slot_01",
            "source_id": "slot_00",
            "target_id": "slot_01",
            "source_anchor": "right_mid",
            "target_anchor": "left_mid",
            "path_percent": [[0.1, 0.1], [0.2, 0.1]],
            "style_token_id": "panel_a_header_001",
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
            "control_kind": "straight_arrow",
        },
        {
            "id": "loop_a",
            "source": "slot_02",
            "target": "slot_03",
            "source_id": "slot_02",
            "target_id": "slot_03",
            "source_anchor": "top_mid",
            "target_anchor": "bottom_mid",
            "path_percent": [[0.3, 0.2], [0.35, 0.15], [0.4, 0.2], [0.35, 0.25], [0.3, 0.2]],
            "style_token_id": "panel_a_header_001",
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
            "control_kind": "dashed_loop",
        },
        {
            "id": "multi_a",
            "source": "slot_04",
            "target": "slot_05",
            "source_id": "slot_04",
            "target_id": "slot_05",
            "source_anchor": "right_mid",
            "target_anchor": "left_mid",
            "path_percent": [[0.45, 0.3], [0.52, 0.3], [0.52, 0.42], [0.62, 0.42]],
            "style_token_id": "panel_a_header_001",
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
            "control_kind": "elbow_connector",
        },
    ]
    arrow_style_by_id = {
        "flow_a": {"semantic_role": "module_flow", "route_style": "soft_straight", "bundle_id": "flow_01", "line_cap": "round", "line_pattern": "solid", "stroke_width_pt": 1.45, "arrowhead_size": "sm", "reference_locked": True, "reference_path_preserved": True, "routing_algorithm": "preserve_reference_path", "route_generation_status": "reference_locked"},
        "loop_a": {"semantic_role": "feedback_loop", "route_style": "dashed_spline_like", "bundle_id": "loop_slot_02_slot_03", "line_cap": "round", "line_pattern": "dash", "stroke_width_pt": 1.8, "arrowhead_size": "sm", "reference_locked": True, "reference_path_preserved": True, "routing_algorithm": "preserve_reference_path", "route_generation_status": "reference_locked"},
        "multi_a": {"semantic_role": "module_flow", "route_style": "rounded_elbow", "bundle_id": "flow_03", "line_cap": "round", "line_pattern": "solid", "stroke_width_pt": 1.65, "arrowhead_size": "sm", "reference_locked": True, "reference_path_preserved": True, "routing_algorithm": "preserve_reference_path", "route_generation_status": "reference_locked"},
    }
    for arrow in arrows:
        arrow.update(arrow_style_by_id[arrow["id"]])
    control_items = []
    for arrow in arrows:
        xs = [point[0] for point in arrow["path_percent"]]
        ys = [point[1] for point in arrow["path_percent"]]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        w, h = max(0.001, x1 - x0), max(0.001, y1 - y0)
        control_items.append({
            "id": arrow["id"],
            "type": "ppt_control",
            "control_kind": arrow["control_kind"],
            "bbox_percent": {"x": round(x0, 4), "y": round(y0, 4), "w": round(w, 4), "h": round(h, 4)},
            "center_percent": {"x": round(x0 + w / 2, 4), "y": round(y0 + h / 2, 4)},
            "width_percent": round(w, 4),
            "height_percent": round(h, 4),
            "aspect_ratio_decimal": round(w / h, 3),
            "aspect_ratio_w_h": f"{w / h:.3f}:1.000",
            "target_pixels_exact": {"width": round(800 * w, 3), "height": round(800 * h, 3)},
            "source_id": arrow["source_id"],
            "target_id": arrow["target_id"],
            "source_anchor": arrow["source_anchor"],
            "target_anchor": arrow["target_anchor"],
            "path_percent": arrow["path_percent"],
            "style_token_id": arrow["style_token_id"],
            "editable_in": "pptx",
            "render_policy": "ppt_shape_not_image_asset",
            "candidate_label": f"AR{len(control_items)+1:02d}",
        })
    groups = [{"id": "group_a", "members": ["panel_a"], "editable_in": "pptx"}]
    labels = [{"id": "label_a", "text": "Panel A", "target_id": "panel_a", "editable_in": "pptx"}]
    reference_palette = ["#2D6FB7", "#E17721", "#6B57C8", "#1B9A94"]
    reference_text_regions = [
        {
            "id": "ref_text_panel_a",
            "text": "Panel A",
            "role": "panel_title",
            "target_id": "panel_a",
            "bbox_percent": {"x": 0.03, "y": 0.03, "w": 0.9, "h": 0.055},
            "center_percent": {"x": 0.48, "y": 0.0575},
            "width_percent": 0.9,
            "height_percent": 0.055,
            "estimated_font_ratio": 0.0341,
            "color_hex": "#FFFFFF",
            "source": "reference_panel_header_geometry",
            "editable_in": "pptx",
        }
    ]
    text_items = [
        {
            "id": "text_ref_text_panel_a",
            "text": "Panel A",
            "role": "panel_title",
            "target_id": "panel_a",
            "source_reference_text_id": "ref_text_panel_a",
            "reference_binding": "reference_panel_header_geometry",
            "bbox_percent": {"x": 0.03, "y": 0.03, "w": 0.9, "h": 0.055},
            "center_percent": {"x": 0.48, "y": 0.0575},
            "width_percent": 0.9,
            "height_percent": 0.055,
            "estimated_font_ratio": 0.0341,
            "font_size_pt": 8.0,
            "color_hex": "#FFFFFF",
            "color_token_id": "panel_a_header_001",
            "font_family_guess": "Arial",
            "font_weight_guess": "bold",
            "fit_strategy": "reference_geometry_bbox",
            "ocr_confidence": None,
            "bold": True,
            "align": "center",
            "editable_in": "pptx",
            "visible": True,
        }
    ]
    text_alignment_items = [
        {
            "label_id": "text_ref_text_panel_a",
            "source_reference_text_id": "ref_text_panel_a",
            "role": "panel_title",
            "center_delta_percent": 0.0,
            "width_delta_percent": 0.0,
            "height_delta_percent": 0.0,
            "font_ratio_delta": 0.0,
            "color_status": "reference_token",
            "editable_in": "pptx",
            "status": "pass",
        }
    ]

    _write_json(root / "input_manifest.json", {"summary": "Archived source inputs.", "paper_archived": "inputs/paper.pdf", "reference_archived": "inputs/reference.png"})
    _write_json(root / "reference_geometry.json", {
        "summary": "Reference geometry.",
        "slots": geometry_slots,
        "panels": [{
            "id": "panel_a",
            "type": "panel",
            "bbox_percent": {"x": 0.03, "y": 0.03, "w": 0.9, "h": 0.5},
            "center_percent": {"x": 0.48, "y": 0.28},
            "width_percent": 0.9,
            "height_percent": 0.5,
            "aspect_ratio_decimal": 1.8,
            "aspect_ratio_w_h": "1.800:1.000",
            "target_pixels_exact": {"width": 720.0, "height": 400.0},
        }],
        "controls": control_items,
        "control_localizer": {
            "requested_mode": "heuristic",
            "effective_mode": "heuristic",
            "candidate_count": len(control_items),
            "candidate_path": "reference_control_candidates.json",
            "slot_overlay_path": "slot_overlay.png",
            "control_overlay_path": "reference_control_overlay.png",
            "warnings": [],
        },
        "reference_palette": reference_palette,
        "color_tokens": color_tokens,
    })
    _write_json(root / "reference_control_candidates.json", {
        "summary": "Reference control candidates.",
        "requested_mode": "heuristic",
        "effective_mode": "heuristic",
        "slot_overlay_path": "slot_overlay.png",
        "control_overlay_path": "reference_control_overlay.png",
        "candidate_count": len(control_items),
        "candidates": control_items,
        "warnings": [],
    })
    _write_json(root / "reference_controls.json", {
        "summary": "Reference controls.",
        "requested_mode": "heuristic",
        "effective_mode": "heuristic",
        "candidate_path": "reference_control_candidates.json",
        "slot_overlay_path": "slot_overlay.png",
        "control_overlay_path": "reference_control_overlay.png",
        "controls": control_items,
        "ppt_arrows": control_items,
    })
    selected_routes = []
    for arrow in arrows:
        selected_routes.append({
            "id": arrow["id"],
            "source_id": arrow["source_id"],
            "target_id": arrow["target_id"],
            "semantic_role": arrow["semantic_role"],
            "route_style": arrow["route_style"],
            "bundle_id": arrow["bundle_id"],
            "lane_index": 0,
            "lane_count": 1,
            "reference_locked": True,
            "reference_path_preserved": True,
            "path_percent": arrow["path_percent"],
            "style_token_id": arrow["style_token_id"],
            "stroke_width_pt": arrow["stroke_width_pt"],
            "arrowhead_size": arrow["arrowhead_size"],
            "line_cap": arrow["line_cap"],
            "line_pattern": arrow["line_pattern"],
            "routing_algorithm": arrow["routing_algorithm"],
            "route_generation_status": arrow["route_generation_status"],
            "metrics": {"path_length": 0.1, "bend_count": max(0, len(arrow["path_percent"]) - 2), "crossing_count": 0, "obstacle_overlap_count": 0},
            "aesthetic_score": 95,
        })
    _write_json(root / "arrow_style_profile.json", {
        "summary": "Reference-first arrow styling profile.",
        "mode": "reference",
        "reference_priority": "reference_image_hard_constraint",
        "routing_principle": "preserve reference-derived source-target logic and path geometry",
        "routing_algorithm": "reference-constrained-orthogonal-v1",
        "fallback_routing_policy": "only missing or fallback_reroute_allowed arrows may use obstacle-aware routing",
        "style_rules": {"module_flow": {"route_style": "soft_straight"}, "feedback_loop": {"route_style": "dashed_spline_like"}},
        "ppt_editability": "all arrows render as PPT connector shapes",
    })
    _write_json(root / "selected_arrow_routes.json", {
        "summary": "Selected reference-preserving arrow routes.",
        "mode": "reference",
        "route_count": len(selected_routes),
        "routes": selected_routes,
    })
    _write_json(root / "arrow_quality_report.json", {
        "summary": "Arrow quality report.",
        "mode": "reference",
        "status": "pass",
        "arrow_count": len(selected_routes),
        "total_crossing_count": 0,
        "total_obstacle_overlap_count": 0,
        "average_aesthetic_score": 95,
        "reference_path_overrides": [],
        "routes": selected_routes,
    })
    _write_json(root / "slot_inventory.json", {
        "summary": "Slot inventory.",
        "slot_count": asset_count,
        "slots": slots,
        "reference_control_candidates_path": "reference_control_candidates.json",
        "slot_overlay_path": "slot_overlay.png",
        "reference_control_overlay_path": "reference_control_overlay.png",
        "control_localizer": {"requested_mode": "heuristic", "effective_mode": "heuristic"},
    })
    _write_json(root / "reference_style_profile.json", {
        "summary": "Reference style profile.",
        "style_summary": "Reference-first scientific style.",
        "illustration_style": "flat academic illustration",
        "line_weight": "medium",
        "shadow_style": "soft",
        "corner_radius": "rounded",
        "icon_detail_level": "high",
        "visual_density": "dense",
        "text_policy": "critical text in PPT",
        "reference_priority": "reference_image_primary",
        "color_tokens": color_tokens,
    })
    (root / "style_sheet.md").write_text("# Summary\nStyle sheet.\n", encoding="utf-8")
    _write_json(root / "layout_plan.json", {"summary": "Layout plan.", "panels": panels, "slots": slots, "arrows": arrows, "control_shapes": control_items})
    _write_json(root / "figure_program.json", {
        "summary": "Figure program.",
        "canvas": {},
        "locator": {"mode": "heuristic", "reference_path": "inputs/reference.png"},
        "style": {"reference_palette": reference_palette, "slot_frame_policy": "frameless_slot", "color_tokens": color_tokens, "reference_style_profile_path": "reference_style_profile.json", "arrow_style_profile_path": "arrow_style_profile.json"},
        "panels": panels,
        "slots": slots,
        "assets": [{"id": item["asset_id"], "slot_id": item["slot_id"], "reference_crop_path": f"reference_slot_crops/{item['slot_id']}.png", "visual_spec_id": f"visual_spec_{item['slot_id']}"} for item in asset_items],
        "labels": labels,
        "arrows": arrows,
        "control_shapes": control_items,
        "groups": groups,
        "text_program": {"summary": "Text program.", "items": text_items},
        "text_program_path": "text_program.json",
        "reference_text_geometry_path": "reference_text_geometry.json",
        "text_alignment_report_path": "text_alignment_report.json",
        "export_targets": [{"type": "pptx", "path": "editable_composition.pptx"}],
    })
    _write_json(root / "reference_text_geometry.json", {
        "summary": "Reference text geometry.",
        "policy": "reference_image_is_highest_authority_for_text_size_position_color_and_hierarchy",
        "detection_mode": "reference_geometry_and_local_color_sampling",
        "text_regions": reference_text_regions,
    })
    _write_json(root / "text_program.json", {
        "summary": "Text program.",
        "policy": "match_reference_text_geometry; reference_layout_over_typography_defaults",
        "reference_text_geometry_path": "reference_text_geometry.json",
        "items": text_items,
    })
    _write_json(root / "ocr_text_quality_report.json", {
        "summary": "OCR text extraction quality report.",
        "mode": "heuristic",
        "ocr_engine": "off",
        "ocr_lang": "en_ch",
        "status": "fallback",
        "text_region_count": len(text_items),
        "low_confidence_count": 0,
        "warnings": ["using_heuristic_text_layer_fallback"],
        "fallback_reason": "ocr_disabled",
    })
    _write_json(root / "text_alignment_report.json", {
        "summary": "Text alignment report.",
        "policy": "reference_alignment_only; no fixed typography failure condition",
        "status": "pass",
        "items": text_alignment_items,
    })
    _write_json(root / "reference_slot_prompt_brief.json", {"summary": "Reference slot prompt briefing.", "mode": "vlm", "slots": prompt_brief_items})
    _write_json(root / "slot_visual_spec.json", {"summary": "Slot visual spec.", "complexity_profile": "reference-dense", "slots": [{
        "slot_id": slot["id"],
        "paper_concept": slot["paper_concept"],
        "complexity_profile": "reference-dense",
        "complexity_kind": "pipeline_module",
        "reference_crop_path": slot["reference_crop_path"],
        "reference_crop_objects": ["paper-specific object", "visible relation"],
        "foreground_subject": "paper-specific object",
        "secondary_objects": ["supporting object", "input-output cue"],
        "micro_details": ["small glyph texture", "internal line detail"],
        "background_fill_elements": ["edge-to-edge colored support", "subtle texture"],
        "scientific_mechanism_detail": "show the concept as a layered mechanism",
        "required_visual_complexity": "dense",
        "forbidden_simplification": ["simple icon", "centered icon", "clean blank background", "single object on white canvas"],
        "object_count_target": 3,
        "detail_score_target": 65,
    } for slot in slots]})
    _write_json(root / "slot_prompt_plan.json", {"summary": "Slot prompt plan.", "mode": "heuristic", "slots": prompt_plan_items})
    (root / "prompts.md").write_text("# Summary\nPrompts.\n", encoding="utf-8")
    _write_json(root / "asset_quality_report.json", {"summary": "Asset quality.", "assets": asset_items})
    _write_json(root / "asset_complexity_report.json", {"summary": "Asset complexity.", "assets": complexity_items})
    _write_json(root / "composition_quality_report.json", {"summary": "Composition quality.", "slots": composition_items, "arrows": [{"arrow_id": item["id"], "segment_count": max(1, len(item["path_percent"]) - 1), "editable_in": "pptx", "render_policy": "ppt_shape_not_image_asset", "route_style": item["route_style"], "line_cap": item["line_cap"], "routing_algorithm": item["routing_algorithm"]} for item in arrows]})
    _write_json(root / "asset_visual_review.json", {"summary": "Asset review.", "status": "pass", "issues": []})
    (root / "alignment_review.md").write_text("# Summary\nAlignment.\n", encoding="utf-8")
    (root / "critic_report.md").write_text("# Summary\nCritic.\n", encoding="utf-8")
    _write_json(root / "visual_critic_iter_0.json", {"summary": "Visual critic.", "status": "pass", "blocking_issues": []})


class ValidatorTests(unittest.TestCase):
    def test_missing_directory_fails(self):
        result = validate_output("Z:/definitely/missing/path")
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])

    def test_minimal_valid_output_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            result = validate_output(root)
            self.assertTrue(result["ok"], result["errors"])

    def test_low_fill_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "asset_quality_report.json").read_text(encoding="utf-8"))
            data["assets"][0]["content_fill_percent"] = 62
            _write_json(root / "asset_quality_report.json", data)
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("fill" in err for err in result["errors"]))

    def test_missing_pptx_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            (root / "editable_composition.pptx").unlink()
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("editable_composition.pptx" in err for err in result["errors"]))

    def test_coarse_ratio_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "figure_program.json").read_text(encoding="utf-8"))
            data["slots"][0]["target_canvas_ratio"] = "3:4"
            _write_json(root / "figure_program.json", data)
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("target_canvas_ratio" in err for err in result["errors"]))

    def test_composition_tile_frame_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "composition_quality_report.json").read_text(encoding="utf-8"))
            data["slots"][0]["tile_frame_added"] = True
            _write_json(root / "composition_quality_report.json", data)
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("tile frame" in err for err in result["errors"]))

    def test_low_composition_fill_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "composition_quality_report.json").read_text(encoding="utf-8"))
            data["slots"][0]["image_slot_area_fill_percent"] = 80
            _write_json(root / "composition_quality_report.json", data)
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("below 95" in err for err in result["errors"]))

    def test_small_reference_matched_font_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "text_program.json").read_text(encoding="utf-8"))
            data["items"][0]["font_size_pt"] = 3.0
            _write_json(root / "text_program.json", data)
            program = json.loads((root / "figure_program.json").read_text(encoding="utf-8"))
            program["text_program"] = data
            _write_json(root / "figure_program.json", program)
            result = validate_output(root)
            self.assertTrue(result["ok"], result["errors"])

    def test_text_alignment_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "text_alignment_report.json").read_text(encoding="utf-8"))
            data["items"][0]["center_delta_percent"] = 0.12
            _write_json(root / "text_alignment_report.json", data)
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("center drift" in err for err in result["errors"]))

    def test_text_without_reference_binding_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_output(root)
            data = json.loads((root / "text_program.json").read_text(encoding="utf-8"))
            data["items"][0]["source_reference_text_id"] = "missing_reference_text"
            _write_json(root / "text_program.json", data)
            result = validate_output(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("source_reference_text_id" in err for err in result["errors"]))


if __name__ == "__main__":
    unittest.main()
