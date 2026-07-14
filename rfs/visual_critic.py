from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from .utils import write_json


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


def _call_vlm_json(prompt: str, image_paths: list[str | Path], model: str | None = None) -> dict:
    api_base = os.getenv("API_BASE", "").rstrip("/")
    api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
    model_name = model or os.getenv("RFS_CRITIC_MODEL") or os.getenv("MODEL_VLM") or "gemini-3-pro-preview-thinking"
    if not api_base or not api_key:
        raise RuntimeError("VLM critic requires API_BASE and API_KEY/GEMINI_API_KEY environment variables")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for path in image_paths:
        p = Path(path)
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }
    response = requests.post(
        f"{api_base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=180,
    )
    response.raise_for_status()
    content_text = response.json()["choices"][0]["message"]["content"]
    return _extract_json(content_text)


def _clean_bbox(bbox: dict) -> dict[str, float]:
    x = max(0.0, min(1.0, float(bbox.get("x", 0.0))))
    y = max(0.0, min(1.0, float(bbox.get("y", 0.0))))
    w = max(0.02, min(0.45, float(bbox.get("w", 0.1))))
    h = max(0.02, min(0.45, float(bbox.get("h", 0.1))))
    if x + w > 0.99:
        x = 0.99 - w
    if y + h > 0.98:
        y = 0.98 - h
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def run_visual_critic(
    out_dir: str | Path,
    reference_path: str | Path,
    final_png_path: str | Path | None,
    layout_plan: dict,
    program: dict,
    mode: str = "heuristic",
    model: str | None = None,
    iteration: int = 0,
) -> dict:
    out = Path(out_dir)
    if mode == "off":
        critic = {"summary": "Visual critic skipped by configuration.", "mode": "off", "status": "skipped", "layout_corrections": [], "arrow_corrections": [], "blocking_issues": []}
    elif mode == "heuristic":
        asset_issues = []
        complexity_path = out / "asset_complexity_report.json"
        if complexity_path.exists():
            try:
                complexity = json.loads(complexity_path.read_text(encoding="utf-8"))
                complexity_items = complexity.get("assets", []) if isinstance(complexity.get("assets"), list) else []
                for item in complexity_items:
                    tags = item.get("complexity_issue_tags", []) if isinstance(item.get("complexity_issue_tags"), list) else []
                    if item.get("simple_icon_risk") or any(tag in {"too_simple", "generic_icon", "reference_crop_ignored", "single_object_on_blank_background", "style_drift"} for tag in tags):
                        asset_issues.append({
                            "slot_id": item.get("slot_id"),
                            "issue_tags": sorted(set(tags + (["too_simple"] if item.get("simple_icon_risk") else []))),
                            "reason": item.get("selected_reason") or "asset complexity report flagged this slot",
                        })
            except Exception as exc:
                asset_issues.append({"slot_id": None, "issue_tags": ["invalid_asset_complexity_report"], "reason": str(exc)})
        critic = {
            "summary": "Heuristic visual critic completed using validator-compatible structural checks.",
            "mode": "heuristic",
            "status": "pass" if not asset_issues else "blocked",
            "layout_corrections": [],
            "arrow_corrections": [],
            "asset_issues": asset_issues,
            "ppt_editability_issues": [],
            "blocking_issues": [] if not asset_issues else ["asset_complexity_report has unresolved too-simple or reference-mismatch issues"],
        }
    elif mode == "vlm":
        if not final_png_path or not Path(final_png_path).exists():
            raise RuntimeError("VLM visual critic requires an exported final PNG")
        slot_brief = [
            {"id": slot.get("id"), "paper_concept": slot.get("paper_concept"), "bbox_percent": slot.get("bbox_percent")}
            for slot in layout_plan.get("slots", [])
        ]
        panel_brief = [
            {"id": panel.get("id"), "title": panel.get("title"), "bbox_percent": panel.get("bbox_percent")}
            for panel in layout_plan.get("panels", [])
        ]
        prompt = f"""
You are a visual layout critic for editable scientific PowerPoint figures.
Compare image 1 (user reference blueprint) and image 2 (current PPT render).
Only output JSON. Do not output Python, SVG, markdown, or prose.

You may only suggest coordinate corrections in normalized bbox_percent or arrow route JSON.
Do not suggest generating a new full diagram. Do not change scientific content.
Keep labels, formulas, arrows, panels, and groups editable in PPTX.

Check:
- major flow direction and panel positions
- slot count and visual density
- resource library location
- branch/candidate layout
- arrows crossing or isolated lines
- image blocks too small or overflowing
- text/labels baked into images
- too_simple/generic_icon/single-object asset failures from asset_complexity_report
- reference_crop_ignored/style_drift failures where slot assets do not follow the local crop

Return schema:
{{
  "summary": "...",
  "mode": "vlm",
  "status": "pass|needs_layout_refinement|blocked",
  "layout_corrections": [{{"target_id":"slot_or_panel_id","bbox_percent":{{"x":0,"y":0,"w":0.1,"h":0.1}},"reason":"..."}}],
  "arrow_corrections": [{{"arrow_id":"...","source_anchor":"right_mid","target_anchor":"left_mid","path_percent":[[0.1,0.2],[0.3,0.2]],"reason":"..."}}],
  "asset_issues": [{{"slot_id":"...","issue_tags":["too_small"],"reason":"..."}}],
  "ppt_editability_issues": ["..."],
  "blocking_issues": ["..."]
}}

Panels:
{json.dumps(panel_brief, ensure_ascii=False)}

Slots:
{json.dumps(slot_brief, ensure_ascii=False)}
""".strip()
        critic = _call_vlm_json(prompt, [reference_path, final_png_path], model=model)
        critic.setdefault("summary", "VLM visual critic compared reference blueprint and current PPT render.")
        critic.setdefault("mode", "vlm")
    else:
        raise ValueError(f"Unsupported visual critic mode: {mode}")

    write_json(out / f"visual_critic_iter_{iteration}.json", critic)
    return critic


def apply_layout_corrections(layout_plan: dict, critic: dict) -> tuple[dict, int]:
    corrections = critic.get("layout_corrections", [])
    changed = 0
    by_id = {item.get("id"): item for item in layout_plan.get("slots", []) if isinstance(item, dict)}
    by_id.update({item.get("id"): item for item in layout_plan.get("panels", []) if isinstance(item, dict)})
    for correction in corrections if isinstance(corrections, list) else []:
        if not isinstance(correction, dict):
            continue
        target_id = correction.get("target_id")
        bbox = correction.get("bbox_percent")
        if target_id in by_id and isinstance(bbox, dict):
            by_id[target_id]["bbox_percent"] = _clean_bbox(bbox)
            changed += 1

    arrow_by_id = {item.get("id"): item for item in layout_plan.get("arrows", []) if isinstance(item, dict)}
    for correction in critic.get("arrow_corrections", []) or []:
        if not isinstance(correction, dict):
            continue
        arrow_id = correction.get("arrow_id")
        path = correction.get("path_percent")
        if arrow_id in arrow_by_id and isinstance(path, list):
            arrow_by_id[arrow_id]["path_percent"] = path
            if str(correction.get("source_anchor", "")).strip():
                arrow_by_id[arrow_id]["source_anchor"] = str(correction.get("source_anchor"))
            if str(correction.get("target_anchor", "")).strip():
                arrow_by_id[arrow_id]["target_anchor"] = str(correction.get("target_anchor"))
            changed += 1

    return layout_plan, changed
