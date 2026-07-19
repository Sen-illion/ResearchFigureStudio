from __future__ import annotations

from pathlib import Path
from typing import Callable


ASSET_TYPES = {
    "character",
    "document_stack",
    "chart_card",
    "tool_icon",
    "tool_combo",
    "device",
    "screenshot_card",
    "legend_marker",
    "thin_tool",
    "generic",
}


def _center(box: dict) -> tuple[float, float]:
    return float(box["x"]) + float(box["w"]) / 2, float(box["y"]) + float(box["h"]) / 2


def _distance(a: dict, b: dict) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _text_regions(text_geometry: dict | None) -> list[dict]:
    if not isinstance(text_geometry, dict):
        return []
    items = text_geometry.get("text_regions") or text_geometry.get("regions") or []
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("bbox_percent"), dict)]


def _nearby_text(slot: dict, text_regions: list[dict]) -> list[str]:
    box = slot["bbox_percent"]
    ranked = sorted(text_regions, key=lambda region: _distance(box, region["bbox_percent"]))
    return [str(item.get("raw_text") or item.get("text") or "").strip() for item in ranked[:3] if str(item.get("raw_text") or item.get("text") or "").strip()]


def _text_by_id(text_regions: list[dict]) -> dict[str, str]:
    return {
        str(item.get("id") or ""): str(item.get("raw_text") or item.get("text") or "").strip()
        for item in text_regions
        if str(item.get("id") or "").strip() and str(item.get("raw_text") or item.get("text") or "").strip()
    }


def _relation_text_by_target(text_intelligence: dict | None, text_regions: list[dict]) -> dict[str, list[str]]:
    if not isinstance(text_intelligence, dict):
        return {}
    text_lookup = _text_by_id(text_regions)
    by_target: dict[str, list[str]] = {}
    allowed = {"label_for_visual_object", "caption_for", "legend_label_for"}
    for relation in text_intelligence.get("text_relations", []) or []:
        if not isinstance(relation, dict):
            continue
        if str(relation.get("relation") or "") not in allowed:
            continue
        target_id = str(relation.get("target_object_id") or "")
        text = text_lookup.get(str(relation.get("source_text_id") or ""))
        if target_id and text:
            by_target.setdefault(target_id, []).append(text)
    return {key: sorted(set(values)) for key, values in by_target.items()}


def _panel_context(slot: dict, panels: list[dict]) -> str:
    panel_id = str(slot.get("panel_id") or "")
    for panel in panels:
        if str(panel.get("id")) == panel_id:
            return str(panel.get("title") or panel.get("id") or "")
    box = slot["bbox_percent"]
    containing = []
    sx, sy = _center(box)
    for panel in panels:
        pbox = panel.get("bbox_percent")
        if not isinstance(pbox, dict):
            continue
        if float(pbox["x"]) <= sx <= float(pbox["x"]) + float(pbox["w"]) and float(pbox["y"]) <= sy <= float(pbox["y"]) + float(pbox["h"]):
            containing.append(panel)
    if containing:
        panel = containing[0]
        return str(panel.get("title") or panel.get("id") or "")
    return ""


def _asset_type_from_text(slot: dict, text: str) -> str:
    raw = f"{slot.get('id', '')} {slot.get('paper_concept', '')} {slot.get('display_label', '')} {text}".lower()
    ratio = float(slot["bbox_percent"]["w"]) / max(float(slot["bbox_percent"]["h"]), 0.001)
    if "legend" in raw:
        return "legend_marker"
    if ratio >= 2.2:
        return "thin_tool"
    if any(term in raw for term in ["robot", "agent", "critic", "designer", "person", "avatar", "human", "interviewer"]):
        return "character"
    if any(term in raw for term in ["document", "paper", "text", "input", "file", "stack"]):
        return "document_stack"
    if any(term in raw for term in ["chart", "score", "graph", "plot", "card", "figure", "output", "final"]):
        return "chart_card"
    if any(term in raw for term in ["camera", "screen", "monitor", "phone", "device"]):
        return "device"
    if any(term in raw for term in ["ocr", "verify", "inspect", "search", "magnifier"]):
        return "tool_icon"
    if any(term in raw for term in ["tool", "erase", "magic", "wand", "palette", "synthesis"]):
        return "tool_combo"
    if ratio >= 1.35:
        return "chart_card"
    if ratio <= 0.78:
        return "character"
    return "generic"


def _relations(slot: dict, controls: list[dict]) -> tuple[list[str], list[str]]:
    slot_id = str(slot.get("id"))
    upstream = []
    downstream = []
    for control in controls:
        source = str(control.get("source_id") or control.get("source") or "")
        target = str(control.get("target_id") or control.get("target") or "")
        if target == slot_id and source:
            upstream.append(source)
        if source == slot_id and target:
            downstream.append(target)
    return sorted(set(upstream)), sorted(set(downstream))


def _apply_adapter(slots: list[dict], adapter_result: dict | list[dict]) -> dict[str, dict]:
    records = adapter_result.get("slots", []) if isinstance(adapter_result, dict) else adapter_result
    by_id = {}
    for item in records or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("id") or item.get("slot_id") or "")
        if not slot_id:
            continue
        by_id[slot_id] = item
    return by_id


def _design_layers(design_plan: dict | None) -> list[dict]:
    if not isinstance(design_plan, dict):
        return []
    if isinstance(design_plan.get("layers"), list):
        return [item for item in design_plan["layers"] if isinstance(item, dict)]
    layer_plan = design_plan.get("layer_plan") if isinstance(design_plan.get("layer_plan"), dict) else {}
    return [item for item in layer_plan.get("layers", []) or [] if isinstance(item, dict)]


def _design_slots_by_id(design_plan: dict | None) -> dict[str, dict]:
    by_id = {}
    for layer in _design_layers(design_plan):
        if str(layer.get("kind") or "") != "visual_slot":
            continue
        slot_id = str(layer.get("id") or layer.get("slot_id") or "")
        if slot_id:
            by_id[slot_id] = layer
    return by_id


def _generation_policy_by_slot(generation_plan: dict | None) -> dict[str, dict]:
    if not isinstance(generation_plan, dict):
        return {}
    policies = {}
    for item in generation_plan.get("asset_policies", []) or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or item.get("object_id") or item.get("id") or "")
        if slot_id:
            policies[slot_id] = item
    return policies


def plan_slot_semantics(
    reference_path: str | Path,
    slots: list[dict],
    panels: list[dict],
    controls: list[dict],
    text_geometry: dict | None,
    semantic_adapter: Callable[[str | Path, list[dict], list[dict], list[dict], dict | None], dict | list[dict]] | None = None,
    text_intelligence: dict | None = None,
    design_plan: dict | None = None,
    generation_plan: dict | None = None,
) -> tuple[list[dict], dict]:
    regions = _text_regions(text_geometry)
    relation_text_by_target = _relation_text_by_target(text_intelligence, regions)
    warnings = []
    adapter_by_id = {}
    semantic_vlm_status = "not_requested"
    semantic_vlm_model = None
    invalid_asset_type_count = 0
    design_by_id = _design_slots_by_id(design_plan)
    policy_by_id = _generation_policy_by_slot(generation_plan)
    global_plan_usage_count = 0
    global_policy_usage_count = 0
    conflict_count = 0
    if semantic_adapter:
        try:
            adapter_text_geometry = dict(text_geometry or {})
            if isinstance(text_intelligence, dict):
                adapter_text_geometry["text_intelligence"] = text_intelligence
                adapter_text_geometry["text_relations"] = text_intelligence.get("text_relations", [])
            adapter_result = semantic_adapter(reference_path, slots, panels, controls, adapter_text_geometry)
            if isinstance(adapter_result, dict) and adapter_result.get("_vlm_model"):
                semantic_vlm_model = str(adapter_result.get("_vlm_model"))
            adapter_by_id = _apply_adapter(slots, adapter_result)
            semantic_vlm_status = "used" if adapter_by_id else "fallback"
            if not adapter_by_id:
                warnings.append("semantic_adapter_returned_no_valid_slots")
        except Exception as exc:
            semantic_vlm_status = "fallback"
            warnings.append(f"semantic_adapter_failed:{exc}")
    planned = []
    relation_text_usage_count = 0
    for slot in slots:
        slot_id = str(slot.get("id"))
        relation_texts = relation_text_by_target.get(slot_id, [])
        if relation_texts:
            relation_text_usage_count += 1
        texts = relation_texts or _nearby_text(slot, regions)
        nearby = " | ".join(texts)
        upstream, downstream = _relations(slot, controls)
        panel_context = _panel_context(slot, panels)
        asset_type = _asset_type_from_text(slot, nearby)
        prompt_subject = nearby or str(slot.get("paper_concept") or slot_id)
        semantic_role = asset_type
        global_slot = design_by_id.get(slot_id, {})
        policy_record = policy_by_id.get(slot_id, {})
        asset_source_policy = slot.get("asset_source_policy")
        policy_source = slot.get("policy_source")
        asset_source_reason = slot.get("asset_source_reason")
        if global_slot:
            global_plan_usage_count += 1
            global_asset_type = str(global_slot.get("asset_type") or "")
            if global_asset_type:
                if global_asset_type in ASSET_TYPES:
                    asset_type = global_asset_type
                else:
                    warnings.append(f"unknown_global_asset_type:{slot_id}:{global_asset_type}")
                    invalid_asset_type_count += 1
            semantic_role = str(global_slot.get("semantic_role") or semantic_role)
            global_subject = str(global_slot.get("prompt_subject") or global_slot.get("label") or "").strip()
            if global_subject:
                if relation_texts and all(text.lower() not in global_subject.lower() for text in relation_texts):
                    conflict_count += 1
                    warnings.append(f"global_prompt_text_relation_conflict:{slot_id}")
                prompt_subject = global_subject
            asset_source_policy = str(global_slot.get("asset_source_policy") or asset_source_policy or "")
            policy_source = str(global_slot.get("policy_source") or "global_layer_plan")
            asset_source_reason = str(global_slot.get("asset_source_reason") or asset_source_reason or "global layer plan policy")
        if policy_record:
            policy = str(policy_record.get("policy") or policy_record.get("asset_source_policy") or "")
            if policy:
                asset_source_policy = policy
                policy_source = str(policy_record.get("source") or "generation_plan")
                asset_source_reason = str(policy_record.get("reason") or policy_record.get("asset_source_reason") or "global generation policy")
                global_policy_usage_count += 1
        override = adapter_by_id.get(slot_id, {})
        if override:
            asset_type = str(override.get("asset_type") or asset_type)
            if asset_type not in ASSET_TYPES:
                warnings.append(f"unknown_asset_type:{slot_id}:{asset_type}")
                invalid_asset_type_count += 1
                asset_type = "generic"
            semantic_role = str(override.get("semantic_role") or semantic_role)
            prompt_subject = str(override.get("prompt_subject") or prompt_subject)
            if override.get("nearby_text"):
                nearby = " | ".join(override["nearby_text"]) if isinstance(override["nearby_text"], list) else str(override["nearby_text"])
        enriched = dict(slot)
        enriched.update({
            "semantic_role": semantic_role,
            "asset_type": asset_type,
            "nearby_text": texts if not override.get("nearby_text") else override.get("nearby_text"),
            "panel_context": panel_context,
            "upstream_ids": upstream,
            "downstream_ids": downstream,
            "prompt_subject": prompt_subject,
            "text_relation_source": "text_intelligence" if relation_texts else "nearest_text",
            "global_plan_object_id": slot_id if global_slot else None,
            "asset_source_policy": asset_source_policy,
            "policy_source": policy_source,
            "asset_source_reason": asset_source_reason,
        })
        enriched = {key: value for key, value in enriched.items() if value is not None}
        planned.append(enriched)
    return planned, {
        "summary": "Slot semantic planning report.",
        "status": "ok",
        "semantic_vlm_status": semantic_vlm_status,
        "vlm_model": semantic_vlm_model,
        "slot_count": len(planned),
        "text_region_count": len(regions),
        "text_intelligence_relation_count": len(text_intelligence.get("text_relations", []) or []) if isinstance(text_intelligence, dict) else 0,
        "relationship_text_usage_percent": round(relation_text_usage_count / max(len(planned), 1) * 100, 2),
        "global_plan_usage_count": global_plan_usage_count,
        "global_policy_usage_count": global_policy_usage_count,
        "global_plan_conflict_count": conflict_count,
        "invalid_asset_type_count": invalid_asset_type_count,
        "warnings": warnings,
        "slots": [{
            "slot_id": item["id"],
            "semantic_role": item.get("semantic_role"),
            "asset_type": item.get("asset_type"),
            "nearby_text": item.get("nearby_text"),
            "panel_context": item.get("panel_context"),
            "upstream_ids": item.get("upstream_ids"),
            "downstream_ids": item.get("downstream_ids"),
            "prompt_subject": item.get("prompt_subject"),
            "text_relation_source": item.get("text_relation_source"),
            "global_plan_object_id": item.get("global_plan_object_id"),
            "asset_source_policy": item.get("asset_source_policy"),
            "policy_source": item.get("policy_source"),
        } for item in planned],
    }
