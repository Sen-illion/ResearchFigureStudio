from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from PIL import Image

from .reference_text_extractor import extract_reference_text
from .utils import write_json


def _bbox_center(bbox: dict) -> dict:
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    return {"x": round(x + w / 2, 4), "y": round(y + h / 2, 4)}


def _clamp_bbox(bbox: dict) -> dict:
    x = max(0.0, min(0.995, float(bbox["x"])))
    y = max(0.0, min(0.995, float(bbox["y"])))
    w = max(0.001, min(float(bbox["w"]), 1.0 - x))
    h = max(0.001, min(float(bbox["h"]), 1.0 - y))
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _region_record(region_id: str, text: str, role: str, bbox: dict, color_hex: str, source: str, target_id: str) -> dict:
    bbox = _clamp_bbox(bbox)
    return {
        "id": region_id,
        "text": text,
        "role": role,
        "target_id": target_id,
        "bbox_percent": bbox,
        "center_percent": _bbox_center(bbox),
        "width_percent": round(float(bbox["w"]), 4),
        "height_percent": round(float(bbox["h"]), 4),
        "estimated_font_ratio": round(float(bbox["h"]) * 0.62, 5),
        "color_hex": color_hex,
        "source": source,
        "editable_in": "pptx",
    }


def _rgb_tuple(hex_color: str) -> tuple[int, int, int]:
    text = str(hex_color or "#000000").strip().lstrip("#")
    if len(text) < 6:
        return 0, 0, 0
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _luminance(rgb: tuple[int, int, int]) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _sample_text_color(reference_path: str | Path, bbox: dict, fallback: str = "#263747") -> str:
    try:
        with Image.open(reference_path) as image:
            image = image.convert("RGB")
            iw, ih = image.size
            x0 = max(0, min(iw - 1, int(float(bbox["x"]) * iw)))
            y0 = max(0, min(ih - 1, int(float(bbox["y"]) * ih)))
            x1 = max(x0 + 1, min(iw, int((float(bbox["x"]) + float(bbox["w"])) * iw)))
            y1 = max(y0 + 1, min(ih, int((float(bbox["y"]) + float(bbox["h"])) * ih)))
            crop = image.crop((x0, y0, x1, y1))
            pixels = list(crop.getdata())
    except Exception:
        return fallback
    if not pixels:
        return fallback
    dark = [px for px in pixels if _luminance(px) < 215]
    candidates = dark or pixels
    candidates.sort(key=_luminance)
    return _hex(candidates[len(candidates) // 3])


def _nearest_token_id(style: dict, color_hex: str) -> str:
    tokens = style.get("color_tokens", []) if isinstance(style.get("color_tokens"), list) else []
    if not tokens:
        return ""
    target = _rgb_tuple(color_hex)
    best_id = ""
    best_dist = math.inf
    for token in tokens:
        if not isinstance(token, dict):
            continue
        token_hex = str(token.get("hex") or "")
        if not token_hex:
            continue
        rgb = _rgb_tuple(token_hex)
        dist = sum((target[i] - rgb[i]) ** 2 for i in range(3))
        if dist < best_dist:
            best_dist = dist
            best_id = str(token.get("token_id") or "")
    return best_id


def _short_label(text: str) -> str:
    replacements = {
        "ffmpeg video-to-audio extraction": "FFmpeg",
        "funasr speech recognition microphone": "FunASR",
        "funasr speech recognition": "FunASR",
        "mtcnn face detection": "MTCNN",
        "alphapose full-body skeleton extraction": "AlphaPose",
        "frame sampling stack": "Frame sampling",
        "frame sampling from video": "Frame sampling",
        "audio waveform output": "audio waveform",
        "spoken text with timestamps": "transcript + time",
        "raw interview video recording": "Raw interview video",
        "participant full-body video thumbnail grid": "Sampled full-body clips",
        "face modality": "Face",
        "frame modality": "Frame",
        "pose modality": "Pose",
        "audio modality": "Audio",
        "text modality": "Text",
        "neo-ffi-3 questionnaire checklist": "NEO-FFI-3 questionnaire",
        "multimodal personality dataset database": "Multimodal signals + Big Five labels",
    }
    normalized = " ".join(str(text or "").strip().split()).lower()
    if normalized in replacements:
        return replacements[normalized]
    raw = str(text or "").strip()
    if len(raw) <= 24:
        return raw
    words = raw.replace("/", " ").split()
    return " ".join(words[:3])


def _slot_role(slot: dict) -> str:
    text = f"{slot.get('id', '')} {slot.get('paper_concept', '')} {slot.get('display_label', '')}".lower()
    if "legend" in text:
        return "legend_label"
    if "modality" in text:
        return "modality_label"
    if any(term in text for term in ("ffmpeg", "funasr", "mtcnn", "alphapose", "frame sampling", "waveform", "transcript")):
        return "method_label"
    if any(term in text for term in ("openness", "conscientious", "extraversion", "agreeableness", "neuroticism", "ocean")):
        return "trait_label"
    if bool(slot.get("show_slot_caption")) or str(slot.get("display_label", "")).strip():
        return "slot_caption"
    return "hidden_slot_label"


def _slot_text_visible(slot: dict, role: str) -> bool:
    if role == "hidden_slot_label":
        return False
    if bool(slot.get("show_slot_caption")) or str(slot.get("display_label", "")).strip():
        return True
    return role in {"legend_label", "modality_label", "method_label", "trait_label"}


def _parent_panel(slot: dict, panels: dict[str, dict]) -> dict | None:
    for key in ("parent_panel", "panel_id", "macro_panel_id"):
        value = str(slot.get(key) or "")
        if value in panels:
            return panels[value]
    return None


def _caption_bbox_for_slot(slot: dict, panels: dict[str, dict]) -> dict:
    box = slot["bbox_percent"]
    x = float(box["x"])
    y = float(box["y"])
    w = float(box["w"])
    h = float(box["h"])
    panel = _parent_panel(slot, panels)
    role = _slot_role(slot)
    if role in {"modality_label", "trait_label"} and panel:
        pbox = panel["bbox_percent"]
        label_x = x + w + 0.004
        panel_right = float(pbox["x"]) + float(pbox["w"])
        return _clamp_bbox({
            "x": label_x,
            "y": y + h * 0.18,
            "w": max(0.014, panel_right - label_x - 0.004),
            "h": h * 0.58,
        })
    label_h = max(0.012, min(0.026, h * 0.20))
    label_y = y + h + 0.006
    if panel:
        pbox = panel["bbox_percent"]
        panel_bottom = float(pbox["y"]) + float(pbox["h"])
        if label_y + label_h > panel_bottom - 0.004:
            label_y = y - label_h - 0.004
    return _clamp_bbox({
        "x": x + w * 0.03,
        "y": label_y,
        "w": w * 0.94,
        "h": label_h,
    })


def _panel_title_bbox(panel: dict, canvas_height_in: float) -> dict:
    bbox = panel["bbox_percent"]
    header_h = min(float(bbox["h"]) * 0.17, 0.34 / max(canvas_height_in, 0.001))
    return _clamp_bbox({"x": bbox["x"], "y": bbox["y"], "w": bbox["w"], "h": header_h})


def _font_pt_from_reference_region(region: dict, canvas_height_in: float) -> float:
    role = str(region.get("role") or "")
    multiplier = 0.44 if role == "panel_title" else 0.62
    return round(max(1.0, float(region["height_percent"]) * canvas_height_in * 72 * multiplier), 2)


def _alignment_item(item: dict, region: dict) -> dict:
    ib = item["bbox_percent"]
    rb = region["bbox_percent"]
    ic = item["center_percent"]
    rc = region["center_percent"]
    center_delta = math.sqrt((float(ic["x"]) - float(rc["x"])) ** 2 + (float(ic["y"]) - float(rc["y"])) ** 2)
    width_delta = abs(float(ib["w"]) - float(rb["w"]))
    height_delta = abs(float(ib["h"]) - float(rb["h"]))
    font_delta = abs(float(item["estimated_font_ratio"]) - float(region["estimated_font_ratio"]))
    status = "pass"
    if center_delta > 0.05 or width_delta > 0.08 or height_delta > 0.06 or item.get("editable_in") != "pptx":
        status = "fail"
    return {
        "label_id": item["id"],
        "source_reference_text_id": region["id"],
        "role": item["role"],
        "center_delta_percent": round(center_delta, 5),
        "width_delta_percent": round(width_delta, 5),
        "height_delta_percent": round(height_delta, 5),
        "font_ratio_delta": round(font_delta, 5),
        "color_status": "reference_token" if item.get("color_token_id") else "sampled_reference_color",
        "editable_in": item.get("editable_in"),
        "status": status,
    }


def _heuristic_regions(reference_path: str | Path, program: dict, canvas_height_in: float) -> list[dict]:
    panels = {panel["id"]: panel for panel in program.get("panels", []) if isinstance(panel, dict) and panel.get("id")}
    regions: list[dict] = []
    for panel in program.get("panels", []):
        if not isinstance(panel, dict) or not panel.get("bbox_percent"):
            continue
        bbox = _panel_title_bbox(panel, canvas_height_in)
        regions.append(_region_record(
            f"ref_text_panel_{panel['id']}",
            str(panel.get("title") or panel.get("paper_concept") or panel["id"]),
            "panel_title",
            bbox,
            "#FFFFFF",
            "reference_panel_header_geometry",
            panel["id"],
        ))

    for slot in program.get("slots", []):
        if not isinstance(slot, dict) or not slot.get("bbox_percent"):
            continue
        role = _slot_role(slot)
        if not _slot_text_visible(slot, role):
            continue
        label = str(slot.get("display_label") or "").strip() or _short_label(str(slot.get("paper_concept") or slot.get("id") or ""))
        bbox = _caption_bbox_for_slot(slot, panels)
        color = _sample_text_color(reference_path, bbox, fallback="#263747")
        regions.append(_region_record(
            f"ref_text_slot_{slot['id']}",
            label,
            role,
            bbox,
            color,
            "reference_slot_text_region_inferred",
            slot["id"],
        ))

    for arrow in program.get("arrows", []):
        label = str(arrow.get("label") or "").strip()
        path = arrow.get("path_percent") if isinstance(arrow.get("path_percent"), list) else []
        if not label or len(path) < 2:
            continue
        xs = [float(point[0]) for point in path if isinstance(point, list) and len(point) >= 2]
        ys = [float(point[1]) for point in path if isinstance(point, list) and len(point) >= 2]
        if not xs or not ys:
            continue
        mid_x = (min(xs) + max(xs)) / 2
        mid_y = (min(ys) + max(ys)) / 2
        bbox = {"x": mid_x - 0.025, "y": mid_y - 0.01, "w": 0.05, "h": 0.02}
        color = _sample_text_color(reference_path, bbox, fallback="#263747")
        regions.append(_region_record(
            f"ref_text_arrow_{arrow.get('id')}",
            label,
            "arrow_label",
            bbox,
            color,
            "reference_arrow_label_region_inferred",
            str(arrow.get("id") or ""),
        ))
    return regions


def _overlap(a: dict, b: dict) -> float:
    ax0, ay0 = float(a["x"]), float(a["y"])
    ax1, ay1 = ax0 + float(a["w"]), ay0 + float(a["h"])
    bx0, by0 = float(b["x"]), float(b["y"])
    bx1, by1 = bx0 + float(b["w"]), by0 + float(b["h"])
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    return (ix * iy) / max(float(b["w"]) * float(b["h"]), 0.000001)


def _merge_ocr_with_fallback(ocr_regions: list[dict], fallback_regions: list[dict]) -> list[dict]:
    if not ocr_regions:
        return fallback_regions
    merged = list(ocr_regions)
    for fallback in fallback_regions:
        target_id = str(fallback.get("target_id") or "")
        role = str(fallback.get("role") or "")
        duplicate = False
        for region in ocr_regions:
            if str(region.get("target_id") or "") == target_id and str(region.get("role") or "") == role:
                duplicate = True
                break
            if _overlap(region["bbox_percent"], fallback["bbox_percent"]) > 0.45:
                duplicate = True
                break
        if not duplicate and role == "panel_title":
            fallback = dict(fallback)
            fallback["source"] = "reference_panel_header_geometry_fallback_after_ocr"
            merged.append(fallback)
    return merged


def build_text_layer(
    reference_path: str | Path,
    program: dict,
    style: dict,
    out_dir: str | Path,
    text_extractor_mode: str = "ocr",
    ocr_engine: str = "paddle",
    ocr_lang: str = "en_ch",
    ocr_adapter: Callable[[str | Path, str], list[dict]] | None = None,
) -> dict:
    """Build reference-first editable text artifacts and attach them to the program."""

    out = Path(out_dir)
    canvas = program.get("canvas", {}) if isinstance(program.get("canvas"), dict) else {}
    canvas_height_in = float(canvas.get("height_in") or 7.5)

    fallback_regions = _heuristic_regions(reference_path, program, canvas_height_in)
    ocr_regions, ocr_report = extract_reference_text(
        reference_path,
        program,
        mode=text_extractor_mode,
        engine=ocr_engine,
        lang=ocr_lang,
        ocr_adapter=ocr_adapter,
    )
    regions = _merge_ocr_with_fallback(ocr_regions, fallback_regions)
    if not ocr_regions:
        ocr_report["text_region_count"] = len(regions)
        ocr_report.setdefault("warnings", [])
        ocr_report["warnings"].append("using_heuristic_text_layer_fallback")

    items: list[dict] = []
    for region in regions:
        font_size = float(region.get("font_size_pt") or _font_pt_from_reference_region(region, canvas_height_in))
        token_id = _nearest_token_id(style, region["color_hex"])
        item = {
            "id": f"text_{region['id']}",
            "text": region["text"],
            "role": region["role"],
            "target_id": region["target_id"],
            "source_reference_text_id": region["id"],
            "reference_binding": region["source"],
            "bbox_percent": region["bbox_percent"],
            "center_percent": region["center_percent"],
            "width_percent": region["width_percent"],
            "height_percent": region["height_percent"],
            "estimated_font_ratio": region["estimated_font_ratio"],
            "font_size_pt": font_size,
            "color_hex": region["color_hex"],
            "color_token_id": token_id,
            "bold": str(region.get("font_weight_guess") or "").lower() == "bold" or region["role"] in {"panel_title", "method_label", "modality_label"},
            "align": "left" if region["role"] in {"modality_label", "trait_label", "arrow_label"} else "center",
            "font_family_guess": region.get("font_family_guess") or ("Microsoft YaHei" if any(ord(char) > 127 for char in str(region.get("text", ""))) else "Arial"),
            "font_weight_guess": region.get("font_weight_guess") or ("bold" if region["role"] in {"panel_title", "method_label", "modality_label"} else "regular"),
            "fit_strategy": "ocr_bbox_exact" if str(region.get("source", "")).startswith("reference_ocr") else "reference_geometry_bbox",
            "ocr_confidence": region.get("confidence"),
            "editable_in": "pptx",
            "visible": True,
        }
        items.append(item)

    geometry = {
        "summary": "Reference-first text geometry extracted or inferred from the reference layout; no publication font threshold is applied.",
        "reference_path": str(reference_path),
        "policy": "reference_image_is_highest_authority_for_text_size_position_color_and_hierarchy",
        "detection_mode": "ocr" if ocr_regions else "reference_geometry_and_local_color_sampling",
        "ocr_engine": ocr_engine,
        "ocr_lang": ocr_lang,
        "text_regions": regions,
    }
    text_program = {
        "summary": "Reference-first editable PPT text program derived from reference_text_geometry.json.",
        "policy": "match_reference_text_geometry; reference_layout_over_typography_defaults",
        "reference_text_geometry_path": "reference_text_geometry.json",
        "items": items,
    }
    region_by_id = {region["id"]: region for region in regions}
    report_items = [_alignment_item(item, region_by_id[item["source_reference_text_id"]]) for item in items]
    alignment_report = {
        "summary": "Text alignment report comparing PPT text program geometry against reference-derived text geometry.",
        "policy": "reference_alignment_only; no fixed typography failure condition",
        "status": "pass" if all(item["status"] == "pass" for item in report_items) else "fail",
        "max_center_delta_percent": max((item["center_delta_percent"] for item in report_items), default=0.0),
        "max_width_delta_percent": max((item["width_delta_percent"] for item in report_items), default=0.0),
        "max_height_delta_percent": max((item["height_delta_percent"] for item in report_items), default=0.0),
        "items": report_items,
    }
    readability_note = {
        "summary": "Optional readability note only; it does not override reference-first text sizing.",
        "status": "informational_only",
        "policy": "do_not_modify_text_size_unless_user_requests_readability_over_reference_matching",
        "note": "Some labels may appear small after manuscript scaling if the reference figure uses small labels.",
    }

    write_json(out / "reference_text_geometry.json", geometry)
    write_json(out / "text_program.json", text_program)
    write_json(out / "text_alignment_report.json", alignment_report)
    write_json(out / "ocr_text_quality_report.json", ocr_report)
    write_json(out / "publication_readability_note.json", readability_note)
    program["text_program"] = text_program
    program["text_program_path"] = "text_program.json"
    program["reference_text_geometry_path"] = "reference_text_geometry.json"
    program["text_alignment_report_path"] = "text_alignment_report.json"
    write_json(out / "figure_program.json", program)
    return program
