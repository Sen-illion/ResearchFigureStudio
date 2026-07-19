from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Any

from .utils import write_json
from .vlm_client import call_vlm_json, resolve_vlm_model


FAMILY_CLASSES = {"sans_serif", "serif", "monospace", "display", "handwriting", "unknown"}
FONT_WEIGHTS = {"regular", "medium", "bold"}
CASE_STYLES = {"uppercase", "title_case", "sentence_case", "mixed", "unknown"}
ALIGNMENTS = {"left", "center", "right"}
ANCHORS = {"top_left", "top_center", "center", "bottom_center", "custom"}
RELATION_TYPES = {
    "title_subtitle",
    "panel_title_of",
    "label_for_visual_object",
    "arrow_label_for",
    "legend_label_for",
    "caption_for",
    "continuation_of",
}


def _text_regions(text_geometry: dict | None) -> list[dict]:
    if not isinstance(text_geometry, dict):
        return []
    items = text_geometry.get("text_regions") or text_geometry.get("regions") or []
    return [item for item in items if isinstance(item, dict)]


def _text_program_items(text_program: dict | None) -> list[dict]:
    if not isinstance(text_program, dict):
        return []
    items = text_program.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _brief(items: list[dict], keys: tuple[str, ...], limit: int = 120) -> list[dict]:
    output = []
    for item in items[:limit]:
        output.append({key: item.get(key) for key in keys if key in item})
    return output


def _context(program: dict, text_geometry: dict, text_program: dict) -> dict:
    return {
        "canvas": program.get("canvas"),
        "panels": _brief(program.get("panels", []), ("id", "title", "bbox_percent")),
        "cards": _brief(program.get("cards", []), ("id", "title", "bbox_percent", "panel_id")),
        "slots": _brief(program.get("slots", []), ("id", "asset_id", "paper_concept", "bbox_percent", "panel_id", "semantic_role", "asset_type")),
        "controls": _brief(program.get("arrows", []), ("id", "source_id", "target_id", "source", "target", "control_kind", "path_percent", "label")),
        "text_regions": _brief(
            _text_regions(text_geometry),
            ("id", "text", "raw_text", "role", "target_id", "bbox_percent", "estimated_font_ratio", "text_size_level_id"),
        ),
        "text_program_items": _brief(
            _text_program_items(text_program),
            ("id", "text", "role", "target_id", "source_reference_text_id", "font_family_guess", "font_weight_guess", "align"),
        ),
    }


def _text_id_aliases(text_geometry: dict, text_program: dict) -> dict[str, str]:
    regions = _text_regions(text_geometry)
    canonical_ids = {str(item.get("id") or "") for item in regions if str(item.get("id") or "")}
    aliases = {text_id: text_id for text_id in canonical_ids}
    for index, region in enumerate(regions, start=1):
        text_id = str(region.get("id") or "")
        if not text_id:
            continue
        aliases[f"{index}"] = text_id
        aliases[f"t{index}"] = text_id
        aliases[f"text_{index}"] = text_id
        aliases[f"text_{text_id}"] = text_id
    for item in _text_program_items(text_program):
        source_id = str(item.get("source_reference_text_id") or "")
        item_id = str(item.get("id") or "")
        if source_id in canonical_ids:
            aliases[source_id] = source_id
            if item_id:
                aliases[item_id] = source_id
    return aliases


def _object_id_aliases(program: dict) -> dict[str, str]:
    aliases = {"canvas": "canvas"}
    for key in ("panels", "cards", "slots", "arrows"):
        for item in program.get(key, []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            object_id = str(item["id"])
            aliases[object_id] = object_id
            asset_id = str(item.get("asset_id") or "")
            if asset_id:
                aliases[asset_id] = object_id
    return aliases


def _case_style(text: str) -> str:
    stripped = "".join(char for char in str(text or "") if char.isalpha())
    if not stripped:
        return "unknown"
    if stripped.upper() == stripped:
        return "uppercase"
    words = str(text or "").replace("-", " ").split()
    if words and sum(1 for word in words if word[:1].isupper()) >= max(1, len(words) // 2):
        return "title_case"
    if str(text or "")[:1].isupper():
        return "sentence_case"
    return "mixed"


def _font_family_class(text: str) -> str:
    raw = str(text or "")
    if any(char in raw for char in "{}[]<>="):
        return "monospace"
    return "sans_serif"


def _heuristic_text_item(region: dict) -> dict:
    text = str(region.get("raw_text") or region.get("text") or "")
    role = str(region.get("role") or "")
    bbox = region.get("bbox_percent") if isinstance(region.get("bbox_percent"), dict) else {}
    y_bucket = int(float(bbox.get("y", 0.0)) * 20) if bbox else 0
    x_bucket = int(float(bbox.get("x", 0.0)) * 20) if bbox else 0
    alignment = "center" if role in {"panel_title", "section_title", "panel_label"} else "left"
    return {
        "text_id": str(region.get("id") or ""),
        "font_style_guess": {
            "family_class": _font_family_class(text),
            "weight": "bold" if role in {"panel_title", "section_title", "method_label", "modality_label"} else "regular",
            "italic": False,
            "case_style": _case_style(text),
            "visual_style": "heuristic_from_text_role",
        },
        "layout_intent": {
            "alignment": alignment,
            "anchor": "top_center" if alignment == "center" else "top_left",
            "belongs_to": str(region.get("target_id") or "canvas"),
            "row_group": f"{role or 'text'}_row_{y_bucket:02d}",
            "column_group": f"{role or 'text'}_col_{x_bucket:02d}",
        },
        "confidence": None,
        "reason": "heuristic_text_intelligence_fallback",
        "source": "heuristic",
    }


def _heuristic_relations(regions: list[dict]) -> list[dict]:
    relations = []
    for region in regions:
        text_id = str(region.get("id") or "")
        role = str(region.get("role") or "")
        target_id = str(region.get("target_id") or "")
        if not text_id or not target_id or target_id == "canvas":
            continue
        if role == "panel_title":
            relation = "panel_title_of"
        elif role == "arrow_label":
            relation = "arrow_label_for"
        elif role in {"slot_caption", "body_label", "method_label", "modality_label", "trait_label"}:
            relation = "label_for_visual_object"
        elif role == "legend_label":
            relation = "legend_label_for"
        else:
            relation = "caption_for"
        relations.append({
            "source_text_id": text_id,
            "target_object_id": target_id,
            "relation": relation,
            "confidence": None,
            "reason": "heuristic_role_target_binding",
            "source": "heuristic",
        })
    return relations


def _heuristic_report(mode: str, text_geometry: dict, fallback_reason: str | None = None) -> dict:
    regions = _text_regions(text_geometry)
    items = [_heuristic_text_item(region) for region in regions]
    report = {
        "summary": "Rebuild text intelligence report.",
        "mode": mode,
        "effective_mode": "heuristic" if mode != "off" else "off",
        "status": "skipped" if mode == "off" else ("fallback_to_heuristic" if fallback_reason else "pass"),
        "model": None,
        "fallback_reason": fallback_reason,
        "text_count": len(items),
        "items": items,
        "text_relations": [] if mode == "off" else _heuristic_relations(regions),
        "warnings": [fallback_reason] if fallback_reason else [],
    }
    return report


def _call_vlm_text_intelligence(reference_path: str | Path, program: dict, text_geometry: dict, text_program: dict, model: str | None = None) -> dict:
    model_name = model or resolve_vlm_model("RFS_REBUILD_TEXT_MODEL", "RFS_TEXT_ROLE_MODEL")
    prompt = f"""
You are analyzing editable text in a reference diagram for a PowerPoint rebuild.
Inspect the reference image and OCR/PPT text metadata.
Only output JSON. Do not include markdown or explanations.

Important:
- Do not output PowerPoint code.
- Do not modify coordinates, font sizes, bbox values, or layout.
- Only judge font style class, text semantic relations, and layout intent.

Allowed family_class values: sans_serif, serif, monospace, display, handwriting, unknown
Allowed weight values: regular, medium, bold
Allowed case_style values: uppercase, title_case, sentence_case, mixed, unknown
Allowed alignment values: left, center, right
Allowed anchor values: top_left, top_center, center, bottom_center, custom
Allowed relation values: title_subtitle, panel_title_of, label_for_visual_object, arrow_label_for, legend_label_for, caption_for, continuation_of

Return schema:
{{
  "summary": "...",
  "items": [
    {{
      "text_id": "reference_text_region_id",
      "font_style_guess": {{"family_class":"sans_serif","weight":"bold","italic":false,"case_style":"title_case","visual_style":"short description"}},
      "layout_intent": {{"alignment":"center","anchor":"top_center","belongs_to":"panel_or_slot_or_control_id_or_canvas","row_group":"stable row group","column_group":"stable column group"}},
      "confidence": 0.0,
      "reason": "short reason"
    }}
  ],
  "text_relations": [
    {{"source_text_id":"text_id","target_text_id":"text_id","target_object_id":"slot_or_panel_or_control_id","relation":"label_for_visual_object","confidence":0.0,"reason":"short reason"}}
  ]
}}

Context:
{json.dumps(_context(program, text_geometry, text_program), ensure_ascii=False)}
""".strip()
    result = call_vlm_json(prompt, [reference_path], model=model_name)
    result["_vlm_model"] = model_name
    return result


def _clean_confidence(value: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return None


def _clean_text_item(raw: dict, fallback: dict) -> dict:
    font = raw.get("font_style_guess") if isinstance(raw.get("font_style_guess"), dict) else {}
    layout = raw.get("layout_intent") if isinstance(raw.get("layout_intent"), dict) else {}
    family = str(font.get("family_class") or fallback["font_style_guess"]["family_class"])
    weight = str(font.get("weight") or fallback["font_style_guess"]["weight"])
    case_style = str(font.get("case_style") or fallback["font_style_guess"]["case_style"])
    alignment = str(layout.get("alignment") or fallback["layout_intent"]["alignment"])
    anchor = str(layout.get("anchor") or fallback["layout_intent"]["anchor"])
    return {
        "text_id": fallback["text_id"],
        "font_style_guess": {
            "family_class": family if family in FAMILY_CLASSES else fallback["font_style_guess"]["family_class"],
            "weight": weight if weight in FONT_WEIGHTS else fallback["font_style_guess"]["weight"],
            "italic": bool(font.get("italic", fallback["font_style_guess"]["italic"])),
            "case_style": case_style if case_style in CASE_STYLES else fallback["font_style_guess"]["case_style"],
            "visual_style": str(font.get("visual_style") or fallback["font_style_guess"]["visual_style"]),
        },
        "layout_intent": {
            "alignment": alignment if alignment in ALIGNMENTS else fallback["layout_intent"]["alignment"],
            "anchor": anchor if anchor in ANCHORS else fallback["layout_intent"]["anchor"],
            "belongs_to": str(layout.get("belongs_to") or fallback["layout_intent"]["belongs_to"] or "canvas"),
            "row_group": str(layout.get("row_group") or fallback["layout_intent"]["row_group"]),
            "column_group": str(layout.get("column_group") or fallback["layout_intent"]["column_group"]),
        },
        "confidence": _clean_confidence(raw.get("confidence")),
        "reason": str(raw.get("reason") or ""),
        "source": "vlm",
    }


def _clean_relation(raw: dict, text_aliases: dict[str, str], object_aliases: dict[str, str]) -> dict | None:
    relation = str(raw.get("relation") or "")
    if relation not in RELATION_TYPES:
        return None
    source_text_id = text_aliases.get(str(raw.get("source_text_id") or ""))
    target_text_id = text_aliases.get(str(raw.get("target_text_id") or ""))
    target_object_id = object_aliases.get(str(raw.get("target_object_id") or raw.get("target_id") or ""))
    if not source_text_id:
        return None
    if not target_text_id and not target_object_id:
        return None
    return {
        "source_text_id": source_text_id,
        "target_text_id": target_text_id or None,
        "target_object_id": target_object_id or None,
        "relation": relation,
        "confidence": _clean_confidence(raw.get("confidence")),
        "reason": str(raw.get("reason") or ""),
        "source": "vlm",
    }


def _normalize_vlm_report(raw: dict, program: dict, text_geometry: dict, text_program: dict, mode: str, model: str | None) -> dict:
    fallback = _heuristic_report("heuristic", text_geometry)
    fallback_by_id = {item["text_id"]: item for item in fallback["items"]}
    text_aliases = _text_id_aliases(text_geometry, text_program)
    raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
    raw_by_id = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        canonical_id = text_aliases.get(str(item.get("text_id") or item.get("id") or ""))
        if canonical_id:
            raw_by_id[canonical_id] = item
    items = []
    fallback_count = 0
    for text_id, fallback_item in fallback_by_id.items():
        raw_item = raw_by_id.get(text_id)
        if raw_item:
            items.append(_clean_text_item(raw_item, fallback_item))
        else:
            fallback_item = dict(fallback_item)
            fallback_item["source"] = "heuristic_fallback"
            fallback_item["fallback_reason"] = "missing_vlm_text_item"
            items.append(fallback_item)
            fallback_count += 1

    object_aliases = _object_id_aliases(program)
    relations = []
    invalid_relation_count = 0
    for raw_relation in raw.get("text_relations", []) if isinstance(raw.get("text_relations"), list) else []:
        if not isinstance(raw_relation, dict):
            invalid_relation_count += 1
            continue
        cleaned = _clean_relation(raw_relation, text_aliases, object_aliases)
        if cleaned:
            relations.append(cleaned)
        else:
            invalid_relation_count += 1

    warnings = []
    if fallback_count:
        warnings.append(f"{fallback_count} text intelligence item(s) used heuristic fallback")
    if invalid_relation_count:
        warnings.append(f"{invalid_relation_count} invalid text relation(s) ignored")
    return {
        "summary": "Rebuild text intelligence report.",
        "mode": mode,
        "effective_mode": "vlm",
        "status": "pass_with_item_fallbacks" if fallback_count else "pass",
        "model": raw.get("_vlm_model") or model,
        "text_count": len(items),
        "fallback_count": fallback_count,
        "invalid_relation_count": invalid_relation_count,
        "raw_summary": raw.get("summary"),
        "items": items,
        "text_relations": relations,
        "warnings": warnings,
    }


def _write_derived_reports(out: Path, report: dict) -> None:
    write_json(out / "text_intelligence_report.json", report)
    write_json(out / "text_relationships.json", {
        "summary": "Text semantic relationships inferred for editable rebuild.",
        "mode": report.get("mode"),
        "effective_mode": report.get("effective_mode"),
        "status": report.get("status"),
        "relation_count": len(report.get("text_relations", [])),
        "relations": report.get("text_relations", []),
    })
    write_json(out / "text_style_profile.json", {
        "summary": "Text font style guesses inferred from the reference image.",
        "mode": report.get("mode"),
        "effective_mode": report.get("effective_mode"),
        "status": report.get("status"),
        "text_count": len(report.get("items", [])),
        "items": [{
            "text_id": item.get("text_id"),
            "font_style_guess": item.get("font_style_guess"),
            "confidence": item.get("confidence"),
            "source": item.get("source"),
        } for item in report.get("items", [])],
    })
    write_json(out / "text_layout_intent_report.json", {
        "summary": "Text layout intent inferred from the reference image.",
        "mode": report.get("mode"),
        "effective_mode": report.get("effective_mode"),
        "status": report.get("status"),
        "text_count": len(report.get("items", [])),
        "items": [{
            "text_id": item.get("text_id"),
            "layout_intent": item.get("layout_intent"),
            "confidence": item.get("confidence"),
            "source": item.get("source"),
        } for item in report.get("items", [])],
    })


def plan_rebuild_text_intelligence(
    reference_path: str | Path,
    program: dict,
    text_geometry: dict,
    text_program: dict,
    out_dir: str | Path,
    *,
    mode: str = "vlm",
    model: str | None = None,
    adapter: Callable[[str | Path, dict, dict, dict, str | None], dict] | None = None,
    fallback_on_error: bool = True,
) -> dict:
    out = Path(out_dir)
    requested_mode = str(mode or "off").lower()
    if requested_mode == "off":
        report = _heuristic_report("off", text_geometry)
        _write_derived_reports(out, report)
        return report
    if requested_mode == "heuristic":
        report = _heuristic_report("heuristic", text_geometry)
        _write_derived_reports(out, report)
        return report
    if requested_mode != "vlm":
        raise ValueError(f"Unsupported text intelligence mode: {mode}")
    try:
        raw = adapter(reference_path, program, text_geometry, text_program, model) if adapter else _call_vlm_text_intelligence(reference_path, program, text_geometry, text_program, model=model)
        report = _normalize_vlm_report(raw, program, text_geometry, text_program, requested_mode, model)
    except Exception as exc:
        if not fallback_on_error:
            raise
        report = _heuristic_report("vlm", text_geometry, fallback_reason=f"vlm_text_intelligence_failed:{exc}")
    _write_derived_reports(out, report)
    return report
