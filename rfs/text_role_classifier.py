from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import requests


ALLOWED_ROLES = {
    "panel_title",
    "section_title",
    "panel_label",
    "body_label",
    "slot_caption",
    "axis_label",
    "legend_label",
    "arrow_label",
    "annotation",
    "method_label",
    "modality_label",
    "trait_label",
    "free_text",
    "hidden_slot_label",
}
ALLOWED_SIZE_CLASSES = {"tiny", "small", "medium", "large", "xlarge"}
MIN_VLM_CONFIDENCE = 0.55


def _extract_json(text: str) -> dict:
    cleaned = text.strip().replace("```json", "```")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _image_content(path: str | Path) -> dict:
    b64 = base64.b64encode(Path(path).read_bytes()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def _ratio(region: dict) -> float:
    try:
        return float(region.get("raw_estimated_font_ratio") or region.get("estimated_font_ratio") or 0.0)
    except Exception:
        return 0.0


def _heuristic_size_class(region: dict) -> str:
    ratio = _ratio(region)
    if ratio >= 0.050:
        return "xlarge"
    if ratio >= 0.034:
        return "large"
    if ratio >= 0.020:
        return "medium"
    if ratio >= 0.012:
        return "small"
    return "tiny"


def _heuristic_hierarchy(region: dict) -> str:
    role = str(region.get("role") or region.get("ocr_role_guess") or "free_text")
    size_class = _heuristic_size_class(region)
    if role in {"panel_title", "section_title", "panel_label"}:
        return "title"
    if role in {"legend_label", "axis_label", "arrow_label", "annotation"} or size_class in {"tiny", "small"}:
        return "annotation"
    if size_class in {"large", "xlarge"}:
        return "subtitle"
    return "body"


def _heuristic_decision(region: dict) -> dict:
    role = str(region.get("role") or "free_text")
    if role not in ALLOWED_ROLES:
        role = "free_text"
    size_class = _heuristic_size_class(region)
    hierarchy = _heuristic_hierarchy({**region, "role": role})
    return {
        "text_id": str(region.get("id") or ""),
        "text": str(region.get("text") or ""),
        "ocr_role_guess": str(region.get("ocr_role_guess") or region.get("role") or ""),
        "role": role,
        "hierarchy_level": hierarchy,
        "size_class": size_class,
        "group_hint": f"{role}:{hierarchy}:{size_class}",
        "confidence": None,
        "reason": "heuristic_role_and_bbox_height",
        "source": "heuristic",
        "fallback_reason": None,
        "vlm_role": None,
        "vlm_hierarchy_level": None,
        "vlm_size_class": None,
        "vlm_group_hint": None,
    }


def _context(program: dict) -> dict:
    def brief(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
        output = []
        for item in items:
            if not isinstance(item, dict):
                continue
            output.append({key: item.get(key) for key in keys if key in item})
        return output[:80]

    return {
        "panels": brief(program.get("panels", []), ("id", "title", "bbox_percent")),
        "slots": brief(program.get("slots", []), ("id", "paper_concept", "bbox_percent")),
        "arrows": brief(program.get("arrows", []), ("id", "source_id", "target_id", "source", "target", "label", "path_percent")),
    }


def _call_vlm_text_roles(reference_path: str | Path, regions: list[dict], program: dict, model: str | None = None) -> dict:
    api_base = os.getenv("API_BASE", "").rstrip("/")
    api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
    model_name = model or os.getenv("RFS_TEXT_ROLE_MODEL") or os.getenv("MODEL_VLM") or "gemini-3-pro-preview-thinking"
    if not api_base or not api_key:
        raise RuntimeError("VLM text role classification requires API_BASE and API_KEY/GEMINI_API_KEY environment variables")

    text_regions = [
        {
            "text_id": region.get("id"),
            "text": region.get("text"),
            "bbox_percent": region.get("bbox_percent"),
            "ocr_role_guess": region.get("ocr_role_guess") or region.get("role"),
            "raw_estimated_font_ratio": region.get("raw_estimated_font_ratio") or region.get("estimated_font_ratio"),
            "confidence": region.get("confidence"),
        }
        for region in regions
    ]
    prompt = f"""
You classify editable text in a scientific reference figure.

Use the reference image, OCR text regions, and figure context to classify text role and visual hierarchy only.
Do not output font sizes, point sizes, PowerPoint code, markdown, or explanations outside JSON.

Allowed role values:
{json.dumps(sorted(ALLOWED_ROLES), ensure_ascii=False)}

Allowed size_class values:
{json.dumps(sorted(ALLOWED_SIZE_CLASSES), ensure_ascii=False)}

Return schema:
{{
  "summary": "VLM text role classification.",
  "items": [
    {{
      "text_id": "input text_id",
      "role": "one allowed role",
      "hierarchy_level": "title|subtitle|body|annotation",
      "size_class": "tiny|small|medium|large|xlarge",
      "group_hint": "short stable grouping label for texts that should share one rendered font size",
      "confidence": 0.0,
      "reason": "short reason"
    }}
  ]
}}

OCR text regions:
{json.dumps(text_regions, ensure_ascii=False)}

Figure context:
{json.dumps(_context(program), ensure_ascii=False)}
""".strip()
    payload = {
        "model": model_name,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                _image_content(reference_path),
            ],
        }],
        "temperature": 0.1,
    }
    response = requests.post(
        f"{api_base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=180,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    parsed.setdefault("model", model_name)
    return parsed


def _coerce_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except Exception:
        return None
    return max(0.0, min(1.0, confidence))


def _clean_group_hint(value: Any, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9:_-]+", "_", str(value or "").strip())
    return text[:80] or fallback


def classify_text_roles(
    reference_path: str | Path,
    regions: list[dict],
    program: dict,
    *,
    mode: str = "heuristic",
    model: str | None = None,
    adapter: Callable[[str | Path, list[dict], dict, str | None], dict] | None = None,
    fallback_on_error: bool = False,
) -> dict:
    requested_mode = str(mode or "heuristic").lower()
    base = {str(region.get("id") or ""): _heuristic_decision(region) for region in regions}
    report = {
        "summary": "Text role classification for OCR-derived editable text regions.",
        "mode": requested_mode,
        "status": "pass",
        "model": model or os.getenv("RFS_TEXT_ROLE_MODEL") or os.getenv("MODEL_VLM"),
        "text_region_count": len(regions),
        "items": list(base.values()),
        "effective_mode": "heuristic" if requested_mode == "heuristic" or not regions else requested_mode,
        "fallback_count": 0,
        "warnings": [],
    }
    if requested_mode == "heuristic" or not regions:
        return report
    if requested_mode != "vlm":
        raise ValueError(f"Unsupported text role mode: {mode}")

    try:
        raw = adapter(reference_path, regions, program, model) if adapter else _call_vlm_text_roles(reference_path, regions, program, model=model)
    except Exception as exc:
        if not fallback_on_error:
            raise
        report.update({
            "status": "fallback_to_heuristic",
            "effective_mode": "heuristic",
            "fallback_reason": f"vlm_text_role_failed:{exc}",
            "items": list(base.values()),
        })
        report["warnings"].append(str(report["fallback_reason"]))
        return report
    raw_items = raw.get("items") or raw.get("text_roles") or []
    if not isinstance(raw_items, list):
        if fallback_on_error:
            report.update({
                "status": "fallback_to_heuristic",
                "effective_mode": "heuristic",
                "fallback_reason": "vlm_text_role_failed:missing_items_list",
                "items": list(base.values()),
            })
            report["warnings"].append(str(report["fallback_reason"]))
            return report
        raise RuntimeError("VLM text role classification returned no items list")
    raw_by_id = {str(item.get("text_id") or item.get("id") or ""): item for item in raw_items if isinstance(item, dict)}

    items = []
    fallback_count = 0
    for region in regions:
        text_id = str(region.get("id") or "")
        fallback = base[text_id]
        raw_item = raw_by_id.get(text_id)
        if not raw_item:
            chosen = dict(fallback)
            chosen.update({"source": "heuristic_fallback", "fallback_reason": "missing_vlm_item"})
            fallback_count += 1
            items.append(chosen)
            continue
        role = str(raw_item.get("role") or "").strip()
        size_class = str(raw_item.get("size_class") or "").strip()
        confidence = _coerce_confidence(raw_item.get("confidence"))
        fallback_reason = None
        if role not in ALLOWED_ROLES:
            fallback_reason = f"invalid_role:{role}"
        elif size_class not in ALLOWED_SIZE_CLASSES:
            fallback_reason = f"invalid_size_class:{size_class}"
        elif confidence is None or confidence < MIN_VLM_CONFIDENCE:
            fallback_reason = f"low_confidence:{confidence}"

        if fallback_reason:
            chosen = dict(fallback)
            chosen.update({
                "source": "heuristic_fallback",
                "fallback_reason": fallback_reason,
                "vlm_role": role or None,
                "vlm_hierarchy_level": raw_item.get("hierarchy_level"),
                "vlm_size_class": size_class or None,
                "vlm_group_hint": raw_item.get("group_hint"),
                "confidence": confidence,
                "reason": str(raw_item.get("reason") or fallback["reason"]),
            })
            fallback_count += 1
            items.append(chosen)
            continue

        hierarchy = str(raw_item.get("hierarchy_level") or fallback["hierarchy_level"]).strip() or fallback["hierarchy_level"]
        group_fallback = f"{role}:{hierarchy}:{size_class}"
        items.append({
            "text_id": text_id,
            "text": str(region.get("text") or ""),
            "ocr_role_guess": fallback["ocr_role_guess"],
            "role": role,
            "hierarchy_level": hierarchy,
            "size_class": size_class,
            "group_hint": _clean_group_hint(raw_item.get("group_hint"), group_fallback),
            "confidence": confidence,
            "reason": str(raw_item.get("reason") or ""),
            "source": "vlm",
            "fallback_reason": None,
            "vlm_role": role,
            "vlm_hierarchy_level": hierarchy,
            "vlm_size_class": size_class,
            "vlm_group_hint": raw_item.get("group_hint"),
        })
    report.update({
        "status": "pass_with_item_fallbacks" if fallback_count else "pass",
        "effective_mode": "vlm",
        "items": items,
        "fallback_count": fallback_count,
        "raw_summary": raw.get("summary"),
    })
    if fallback_count:
        report["warnings"].append(f"{fallback_count} text role item(s) used heuristic fallback")
    return report
