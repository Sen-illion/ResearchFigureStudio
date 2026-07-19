from __future__ import annotations

import json
from pathlib import Path

from .layout_semantic_planner import ASSET_TYPES
from .utils import write_json


ASSET_POLICIES = {"reference_crop", "api_generate", "placeholder", "ppt_shape", "editable_text", "ppt_connector", "ignore"}
NON_RASTER_POLICIES = {"ppt_shape", "editable_text", "ppt_connector", "ignore"}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _valid_bbox(bbox: dict | None) -> bool:
    if not isinstance(bbox, dict):
        return False
    try:
        x = float(bbox["x"])
        y = float(bbox["y"])
        w = float(bbox["w"])
        h = float(bbox["h"])
    except Exception:
        return False
    return 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1.0001 and y + h <= 1.0001


def _duplicate_ids(items: list[dict]) -> list[str]:
    seen = set()
    duplicates = []
    for item in items:
        item_id = str(item.get("id") or item.get("slot_id") or "")
        if not item_id:
            continue
        if item_id in seen and item_id not in duplicates:
            duplicates.append(item_id)
        seen.add(item_id)
    return duplicates


def _path_changed(raw_arrow: dict | None, routed_arrow: dict | None) -> bool:
    if not raw_arrow or not routed_arrow:
        return False
    raw_path = raw_arrow.get("path_percent")
    routed_path = routed_arrow.get("path_percent")
    if not isinstance(raw_path, list) or not isinstance(routed_path, list):
        return False
    return raw_path != routed_path


def build_rebuild_vlm_validation_report(
    out_dir: str | Path,
    reference_geometry: dict,
    reference_controls: dict,
    semantic_report: dict,
    asset_summary: dict | None = None,
    text_role_report: dict | None = None,
    raw_controls_report: dict | None = None,
    text_intelligence_report: dict | None = None,
) -> dict:
    panels = [item for item in reference_geometry.get("panels", []) if isinstance(item, dict)]
    slots = [item for item in reference_geometry.get("slots", []) if isinstance(item, dict)]
    cards = [item for item in reference_geometry.get("cards", []) if isinstance(item, dict)]
    legends = [item for item in reference_geometry.get("legend_regions", []) if isinstance(item, dict)]
    arrows = [item for item in reference_controls.get("arrows", []) if isinstance(item, dict)]
    raw_controls = raw_controls_report if isinstance(raw_controls_report, dict) else {}
    raw_arrows = [item for item in raw_controls.get("arrows", []) if isinstance(item, dict)]
    semantic_slots = [item for item in semantic_report.get("slots", []) if isinstance(item, dict)]
    slot_ids = {str(item.get("id")) for item in slots}

    invalid_layout_bboxes = [
        str(item.get("id") or "")
        for item in panels + slots + cards + legends
        if not _valid_bbox(item.get("bbox_percent"))
    ]
    clamped_bboxes = [
        str(item.get("id") or "")
        for item in panels + slots + cards + legends
        if bool(item.get("bbox_was_clamped"))
    ]
    cards_missing_style = [
        str(item.get("id") or "")
        for item in cards
        if not str(item.get("stroke_color") or "").strip()
        or not str(item.get("stroke_width_pt") or "").strip()
        or not str(item.get("dash_style") or "").strip()
        or not str(item.get("fill_color") or "").strip()
        or not str(item.get("shape_kind") or "").strip()
    ]
    invalid_arrows = []
    for arrow in arrows:
        source = str(arrow.get("source_id") or arrow.get("source") or "")
        target = str(arrow.get("target_id") or arrow.get("target") or "")
        path = arrow.get("path_percent")
        if source not in slot_ids or target not in slot_ids or not isinstance(path, list) or len(path) < 2:
            invalid_arrows.append(str(arrow.get("id") or ""))
    invalid_semantic_types = [
        str(item.get("slot_id") or "")
        for item in semantic_slots
        if str(item.get("asset_type") or "") not in ASSET_TYPES
    ]
    prompt_subject_missing = [
        str(item.get("slot_id") or "")
        for item in semantic_slots
        if not str(item.get("prompt_subject") or "").strip()
    ]
    warnings = []
    if invalid_layout_bboxes:
        warnings.append(f"{len(invalid_layout_bboxes)} invalid layout bbox(es)")
    if clamped_bboxes:
        warnings.append(f"{len(clamped_bboxes)} VLM bbox(es) were clamped")
    if cards_missing_style:
        warnings.append(f"{len(cards_missing_style)} card frame(s) missing style fields")
    if invalid_arrows:
        warnings.append(f"{len(invalid_arrows)} invalid arrow(s)")
    if invalid_semantic_types:
        warnings.append(f"{len(invalid_semantic_types)} invalid semantic asset type(s)")
    if prompt_subject_missing:
        warnings.append(f"{len(prompt_subject_missing)} slot prompt_subject value(s) missing")
    render_styles = [str(arrow.get("render_style") or "line_connector") for arrow in arrows]
    render_style_counts = {style: render_styles.count(style) for style in sorted(set(render_styles))}
    raw_by_id = {str(item.get("id") or ""): item for item in raw_arrows}
    routed_path_changed_count = sum(1 for arrow in arrows if _path_changed(raw_by_id.get(str(arrow.get("id") or "")), arrow))
    text_role = text_role_report or {}
    if text_role.get("status") == "fallback_to_heuristic":
        warnings.append("text role VLM fell back to heuristic")
    text_intelligence = text_intelligence_report or {}
    if text_intelligence.get("status") == "fallback_to_heuristic":
        warnings.append("text intelligence VLM fell back to heuristic")
    out_path = Path(out_dir)
    logic_plan = _read_json(out_path / "reference_logic_plan.json")
    layer_plan = _read_json(out_path / "reference_layer_plan.json")
    generation_plan = _read_json(out_path / "reference_generation_plan.json")
    flow_graph = _read_json(out_path / "reference_flow_graph.json")
    policies = [item for item in generation_plan.get("asset_policies", []) or [] if isinstance(item, dict)]
    invalid_policies = [
        str(item.get("slot_id") or item.get("object_id") or item.get("id") or "")
        for item in policies
        if str(item.get("policy") or item.get("asset_source_policy") or "") not in ASSET_POLICIES
    ]
    asset_records = [item for item in (asset_summary or {}).get("assets", []) or [] if isinstance(item, dict)]
    non_raster_assets = [
        str(item.get("slot_id") or item.get("asset_id") or "")
        for item in asset_records
        if str(item.get("asset_source_policy") or "") in NON_RASTER_POLICIES
    ]
    if invalid_policies:
        warnings.append(f"{len(invalid_policies)} invalid asset source policy value(s)")
    if non_raster_assets:
        warnings.append(f"{len(non_raster_assets)} non-raster policy asset(s) were generated")
    flow_edges = [item for item in flow_graph.get("edges", []) or [] if isinstance(item, dict)]
    object_ids = {str(item.get("id")) for item in panels + cards + slots if isinstance(item, dict)}
    unbound_flow_edges = [
        str(edge.get("id") or "")
        for edge in flow_edges
        if str(edge.get("source_id") or "") not in object_ids or str(edge.get("target_id") or "") not in object_ids
    ]

    report = {
        "summary": "VLM adapter validation report for rebuild-editable.",
        "status": "pass" if not warnings else "warning",
        "warnings": warnings,
        "layout": {
            "layout_mode": reference_geometry.get("layout_mode"),
            "vlm_status": reference_geometry.get("vlm_status"),
            "vlm_model": reference_geometry.get("vlm_model"),
            "panel_count": len(panels),
            "card_count": len(cards),
            "cards_missing_style_count": len(cards_missing_style),
            "cards_missing_style_ids": cards_missing_style,
            "slot_count": len(slots),
            "legend_region_count": len(legends),
            "invalid_bbox_ids": invalid_layout_bboxes,
            "clamped_bbox_ids": clamped_bboxes,
            "duplicate_panel_ids": _duplicate_ids(panels),
            "duplicate_slot_ids": _duplicate_ids(slots),
            "warnings": reference_geometry.get("warnings", []),
        },
        "control": {
            "control_mode": reference_controls.get("mode"),
            "vlm_status": reference_controls.get("vlm_status"),
            "vlm_model": reference_controls.get("vlm_model"),
            "raw_controls_path": reference_controls.get("raw_controls_path"),
            "routing_applied": reference_controls.get("routing_applied"),
            "arrow_style_mode": reference_controls.get("arrow_style_mode"),
            "raw_arrow_count": len(raw_arrows) if raw_arrows else reference_controls.get("raw_arrow_count", 0),
            "routed_arrow_count": len(arrows),
            "arrow_count": len(arrows),
            "invalid_arrow_ids": invalid_arrows,
            "missing_or_invalid_source_target_count": len(invalid_arrows),
            "arrows_with_path_count": sum(1 for arrow in arrows if isinstance(arrow.get("path_percent"), list) and len(arrow.get("path_percent")) >= 2),
            "dashed_arrow_count": sum(1 for arrow in arrows if str(arrow.get("dash_style") or arrow.get("line_pattern") or "").lower() in {"dash", "dashed"}),
            "block_arrow_count": render_style_counts.get("filled_block_arrow", 0),
            "branch_arrow_count": render_style_counts.get("branch_line_connector", 0),
            "routed_path_changed_count": routed_path_changed_count if raw_arrows else reference_controls.get("routed_path_changed_count", 0),
            "render_style_counts": render_style_counts,
            "arrows_with_render_style_count": sum(1 for arrow in arrows if arrow.get("render_style")),
            "flow_graph_used": bool(reference_controls.get("flow_graph_used")),
            "flow_graph_edge_count": reference_controls.get("flow_graph_edge_count", 0),
            "invalid_flow_edge_count": reference_controls.get("invalid_flow_edge_count", 0),
            "invalid_flow_edge_ids": reference_controls.get("invalid_flow_edge_ids", []),
            "warnings": reference_controls.get("warnings", []),
        },
        "text_role": {
            "mode": text_role.get("mode"),
            "effective_mode": text_role.get("effective_mode"),
            "status": text_role.get("status"),
            "model": text_role.get("model"),
            "fallback_count": text_role.get("fallback_count", 0),
            "fallback_reason": text_role.get("fallback_reason"),
            "warnings": text_role.get("warnings", []),
        },
        "text_intelligence": {
            "mode": text_intelligence.get("mode"),
            "effective_mode": text_intelligence.get("effective_mode"),
            "status": text_intelligence.get("status"),
            "model": text_intelligence.get("model"),
            "text_count": text_intelligence.get("text_count", 0),
            "relation_count": len(text_intelligence.get("text_relations", []) or []),
            "fallback_count": text_intelligence.get("fallback_count", 0),
            "fallback_reason": text_intelligence.get("fallback_reason"),
            "warnings": text_intelligence.get("warnings", []),
        },
        "design_plan": {
            "mode": logic_plan.get("mode"),
            "effective_mode": logic_plan.get("effective_mode"),
            "status": logic_plan.get("status") or ("missing" if not logic_plan else None),
            "model": logic_plan.get("model"),
            "fallback_reason": logic_plan.get("fallback_reason"),
            "fallback_reason_present": bool(logic_plan.get("fallback_reason")) if logic_plan else False,
            "layer_count": layer_plan.get("layer_count", len(layer_plan.get("layers", []) or [])),
            "asset_policy_count": len(policies),
            "invalid_asset_policy_ids": invalid_policies,
            "policy_coverage_percent": round(len(policies) / max(len(slots), 1) * 100, 2),
            "non_raster_policy_asset_ids": non_raster_assets,
            "flow_graph_edge_count": len(flow_edges),
            "unbound_flow_edge_ids": unbound_flow_edges,
        },
        "semantic": {
            "semantic_vlm_status": semantic_report.get("semantic_vlm_status"),
            "vlm_model": semantic_report.get("vlm_model"),
            "slot_count": len(semantic_slots),
            "invalid_asset_type_ids": invalid_semantic_types,
            "prompt_subject_missing_ids": prompt_subject_missing,
            "prompt_subject_coverage_percent": round((len(semantic_slots) - len(prompt_subject_missing)) / max(len(semantic_slots), 1) * 100, 2),
            "nearby_text_usage_percent": round(sum(1 for item in semantic_slots if item.get("nearby_text")) / max(len(semantic_slots), 1) * 100, 2),
            "warnings": semantic_report.get("warnings", []),
        },
        "asset_generation": {
            "asset_mode": (asset_summary or {}).get("asset_mode"),
            "api_requests_attempted": (asset_summary or {}).get("api_requests_attempted", 0),
        },
    }
    write_json(Path(out_dir) / "rebuild_vlm_validation_report.json", report)
    return report
