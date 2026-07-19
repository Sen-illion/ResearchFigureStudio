from __future__ import annotations

from statistics import median
from typing import Callable

from .utils import write_json


def _clamp_bbox(bbox: dict) -> dict[str, float]:
    x = max(0.0, min(0.995, float(bbox["x"])))
    y = max(0.0, min(0.995, float(bbox["y"])))
    w = max(0.001, min(float(bbox["w"]), 1.0 - x))
    h = max(0.001, min(float(bbox["h"]), 1.0 - y))
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _center(bbox: dict) -> dict[str, float]:
    return {
        "x": round(float(bbox["x"]) + float(bbox["w"]) / 2, 4),
        "y": round(float(bbox["y"]) + float(bbox["h"]) / 2, 4),
    }


def _union_bbox(regions: list[dict], expand: float = 0.0) -> dict[str, float]:
    xs0 = [float(item["bbox_percent"]["x"]) for item in regions]
    ys0 = [float(item["bbox_percent"]["y"]) for item in regions]
    xs1 = [float(item["bbox_percent"]["x"]) + float(item["bbox_percent"]["w"]) for item in regions]
    ys1 = [float(item["bbox_percent"]["y"]) + float(item["bbox_percent"]["h"]) for item in regions]
    x0 = min(xs0) - expand
    y0 = min(ys0) - expand
    x1 = max(xs1) + expand
    y1 = max(ys1) + expand
    return _clamp_bbox({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})


def _raw_ratio(region: dict) -> float:
    try:
        return float(region.get("raw_estimated_font_ratio") or region.get("estimated_font_ratio") or 0.0)
    except Exception:
        return 0.0


def _font_pt(region: dict) -> float:
    try:
        return float(region.get("raw_font_size_pt") or region.get("font_size_pt") or 0.0)
    except Exception:
        return 0.0


def _line_sort_key(region: dict) -> tuple[float, float]:
    bbox = region["bbox_percent"]
    return float(bbox["y"]), float(bbox["x"])


def _eligible_for_heuristic_grouping(region: dict) -> bool:
    if not str(region.get("source") or "").startswith("reference_ocr"):
        return False
    if str(region.get("role") or "") == "panel_title":
        return False
    text = str(region.get("text") or "").strip()
    return bool(text)


def _same_paragraph(previous: dict, current: dict) -> bool:
    if str(previous.get("target_id") or "") != str(current.get("target_id") or ""):
        return False
    if str(previous.get("role") or "") != str(current.get("role") or ""):
        return False
    if str(previous.get("font_family_guess") or "") != str(current.get("font_family_guess") or ""):
        return False
    prev = previous["bbox_percent"]
    cur = current["bbox_percent"]
    prev_h = float(prev["h"])
    cur_h = float(cur["h"])
    median_h = max(0.001, median([prev_h, cur_h]))
    vertical_gap = float(cur["y"]) - (float(prev["y"]) + prev_h)
    if vertical_gap < -median_h * 0.25 or vertical_gap > max(0.012, median_h * 0.95):
        return False
    height_delta = abs(prev_h - cur_h) / median_h
    if height_delta > 0.35:
        return False
    left_delta = abs(float(prev["x"]) - float(cur["x"]))
    if left_delta > max(0.018, median_h * 1.25):
        return False
    width_ratio = min(float(prev["w"]), float(cur["w"])) / max(float(prev["w"]), float(cur["w"]), 0.001)
    if width_ratio < 0.28:
        return False
    ratio_values = [value for value in [_raw_ratio(previous), _raw_ratio(current)] if value > 0]
    if len(ratio_values) == 2 and abs(ratio_values[0] - ratio_values[1]) / max(median(ratio_values), 0.0001) > 0.35:
        return False
    return True


def _make_group(group_id: str, members: list[dict]) -> dict:
    ordered = sorted(members, key=_line_sort_key)
    bbox = _union_bbox(ordered, expand=0.0015)
    raw_ratios = [_raw_ratio(item) for item in ordered if _raw_ratio(item) > 0]
    raw_pts = [_font_pt(item) for item in ordered if _font_pt(item) > 0]
    confidences = [float(item.get("confidence") or 0.0) for item in ordered if item.get("confidence") is not None]
    estimated_ratio = round(median(raw_ratios), 5) if raw_ratios else round(float(bbox["h"]) * 0.62, 5)
    font_pt = round(median(raw_pts), 2) if raw_pts else None
    region = dict(ordered[0])
    region.update({
        "id": group_id,
        "text": "\n".join(str(item.get("text") or "").strip() for item in ordered if str(item.get("text") or "").strip()),
        "raw_text": "\n".join(str(item.get("raw_text") or item.get("text") or "").strip() for item in ordered if str(item.get("raw_text") or item.get("text") or "").strip()),
        "bbox_percent": bbox,
        "line_bbox_percent": [item["bbox_percent"] for item in ordered],
        "word_bbox_percent": [box for item in ordered for box in (item.get("word_bbox_percent") or [item["bbox_percent"]])],
        "center_percent": _center(bbox),
        "width_percent": round(float(bbox["w"]), 4),
        "height_percent": round(float(bbox["h"]), 4),
        "estimated_font_ratio": estimated_ratio,
        "raw_estimated_font_ratio": estimated_ratio,
        "font_size_pt": font_pt or region.get("font_size_pt"),
        "raw_font_size_pt": font_pt or region.get("raw_font_size_pt"),
        "confidence": round(sum(confidences) / len(confidences), 4) if confidences else region.get("confidence"),
        "source": "reference_ocr_paragraph_group_heuristic",
        "ocr_member_ids": [str(item.get("id") or "") for item in ordered],
        "ocr_member_count": len(ordered),
        "grouping_source": "heuristic",
        "editable_in": "pptx",
    })
    return region


def group_text_regions_heuristic(regions: list[dict]) -> tuple[list[dict], dict, dict]:
    eligible = [item for item in regions if isinstance(item, dict) and isinstance(item.get("bbox_percent"), dict) and _eligible_for_heuristic_grouping(item)]
    ineligible = [item for item in regions if item not in eligible]
    grouped: list[list[dict]] = []
    for region in sorted(eligible, key=lambda item: (str(item.get("target_id") or ""), str(item.get("role") or ""), *_line_sort_key(item))):
        if grouped and _same_paragraph(grouped[-1][-1], region):
            grouped[-1].append(region)
        else:
            grouped.append([region])

    result: list[dict] = []
    group_records: list[dict] = []
    for index, members in enumerate(grouped, start=1):
        if len(members) == 1:
            item = dict(members[0])
            item.setdefault("ocr_member_ids", [str(item.get("id") or "")])
            item.setdefault("ocr_member_count", 1)
            item.setdefault("grouping_source", "heuristic_singleton")
            result.append(item)
            continue
        group_id = f"ref_text_group_{index:03d}"
        group = _make_group(group_id, members)
        result.append(group)
        group_records.append({
            "group_id": group_id,
            "ocr_member_ids": group["ocr_member_ids"],
            "target_id": group.get("target_id"),
            "role": group.get("role"),
            "bbox_percent": group.get("bbox_percent"),
            "text": group.get("text"),
        })
    for item in ineligible:
        singleton = dict(item)
        singleton.setdefault("ocr_member_ids", [str(singleton.get("id") or "")])
        singleton.setdefault("ocr_member_count", 1)
        singleton.setdefault("grouping_source", "heuristic_ineligible_singleton")
        result.append(singleton)
    result.sort(key=lambda item: _line_sort_key(item) if isinstance(item.get("bbox_percent"), dict) else (1.0, 1.0))

    plan = {
        "summary": "Heuristic OCR grouping plan.",
        "mode": "heuristic",
        "groups": group_records,
        "ignored_ocr_ids": [],
    }
    report = {
        "summary": "Text grouping report.",
        "mode": "heuristic",
        "status": "pass",
        "raw_region_count": len(regions),
        "grouped_region_count": len(result),
        "paragraph_group_count": len(group_records),
        "single_region_count": len([item for item in result if int(item.get("ocr_member_count") or 1) == 1]),
        "warnings": [],
    }
    return result, plan, report


def group_text_regions(
    regions: list[dict],
    mode: str = "heuristic",
    adapter: Callable | None = None,
    **_kwargs,
) -> tuple[list[dict], dict, dict]:
    effective_mode = str(mode or "heuristic").lower()
    if effective_mode == "off" or not regions:
        plan = {"summary": "Text grouping skipped.", "mode": effective_mode, "groups": [], "ignored_ocr_ids": []}
        report = {
            "summary": "Text grouping report.",
            "mode": effective_mode,
            "status": "skipped" if effective_mode == "off" else "pass",
            "raw_region_count": len(regions),
            "grouped_region_count": len(regions),
            "paragraph_group_count": 0,
            "single_region_count": len(regions),
            "warnings": [],
        }
        return regions, plan, report
    if effective_mode != "heuristic":
        raise ValueError(f"Unsupported text grouping mode for this build: {mode}")
    return group_text_regions_heuristic(regions)


def write_text_grouping_artifacts(out_dir, raw_geometry: dict, plan: dict, report: dict) -> None:
    write_json(out_dir / "reference_text_geometry_raw.json", raw_geometry)
    write_json(out_dir / "text_grouping_plan.json", plan)
    write_json(out_dir / "text_grouping_report.json", report)
