from __future__ import annotations

import json
from pathlib import Path

from .editable_rebuild import rebuild_editable
from .rebuild_vlm_adapters import build_rebuild_vlm_adapters
from .utils import ensure_dir, write_json


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _case_summary(case_dir: Path, result: dict) -> dict:
    validation = _read_json(case_dir / "rebuild_vlm_validation_report.json")
    geometry = _read_json(case_dir / "reference_geometry.json")
    controls = _read_json(case_dir / "reference_controls.json")
    semantic = _read_json(case_dir / "slot_semantic_report.json")
    text_intelligence = _read_json(case_dir / "text_intelligence_report.json")
    return {
        "out_dir": str(case_dir),
        "ok": result.get("ok"),
        "pptx": result.get("pptx"),
        "preview": result.get("preview"),
        "layout_mode": result.get("layout_mode"),
        "control_mode": result.get("control_mode"),
        "asset_mode": result.get("asset_mode"),
        "api_requests_attempted": result.get("api_requests_attempted", 0),
        "layout_vlm_status": geometry.get("vlm_status"),
        "control_vlm_status": controls.get("vlm_status"),
        "semantic_vlm_status": semantic.get("semantic_vlm_status"),
        "text_intelligence_status": text_intelligence.get("status"),
        "text_intelligence_effective_mode": text_intelligence.get("effective_mode"),
        "panel_count": validation.get("layout", {}).get("panel_count"),
        "slot_count": validation.get("layout", {}).get("slot_count"),
        "arrow_count": validation.get("control", {}).get("arrow_count"),
        "prompt_subject_coverage_percent": validation.get("semantic", {}).get("prompt_subject_coverage_percent"),
        "validation_status": validation.get("status"),
        "validation_warnings": validation.get("warnings", []),
    }


def evaluate_rebuild_vlm(
    reference: str | Path,
    out: str | Path,
    asset_mode: str = "crop",
    text_mode: str = "ocr",
    export_preview: bool = True,
) -> dict:
    out_dir = ensure_dir(out)
    reference_path = Path(reference)
    heuristic_dir = out_dir / "case_heuristic"
    vlm_dir = out_dir / "case_vlm"

    heuristic = rebuild_editable(
        reference=reference_path,
        out=heuristic_dir,
        asset_mode=asset_mode,
        text_mode=text_mode,
        layout_mode="heuristic",
        control_mode="heuristic",
        export_preview=export_preview,
    )

    adapters = build_rebuild_vlm_adapters(vlm_dir)
    vlm = rebuild_editable(
        reference=reference_path,
        out=vlm_dir,
        asset_mode=asset_mode,
        text_mode=text_mode,
        layout_mode="hybrid",
        control_mode="hybrid",
        export_preview=export_preview,
        vlm_layout_adapter=adapters["layout"],
        control_adapter=adapters["control"],
        semantic_adapter=adapters["semantic"],
    )

    summary = {
        "summary": "Heuristic vs hybrid VLM rebuild-editable evaluation.",
        "ok": bool(heuristic.get("ok")) and bool(vlm.get("ok")),
        "reference": str(reference_path),
        "asset_mode": asset_mode,
        "text_mode": text_mode,
        "image_generation_api_expected": asset_mode == "api",
        "cases": {
            "heuristic": _case_summary(heuristic_dir, heuristic),
            "vlm": _case_summary(vlm_dir, vlm),
        },
        "review_files": [
            "case_heuristic/reference_geometry_overlay.png",
            "case_heuristic/reference_controls_overlay.png",
            "case_heuristic/rebuild_preview.png",
            "case_vlm/reference_geometry_overlay.png",
            "case_vlm/reference_controls_overlay.png",
            "case_vlm/rebuild_preview.png",
        ],
    }
    write_json(out_dir / "rebuild_vlm_eval_summary.json", summary)
    return summary
