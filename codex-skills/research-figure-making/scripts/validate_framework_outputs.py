#!/usr/bin/env python3
"""
Validate image-rich research framework figure outputs.

Usage:
    python validate_framework_outputs.py <output_dir>

This script checks that a framework figure was assembled from slot-level image
assets instead of being satisfied by a single generated full diagram, screenshot,
or vector-only composition.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
FINAL_NAME_HINTS = ("architecture", "system", "framework", "pipeline", "figure")
MAIN_PPTX_NAME = "editable_composition.pptx"
REQUIRED_PROGRAM_KEYS = (
    "summary",
    "canvas",
    "locator",
    "panels",
    "slots",
    "assets",
    "labels",
    "arrows",
    "groups",
    "export_targets",
)
WHITESPACE_MARKERS = (
    "too_much_whitespace",
    "tiny_centered_subject",
    "large_blank_canvas",
)
COMPLEXITY_BLOCKERS = {
    "too_simple",
    "generic_icon",
    "reference_crop_ignored",
    "single_object_on_blank_background",
    "style_drift",
}
COARSE_RATIO_PRESETS = {"1:1", "4:3", "3:4", "16:9", "9:16", "2:1", "1:2", "3:2", "2:3"}
ARROW_ASSET_ID_TERMS = ("arrow", "dashed_arc", "dashed_arrows", "transition_arrow", "loop_dashed", "graph_connector")
RESOLVED_ACTIONS = {
    "ok",
    "ok_no_crop",
    "accepted",
    "accepted_by_critic",
    "fixed",
    "resolved",
    "regenerated",
    "reprompted",
    "replaced",
    "manual_override_resolved",
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"[OK] {message}")


def find_one(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            return path
    return None


def find_one_pattern(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(p for p in root.glob(pattern) if p.is_file())
        if matches:
            return matches[0]
    return None


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Invalid JSON in {path.name}: {exc}")


def has_front_summary(path: Path) -> bool:
    if path.suffix.lower() == ".json":
        data = read_json(path)
        return isinstance(data, dict) and bool(str(data.get("summary", "")).strip())

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return False
    for line in lines:
        text = line.strip()
        if not text:
            continue
        heading = text.lstrip("#").strip().lower()
        return heading == "summary"
    return False


def require_front_summary(path: Path) -> None:
    if not has_front_summary(path):
        fail(f"{path.name} must start with a Summary section or top-level summary field")


def number_value(item: dict, key: str, item_name: str) -> float:
    if key not in item:
        fail(f"asset_quality_report item {item_name} missing key: {key}")
    try:
        return float(item[key])
    except (TypeError, ValueError):
        fail(f"asset_quality_report item {item_name} key '{key}' must be numeric")


def is_precise_ratio(value: object) -> bool:
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


def color_family(hex_color: str) -> str:
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


def arrow_like_asset_id(value: object) -> bool:
    text = str(value or "").lower()
    return any(term in text for term in ARROW_ASSET_ID_TERMS)


def validate_geometry_item(item: dict, item_name: str) -> None:
    for key in ("bbox_percent", "center_percent", "width_percent", "height_percent", "aspect_ratio_decimal", "aspect_ratio_w_h", "target_pixels_exact"):
        if key not in item:
            fail(f"reference_geometry item {item_name} missing key: {key}")
    if not is_precise_ratio(item.get("aspect_ratio_w_h")):
        fail(f"reference_geometry item {item_name} must use precise decimal aspect_ratio_w_h")


def pixel_pair(value: object) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        return float(value["width"]), float(value["height"])
    except Exception:
        return None


def normalized_action(item: dict) -> str:
    return str(item.get("action", "")).strip().lower()


def is_resolved_action(action: str) -> bool:
    return action in RESOLVED_ACTIONS or action.endswith("_resolved")


def report_items(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("assets", "items", "asset_quality_report"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def validate_asset_quality(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("asset_quality_report.json must be a JSON object with a summary field")
    items = report_items(data)
    if len(items) < 25:
        fail(f"Too few asset quality entries: {len(items)}; expected at least 25")

    for index, item in enumerate(items):
        item_name = str(item.get("asset_id") or item.get("slot_id") or index)
        if "selected_candidate_index" not in item:
            fail(f"asset_quality_report item {item_name} missing selected_candidate_index")
        content_fill = number_value(item, "content_fill_percent", item_name)
        min_fill = number_value(item, "min_content_fill_percent", item_name)
        empty_margin = number_value(item, "empty_margin_percent", item_name)
        max_margin = number_value(item, "max_empty_margin_percent", item_name)

        if min_fill < 85:
            fail(f"asset_quality_report item {item_name} min_content_fill_percent below 85")
        if max_margin > 10:
            fail(f"asset_quality_report item {item_name} max_empty_margin_percent above 10")
        if content_fill < min_fill:
            fail(
                f"asset_quality_report item {item_name} content_fill_percent "
                f"{content_fill:g} below minimum {min_fill:g}"
            )
        if empty_margin > max_margin:
            fail(
                f"asset_quality_report item {item_name} empty_margin_percent "
                f"{empty_margin:g} above maximum {max_margin:g}"
            )

        for key in ("edge_cutoff_status", "ratio_status", "action"):
            if not str(item.get(key, "")).strip():
                fail(f"asset_quality_report item {item_name} missing non-empty key: {key}")

        edge_status = str(item.get("edge_cutoff_status", "")).lower()
        if edge_status not in {"ok", "none", "no_cutoff", "not_cut_off", "complete"}:
            fail(f"asset_quality_report item {item_name} has bad edge_cutoff_status: {edge_status}")

        ratio_status = str(item.get("ratio_status", "")).lower()
        if any(marker in ratio_status for marker in ("fail", "bad", "mismatch", "wrong")):
            fail(f"asset_quality_report item {item_name} has bad ratio_status: {ratio_status}")

        item_text = json.dumps(item, ensure_ascii=False).lower()
        action = normalized_action(item)
        hits = [marker for marker in WHITESPACE_MARKERS if marker in item_text]
        if hits and not is_resolved_action(action):
            fail(
                f"asset_quality_report item {item_name} has unresolved whitespace marker(s): "
                + ", ".join(hits)
            )

    return len(items)


def validate_asset_visual_review(path: Path) -> None:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("asset_visual_review.json must be a JSON object")
    status = str(data.get("status", "")).strip().lower()
    if status in {"needs_regeneration", "blocked", "fail", "failed"}:
        issues = data.get("issues", [])
        fail(f"asset_visual_review.json has unresolved issues: {len(issues) if isinstance(issues, list) else 'unknown'}")


def validate_slot_visual_spec(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("slot_visual_spec.json must be a JSON object")
    slots = data.get("slots")
    if not isinstance(slots, list) or len(slots) < 25:
        fail("slot_visual_spec.json must contain at least 25 slot entries")
    for index, item in enumerate(slots):
        if not isinstance(item, dict):
            fail(f"slot_visual_spec item at index {index} must be an object")
        slot_id = item.get("slot_id", index)
        required = (
            "reference_crop_objects",
            "foreground_subject",
            "secondary_objects",
            "micro_details",
            "background_fill_elements",
            "scientific_mechanism_detail",
            "required_visual_complexity",
            "forbidden_simplification",
        )
        for key in required:
            if key not in item:
                fail(f"slot_visual_spec item {slot_id} missing key: {key}")
        if str(item.get("complexity_kind", "")).lower() != "legend_icon":
            if not isinstance(item.get("secondary_objects"), list) or len(item.get("secondary_objects", [])) < 2:
                fail(f"slot_visual_spec item {slot_id} must include at least 2 secondary_objects")
            if not isinstance(item.get("micro_details"), list) or len(item.get("micro_details", [])) < 2:
                fail(f"slot_visual_spec item {slot_id} must include at least 2 micro_details")
            forbidden_items = item.get("forbidden_simplification", []) if isinstance(item.get("forbidden_simplification"), list) else []
            forbidden = " ".join(str(x).lower() for x in forbidden_items)
            if "simple icon" not in forbidden:
                fail(f"slot_visual_spec item {slot_id} must explicitly forbid simple icon simplification")
    return len(slots)


def validate_asset_complexity(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("asset_complexity_report.json must be a JSON object")
    items = report_items(data)
    if len(items) < 25:
        fail(f"Too few asset complexity entries: {len(items)}; expected at least 25")
    for index, item in enumerate(items):
        item_name = str(item.get("asset_id") or item.get("slot_id") or index)
        for key in ("detail_score", "detail_score_target", "object_count_estimate", "object_count_target", "simple_icon_risk", "reference_crop_match", "style_match", "selected_reason"):
            if key not in item:
                fail(f"asset_complexity_report item {item_name} missing key: {key}")
        try:
            if float(item.get("detail_score")) < float(item.get("detail_score_target")):
                fail(f"asset_complexity_report item {item_name} detail_score below target")
        except (TypeError, ValueError):
            fail(f"asset_complexity_report item {item_name} detail_score fields must be numeric")
        if item.get("simple_icon_risk") is True:
            fail(f"asset_complexity_report item {item_name} simple_icon_risk must be false")
        tags = item.get("complexity_issue_tags", []) if isinstance(item.get("complexity_issue_tags"), list) else []
        blockers = sorted(COMPLEXITY_BLOCKERS.intersection(str(tag) for tag in tags))
        if blockers:
            fail(f"asset_complexity_report item {item_name} has unresolved complexity issue(s): " + ", ".join(blockers))
        if str(item.get("reference_crop_match", "")).startswith("missing"):
            fail(f"asset_complexity_report item {item_name} missing reference crop match")
        if str(item.get("style_match", "")).startswith("missing"):
            fail(f"asset_complexity_report item {item_name} missing style match")
    return len(items)


def validate_visual_critic(path: Path) -> None:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("visual_critic_iter_0.json must be a JSON object")
    status = str(data.get("status", "")).strip().lower()
    if status in {"needs_layout_refinement", "blocked", "fail", "failed"}:
        fail(f"visual_critic_iter_0.json reports unresolved status: {status}")
    blocking = data.get("blocking_issues", [])
    if isinstance(blocking, list) and blocking:
        fail(f"visual_critic_iter_0.json has blocking issues: {len(blocking)}")


def load_slot_count(path: Path) -> int | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("slots", "slot_inventory", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def is_pptx_target(target: object) -> bool:
    if not isinstance(target, dict):
        return False
    target_type = str(target.get("type", "")).lower()
    target_path = str(target.get("path", "")).lower()
    return target_type == "pptx" or target_path.endswith(".pptx")


def is_pptx_editable(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() == "pptx"
    if isinstance(value, list):
        return any(isinstance(item, str) and item.lower() == "pptx" for item in value)
    return False


def validate_editable_objects(data: dict) -> None:
    for key in ("panels", "labels", "arrows", "groups"):
        for index, item in enumerate(data.get(key, [])):
            if not isinstance(item, dict):
                fail(f"figure_program.json {key} item at index {index} must be an object")
            if not is_pptx_editable(item.get("editable_in")):
                item_id = item.get("id", index)
                fail(f"figure_program.json {key} item {item_id} must set editable_in to pptx")


def validate_program(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("figure_program.json must be a JSON object")

    missing = [key for key in REQUIRED_PROGRAM_KEYS if key not in data]
    if missing:
        fail("figure_program.json missing key(s): " + ", ".join(missing))

    for key in ("panels", "slots", "assets", "labels", "arrows"):
        if not isinstance(data.get(key), list):
            fail(f"figure_program.json key '{key}' must be a list")

    if not isinstance(data.get("canvas"), dict):
        fail("figure_program.json key 'canvas' must be an object")
    if not isinstance(data.get("groups"), list):
        fail("figure_program.json key 'groups' must be a list")
    if not isinstance(data.get("export_targets"), list):
        fail("figure_program.json key 'export_targets' must be a list")
    if not any(is_pptx_target(target) for target in data["export_targets"]):
        fail("figure_program.json export_targets must include a PPTX target")
    validate_editable_objects(data)

    slots = data["slots"]
    if len(slots) < 25:
        fail(f"Too few slots in figure_program.json: {len(slots)}; expected at least 25")

    required_slot_keys = {
        "id",
        "paper_concept",
        "bbox_percent",
        "center_percent",
        "width_percent",
        "height_percent",
        "aspect_ratio_decimal",
        "aspect_ratio_w_h",
        "target_canvas_ratio",
        "target_pixels",
        "target_pixels_exact",
        "generation_min_pixels",
        "safe_area_percent",
        "fit_policy",
        "text_policy",
        "asset_id",
        "target_content_fill_percent",
        "min_content_fill_percent",
        "max_empty_margin_percent",
        "composition_type",
        "slot_frame_policy",
        "blank_space_policy",
    }
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            fail(f"figure_program.json slot at index {index} must be an object")
        if arrow_like_asset_id(slot.get("id")) or arrow_like_asset_id(slot.get("asset_id")):
            fail(f"figure_program.json slot {slot.get('id', index)} looks like an arrow/control and must not be an image asset")
        missing = sorted(required_slot_keys - set(slot))
        if missing:
            fail(f"figure_program.json slot {slot.get('id', index)} missing key(s): {', '.join(missing)}")
        fit_policy = str(slot.get("fit_policy", "")).lower()
        if "crop" in fit_policy and "no_crop" not in fit_policy and "without_crop" not in fit_policy:
            fail(f"figure_program.json slot {slot.get('id', index)} uses forbidden crop fit_policy")
        if not is_precise_ratio(slot.get("target_canvas_ratio")):
            fail(f"figure_program.json slot {slot.get('id', index)} uses a coarse/non-decimal target_canvas_ratio")
        target_pixels = pixel_pair(slot.get("target_pixels"))
        exact_pixels = pixel_pair(slot.get("target_pixels_exact"))
        if target_pixels and exact_pixels:
            if abs(target_pixels[0] - exact_pixels[0]) > 0.01 or abs(target_pixels[1] - exact_pixels[1]) > 0.01:
                fail(f"figure_program.json slot {slot.get('id', index)} target_pixels must equal target_pixels_exact; use generation_min_pixels for minimum generation size")
        if str(slot.get("slot_frame_policy", "")).lower() != "frameless_slot":
            fail(f"figure_program.json slot {slot.get('id', index)} must use frameless_slot")
        crop_path = str(slot.get("reference_crop_path", "")).strip()
        if not crop_path:
            fail(f"figure_program.json slot {slot.get('id', index)} missing reference_crop_path")
        if not str(slot.get("reference_style_profile_path", "")).strip():
            fail(f"figure_program.json slot {slot.get('id', index)} missing reference_style_profile_path")
        if not isinstance(slot.get("local_color_token_ids"), list) or not slot.get("local_color_token_ids"):
            fail(f"figure_program.json slot {slot.get('id', index)} missing local_color_token_ids")
        for key in ("visual_spec_id", "complexity_profile", "complexity_kind", "foreground_subject", "secondary_objects", "micro_details", "background_fill_elements", "scientific_mechanism_detail", "required_visual_complexity", "forbidden_simplification"):
            if key not in slot:
                fail(f"figure_program.json slot {slot.get('id', index)} missing visual complexity key: {key}")
        if str(slot.get("complexity_kind", "")).lower() != "legend_icon":
            if not isinstance(slot.get("secondary_objects"), list) or len(slot.get("secondary_objects", [])) < 2:
                fail(f"figure_program.json slot {slot.get('id', index)} must include at least 2 secondary_objects")
            if not isinstance(slot.get("micro_details"), list) or len(slot.get("micro_details", [])) < 2:
                fail(f"figure_program.json slot {slot.get('id', index)} must include at least 2 micro_details")
        slot_id = slot.get("id", index)
        try:
            target_fill = float(slot.get("target_content_fill_percent"))
            min_fill = float(slot.get("min_content_fill_percent"))
            max_margin = float(slot.get("max_empty_margin_percent"))
        except (TypeError, ValueError):
            fail(f"figure_program.json slot {slot_id} fill and margin fields must be numeric")
        if target_fill < 88 or target_fill > 95:
            fail(f"figure_program.json slot {slot_id} target_content_fill_percent must be 88-95")
        if min_fill < 85:
            fail(f"figure_program.json slot {slot_id} min_content_fill_percent must be at least 85")
        if max_margin > 10:
            fail(f"figure_program.json slot {slot_id} max_empty_margin_percent must be at most 10")
        composition_type = str(slot.get("composition_type", "")).lower()
        allowed_types = {"full_frame_icon", "full_bleed_card", "scene_thumbnail", "symbol_cutout"}
        if composition_type not in allowed_types:
            fail(
                f"figure_program.json slot {slot_id} composition_type must be one of: "
                + ", ".join(sorted(allowed_types))
            )

    for asset in data["assets"]:
        if not isinstance(asset, dict):
            fail("figure_program.json assets must be objects")
        if arrow_like_asset_id(asset.get("id")) or arrow_like_asset_id(asset.get("slot_id")):
            fail(f"figure_program.json asset {asset.get('id')} looks like an arrow/control and must not be generated by image2")
        if not str(asset.get("reference_crop_path", "")).strip():
            fail(f"figure_program.json asset {asset.get('id')} missing reference_crop_path")
        if not str(asset.get("visual_spec_id", "")).strip():
            fail(f"figure_program.json asset {asset.get('id')} missing visual_spec_id")

    for arrow in data["arrows"]:
        if not isinstance(arrow, dict):
            fail("figure_program.json arrows must be objects")
        aid = arrow.get("id")
        for key in ("source_id", "target_id", "source_anchor", "target_anchor", "path_percent", "style_token_id", "render_policy"):
            if key not in arrow or not str(arrow.get(key, "")).strip():
                fail(f"figure_program.json arrow/control {aid} missing {key}")
        if not isinstance(arrow.get("path_percent"), list) or len(arrow.get("path_percent", [])) < 2:
            fail(f"figure_program.json arrow/control {aid} must have at least 2 path_percent points")
        for key in ("semantic_role", "route_style", "line_cap", "arrowhead_size"):
            if not str(arrow.get(key, "")).strip():
                fail(f"figure_program.json arrow/control {aid} missing {key}")
        for key in ("routing_algorithm", "route_generation_status"):
            if not str(arrow.get(key, "")).strip():
                fail(f"figure_program.json arrow/control {aid} missing {key}")
        if arrow.get("reference_locked") and arrow.get("reference_path_preserved") is not True:
            fail(f"figure_program.json arrow/control {aid} overrides a locked reference path")
        if str(arrow.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
            fail(f"figure_program.json arrow/control {aid} must render as PPT shape, not image asset")

    style = data.get("style", {}) if isinstance(data.get("style"), dict) else {}
    if not isinstance(style.get("color_tokens"), list) or not style.get("color_tokens"):
        fail("figure_program.json style must include non-empty color_tokens")
    if not str(style.get("reference_style_profile_path", "")).strip():
        fail("figure_program.json style must include reference_style_profile_path")
    if not str(style.get("arrow_style_profile_path", "")).strip():
        fail("figure_program.json style must include arrow_style_profile_path")
    if not str(data.get("text_program_path", "")).strip():
        fail("figure_program.json must include text_program_path")
    if not str(data.get("reference_text_geometry_path", "")).strip():
        fail("figure_program.json must include reference_text_geometry_path")
    if not str(data.get("text_alignment_report_path", "")).strip():
        fail("figure_program.json must include text_alignment_report_path")
    text_program_inline = data.get("text_program")
    if not isinstance(text_program_inline, dict) or not isinstance(text_program_inline.get("items"), list) or not text_program_inline.get("items"):
        fail("figure_program.json must embed non-empty text_program items")
    palette = style.get("reference_palette") or style.get("palette") or []
    distinct = {str(color).upper() for color in palette if str(color).strip()}
    if len(distinct) < 4:
        fail("figure_program.json style must preserve reference-derived palette tokens, not a hardcoded fallback template")

    return len(slots)


def validate_arrow_style_profile(path: Path) -> None:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("arrow_style_profile.json must be a JSON object")
    if str(data.get("reference_priority", "")).lower() != "reference_image_hard_constraint":
        fail("arrow_style_profile.json must keep reference_image_hard_constraint")
    if not isinstance(data.get("style_rules"), dict) or not data.get("style_rules"):
        fail("arrow_style_profile.json must contain style_rules")
    if "reference" not in str(data.get("routing_principle", "")).lower():
        fail("arrow_style_profile.json routing_principle must explicitly preserve the reference image")
    if not str(data.get("routing_algorithm", "")).strip():
        fail("arrow_style_profile.json must record routing_algorithm")
    if "fallback" not in str(data.get("fallback_routing_policy", "")).lower():
        fail("arrow_style_profile.json must record fallback_routing_policy")


def validate_selected_arrow_routes(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("selected_arrow_routes.json must be a JSON object")
    routes = data.get("routes")
    if not isinstance(routes, list):
        fail("selected_arrow_routes.json routes must be a list")
    for index, item in enumerate(routes):
        if not isinstance(item, dict):
            fail(f"selected_arrow_routes item at index {index} must be an object")
        rid = item.get("id", index)
        for key in ("source_id", "target_id", "semantic_role", "route_style", "path_percent", "style_token_id", "stroke_width_pt", "arrowhead_size", "line_cap", "routing_algorithm", "route_generation_status"):
            if key not in item or not str(item.get(key, "")).strip():
                fail(f"selected_arrow_routes item {rid} missing {key}")
        if item.get("reference_locked") and item.get("reference_path_preserved") is not True:
            fail(f"selected_arrow_routes item {rid} overrides a locked reference path")
        if not isinstance(item.get("path_percent"), list) or len(item.get("path_percent", [])) < 2:
            fail(f"selected_arrow_routes item {rid} must have at least 2 path_percent points")
        if str(item.get("route_generation_status", "")).lower() == "aesthetic_tunnel_adjusted":
            if not isinstance(item.get("reference_original_path_percent"), list) or len(item.get("reference_original_path_percent", [])) < 2:
                fail(f"selected_arrow_routes item {rid} missing reference_original_path_percent for aesthetic adjustment")
            if item.get("reference_tunnel_preserved") is not True:
                fail(f"selected_arrow_routes item {rid} left its reference tunnel")
    return len(routes)


def validate_arrow_quality_report(path: Path) -> None:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("arrow_quality_report.json must be a JSON object")
    if str(data.get("status", "")).lower() in {"fail", "failed", "blocked"}:
        fail("arrow_quality_report.json reports failed arrow quality")
    if data.get("reference_path_overrides"):
        fail("arrow_quality_report.json contains reference_path_overrides")
    if data.get("reference_tunnel_violations"):
        fail("arrow_quality_report.json contains reference_tunnel_violations")
    for key in ("total_crossing_count", "average_aesthetic_score"):
        if key not in data:
            fail(f"arrow_quality_report.json missing {key}")


def validate_slot_prompt_brief(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("reference_slot_prompt_brief.json must be a JSON object")
    slots = data.get("slots")
    if not isinstance(slots, list):
        fail("reference_slot_prompt_brief.json key 'slots' must be a list")
    if len(slots) < 25:
        fail(f"Too few slot prompt brief entries: {len(slots)}; expected at least 25")
    for index, item in enumerate(slots):
        if not isinstance(item, dict):
            fail(f"reference_slot_prompt_brief item at index {index} must be an object")
        slot_id = item.get("slot_id", index)
        for key in ("slot_id", "paper_concept", "slot_function", "bbox_percent", "target_canvas_ratio", "composition_type"):
            if not str(item.get(key, "")).strip():
                fail(f"reference_slot_prompt_brief item {slot_id} missing non-empty key: {key}")
        for key in ("reference_crop_path", "reference_style_profile_path"):
            if not str(item.get(key, "")).strip():
                fail(f"reference_slot_prompt_brief item {slot_id} missing non-empty key: {key}")
        if not isinstance(item.get("local_color_token_ids"), list) or not item.get("local_color_token_ids"):
            fail(f"reference_slot_prompt_brief item {slot_id} missing local_color_token_ids")
    return len(slots)


def validate_slot_prompt_plan(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("slot_prompt_plan.json must be a JSON object")
    slots = data.get("slots")
    if not isinstance(slots, list):
        fail("slot_prompt_plan.json key 'slots' must be a list")
    if len(slots) < 25:
        fail(f"Too few slot prompt plan entries: {len(slots)}; expected at least 25")
    required = (
        "slot_id",
        "paper_concept",
        "slot_function",
        "reference_slot_role",
        "reference_shape_language",
        "reference_local_style",
        "reference_prompt_hint",
        "visual_metaphor",
        "image_prompt_core",
    )
    for index, item in enumerate(slots):
        if not isinstance(item, dict):
            fail(f"slot_prompt_plan item at index {index} must be an object")
        slot_id = item.get("slot_id", index)
        for key in required:
            if not str(item.get(key, "")).strip():
                fail(f"slot_prompt_plan item {slot_id} missing non-empty key: {key}")
        for key in ("center_percent", "width_percent", "height_percent", "aspect_ratio_decimal", "aspect_ratio_w_h", "target_canvas_ratio", "target_pixels", "target_pixels_exact", "generation_min_pixels"):
            if key not in item:
                fail(f"slot_prompt_plan item {slot_id} missing precise geometry key: {key}")
        for key in ("reference_crop_path", "reference_style_profile_path"):
            if not str(item.get(key, "")).strip():
                fail(f"slot_prompt_plan item {slot_id} missing non-empty key: {key}")
        if not item.get("reference_crop_used"):
            fail(f"slot_prompt_plan item {slot_id} must record reference_crop_used=true")
        if not isinstance(item.get("local_color_token_ids"), list) or not item.get("local_color_token_ids"):
            fail(f"slot_prompt_plan item {slot_id} missing local_color_token_ids")
        if not is_precise_ratio(item.get("target_canvas_ratio")):
            fail(f"slot_prompt_plan item {slot_id} uses coarse/non-decimal target_canvas_ratio")
        core = str(item.get("image_prompt_core", "")).lower()
        if "90-97" not in core or "10%" not in core:
            fail(f"slot_prompt_plan item {slot_id} image_prompt_core must mention 90-97% fill and 10% margin")
        if "reference_style_profile" not in core or "crop" not in core:
            fail(f"slot_prompt_plan item {slot_id} image_prompt_core must mention reference_style_profile and local crop grounding")
        if str(item.get("complexity_kind", "")).lower() != "legend_icon":
            for phrase in ("dense mini scientific", "2-5", "standalone pictogram"):
                if phrase not in core:
                    fail(f"slot_prompt_plan item {slot_id} image_prompt_core must mention {phrase}")
        for key in ("visual_spec_id", "complexity_kind", "foreground_subject", "secondary_objects", "micro_details", "background_fill_elements", "scientific_mechanism_detail", "required_visual_complexity", "forbidden_simplification"):
            if key not in item:
                fail(f"slot_prompt_plan item {slot_id} missing visual complexity key: {key}")
        must_show = item.get("must_show")
        if not isinstance(must_show, list) or not must_show:
            fail(f"slot_prompt_plan item {slot_id} must include non-empty must_show")
    return len(slots)


def validate_reference_geometry(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("reference_geometry.json must be a JSON object")
    slots = data.get("slots")
    panels = data.get("panels")
    if not isinstance(slots, list) or len(slots) < 25:
        fail("reference_geometry.json must contain at least 25 slot entries")
    if not isinstance(panels, list) or not panels:
        fail("reference_geometry.json must contain panel entries")
    for item in slots:
        if not isinstance(item, dict):
            fail("reference_geometry.json slots must be objects")
        if arrow_like_asset_id(item.get("id")):
            fail(f"reference_geometry slot {item.get('id')} looks like an arrow/control and must be moved to reference_controls.json")
        validate_geometry_item(item, str(item.get("id")))
    for item in panels:
        if not isinstance(item, dict):
            fail("reference_geometry.json panels must be objects")
        validate_geometry_item(item, str(item.get("id")))
    controls = data.get("controls", [])
    if not isinstance(controls, list):
        fail("reference_geometry.json controls must be a list")
    for item in controls:
        if not isinstance(item, dict):
            fail("reference_geometry.json controls must be objects")
        validate_geometry_item(item, str(item.get("id")))
        cid = item.get("id")
        for key in ("source_id", "target_id", "source_anchor", "target_anchor", "path_percent"):
            if key not in item or not str(item.get(key, "")).strip():
                fail(f"reference_geometry control {cid} missing key: {key}")
        if not isinstance(item.get("path_percent"), list) or len(item.get("path_percent", [])) < 2:
            fail(f"reference_geometry control {cid} must have at least 2 path_percent points")
        if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
            fail(f"reference_geometry control {item.get('id')} must render as PPT shape, not image asset")
    palette = data.get("reference_palette")
    if not isinstance(palette, list) or len({str(color).upper() for color in palette}) < 4:
        fail("reference_geometry.json reference_palette must contain at least 4 distinct colors")
    if not isinstance(data.get("color_tokens"), list) or not data.get("color_tokens"):
        fail("reference_geometry.json must contain non-empty color_tokens")
    return len(slots)


def validate_reference_control_candidates(path: Path, root: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("reference_control_candidates.json must be a JSON object")
    if not str(data.get("effective_mode", "")).strip():
        fail("reference_control_candidates.json missing effective_mode")
    for key in ("slot_overlay_path", "control_overlay_path"):
        overlay = str(data.get(key, "")).strip()
        if not overlay:
            fail(f"reference_control_candidates.json missing {key}")
        if not (root / overlay).exists() or (root / overlay).stat().st_size == 0:
            fail(f"reference_control_candidates.json {key} does not point to a non-empty file")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        fail("reference_control_candidates.json candidates must be a list")
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            fail(f"reference_control_candidates item at index {index} must be an object")
        cid = item.get("id", index)
        for key in ("bbox_percent", "center_percent", "width_percent", "height_percent", "path_percent", "editable_in", "render_policy"):
            if key not in item:
                fail(f"reference_control_candidates item {cid} missing key: {key}")
        if arrow_like_asset_id(item.get("asset_id")):
            fail(f"reference_control_candidates item {cid} must not bind to an image asset")
        if str(item.get("editable_in", "")).lower() != "pptx":
            fail(f"reference_control_candidates item {cid} must be editable in PPTX")
        if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
            fail(f"reference_control_candidates item {cid} must use ppt_shape_not_image_asset")
        if not isinstance(item.get("path_percent"), list) or len(item.get("path_percent", [])) < 2:
            fail(f"reference_control_candidates item {cid} must have at least 2 path_percent points")
    return len(candidates)


def validate_reference_controls(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("reference_controls.json must be a JSON object")
    controls = data.get("controls")
    if not isinstance(controls, list):
        fail("reference_controls.json controls must be a list")
    for index, item in enumerate(controls):
        if not isinstance(item, dict):
            fail(f"reference_controls item at index {index} must be an object")
        cid = item.get("id", index)
        for key in ("bbox_percent", "center_percent", "width_percent", "height_percent", "source_id", "target_id", "source_anchor", "target_anchor", "path_percent", "style_token_id", "editable_in", "render_policy"):
            if key not in item or not str(item.get(key, "")).strip():
                fail(f"reference_controls item {cid} missing key: {key}")
        if not isinstance(item.get("path_percent"), list) or len(item.get("path_percent", [])) < 2:
            fail(f"reference_controls item {cid} must have at least 2 path_percent points")
        if str(item.get("editable_in", "")).lower() != "pptx":
            fail(f"reference_controls item {cid} must be editable in PPTX")
        if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
            fail(f"reference_controls item {cid} must use ppt_shape_not_image_asset")
    return len(controls)


def validate_reference_text_geometry(path: Path) -> set[str]:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("reference_text_geometry.json must be a JSON object")
    policy = str(data.get("policy", "")).lower()
    if "publication" in policy and "reference" not in policy:
        fail("reference_text_geometry.json policy must be reference-first, not publication-scale-first")
    regions = data.get("text_regions")
    if not isinstance(regions, list) or not regions:
        fail("reference_text_geometry.json must contain non-empty text_regions")
    ids: set[str] = set()
    for index, item in enumerate(regions):
        if not isinstance(item, dict):
            fail(f"reference_text_geometry item at index {index} must be an object")
        rid = str(item.get("id") or index)
        ids.add(rid)
        for key in ("bbox_percent", "center_percent", "width_percent", "height_percent", "estimated_font_ratio", "color_hex", "role", "target_id"):
            if key not in item:
                fail(f"reference_text_geometry item {rid} missing key: {key}")
        try:
            if float(item.get("width_percent", 0)) <= 0 or float(item.get("height_percent", 0)) <= 0:
                fail(f"reference_text_geometry item {rid} has non-positive size")
            if float(item.get("estimated_font_ratio", 0)) <= 0:
                fail(f"reference_text_geometry item {rid} has non-positive estimated_font_ratio")
        except (TypeError, ValueError):
            fail(f"reference_text_geometry item {rid} size/font fields must be numeric")
        if str(item.get("editable_in", "")).lower() != "pptx":
            fail(f"reference_text_geometry item {rid} must be intended for editable PPTX text")
        color = str(item.get("color_hex", ""))
        if not color.startswith("#") or len(color.strip()) < 7:
            fail(f"reference_text_geometry item {rid} must record reference color_hex")
    return ids


def validate_text_program(path: Path, reference_text_ids: set[str]) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("text_program.json must be a JSON object")
    policy = str(data.get("policy", "")).lower()
    if "paper_double_column" in policy or "minimum_effective_font" in policy:
        fail("text_program.json must not apply fixed publication-scale font thresholds by default")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        fail("text_program.json must contain non-empty items")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"text_program item at index {index} must be an object")
        tid = str(item.get("id") or index)
        for key in ("text", "role", "target_id", "source_reference_text_id", "reference_binding", "bbox_percent", "center_percent", "width_percent", "height_percent", "estimated_font_ratio", "font_size_pt", "color_hex", "editable_in"):
            if key not in item:
                fail(f"text_program item {tid} missing key: {key}")
        if str(item.get("source_reference_text_id") or "") not in reference_text_ids:
            fail(f"text_program item {tid} source_reference_text_id does not exist in reference_text_geometry.json")
        if str(item.get("editable_in", "")).lower() != "pptx":
            fail(f"text_program item {tid} must render as editable PPTX text")
        if "reference" not in str(item.get("reference_binding", "")).lower():
            fail(f"text_program item {tid} must bind to a reference-derived text region")
        try:
            if float(item.get("font_size_pt", 0)) <= 0:
                fail(f"text_program item {tid} font_size_pt must be positive")
            if float(item.get("estimated_font_ratio", 0)) <= 0:
                fail(f"text_program item {tid} estimated_font_ratio must be positive")
        except (TypeError, ValueError):
            fail(f"text_program item {tid} font fields must be numeric")
    return len(items)


def validate_text_alignment_report(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("text_alignment_report.json must be a JSON object")
    policy = str(data.get("policy", "")).lower()
    if "fixed publication" in policy or "paper_double_column" in policy:
        fail("text_alignment_report.json must check reference alignment, not fixed publication font thresholds")
    if str(data.get("status", "")).lower() in {"fail", "failed", "blocked"}:
        fail("text_alignment_report.json reports failed text alignment")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        fail("text_alignment_report.json must contain non-empty items")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"text_alignment_report item at index {index} must be an object")
        tid = str(item.get("label_id") or index)
        if str(item.get("editable_in", "")).lower() != "pptx":
            fail(f"text_alignment_report item {tid} is not editable in PPTX")
        if str(item.get("status", "")).lower() in {"fail", "failed", "blocked"}:
            fail(f"text_alignment_report item {tid} failed reference alignment")
        try:
            if float(item.get("center_delta_percent", 0)) > 0.05:
                fail(f"text_alignment_report item {tid} center drift exceeds reference tolerance")
            if float(item.get("width_delta_percent", 0)) > 0.08:
                fail(f"text_alignment_report item {tid} width drift exceeds reference tolerance")
            if float(item.get("height_delta_percent", 0)) > 0.06:
                fail(f"text_alignment_report item {tid} height drift exceeds reference tolerance")
        except (TypeError, ValueError):
            fail(f"text_alignment_report item {tid} delta fields must be numeric")
        if not str(item.get("source_reference_text_id", "")).strip():
            fail(f"text_alignment_report item {tid} missing source_reference_text_id")
    return len(items)


def validate_reference_style_profile(path: Path) -> None:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("reference_style_profile.json must be a JSON object")
    for key in ("style_summary", "illustration_style", "line_weight", "shadow_style", "corner_radius", "icon_detail_level", "visual_density", "text_policy", "reference_priority"):
        if not str(data.get(key, "")).strip():
            fail(f"reference_style_profile.json missing key: {key}")
    if not isinstance(data.get("color_tokens"), list) or not data.get("color_tokens"):
        fail("reference_style_profile.json must contain non-empty color_tokens")


def validate_composition_quality(path: Path) -> int:
    data = read_json(path)
    if not isinstance(data, dict):
        fail("composition_quality_report.json must be a JSON object")
    slots = data.get("slots")
    if not isinstance(slots, list) or len(slots) < 25:
        fail("composition_quality_report.json must contain at least 25 slot entries")
    for item in slots:
        if not isinstance(item, dict):
            fail("composition_quality_report.json slot entries must be objects")
        sid = item.get("slot_id")
        if item.get("tile_frame_added") is not False:
            fail(f"composition_quality_report slot {sid} added an extra tile frame")
        if item.get("caption_inside_image_slot") is not False:
            fail(f"composition_quality_report slot {sid} has caption inside image slot")
        if str(item.get("slot_frame_policy", "")).lower() != "frameless_slot":
            fail(f"composition_quality_report slot {sid} must use frameless_slot")
        try:
            fill = float(item.get("image_slot_area_fill_percent"))
        except (TypeError, ValueError):
            fail(f"composition_quality_report slot {sid} missing numeric image_slot_area_fill_percent")
        if fill < 95:
            fail(f"composition_quality_report slot {sid} image_slot_area_fill_percent {fill:g} below 95")
    arrows = data.get("arrows")
    if not isinstance(arrows, list):
        fail("composition_quality_report.json must contain arrows list")
    for item in arrows:
        if not isinstance(item, dict):
            fail("composition_quality_report arrow entries must be objects")
        aid = item.get("arrow_id")
        if str(item.get("editable_in", "")).lower() != "pptx":
            fail(f"composition_quality_report arrow {aid} must be editable in PPTX")
        if str(item.get("render_policy", "")).lower() != "ppt_shape_not_image_asset":
            fail(f"composition_quality_report arrow {aid} must render as a PPT shape")
        if not str(item.get("route_style", "")).strip():
            fail(f"composition_quality_report arrow {aid} missing route_style")
        if not str(item.get("line_cap", "")).strip():
            fail(f"composition_quality_report arrow {aid} missing line_cap")
        if not str(item.get("routing_algorithm", "")).strip():
            fail(f"composition_quality_report arrow {aid} missing routing_algorithm")
        try:
            segment_count = int(item.get("segment_count", 0))
        except (TypeError, ValueError):
            fail(f"composition_quality_report arrow {aid} missing numeric segment_count")
        if segment_count < 1:
            fail(f"composition_quality_report arrow {aid} rendered no connector segments")
    return len(slots)


def count_assets(root: Path) -> int:
    asset_dirs = [root / "assets", root / "assets_raw", root / "assets_generated"]
    total = 0
    for directory in asset_dirs:
        if directory.exists() and directory.is_dir():
            total += sum(1 for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if total:
        return total
    return sum(
        1
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in IMAGE_EXTS
        and "contact_sheet" not in p.name.lower()
        and not any(h in p.stem.lower() for h in FINAL_NAME_HINTS)
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        fail("Usage: validate_framework_outputs.py <output_dir>")

    root = Path(argv[1]).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        fail(f"Output directory not found: {root}")

    input_manifest = root / "input_manifest.json"
    if not input_manifest.exists() or input_manifest.stat().st_size == 0:
        fail("Missing non-empty input_manifest.json")
    require_front_summary(input_manifest)
    manifest = read_json(input_manifest)
    if not isinstance(manifest, dict) or not manifest.get("paper_archived") or not manifest.get("reference_archived"):
        fail("input_manifest.json must record paper_archived and reference_archived")
    ok("Found input manifest")

    reference_geometry = root / "reference_geometry.json"
    if not reference_geometry.exists() or reference_geometry.stat().st_size == 0:
        fail("Missing non-empty reference_geometry.json")
    require_front_summary(reference_geometry)
    reference_geometry_count = validate_reference_geometry(reference_geometry)
    ok(f"Validated reference_geometry.json with {reference_geometry_count} slots")

    reference_control_candidates = root / "reference_control_candidates.json"
    if not reference_control_candidates.exists() or reference_control_candidates.stat().st_size == 0:
        fail("Missing non-empty reference_control_candidates.json")
    require_front_summary(reference_control_candidates)
    candidate_count = validate_reference_control_candidates(reference_control_candidates, root)
    ok(f"Validated reference_control_candidates.json with {candidate_count} candidates")

    for overlay_name in ("slot_overlay.png", "reference_control_overlay.png"):
        overlay = root / overlay_name
        if not overlay.exists() or overlay.stat().st_size == 0:
            fail(f"Missing non-empty {overlay_name}")
        ok(f"Found {overlay_name}")

    reference_controls = root / "reference_controls.json"
    if not reference_controls.exists() or reference_controls.stat().st_size == 0:
        fail("Missing non-empty reference_controls.json")
    require_front_summary(reference_controls)
    controls_count = validate_reference_controls(reference_controls)
    ok(f"Validated reference_controls.json with {controls_count} controls")

    arrow_style_profile = root / "arrow_style_profile.json"
    if not arrow_style_profile.exists() or arrow_style_profile.stat().st_size == 0:
        fail("Missing non-empty arrow_style_profile.json")
    require_front_summary(arrow_style_profile)
    validate_arrow_style_profile(arrow_style_profile)
    ok("Validated arrow_style_profile.json")

    selected_arrow_routes = root / "selected_arrow_routes.json"
    if not selected_arrow_routes.exists() or selected_arrow_routes.stat().st_size == 0:
        fail("Missing non-empty selected_arrow_routes.json")
    require_front_summary(selected_arrow_routes)
    route_count = validate_selected_arrow_routes(selected_arrow_routes)
    ok(f"Validated selected_arrow_routes.json with {route_count} routes")

    arrow_quality_report = root / "arrow_quality_report.json"
    if not arrow_quality_report.exists() or arrow_quality_report.stat().st_size == 0:
        fail("Missing non-empty arrow_quality_report.json")
    require_front_summary(arrow_quality_report)
    validate_arrow_quality_report(arrow_quality_report)
    ok("Validated arrow_quality_report.json")

    slot_inventory = find_one(root, ("slot_inventory.json", "slot_inventory.md"))
    if not slot_inventory:
        fail("Missing slot_inventory.json or slot_inventory.md")
    require_front_summary(slot_inventory)
    ok(f"Found slot inventory: {slot_inventory.name}")

    prompts = root / "prompts.md"
    if not prompts.exists() or prompts.stat().st_size == 0:
        fail("Missing non-empty prompts.md")
    require_front_summary(prompts)
    ok("Found prompts.md")

    style_sheet = find_one_pattern(root, ("style_sheet.md", "style_sheet.json"))
    if not style_sheet or style_sheet.stat().st_size == 0:
        fail("Missing non-empty style_sheet.md or style_sheet.json")
    require_front_summary(style_sheet)
    ok(f"Found style sheet: {style_sheet.name}")

    reference_style_profile = root / "reference_style_profile.json"
    if not reference_style_profile.exists() or reference_style_profile.stat().st_size == 0:
        fail("Missing non-empty reference_style_profile.json")
    require_front_summary(reference_style_profile)
    validate_reference_style_profile(reference_style_profile)
    ok("Validated reference_style_profile.json")

    editable_pptx = root / MAIN_PPTX_NAME
    if not editable_pptx.exists() or editable_pptx.stat().st_size == 0:
        fail(f"Missing non-empty {MAIN_PPTX_NAME}")
    ok(f"Found main editable PPTX: {MAIN_PPTX_NAME}")

    layout_plan = root / "layout_plan.json"
    if not layout_plan.exists() or layout_plan.stat().st_size == 0:
        fail("Missing non-empty layout_plan.json")
    require_front_summary(layout_plan)
    layout_data = read_json(layout_plan)
    if not isinstance(layout_data, dict) or not isinstance(layout_data.get("slots"), list) or len(layout_data["slots"]) < 25:
        fail("layout_plan.json must contain at least 25 slots")
    ok(f"Validated layout_plan.json with {len(layout_data['slots'])} slots")

    figure_program = root / "figure_program.json"
    if not figure_program.exists() or figure_program.stat().st_size == 0:
        fail("Missing non-empty figure_program.json")
    require_front_summary(figure_program)
    program_slot_count = validate_program(figure_program)
    ok(f"Validated figure_program.json with {program_slot_count} slots")

    reference_text_geometry = root / "reference_text_geometry.json"
    if not reference_text_geometry.exists() or reference_text_geometry.stat().st_size == 0:
        fail("Missing non-empty reference_text_geometry.json")
    require_front_summary(reference_text_geometry)
    reference_text_ids = validate_reference_text_geometry(reference_text_geometry)
    ok(f"Validated reference_text_geometry.json with {len(reference_text_ids)} text regions")

    text_program = root / "text_program.json"
    if not text_program.exists() or text_program.stat().st_size == 0:
        fail("Missing non-empty text_program.json")
    require_front_summary(text_program)
    text_item_count = validate_text_program(text_program, reference_text_ids)
    ok(f"Validated text_program.json with {text_item_count} editable text items")

    text_alignment_report = root / "text_alignment_report.json"
    if not text_alignment_report.exists() or text_alignment_report.stat().st_size == 0:
        fail("Missing non-empty text_alignment_report.json")
    require_front_summary(text_alignment_report)
    text_alignment_count = validate_text_alignment_report(text_alignment_report)
    ok(f"Validated text_alignment_report.json with {text_alignment_count} text alignment items")

    slot_visual_spec = root / "slot_visual_spec.json"
    if not slot_visual_spec.exists() or slot_visual_spec.stat().st_size == 0:
        fail("Missing non-empty slot_visual_spec.json")
    require_front_summary(slot_visual_spec)
    slot_visual_spec_count = validate_slot_visual_spec(slot_visual_spec)
    ok(f"Validated slot_visual_spec.json with {slot_visual_spec_count} slots")

    reference_slot_prompt_brief = root / "reference_slot_prompt_brief.json"
    if not reference_slot_prompt_brief.exists() or reference_slot_prompt_brief.stat().st_size == 0:
        fail("Missing non-empty reference_slot_prompt_brief.json")
    require_front_summary(reference_slot_prompt_brief)
    prompt_brief_count = validate_slot_prompt_brief(reference_slot_prompt_brief)
    ok(f"Validated reference_slot_prompt_brief.json with {prompt_brief_count} slots")

    slot_prompt_plan = root / "slot_prompt_plan.json"
    if not slot_prompt_plan.exists() or slot_prompt_plan.stat().st_size == 0:
        fail("Missing non-empty slot_prompt_plan.json")
    require_front_summary(slot_prompt_plan)
    prompt_plan_count = validate_slot_prompt_plan(slot_prompt_plan)
    ok(f"Validated slot_prompt_plan.json with {prompt_plan_count} slots")

    crop_dir = root / "reference_slot_crops"
    if not crop_dir.exists() or not crop_dir.is_dir():
        fail("Missing reference_slot_crops directory")
    prompt_plan_data = read_json(slot_prompt_plan)
    for item in prompt_plan_data.get("slots", []):
        crop_path = root / str(item.get("reference_crop_path", ""))
        if not crop_path.exists() or crop_path.stat().st_size == 0:
            fail(f"Missing non-empty local reference crop for slot {item.get('slot_id')}: {item.get('reference_crop_path')}")
    ok("Validated local reference crops for all prompt-plan slots")

    asset_quality_report = root / "asset_quality_report.json"
    if not asset_quality_report.exists() or asset_quality_report.stat().st_size == 0:
        fail("Missing non-empty asset_quality_report.json")
    require_front_summary(asset_quality_report)
    asset_quality_count = validate_asset_quality(asset_quality_report)
    ok(f"Validated asset quality report with {asset_quality_count} entries")

    asset_complexity_report = root / "asset_complexity_report.json"
    if not asset_complexity_report.exists() or asset_complexity_report.stat().st_size == 0:
        fail("Missing non-empty asset_complexity_report.json")
    require_front_summary(asset_complexity_report)
    asset_complexity_count = validate_asset_complexity(asset_complexity_report)
    ok(f"Validated asset complexity report with {asset_complexity_count} entries")

    composition_quality = root / "composition_quality_report.json"
    if not composition_quality.exists() or composition_quality.stat().st_size == 0:
        fail("Missing non-empty composition_quality_report.json")
    require_front_summary(composition_quality)
    composition_count = validate_composition_quality(composition_quality)
    ok(f"Validated composition quality report with {composition_count} entries")

    asset_visual_review = root / "asset_visual_review.json"
    if not asset_visual_review.exists() or asset_visual_review.stat().st_size == 0:
        fail("Missing non-empty asset_visual_review.json")
    require_front_summary(asset_visual_review)
    validate_asset_visual_review(asset_visual_review)
    ok("Validated asset visual review")

    contact_sheet = root / "asset_contact_sheet.png"
    if not contact_sheet.exists() or contact_sheet.stat().st_size == 0:
        fail("Missing asset_contact_sheet.png")
    ok("Found asset contact sheet")

    candidate_contact_sheet = root / "asset_candidate_contact_sheet.png"
    if not candidate_contact_sheet.exists() or candidate_contact_sheet.stat().st_size == 0:
        fail("Missing asset_candidate_contact_sheet.png")
    ok("Found candidate asset contact sheet")

    visual_critic = root / "visual_critic_iter_0.json"
    if not visual_critic.exists() or visual_critic.stat().st_size == 0:
        fail("Missing non-empty visual_critic_iter_0.json")
    require_front_summary(visual_critic)
    validate_visual_critic(visual_critic)
    ok("Validated visual critic report")

    review = root / "alignment_review.md"
    if not review.exists() or review.stat().st_size == 0:
        fail("Missing non-empty alignment_review.md")
    require_front_summary(review)
    ok("Found alignment review")

    critic_report = find_one_pattern(root, ("critic_report.md", "critic_report.json"))
    if not critic_report or critic_report.stat().st_size == 0:
        fail("Missing non-empty critic_report.md or critic_report.json")
    require_front_summary(critic_report)
    ok(f"Found critic report: {critic_report.name}")

    assets = count_assets(root)
    if assets < 25:
        fail(f"Too few generated image assets: {assets}; expected at least 25")
    ok(f"Generated image assets: {assets}")

    slot_count = load_slot_count(slot_inventory)
    if slot_count is not None and slot_count < 25:
        fail(f"Too few slots in slot inventory: {slot_count}; expected at least 25")
    if slot_count is not None:
        ok(f"Slot count: {slot_count}")

    text_blob = ""
    for path in (
        root / "asset_quality_report.json",
        root / "asset_visual_review.json",
        root / "layout_plan.json",
        root / "reference_geometry.json",
        root / "reference_control_candidates.json",
        root / "reference_controls.json",
        root / "reference_text_geometry.json",
        root / "text_program.json",
        root / "text_alignment_report.json",
        root / "arrow_style_profile.json",
        root / "selected_arrow_routes.json",
        root / "arrow_quality_report.json",
        root / "reference_style_profile.json",
        root / "composition_quality_report.json",
        root / "visual_critic_iter_0.json",
        slot_visual_spec,
        asset_complexity_report,
        review,
        prompts,
        style_sheet,
        figure_program,
        reference_slot_prompt_brief,
        slot_prompt_plan,
        critic_report,
    ):
        if path.exists() and path.is_file():
            try:
                text_blob += "\n" + path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

    forbidden_markers = (
        "ok_after_crop",
        "cover-crop",
        "fill-crop",
        "forced crop",
        "crop-to-ratio",
        "single full diagram",
        "vector-only",
        "svg-only",
        "baked labels",
        "baked-in labels",
        "baked into svg",
        "flattened full-figure screenshot",
    )
    hits = [marker for marker in forbidden_markers if marker.lower() in text_blob.lower()]
    if hits:
        fail("Found forbidden output markers: " + ", ".join(hits))

    ok("No forbidden crop/vector-only markers found")
    ok("Framework output validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
