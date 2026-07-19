from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .utils import write_json
from .vlm_client import call_vlm_json, resolve_vlm_model


def _bbox(item: dict) -> dict | None:
    box = item.get("bbox_percent")
    return box if isinstance(box, dict) else None


def _valid_bbox(box: dict | None) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x = float(box["x"])
        y = float(box["y"])
        w = float(box["w"])
        h = float(box["h"])
    except Exception:
        return False
    return 0 <= x <= 1 and 0 <= y <= 1 and w > 0 and h > 0 and x + w <= 1.0001 and y + h <= 1.0001


def _overlap_area(a: dict, b: dict) -> float:
    ax0, ay0 = float(a["x"]), float(a["y"])
    ax1, ay1 = ax0 + float(a["w"]), ay0 + float(a["h"])
    bx0, by0 = float(b["x"]), float(b["y"])
    bx1, by1 = bx0 + float(b["w"]), by0 + float(b["h"])
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    return ix * iy


def _overlap_ratio(a: dict, b: dict) -> float:
    area = _overlap_area(a, b)
    if area <= 0:
        return 0.0
    a_area = float(a["w"]) * float(a["h"])
    b_area = float(b["w"]) * float(b["h"])
    return area / max(min(a_area, b_area), 0.000001)


def _visible_text_items(program: dict) -> list[dict]:
    text_program = program.get("text_program")
    if not isinstance(text_program, dict):
        return []
    return [item for item in text_program.get("items", []) if isinstance(item, dict) and item.get("visible", True)]


def _detect_text_issues(program: dict) -> list[dict]:
    issues = []
    items = _visible_text_items(program)
    for item in items:
        if not _valid_bbox(_bbox(item)):
            issues.append({"type": "text_bbox_out_of_bounds", "text_id": item.get("id"), "reason": "text bbox is missing or outside canvas"})
    for index, left in enumerate(items):
        lbox = _bbox(left)
        if not _valid_bbox(lbox):
            continue
        for right in items[index + 1:]:
            rbox = _bbox(right)
            if not _valid_bbox(rbox):
                continue
            ratio = _overlap_ratio(lbox, rbox)
            if ratio > 0.18:
                issues.append({
                    "type": "text_overlap",
                    "text_id": left.get("id"),
                    "other_text_id": right.get("id"),
                    "overlap_ratio": round(ratio, 4),
                    "reason": "visible text boxes overlap substantially",
                })
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        key = (str(item.get("target_id") or ""), str(item.get("role") or ""))
        grouped.setdefault(key, []).append(item)
    for (target_id, role), group in grouped.items():
        if len(group) < 3:
            continue
        centers = [
            float(item["bbox_percent"]["y"]) + float(item["bbox_percent"]["h"]) / 2
            for item in group
            if _valid_bbox(_bbox(item))
        ]
        if len(centers) >= 3 and max(centers) - min(centers) > 0.035:
            issues.append({
                "type": "text_group_misaligned",
                "target_id": target_id,
                "role": role,
                "text_ids": [item.get("id") for item in group],
                "center_y_span": round(max(centers) - min(centers), 4),
                "reason": "same target/role text group is visually uneven",
            })
    return issues


def _detect_object_issues(program: dict) -> list[dict]:
    issues = []
    for collection_name in ("panels", "slots"):
        items = [item for item in program.get(collection_name, []) if isinstance(item, dict)]
        for item in items:
            if not _valid_bbox(_bbox(item)):
                issues.append({"type": f"{collection_name[:-1]}_bbox_out_of_bounds", "id": item.get("id"), "reason": "bbox is missing or outside canvas"})
        for index, left in enumerate(items):
            lbox = _bbox(left)
            if not _valid_bbox(lbox):
                continue
            for right in items[index + 1:]:
                rbox = _bbox(right)
                if not _valid_bbox(rbox):
                    continue
                ratio = _overlap_ratio(lbox, rbox)
                if ratio > (0.35 if collection_name == "slots" else 0.18):
                    issues.append({
                        "type": f"{collection_name[:-1]}_overlap",
                        "id": left.get("id"),
                        "other_id": right.get("id"),
                        "overlap_ratio": round(ratio, 4),
                        "reason": f"{collection_name[:-1]} boxes overlap substantially",
                    })
    return issues


def _detect_arrow_issues(program: dict) -> list[dict]:
    issues = []
    for arrow in program.get("arrows", []) or []:
        if not isinstance(arrow, dict):
            continue
        path = arrow.get("path_percent")
        if not isinstance(path, list) or len(path) < 2:
            issues.append({"type": "arrow_missing_path", "arrow_id": arrow.get("id"), "reason": "arrow has no usable path_percent"})
    return issues


def _detect_ownership_issues(program: dict, ownership_report: dict | None) -> list[dict]:
    issues = []
    text_ids = {str(item.get("source_reference_text_id") or item.get("id") or "") for item in _visible_text_items(program)}
    report = ownership_report if isinstance(ownership_report, dict) else {}
    for item in report.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        text_id = str(item.get("text_id") or "")
        ownership = str(item.get("layer_ownership") or "")
        included = bool(item.get("included_in_text_program"))
        if ownership != "editable_text_layer" and text_id in text_ids:
            issues.append({"type": "text_layer_ownership_conflict", "text_id": text_id, "layer_ownership": ownership, "reason": "non-editable-owned text is present in text_program"})
        if ownership == "editable_text_layer" and not included:
            issues.append({"type": "text_layer_ownership_conflict", "text_id": text_id, "layer_ownership": ownership, "reason": "editable-owned text is missing from text_program"})
    return issues


def run_rebuild_visual_quality_check(
    out_dir: str | Path,
    program: dict,
    reference_geometry: dict | None = None,
    reference_controls: dict | None = None,
    ownership_report: dict | None = None,
    mode: str = "heuristic",
) -> dict[str, Any]:
    text_issues = _detect_text_issues(program)
    object_issues = _detect_object_issues(program)
    arrow_issues = _detect_arrow_issues(program)
    ownership_issues = _detect_ownership_issues(program, ownership_report)
    issues = text_issues + object_issues + arrow_issues + ownership_issues
    blocking_types = {"text_overlap", "text_bbox_out_of_bounds", "arrow_missing_path", "text_layer_ownership_conflict"}
    blocking = [item for item in issues if item.get("type") in blocking_types]
    report = {
        "summary": "Deterministic rebuild visual quality report.",
        "mode": mode,
        "status": "blocked" if blocking else ("warning" if issues else "pass"),
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking),
        "text_issue_count": len(text_issues),
        "object_issue_count": len(object_issues),
        "arrow_issue_count": len(arrow_issues),
        "ownership_issue_count": len(ownership_issues),
        "issues": issues,
        "reference_geometry_status": (reference_geometry or {}).get("status"),
        "reference_controls_status": (reference_controls or {}).get("status"),
        "policy": "deterministic check only; no program mutation",
    }
    write_json(Path(out_dir) / "rebuild_visual_quality_report.json", report)
    return report


def _brief_text(program: dict) -> list[dict]:
    return [{
        "id": item.get("id"),
        "source_reference_text_id": item.get("source_reference_text_id"),
        "text": item.get("text"),
        "role": item.get("role"),
        "target_id": item.get("target_id"),
        "bbox_percent": item.get("bbox_percent"),
        "font_size_pt": item.get("font_size_pt"),
        "align": item.get("align"),
        "visible": item.get("visible", True),
        "z_index": item.get("z_index"),
        "layer_ownership": item.get("layer_ownership"),
    } for item in _visible_text_items(program)]


def _brief_objects(program: dict, key: str) -> list[dict]:
    return [{
        "id": item.get("id"),
        "bbox_percent": item.get("bbox_percent"),
        "title": item.get("title"),
        "paper_concept": item.get("paper_concept"),
    } for item in program.get(key, []) or [] if isinstance(item, dict)]


def _brief_arrows(program: dict) -> list[dict]:
    return [{
        "id": item.get("id"),
        "source_id": item.get("source_id") or item.get("source"),
        "target_id": item.get("target_id") or item.get("target"),
        "path_percent": item.get("path_percent"),
        "render_style": item.get("render_style"),
        "stroke_width_pt": item.get("stroke_width_pt"),
        "line_pattern": item.get("line_pattern"),
    } for item in program.get("arrows", []) or [] if isinstance(item, dict)]


def run_rebuild_visual_critic(
    out_dir: str | Path,
    reference_path: str | Path,
    preview_path: str | Path | None,
    program: dict,
    deterministic_report: dict,
    mode: str = "heuristic",
    model: str | None = None,
    iteration: int = 0,
) -> dict:
    out = Path(out_dir)
    effective_mode = str(mode or "off").lower()
    if effective_mode == "off":
        critic = {"summary": "Rebuild visual critic skipped.", "mode": "off", "status": "skipped", "patches": [], "warnings": []}
    elif effective_mode == "heuristic":
        critic = {
            "summary": "Heuristic rebuild visual critic produced no mutating patches.",
            "mode": "heuristic",
            "status": deterministic_report.get("status", "pass"),
            "patches": [],
            "issues": deterministic_report.get("issues", []),
            "warnings": [],
        }
    elif effective_mode == "vlm":
        if not preview_path or not Path(preview_path).exists():
            critic = {
                "summary": "VLM rebuild visual critic skipped because preview PNG is unavailable.",
                "mode": "vlm",
                "status": "skipped",
                "patches": [],
                "warnings": ["preview_png_unavailable"],
            }
        else:
            model_name = resolve_vlm_model("RFS_REBUILD_CRITIC_MODEL", "RFS_CRITIC_MODEL", explicit_model=model)
            prompt = f"""
You are a visual patch generator for an editable PowerPoint reconstruction.
Compare image 1 (reference) and image 2 (current PPT preview).
Only output JSON. Do not output markdown, prose, Python, SVG, or PPT code.

Every fix must be a concrete patch operation with exact fields. Do not say "optimize", "improve", or "make better" unless you also provide exact patch fields.
Examples of concrete text instructions:
- update_text with font_size_pt: 10, z_index: 8
- update_text with bbox_percent: {{"x":0.615,"y":0.338,"w":0.12,"h":0.03}}, align:"center"
- update_arrow with path_percent:[[0.1,0.2],[0.3,0.2]], render_style:"line_connector"

Allowed patch operations:
- update_text: text_id required; may set bbox_percent, font_size_pt, align, visible, z_index, layer_ownership.
- update_slot: slot_id required; may set bbox_percent only.
- update_panel: panel_id required; may set bbox_percent only.
- update_arrow: arrow_id required; may set path_percent, render_style, stroke_width_pt, line_pattern.

Forbidden:
- Do not change text content.
- Do not request crop masking or image pixel edits.
- Do not write PPT code.
- Do not invent new objects.

Return schema:
{{
  "summary": "...",
  "mode": "vlm",
  "status": "pass|needs_patch|blocked",
  "patches": [
    {{"op":"update_text","text_id":"text_ref","font_size_pt":10,"z_index":8,"reason":"specific reason"}},
    {{"op":"update_slot","slot_id":"slot_1","bbox_percent":{{"x":0.1,"y":0.2,"w":0.2,"h":0.1}},"reason":"specific reason"}},
    {{"op":"update_arrow","arrow_id":"arrow_1","path_percent":[[0.1,0.2],[0.3,0.2]],"reason":"specific reason"}}
  ],
  "warnings": []
}}

Deterministic issues:
{json.dumps(deterministic_report.get("issues", []), ensure_ascii=False)}

Text items:
{json.dumps(_brief_text(program), ensure_ascii=False)}

Panels:
{json.dumps(_brief_objects(program, "panels"), ensure_ascii=False)}

Slots:
{json.dumps(_brief_objects(program, "slots"), ensure_ascii=False)}

Arrows:
{json.dumps(_brief_arrows(program), ensure_ascii=False)}
""".strip()
            critic = call_vlm_json(prompt, [reference_path, preview_path], model=model_name)
            critic.setdefault("summary", "VLM rebuild visual critic returned concrete patch operations.")
            critic.setdefault("mode", "vlm")
            critic.setdefault("status", "needs_patch" if critic.get("patches") else "pass")
            critic.setdefault("warnings", [])
            critic["vlm_model"] = model_name
    else:
        raise ValueError(f"Unsupported rebuild visual critic mode: {mode}")
    write_json(out / f"rebuild_visual_critic_iter_{iteration}.json", critic)
    return critic


def _limit_bbox_change(original: dict, requested: dict, center_limit: float, size_limit: float) -> dict:
    ox, oy, ow, oh = float(original["x"]), float(original["y"]), float(original["w"]), float(original["h"])
    rx = float(requested.get("x", ox))
    ry = float(requested.get("y", oy))
    rw = float(requested.get("w", ow))
    rh = float(requested.get("h", oh))
    ocx, ocy = ox + ow / 2, oy + oh / 2
    rcx, rcy = rx + rw / 2, ry + rh / 2
    dcx = max(-center_limit, min(center_limit, rcx - ocx))
    dcy = max(-center_limit, min(center_limit, rcy - ocy))
    min_w, max_w = ow * (1 - size_limit), ow * (1 + size_limit)
    min_h, max_h = oh * (1 - size_limit), oh * (1 + size_limit)
    nw = max(0.001, min(max_w, max(min_w, rw)))
    nh = max(0.001, min(max_h, max(min_h, rh)))
    nx = ocx + dcx - nw / 2
    ny = ocy + dcy - nh / 2
    return {
        "x": round(max(0.0, min(0.995, nx)), 4),
        "y": round(max(0.0, min(0.995, ny)), 4),
        "w": round(max(0.001, min(nw, 1.0 - max(0.0, min(0.995, nx)))), 4),
        "h": round(max(0.001, min(nh, 1.0 - max(0.0, min(0.995, ny)))), 4),
    }


def _limit_font_change(original: object, requested: object) -> float | None:
    try:
        original_value = float(original)
        requested_value = float(requested)
    except Exception:
        return None
    if original_value <= 0:
        return round(max(1.0, requested_value), 2)
    return round(max(original_value * 0.8, min(original_value * 1.2, requested_value)), 2)


def _coerce_path(path: object) -> list[list[float]] | None:
    if not isinstance(path, list) or len(path) < 2:
        return None
    points = []
    for item in path:
        if not isinstance(item, list) or len(item) < 2:
            return None
        points.append([round(max(0.0, min(1.0, float(item[0]))), 4), round(max(0.0, min(1.0, float(item[1]))), 4)])
    return points


def _refresh_ownership_report(out: Path, program: dict) -> None:
    path = out / "text_layer_ownership_report.json"
    if not path.exists():
        return
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    text_program = program.get("text_program", {}) if isinstance(program.get("text_program"), dict) else {}
    by_source = {str(item.get("source_reference_text_id") or ""): item for item in text_program.get("items", []) if isinstance(item, dict)}
    changed = False
    for item in report.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        text_id = str(item.get("text_id") or "")
        if text_id in by_source:
            item["layer_ownership"] = by_source[text_id].get("layer_ownership", item.get("layer_ownership"))
            item["included_in_text_program"] = bool(by_source[text_id].get("visible", True)) and item["layer_ownership"] == "editable_text_layer"
            changed = True
    if changed:
        write_json(path, report)


def apply_rebuild_corrections(out_dir: str | Path, program: dict, critic: dict, iteration: int = 0) -> tuple[dict, dict]:
    out = Path(out_dir)
    updated = copy.deepcopy(program)
    patches = critic.get("patches", []) if isinstance(critic.get("patches"), list) else []
    applied = []
    rejected = []
    changed_slots: set[str] = set()
    changed_arrows = False
    text_program = updated.get("text_program") if isinstance(updated.get("text_program"), dict) else {"items": []}
    text_by_id = {str(item.get("id") or ""): item for item in text_program.get("items", []) if isinstance(item, dict)}
    slots_by_id = {str(item.get("id") or ""): item for item in updated.get("slots", []) if isinstance(item, dict)}
    panels_by_id = {str(item.get("id") or ""): item for item in updated.get("panels", []) if isinstance(item, dict)}
    arrows_by_id = {str(item.get("id") or ""): item for item in updated.get("arrows", []) if isinstance(item, dict)}

    for patch in patches:
        if not isinstance(patch, dict):
            rejected.append({"patch": patch, "reason": "patch_not_object"})
            continue
        op = str(patch.get("op") or "").strip()
        if op == "update_text":
            text_id = str(patch.get("text_id") or "")
            item = text_by_id.get(text_id)
            if not item:
                rejected.append({"patch": patch, "reason": "unknown_text_id"})
                continue
            changed = {}
            if isinstance(patch.get("bbox_percent"), dict) and isinstance(item.get("bbox_percent"), dict):
                item["bbox_percent"] = _limit_bbox_change(item["bbox_percent"], patch["bbox_percent"], center_limit=0.03, size_limit=0.20)
                item["center_percent"] = {"x": round(float(item["bbox_percent"]["x"]) + float(item["bbox_percent"]["w"]) / 2, 4), "y": round(float(item["bbox_percent"]["y"]) + float(item["bbox_percent"]["h"]) / 2, 4)}
                item["width_percent"] = item["bbox_percent"]["w"]
                item["height_percent"] = item["bbox_percent"]["h"]
                changed["bbox_percent"] = item["bbox_percent"]
            if patch.get("font_size_pt") is not None:
                limited = _limit_font_change(item.get("font_size_pt"), patch.get("font_size_pt"))
                if limited is not None:
                    item["font_size_pt"] = limited
                    changed["font_size_pt"] = limited
            if str(patch.get("align") or "").lower() in {"left", "center", "right"}:
                item["align"] = str(patch["align"]).lower()
                changed["align"] = item["align"]
            if patch.get("visible") is not None:
                item["visible"] = bool(patch.get("visible"))
                changed["visible"] = item["visible"]
            if patch.get("z_index") is not None:
                try:
                    item["z_index"] = int(max(0, min(1000, int(patch.get("z_index")))))
                    changed["z_index"] = item["z_index"]
                except Exception:
                    pass
            ownership = str(patch.get("layer_ownership") or "")
            if ownership in {"editable_text_layer", "raster_asset_layer", "decorative_asset_text", "ignore"}:
                item["layer_ownership"] = ownership
                if ownership != "editable_text_layer":
                    item["visible"] = False
                changed["layer_ownership"] = ownership
            if changed:
                applied.append({"op": op, "text_id": text_id, "applied": changed, "reason": patch.get("reason")})
            else:
                rejected.append({"patch": patch, "reason": "no_allowed_text_fields"})
        elif op in {"update_slot", "update_panel"}:
            key = "slot_id" if op == "update_slot" else "panel_id"
            object_id = str(patch.get(key) or "")
            item = (slots_by_id if op == "update_slot" else panels_by_id).get(object_id)
            if not item or not isinstance(patch.get("bbox_percent"), dict) or not isinstance(item.get("bbox_percent"), dict):
                rejected.append({"patch": patch, "reason": f"unknown_or_invalid_{key}"})
                continue
            item["bbox_percent"] = _limit_bbox_change(item["bbox_percent"], patch["bbox_percent"], center_limit=0.05, size_limit=0.20)
            if op == "update_slot":
                changed_slots.add(object_id)
            applied.append({"op": op, key: object_id, "applied": {"bbox_percent": item["bbox_percent"]}, "reason": patch.get("reason")})
        elif op == "update_arrow":
            arrow_id = str(patch.get("arrow_id") or "")
            item = arrows_by_id.get(arrow_id)
            if not item:
                rejected.append({"patch": patch, "reason": "unknown_arrow_id"})
                continue
            changed = {}
            path = _coerce_path(patch.get("path_percent"))
            if path:
                item["path_percent"] = path
                changed["path_percent"] = path
            if str(patch.get("render_style") or "") in {"filled_block_arrow", "line_connector", "elbow_connector", "branch_line_connector", "dashed_loop_connector"}:
                item["render_style"] = str(patch["render_style"])
                changed["render_style"] = item["render_style"]
            if patch.get("stroke_width_pt") is not None:
                try:
                    item["stroke_width_pt"] = round(max(0.25, min(12.0, float(patch["stroke_width_pt"]))), 2)
                    changed["stroke_width_pt"] = item["stroke_width_pt"]
                except Exception:
                    pass
            if str(patch.get("line_pattern") or "") in {"solid", "dash", "dashed"}:
                item["line_pattern"] = "dash" if str(patch["line_pattern"]) == "dashed" else str(patch["line_pattern"])
                changed["line_pattern"] = item["line_pattern"]
            if changed:
                changed_arrows = True
                applied.append({"op": op, "arrow_id": arrow_id, "applied": changed, "reason": patch.get("reason")})
            else:
                rejected.append({"patch": patch, "reason": "no_allowed_arrow_fields"})
        else:
            rejected.append({"patch": patch, "reason": "unsupported_operation"})

    correction_report = {
        "summary": "Applied controlled rebuild visual critic corrections.",
        "iteration": iteration,
        "status": "changed" if applied else "no_changes",
        "applied_count": len(applied),
        "rejected_count": len(rejected),
        "changed_slot_ids": sorted(changed_slots),
        "changed_arrows": changed_arrows,
        "applied": applied,
        "rejected": rejected,
        "limits": {
            "text_center_move_percent": 0.03,
            "text_font_scale": "80%-120%",
            "slot_panel_center_move_percent": 0.05,
            "slot_panel_size_scale": "80%-120%",
        },
    }
    write_json(out / f"rebuild_corrections_iter_{iteration}.json", correction_report)
    if isinstance(updated.get("text_program"), dict):
        write_json(out / "text_program.json", updated["text_program"])
        _refresh_ownership_report(out, updated)
    return updated, correction_report
