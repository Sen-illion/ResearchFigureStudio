from __future__ import annotations

from pathlib import Path
from .utils import ratio_string, write_json


def _center(bbox: dict) -> tuple[float, float]:
    return float(bbox["x"]) + float(bbox["w"]) / 2, float(bbox["y"]) + float(bbox["h"]) / 2


def _edge_path(source: dict | None, target: dict | None) -> list[list[float]]:
    if not source or not target:
        return []
    sbox = source.get("bbox_percent") if isinstance(source.get("bbox_percent"), dict) else None
    tbox = target.get("bbox_percent") if isinstance(target.get("bbox_percent"), dict) else None
    if not sbox or not tbox:
        return []
    sx, sy = _center(sbox)
    tx, ty = _center(tbox)
    dx = tx - sx
    dy = ty - sy
    if abs(dx) >= abs(dy):
        start = [float(sbox["x"]) + (float(sbox["w"]) if dx >= 0 else 0.0), sy]
        end = [float(tbox["x"]) if dx >= 0 else float(tbox["x"]) + float(tbox["w"]), ty]
    else:
        start = [sx, float(sbox["y"]) + (float(sbox["h"]) if dy >= 0 else 0.0)]
        end = [tx, float(tbox["y"]) if dy >= 0 else float(tbox["y"]) + float(tbox["h"])]
    return [[round(start[0], 4), round(start[1], 4)], [round(end[0], 4), round(end[1], 4)]]


def _control_record_from_arrow(arrow: dict) -> dict:
    points = arrow.get("path_percent") if isinstance(arrow.get("path_percent"), list) else []
    xs = [float(point[0]) for point in points if isinstance(point, list) and len(point) >= 2]
    ys = [float(point[1]) for point in points if isinstance(point, list) and len(point) >= 2]
    if not xs or not ys:
        xs, ys = [0.0, 0.001], [0.0, 0.001]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    w = max(0.001, x1 - x0)
    h = max(0.001, y1 - y0)
    return {
        "id": arrow.get("id"),
        "type": "ppt_control",
        "control_kind": arrow.get("control_kind") or arrow.get("type") or "straight_arrow",
        "bbox_percent": {"x": round(x0, 4), "y": round(y0, 4), "w": round(w, 4), "h": round(h, 4)},
        "center_percent": {"x": round(x0 + w / 2, 4), "y": round(y0 + h / 2, 4)},
        "width_percent": round(w, 4),
        "height_percent": round(h, 4),
        "aspect_ratio_decimal": round(w / max(h, 0.001), 3),
        "aspect_ratio_w_h": ratio_string(w, h),
        "source_id": arrow.get("source_id") or arrow.get("source"),
        "target_id": arrow.get("target_id") or arrow.get("target"),
        "source_anchor": arrow.get("source_anchor") or "auto",
        "target_anchor": arrow.get("target_anchor") or "auto",
        "path_percent": points,
        "style_token_id": arrow.get("style_token_id"),
        "candidate_label": arrow.get("candidate_label"),
        "detected_by": arrow.get("detected_by"),
        "binding_source": arrow.get("binding_source"),
        "confidence": arrow.get("confidence"),
        "editable_in": "pptx",
        "render_policy": "ppt_shape_not_image_asset",
    }


def build_figure_program(paper_brief: dict, inventory: dict, style: dict, out_dir: str | Path, layout_plan: dict) -> dict:
    panels = layout_plan["panels"]
    slots = layout_plan["slots"]
    objects_by_id = {item.get("id"): item for item in panels + slots if isinstance(item, dict)}
    color_tokens = style.get("color_tokens", []) if isinstance(style.get("color_tokens"), list) else []
    default_arrow_token = next((str(item.get("token_id")) for item in color_tokens if "arrow" in str(item.get("usage", "")).lower() or "connector" in str(item.get("usage", "")).lower()), "")
    if not default_arrow_token and color_tokens:
        default_arrow_token = str(color_tokens[0].get("token_id") or "")
    arrows = []
    for item in layout_plan.get("arrows", []):
        if not isinstance(item, dict):
            continue
        arrow = dict(item)
        arrow["source"] = arrow.get("source") or arrow.get("source_id") or ""
        arrow["target"] = arrow.get("target") or arrow.get("target_id") or ""
        arrow["source_id"] = arrow.get("source_id") or arrow.get("source")
        arrow["target_id"] = arrow.get("target_id") or arrow.get("target")
        arrow["source_anchor"] = arrow.get("source_anchor") or "auto"
        arrow["target_anchor"] = arrow.get("target_anchor") or "auto"
        arrow["editable_in"] = "pptx"
        arrow["render_policy"] = arrow.get("render_policy") or "ppt_shape_not_image_asset"
        arrow["style_token_id"] = arrow.get("style_token_id") or default_arrow_token
        if not arrow.get("path_percent"):
            arrow["path_percent"] = _edge_path(objects_by_id.get(arrow["source"]), objects_by_id.get(arrow["target"]))
        arrows.append(arrow)

    assets = [
        {
            "id": slot["asset_id"],
            "slot_id": slot["id"],
            "path": f"assets/{slot['asset_id']}.png",
            "source": "slot_image_generation",
            "fit_policy": "contain_no_crop",
            "z_index": slot.get("z_index", 20),
            "reference_crop_path": slot.get("reference_crop_path"),
            "local_color_token_ids": slot.get("local_color_token_ids", []),
            "style_profile_path": style.get("reference_style_profile_path", "reference_style_profile.json"),
        }
        for slot in slots
    ]

    labels = []
    for panel in panels:
        labels.append({
            "id": f"label_{panel['id']}",
            "text": panel["title"],
            "target_id": panel["id"],
            "role": "panel_title",
            "editable_in": "pptx",
        })
    for slot in slots:
        labels.append({
            "id": f"label_{slot['id']}",
            "text": slot["paper_concept"],
            "target_id": slot["id"],
            "role": "slot_caption",
            "editable_in": "pptx",
        })

    canvas_ratio = float(inventory.get("canvas_aspect_ratio") or 16 / 9)
    height_in = 7.5
    width_in = max(13.333, min(16.0, height_in * canvas_ratio))
    program = {
        "summary": "Structured figure program used as the only layout source for PPT composition.",
        "canvas": {"width_in": round(width_in, 3), "height_in": height_in, "ratio": round(canvas_ratio, 4), "background": "#FFFFFF"},
        "paper_brief": {
            "title_guess": paper_brief.get("title_guess"),
            "figure_goal": paper_brief.get("figure_goal"),
            "variables": paper_brief.get("variables", []),
        },
        "style": {
            "palette": style.get("palette", []),
            "reference_palette": style.get("reference_palette", []),
            "color_tokens": style.get("color_tokens", []),
            "reference_style_profile_path": style.get("reference_style_profile_path", "reference_style_profile.json"),
            "panel_styles": style.get("panel_styles", {}),
            "slot_frame_policy": style.get("slot_frame_policy", "frameless_slot"),
            "picture_fill_policy": style.get("picture_fill_policy", "direct_full_slot_contain_no_tile"),
        },
        "locator": {
            "mode": layout_plan.get("locator_mode"),
            "reference_path": layout_plan.get("reference_path") or inventory.get("reference_path"),
        },
        "panels": panels,
        "slots": slots,
        "assets": assets,
        "labels": labels,
        "arrows": arrows,
        "control_shapes": layout_plan.get("control_shapes", []) or [_control_record_from_arrow(arrow) for arrow in arrows],
        "ppt_shapes": layout_plan.get("ppt_shapes", []),
        "text_regions": layout_plan.get("text_regions", []),
        "groups": [
            {
                "id": "top_pipeline",
                "members": [p["id"] for p in panels if p["id"] != "shared_resource_library"],
                "editable_in": "pptx",
            },
            {
                "id": "shared_resources",
                "members": [p["id"] for p in panels if p["id"] == "shared_resource_library"],
                "editable_in": "pptx",
            },
        ],
        "export_targets": [
            {"type": "pptx", "path": "editable_composition.pptx", "role": "main_editable_source"},
            {"type": "pdf", "path": "review.pdf", "role": "review_export"},
            {"type": "png", "path": "final_600dpi.png", "role": "publication_preview"},
        ],
    }
    controls_doc = {
        "summary": "Reference arrows, connectors, loops, and other non-image controls measured for editable PPT rendering.",
        "reference_path": layout_plan.get("reference_path") or inventory.get("reference_path"),
        "candidate_path": inventory.get("reference_control_candidates_path") or "reference_control_candidates.json",
        "slot_overlay_path": inventory.get("slot_overlay_path"),
        "control_overlay_path": inventory.get("reference_control_overlay_path"),
        "requested_mode": (inventory.get("control_localizer") or {}).get("requested_mode"),
        "effective_mode": (inventory.get("control_localizer") or {}).get("effective_mode"),
        "controls": [_control_record_from_arrow(arrow) for arrow in arrows],
        "ppt_arrows": [_control_record_from_arrow(arrow) for arrow in arrows],
        "render_policy": "ppt_shape_not_image_asset",
    }
    write_json(Path(out_dir) / "reference_controls.json", controls_doc)
    write_json(Path(out_dir) / "figure_program.json", program)
    return program

