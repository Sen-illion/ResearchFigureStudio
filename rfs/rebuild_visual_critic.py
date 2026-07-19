from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import write_json


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
