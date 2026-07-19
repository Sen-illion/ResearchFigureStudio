from __future__ import annotations

from typing import Callable

from .utils import write_json


OWNERSHIP_VALUES = {"editable_text_layer", "raster_asset_layer", "decorative_asset_text", "ignore"}
CRITICAL_EDITABLE_ROLES = {
    "panel_title",
    "section_title",
    "arrow_label",
    "legend_label",
    "method_label",
    "modality_label",
    "trait_label",
    "slot_caption",
    "title",
    "subtitle",
}


def _contains_center(container: dict, item: dict) -> bool:
    box = item.get("bbox_percent")
    cbox = container.get("bbox_percent")
    if not isinstance(box, dict) or not isinstance(cbox, dict):
        return False
    cx = float(box["x"]) + float(box["w"]) / 2
    cy = float(box["y"]) + float(box["h"]) / 2
    return (
        float(cbox["x"]) <= cx <= float(cbox["x"]) + float(cbox["w"])
        and float(cbox["y"]) <= cy <= float(cbox["y"]) + float(cbox["h"])
    )


def _slot_ids_containing_text(region: dict, program: dict) -> list[str]:
    return [
        str(slot.get("id") or "")
        for slot in program.get("slots", []) or []
        if isinstance(slot, dict) and str(slot.get("id") or "").strip() and _contains_center(slot, region)
    ]


def _font_size(region: dict) -> float:
    try:
        return float(region.get("font_size_pt") or region.get("raw_font_size_pt") or 0.0)
    except Exception:
        return 0.0


def _decide_heuristic(region: dict, program: dict) -> tuple[str, str]:
    text = str(region.get("text") or "").strip()
    role = str(region.get("role") or "")
    if not text:
        return "ignore", "empty text"
    if _font_size(region) < 4.0 or len(text) <= 1:
        return "decorative_asset_text", "tiny or one-character OCR text is treated as decorative asset text"
    if role in CRITICAL_EDITABLE_ROLES:
        return "editable_text_layer", f"{role} is a critical editable text role"
    containing_slots = _slot_ids_containing_text(region, program)
    target_id = str(region.get("target_id") or "")
    if target_id in containing_slots or (containing_slots and role in {"free_text", "body_label", "annotation"}):
        return "raster_asset_layer", "OCR text is visually inside a slot asset and is not a critical label"
    if role in {"body_label", "annotation", "free_text"}:
        return "editable_text_layer", f"{role} remains editable because it is not owned by a slot asset"
    return "editable_text_layer", "default editable text ownership"


def apply_text_layer_ownership(
    regions: list[dict],
    program: dict,
    mode: str = "heuristic",
    adapter: Callable | None = None,
) -> tuple[list[dict], dict, dict]:
    effective_mode = str(mode or "heuristic").lower()
    raw_overrides = {}
    warnings = []
    if effective_mode in {"vlm", "hybrid"} and adapter:
        try:
            raw = adapter(regions, program)
            records = raw.get("items", []) if isinstance(raw, dict) else raw
            for item in records or []:
                if not isinstance(item, dict):
                    continue
                text_id = str(item.get("text_id") or item.get("id") or "")
                ownership = str(item.get("layer_ownership") or item.get("ownership") or "")
                if text_id and ownership in OWNERSHIP_VALUES:
                    raw_overrides[text_id] = item
        except Exception as exc:
            warnings.append(f"ownership_adapter_failed:{exc}")
            effective_mode = "heuristic"
    elif effective_mode in {"vlm", "hybrid"}:
        warnings.append("ownership_vlm_unavailable_fallback_to_heuristic")
        effective_mode = "heuristic"

    planned_regions = []
    items = []
    for region in regions:
        region = dict(region)
        ownership, reason = _decide_heuristic(region, program)
        override = raw_overrides.get(str(region.get("id") or ""))
        if override:
            ownership = str(override.get("layer_ownership") or override.get("ownership") or ownership)
            reason = str(override.get("reason") or reason)
        if ownership not in OWNERSHIP_VALUES:
            warnings.append(f"invalid_ownership:{region.get('id')}:{ownership}")
            ownership = "editable_text_layer"
            reason = "invalid ownership value fell back to editable text"
        region["layer_ownership"] = ownership
        region["layer_ownership_source"] = "vlm" if override else "heuristic"
        region["layer_ownership_reason"] = reason
        planned_regions.append(region)
        items.append({
            "text_id": region.get("id"),
            "text": region.get("text"),
            "role": region.get("role"),
            "target_id": region.get("target_id"),
            "layer_ownership": ownership,
            "source": region["layer_ownership_source"],
            "reason": reason,
            "included_in_text_program": ownership == "editable_text_layer",
        })

    plan = {
        "summary": "Text layer ownership plan.",
        "mode": mode,
        "effective_mode": effective_mode,
        "items": items,
        "warnings": warnings,
    }
    report = {
        "summary": "Text layer ownership report.",
        "mode": mode,
        "effective_mode": effective_mode,
        "status": "pass" if not warnings else "warning",
        "text_region_count": len(planned_regions),
        "editable_text_count": sum(1 for item in items if item["layer_ownership"] == "editable_text_layer"),
        "raster_asset_text_count": sum(1 for item in items if item["layer_ownership"] == "raster_asset_layer"),
        "decorative_asset_text_count": sum(1 for item in items if item["layer_ownership"] == "decorative_asset_text"),
        "ignored_text_count": sum(1 for item in items if item["layer_ownership"] == "ignore"),
        "warnings": warnings,
        "items": items,
    }
    return planned_regions, plan, report


def write_text_layer_ownership_artifacts(out_dir, plan: dict, report: dict) -> None:
    write_json(out_dir / "text_layer_ownership_plan.json", plan)
    write_json(out_dir / "text_layer_ownership_report.json", report)
