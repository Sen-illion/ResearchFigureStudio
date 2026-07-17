from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_WEIGHTS = {"scientific": 0.50, "aesthetic": 0.35, "visual_quality": 0.15}
DEFAULT_THRESHOLDS = {"total": 0.85, "scientific": 0.90, "aesthetic": 0.80}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _resolve_paths(value: Any, base: Path) -> Any:
    if isinstance(value, list):
        return [_resolve_paths(item, base) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_paths(item, base) for key, item in value.items()}
    return value


def load_ground_truth(path: str | Path) -> dict:
    source = Path(path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Ground Truth file does not exist: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ground Truth must be valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Ground Truth root must be a JSON object")

    paper_value = str(raw.get("paper_path") or "").strip()
    if not paper_value:
        raise ValueError("Ground Truth requires paper_path")
    paper = Path(paper_value)
    if not paper.is_absolute():
        paper = (source.parent / paper).resolve()
    if not paper.exists():
        raise FileNotFoundError(f"Ground Truth paper_path does not exist: {paper}")

    scientific = raw.get("scientific_truth")
    aesthetics = raw.get("aesthetic_preferences")
    if not isinstance(scientific, dict) or not scientific:
        raise ValueError("Ground Truth requires a non-empty scientific_truth object")
    if not isinstance(aesthetics, dict) or not aesthetics:
        raise ValueError("Ground Truth requires a non-empty aesthetic_preferences object")

    must_show = {str(item).strip().lower() for item in _list(scientific.get("must_show")) if str(item).strip()}
    forbidden = {
        str(item).strip().lower()
        for key in ("must_not_invent", "forbidden", "must_not_show")
        for item in _list(scientific.get(key))
        if str(item).strip()
    }
    contradictions = sorted(must_show & forbidden)
    if contradictions:
        raise ValueError(f"Ground Truth scientific constraints contradict each other: {contradictions}")

    positive = {str(item).strip() for item in _list(aesthetics.get("positive_references")) if str(item).strip()}
    negative = {str(item).strip() for item in _list(aesthetics.get("negative_references")) if str(item).strip()}
    if positive & negative:
        raise ValueError("The same aesthetic reference cannot be both positive and negative")

    resolved_aesthetics = dict(aesthetics)
    for key in ("positive_references", "negative_references"):
        refs = []
        for item in _list(aesthetics.get(key)):
            ref = Path(str(item))
            if not ref.is_absolute():
                ref = (source.parent / ref).resolve()
            if not ref.exists():
                raise FileNotFoundError(f"Ground Truth {key} file does not exist: {ref}")
            refs.append(str(ref))
        resolved_aesthetics[key] = refs

    weights = dict(DEFAULT_WEIGHTS)
    weights.update(raw.get("weights") if isinstance(raw.get("weights"), dict) else {})
    weights = {key: float(weights[key]) for key in DEFAULT_WEIGHTS}
    if any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Ground Truth weights must be non-negative and sum to more than zero")
    total_weight = sum(weights.values())
    weights = {key: round(value / total_weight, 6) for key, value in weights.items()}

    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {})
    thresholds = {key: float(thresholds[key]) for key in DEFAULT_THRESHOLDS}
    if any(value < 0 or value > 1 for value in thresholds.values()):
        raise ValueError("Ground Truth thresholds must be between 0 and 1")

    generation = raw.get("generation") if isinstance(raw.get("generation"), dict) else {}
    normalized = _resolve_paths(dict(raw), source.parent)
    normalized.update({
        "schema_version": str(raw.get("schema_version") or "1.0"),
        "source_path": str(source),
        "paper_path": str(paper),
        "scientific_truth": scientific,
        "aesthetic_preferences": resolved_aesthetics,
        "weights": weights,
        "thresholds": thresholds,
        "generation": {
            "aspect_ratio": str(generation.get("aspect_ratio") or "16:9"),
            "language": str(generation.get("language") or "English"),
        },
    })
    return normalized
