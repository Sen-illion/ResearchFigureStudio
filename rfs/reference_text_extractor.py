from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from PIL import Image


OCR_LOW_CONFIDENCE = 0.65


def _round4(value: float) -> float:
    return round(float(value), 4)


def _clamp_bbox(bbox: dict[str, float]) -> dict[str, float]:
    x = max(0.0, min(0.995, float(bbox["x"])))
    y = max(0.0, min(0.995, float(bbox["y"])))
    w = max(0.001, min(float(bbox["w"]), 1.0 - x))
    h = max(0.001, min(float(bbox["h"]), 1.0 - y))
    return {"x": _round4(x), "y": _round4(y), "w": _round4(w), "h": _round4(h)}


def _bbox_center(bbox: dict[str, float]) -> dict[str, float]:
    return {"x": _round4(float(bbox["x"]) + float(bbox["w"]) / 2), "y": _round4(float(bbox["y"]) + float(bbox["h"]) / 2)}


def _luminance(rgb: tuple[int, int, int]) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return abs(_luminance(a) - _luminance(b))


def _sample_text_color(image: Image.Image, bbox: dict[str, float], fallback: str = "#263747") -> tuple[str, str]:
    try:
        rgb_image = image.convert("RGB")
        iw, ih = rgb_image.size
        pad_x = max(1, int(float(bbox["w"]) * iw * 0.04))
        pad_y = max(1, int(float(bbox["h"]) * ih * 0.10))
        x0 = max(0, min(iw - 1, int(float(bbox["x"]) * iw) - pad_x))
        y0 = max(0, min(ih - 1, int(float(bbox["y"]) * ih) - pad_y))
        x1 = max(x0 + 1, min(iw, int((float(bbox["x"]) + float(bbox["w"])) * iw) + pad_x))
        y1 = max(y0 + 1, min(ih, int((float(bbox["y"]) + float(bbox["h"])) * ih) + pad_y))
        crop = rgb_image.crop((x0, y0, x1, y1))
        pixels = list(crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata())
    except Exception:
        return fallback, "sample_failed"
    if not pixels:
        return fallback, "empty_crop"
    pixels = sorted(pixels, key=_luminance)
    dark = pixels[: max(1, len(pixels) // 5)]
    light = pixels[-max(1, len(pixels) // 5):]
    dark_avg = tuple(int(sum(px[i] for px in dark) / len(dark)) for i in range(3))
    light_avg = tuple(int(sum(px[i] for px in light) / len(light)) for i in range(3))
    if _contrast(dark_avg, light_avg) < 32:
        return fallback, "low_contrast_fallback"
    text_rgb = dark_avg if _luminance(dark_avg) < _luminance(light_avg) else light_avg
    return _hex(text_rgb), "sampled_foreground"


def _bbox_overlap(a: dict[str, float], b: dict[str, float]) -> float:
    ax0, ay0 = float(a["x"]), float(a["y"])
    ax1, ay1 = ax0 + float(a["w"]), ay0 + float(a["h"])
    bx0, by0 = float(b["x"]), float(b["y"])
    bx1, by1 = bx0 + float(b["w"]), by0 + float(b["h"])
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    area = ix * iy
    return area / max(float(a["w"]) * float(a["h"]), 0.000001)


def _nearest_target(bbox: dict[str, float], program: dict) -> tuple[str, str]:
    candidates: list[tuple[float, str, str]] = []
    for panel in program.get("panels", []):
        if isinstance(panel, dict) and isinstance(panel.get("bbox_percent"), dict):
            overlap = _bbox_overlap(bbox, panel["bbox_percent"])
            if overlap > 0:
                candidates.append((overlap, "panel_title", str(panel.get("id") or "")))
    for slot in program.get("slots", []):
        if isinstance(slot, dict) and isinstance(slot.get("bbox_percent"), dict):
            overlap = _bbox_overlap(bbox, slot["bbox_percent"])
            if overlap > 0:
                candidates.append((overlap, "slot_caption", str(slot.get("id") or "")))
    if candidates:
        _overlap, role, target_id = max(candidates, key=lambda item: item[0])
        return role, target_id
    return "free_text", "canvas"


def _font_family_guess(text: str) -> str:
    if any(ord(char) > 127 for char in text):
        return "Microsoft YaHei"
    return "Arial"


def _normalize_quad(quad: Any) -> list[list[float]] | None:
    if not isinstance(quad, (list, tuple)) or len(quad) < 4:
        return None
    points: list[list[float]] = []
    for point in quad[:4]:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        points.append([float(point[0]), float(point[1])])
    return points


def _flatten_paddle_result(result: Any) -> list[Any]:
    if not isinstance(result, list):
        return []
    if result and all(isinstance(item, list) and len(item) >= 2 and _normalize_quad(item[0]) for item in result):
        return result
    flattened: list[Any] = []
    for page in result:
        if isinstance(page, list):
            flattened.extend(_flatten_paddle_result(page))
    return flattened


def _parse_ocr_result(result: Any) -> list[dict[str, Any]]:
    records = []
    for item in _flatten_paddle_result(result):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        quad = _normalize_quad(item[0])
        payload = item[1]
        if not quad:
            continue
        text = ""
        confidence = 0.0
        if isinstance(payload, (list, tuple)) and payload:
            text = str(payload[0] or "").strip()
            if len(payload) > 1:
                try:
                    confidence = float(payload[1])
                except Exception:
                    confidence = 0.0
        else:
            text = str(payload or "").strip()
        if text:
            records.append({"text": text, "confidence": confidence, "quad": quad})
    return records


def run_paddle_ocr(image_path: str | Path, lang: str) -> list[dict[str, Any]]:
    from paddleocr import PaddleOCR  # type: ignore

    lang_map = {"en_ch": "ch", "ch": "ch", "en": "en"}
    ocr = PaddleOCR(use_angle_cls=True, lang=lang_map.get(str(lang), "ch"), show_log=False)
    return _parse_ocr_result(ocr.ocr(str(image_path), cls=True))


def run_easyocr(image_path: str | Path, lang: str) -> list[dict[str, Any]]:
    import easyocr  # type: ignore

    lang_map = {"en_ch": ["ch_sim", "en"], "ch": ["ch_sim"], "en": ["en"]}
    reader = easyocr.Reader(lang_map.get(str(lang), ["ch_sim", "en"]), gpu=False)
    records = []
    for quad, text, confidence in reader.readtext(str(image_path)):
        points = _normalize_quad(quad)
        if points and str(text).strip():
            records.append({"text": str(text).strip(), "confidence": float(confidence), "quad": points})
    return records


def _record_to_region(record: dict[str, Any], image: Image.Image, program: dict, index: int, canvas_height_in: float, engine: str) -> dict:
    width, height = image.size
    xs = [point[0] for point in record["quad"]]
    ys = [point[1] for point in record["quad"]]
    bbox = _clamp_bbox({
        "x": min(xs) / max(width, 1),
        "y": min(ys) / max(height, 1),
        "w": (max(xs) - min(xs)) / max(width, 1),
        "h": (max(ys) - min(ys)) / max(height, 1),
    })
    text = str(record.get("text") or "").strip()
    confidence = float(record.get("confidence") or 0.0)
    color_hex, color_status = _sample_text_color(image, bbox)
    role, target_id = _nearest_target(bbox, program)
    font_size = max(1.0, float(bbox["h"]) * canvas_height_in * 72 * 0.72)
    return {
        "id": f"ref_text_ocr_{index:03d}",
        "text": text,
        "raw_text": text,
        "role": role,
        "target_id": target_id,
        "bbox_percent": bbox,
        "line_bbox_percent": bbox,
        "word_bbox_percent": [bbox],
        "center_percent": _bbox_center(bbox),
        "width_percent": _round4(bbox["w"]),
        "height_percent": _round4(bbox["h"]),
        "estimated_font_ratio": _round4(float(bbox["h"]) * 0.72),
        "font_size_pt": round(font_size, 2),
        "font_family_guess": _font_family_guess(text),
        "font_weight_guess": "bold" if role == "panel_title" and float(bbox["h"]) > 0.025 else "regular",
        "color_hex": color_hex,
        "color_sampling_status": color_status,
        "confidence": round(confidence, 4),
        "ocr_engine": engine,
        "source": "reference_ocr_text_region",
        "editable_in": "pptx",
    }


def extract_reference_text(
    reference_path: str | Path,
    program: dict,
    *,
    mode: str = "ocr",
    engine: str = "paddle",
    lang: str = "en_ch",
    ocr_adapter: Callable[[str | Path, str], list[dict[str, Any]]] | None = None,
) -> tuple[list[dict], dict]:
    requested_mode = str(mode or "ocr").lower()
    requested_engine = str(engine or "paddle").lower()
    report = {
        "summary": "OCR text extraction quality report.",
        "mode": requested_mode,
        "ocr_engine": requested_engine,
        "ocr_lang": lang,
        "status": "not_run",
        "text_region_count": 0,
        "low_confidence_count": 0,
        "warnings": [],
        "fallback_reason": None,
    }
    if requested_mode != "ocr" or requested_engine == "off":
        report.update({"status": "fallback", "fallback_reason": "ocr_disabled"})
        return [], report
    try:
        if ocr_adapter:
            raw_records = ocr_adapter(reference_path, lang)
        elif requested_engine == "easyocr":
            raw_records = run_easyocr(reference_path, lang)
        else:
            raw_records = run_paddle_ocr(reference_path, lang)
    except Exception as exc:
        report.update({"status": "fallback", "fallback_reason": f"ocr_unavailable:{exc}"})
        report["warnings"].append(str(exc))
        return [], report
    try:
        with Image.open(reference_path) as image:
            rgb_image = image.convert("RGB")
            canvas = program.get("canvas", {}) if isinstance(program.get("canvas"), dict) else {}
            canvas_height_in = float(canvas.get("height_in") or 7.5)
            regions = [_record_to_region(record, rgb_image, program, index, canvas_height_in, requested_engine) for index, record in enumerate(raw_records, start=1)]
    except Exception as exc:
        report.update({"status": "fallback", "fallback_reason": f"ocr_postprocess_failed:{exc}"})
        report["warnings"].append(str(exc))
        return [], report
    regions = [region for region in regions if str(region.get("text", "")).strip()]
    low_conf = [region for region in regions if float(region.get("confidence") or 0.0) < OCR_LOW_CONFIDENCE]
    overlap_warnings = []
    for region in regions:
        if region.get("role") == "slot_caption":
            overlap_warnings.append(region["id"])
    if not regions:
        report.update({"status": "fallback", "fallback_reason": "ocr_returned_no_text", "text_region_count": 0})
        return [], report
    report.update({
        "status": "pass",
        "text_region_count": len(regions),
        "low_confidence_count": len(low_conf),
        "low_confidence_text_ids": [region["id"] for region in low_conf],
        "slot_overlap_text_ids": overlap_warnings,
        "warnings": report["warnings"] + ([f"{len(low_conf)} low-confidence OCR text region(s)"] if low_conf else []),
    })
    return regions, report
