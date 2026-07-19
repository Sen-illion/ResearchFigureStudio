from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

from .layout_planner import canvas_inches, dominant_palette, estimate_background
from .utils import write_json, write_text
from .vlm_client import resolve_vlm_model


LAYER_KINDS = {"background", "panel", "card", "visual_slot", "text", "connector", "legend", "ignore"}
ASSET_POLICIES = {"reference_crop", "api_generate", "placeholder", "ppt_shape", "editable_text", "ppt_connector", "ignore"}


def _clamp_bbox(bbox: dict | None) -> dict[str, float]:
    bbox = bbox if isinstance(bbox, dict) else {}
    x = max(0.0, min(0.995, float(bbox.get("x", 0.0))))
    y = max(0.0, min(0.995, float(bbox.get("y", 0.0))))
    w = max(0.001, min(float(bbox.get("w", 0.001)), 1.0 - x))
    h = max(0.001, min(float(bbox.get("h", 0.001)), 1.0 - y))
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _clean_kind(value: object, default: str = "visual_slot") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "slot": "visual_slot",
        "image": "visual_slot",
        "visual": "visual_slot",
        "arrow": "connector",
        "control": "connector",
        "box": "card",
        "background_panel": "panel",
    }
    text = aliases.get(text, text)
    return text if text in LAYER_KINDS else default


def _clean_policy(value: object, kind: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "crop": "reference_crop",
        "screenshot": "reference_crop",
        "api": "api_generate",
        "generate": "api_generate",
        "generated": "api_generate",
        "shape": "ppt_shape",
        "text": "editable_text",
        "arrow": "ppt_connector",
        "connector": "ppt_connector",
    }
    text = aliases.get(text, text)
    if text in ASSET_POLICIES:
        return text
    if kind in {"background", "panel", "card"}:
        return "ppt_shape"
    if kind == "text":
        return "editable_text"
    if kind == "connector":
        return "ppt_connector"
    if kind in {"legend", "ignore"}:
        return "ignore"
    return "api_generate"


def _normalize_layers(raw_layers: list | None) -> list[dict]:
    layers = []
    for idx, raw in enumerate(raw_layers or [], start=1):
        if not isinstance(raw, dict):
            continue
        kind = _clean_kind(raw.get("kind") or raw.get("layer_kind") or raw.get("type"))
        object_id = str(raw.get("id") or raw.get("object_id") or f"{kind}_{idx:02d}").strip()
        if not object_id:
            object_id = f"{kind}_{idx:02d}"
        policy = _clean_policy(raw.get("asset_source_policy") or raw.get("policy") or raw.get("render_as"), kind)
        record = {
            "id": object_id,
            "kind": kind,
            "label": str(raw.get("label") or raw.get("title") or raw.get("prompt_subject") or object_id),
            "bbox_percent": _clamp_bbox(raw.get("bbox_percent")),
            "asset_source_policy": policy,
            "asset_source_reason": str(raw.get("asset_source_reason") or raw.get("reason") or f"{kind}_default_policy"),
            "z_order_hint": str(raw.get("z_order_hint") or raw.get("z_layer") or ""),
            "confidence": _confidence(raw.get("confidence"), default=0.65),
        }
        if raw.get("panel_id"):
            record["panel_id"] = str(raw.get("panel_id"))
        if raw.get("prompt_subject"):
            record["prompt_subject"] = str(raw.get("prompt_subject"))
        if raw.get("semantic_role"):
            record["semantic_role"] = str(raw.get("semantic_role"))
        if raw.get("asset_type"):
            record["asset_type"] = str(raw.get("asset_type"))
        layers.append({key: value for key, value in record.items() if value not in ("", None)})
    return layers


def _confidence(value: object, default: float = 0.5) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except Exception:
        return default


def _normalize_asset_policies(raw_policies: list | None, layers: list[dict]) -> list[dict]:
    by_id = {str(layer["id"]): layer for layer in layers}
    policies = []
    for layer in layers:
        if layer["kind"] == "visual_slot":
            policies.append({
                "slot_id": layer["id"],
                "object_id": layer["id"],
                "policy": layer["asset_source_policy"],
                "reason": layer.get("asset_source_reason") or "layer_policy",
                "source": "layer_plan",
                "confidence": layer.get("confidence", 0.65),
            })
    for raw in raw_policies or []:
        if not isinstance(raw, dict):
            continue
        object_id = str(raw.get("slot_id") or raw.get("object_id") or raw.get("id") or "")
        if not object_id:
            continue
        kind = by_id.get(object_id, {}).get("kind", "visual_slot")
        policies.append({
            "slot_id": object_id,
            "object_id": object_id,
            "policy": _clean_policy(raw.get("policy") or raw.get("asset_source_policy"), kind),
            "reason": str(raw.get("reason") or raw.get("asset_source_reason") or "global_generation_policy"),
            "source": "design_plan",
            "confidence": _confidence(raw.get("confidence"), default=0.7),
        })
    deduped = {}
    for policy in policies:
        deduped[str(policy["slot_id"])] = policy
    return list(deduped.values())


def _normalize_flow_graph(raw_flow: dict | None, layers: list[dict]) -> dict:
    raw_flow = raw_flow if isinstance(raw_flow, dict) else {}
    layer_ids = {str(layer["id"]) for layer in layers}
    nodes = []
    seen = set()
    for raw in raw_flow.get("nodes", []) if isinstance(raw_flow.get("nodes"), list) else []:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or raw.get("object_id") or "")
        if not node_id:
            continue
        nodes.append({
            "id": node_id,
            "label": str(raw.get("label") or node_id),
            "kind": _clean_kind(raw.get("kind"), default="visual_slot"),
            "confidence": _confidence(raw.get("confidence"), default=0.65),
        })
        seen.add(node_id)
    for layer in layers:
        if layer["kind"] == "visual_slot" and layer["id"] not in seen:
            nodes.append({"id": layer["id"], "label": layer.get("label", layer["id"]), "kind": "visual_slot", "confidence": layer.get("confidence", 0.65)})
            seen.add(layer["id"])
    edges = []
    invalid_count = 0
    for idx, raw in enumerate(raw_flow.get("edges", []) if isinstance(raw_flow.get("edges"), list) else [], start=1):
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source_id") or raw.get("source") or "")
        target = str(raw.get("target_id") or raw.get("target") or "")
        if not source or not target:
            invalid_count += 1
            continue
        edges.append({
            "id": str(raw.get("id") or f"flow_{idx:02d}"),
            "source_id": source,
            "target_id": target,
            "relation": str(raw.get("relation") or "flows_to"),
            "expected_connector": str(raw.get("expected_connector") or raw.get("connector") or "solid_arrow"),
            "confidence": _confidence(raw.get("confidence"), default=0.7),
            "source_known_in_layer_plan": source in layer_ids,
            "target_known_in_layer_plan": target in layer_ids,
        })
    return {
        "summary": "Reference flow graph inferred by global rebuild design planner.",
        "nodes": nodes,
        "edges": edges,
        "invalid_edge_count": invalid_count,
    }


def _heuristic_layers(reference_path: Path) -> tuple[dict, list[dict], list[dict], dict]:
    with Image.open(reference_path).convert("RGB") as image:
        width_px, height_px = image.size
        width_in, height_in = canvas_inches(width_px, height_px)
        background = estimate_background(image)
        palette = dominant_palette(image)
    layers = [
        {
            "id": "reference_background",
            "kind": "background",
            "label": "Reference background",
            "bbox_percent": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "asset_source_policy": "ppt_shape",
            "asset_source_reason": "full canvas background remains editable PPT shape",
            "z_order_hint": "background",
            "confidence": 0.35,
        },
        {
            "id": "reference_canvas",
            "kind": "panel",
            "label": "Reference canvas",
            "bbox_percent": {"x": 0.025, "y": 0.065, "w": 0.95, "h": 0.84},
            "asset_source_policy": "ppt_shape",
            "asset_source_reason": "default panel remains editable PPT shape",
            "z_order_hint": "panel",
            "confidence": 0.35,
        },
    ]
    logic = {
        "summary": "Reference logic plan inferred by heuristic fallback.",
        "mode": "heuristic",
        "effective_mode": "heuristic",
        "status": "fallback" if False else "pass",
        "model": None,
        "narrative": {
            "figure_type": "workflow",
            "main_story": "Reference-only editable rebuild of a scientific diagram.",
            "key_message": "Preserve layout, editable text, connectors, and slot-level visual assets.",
        },
        "reading_order": ["reference_canvas"],
        "canvas": {
            "width_px": width_px,
            "height_px": height_px,
            "width_in": width_in,
            "height_in": height_in,
            "background": background,
            "palette": palette,
        },
        "layers": layers,
        "warnings": [],
    }
    generation = {
        "summary": "Reference generation plan inferred by heuristic fallback.",
        "mode": "heuristic",
        "effective_mode": "heuristic",
        "asset_policies": _normalize_asset_policies([], layers),
    }
    flow = _normalize_flow_graph({}, layers)
    return logic, layers, generation["asset_policies"], flow


def _normalize_design_result(raw: dict, reference_path: Path, mode: str, model: str | None, fallback_reason: str | None = None) -> tuple[dict, dict, dict, dict]:
    heuristic_logic, heuristic_layers, _heuristic_policies, heuristic_flow = _heuristic_layers(reference_path)
    layers = _normalize_layers(raw.get("layers")) or heuristic_layers
    policies = _normalize_asset_policies(raw.get("asset_policies"), layers)
    flow = _normalize_flow_graph(raw.get("flow_graph"), layers)
    effective_mode = "heuristic" if fallback_reason else ("off" if mode == "off" else mode)
    status = "fallback_to_heuristic" if fallback_reason else ("skipped" if mode == "off" else "pass")
    logic = {
        "summary": "Global reference logic plan for editable rebuild.",
        "mode": mode,
        "effective_mode": effective_mode,
        "status": status,
        "model": raw.get("_vlm_model") or model,
        "fallback_reason": fallback_reason,
        "narrative": raw.get("narrative") if isinstance(raw.get("narrative"), dict) else heuristic_logic["narrative"],
        "reading_order": raw.get("reading_order") if isinstance(raw.get("reading_order"), list) else heuristic_logic["reading_order"],
        "canvas": heuristic_logic["canvas"],
        "layers": layers,
        "warnings": [fallback_reason] if fallback_reason else [],
    }
    layer_plan = {
        "summary": "Reference layer plan for editable rebuild.",
        "mode": mode,
        "effective_mode": effective_mode,
        "status": status,
        "layer_count": len(layers),
        "layers": layers,
        "warnings": logic["warnings"],
    }
    generation = {
        "summary": "Reference generation policy plan for editable rebuild.",
        "mode": mode,
        "effective_mode": effective_mode,
        "status": status,
        "asset_policies": policies,
        "warnings": logic["warnings"],
    }
    flow["mode"] = mode
    flow["effective_mode"] = effective_mode
    flow["status"] = status
    flow["warnings"] = logic["warnings"]
    return logic, layer_plan, generation, flow


def _write_markdown(out: Path, logic: dict, layer_plan: dict, generation: dict, flow: dict) -> None:
    lines = [
        "# Summary",
        str(logic.get("summary") or "Global reference logic plan."),
        "",
        f"- Mode: {logic.get('mode')}",
        f"- Effective mode: {logic.get('effective_mode')}",
        f"- Status: {logic.get('status')}",
        f"- Model: {logic.get('model')}",
        f"- Layer count: {layer_plan.get('layer_count')}",
        f"- Asset policy count: {len(generation.get('asset_policies', []))}",
        f"- Flow edge count: {len(flow.get('edges', []))}",
    ]
    narrative = logic.get("narrative") if isinstance(logic.get("narrative"), dict) else {}
    if narrative:
        lines.extend(["", "## Narrative"])
        for key in ("figure_type", "main_story", "key_message"):
            if narrative.get(key):
                lines.append(f"- {key}: {narrative[key]}")
    write_text(out / "reference_logic_plan.md", "\n".join(lines) + "\n")


def plan_rebuild_design(
    reference_path: str | Path,
    out_dir: str | Path,
    *,
    mode: str = "vlm",
    model: str | None = None,
    adapter: Callable[[str | Path, str | None], dict] | None = None,
    fallback_on_error: bool = True,
) -> dict:
    reference = Path(reference_path)
    out = Path(out_dir)
    requested = str(mode or "off").lower()
    if requested == "off":
        raw = {}
        logic, layer_plan, generation, flow = _normalize_design_result(raw, reference, "off", None)
    elif requested == "heuristic":
        raw = {}
        logic, layer_plan, generation, flow = _normalize_design_result(raw, reference, "heuristic", None)
    elif requested == "vlm":
        resolved_model = resolve_vlm_model("RFS_REBUILD_DESIGN_MODEL", "RFS_REBUILD_LAYOUT_MODEL", explicit_model=model)
        try:
            raw = adapter(reference, resolved_model) if adapter else {}
            if not adapter:
                raise RuntimeError("design VLM adapter unavailable")
            logic, layer_plan, generation, flow = _normalize_design_result(raw, reference, "vlm", resolved_model)
        except Exception as exc:
            if not fallback_on_error:
                raise
            logic, layer_plan, generation, flow = _normalize_design_result({}, reference, "vlm", resolved_model, fallback_reason=f"vlm_design_planning_failed:{exc}")
    else:
        raise ValueError(f"Unsupported design plan mode: {mode}")

    write_json(out / "reference_logic_plan.json", logic)
    write_json(out / "reference_layer_plan.json", layer_plan)
    write_json(out / "reference_generation_plan.json", generation)
    write_json(out / "reference_flow_graph.json", flow)
    _write_markdown(out, logic, layer_plan, generation, flow)
    return {
        "logic": logic,
        "layer_plan": layer_plan,
        "generation_plan": generation,
        "flow_graph": flow,
    }
