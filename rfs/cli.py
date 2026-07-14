from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .presentations_qa import run_presentations_qa
from .utils import env_present, mask_secret
from .validator import validate_output
from .workflow import make_framework


def _json_print(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _doctor() -> dict:
    deps = {}
    for name, module in [("Pillow", "PIL"), ("python-pptx", "pptx"), ("PyMuPDF", "fitz"), ("requests", "requests"), ("opencv-python-headless", "cv2")]:
        try:
            __import__(module)
            deps[name] = {"available": True}
        except Exception as exc:
            deps[name] = {"available": False, "error": str(exc)}

    powerpnt_candidates = [
        Path(r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"),
        Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE"),
    ]
    powerpnt = next((str(p) for p in powerpnt_candidates if p.exists()), None)
    auth = {
        "API_BASE": {"present": env_present("API_BASE"), "value": os.getenv("API_BASE") if env_present("API_BASE") else None},
        "API_KEY": {"present": env_present("API_KEY"), "masked": mask_secret(os.getenv("API_KEY"))},
        "GEMINI_API_KEY": {"present": env_present("GEMINI_API_KEY"), "masked": mask_secret(os.getenv("GEMINI_API_KEY"))},
        "GEMINI_GEN_IMG_URL": {"present": env_present("GEMINI_GEN_IMG_URL"), "value": os.getenv("GEMINI_GEN_IMG_URL") if env_present("GEMINI_GEN_IMG_URL") else None},
        "RFS_IMAGE_MODEL": {"present": env_present("RFS_IMAGE_MODEL"), "value": os.getenv("RFS_IMAGE_MODEL") if env_present("RFS_IMAGE_MODEL") else "image-2 -> gpt-image-2"},
        "IMAGE_MODEL": {"present": env_present("IMAGE_MODEL"), "value": os.getenv("IMAGE_MODEL") if env_present("IMAGE_MODEL") else None},
        "RFS_LOCATOR_MODEL": {"present": env_present("RFS_LOCATOR_MODEL"), "value": os.getenv("RFS_LOCATOR_MODEL") if env_present("RFS_LOCATOR_MODEL") else None},
        "RFS_PROMPT_PLANNER_MODEL": {"present": env_present("RFS_PROMPT_PLANNER_MODEL"), "value": os.getenv("RFS_PROMPT_PLANNER_MODEL") if env_present("RFS_PROMPT_PLANNER_MODEL") else None},
        "MODEL_VLM": {"present": env_present("MODEL_VLM"), "value": os.getenv("MODEL_VLM") if env_present("MODEL_VLM") else None},
    }
    ok = all(item["available"] for item in deps.values())
    return {
        "summary": "ResearchFigureStudio doctor report.",
        "ok": ok,
        "version": __version__,
        "python": sys.executable,
        "dependencies": deps,
        "powerpoint": powerpnt,
        "auth": auth,
        "notes": [
            "No LiveFigure code is imported or required by the main workflow.",
            "Use --locator-mode vlm to borrow the reference-image positioning idea as JSON coordinates.",
            "Use --control-localizer-mode hybrid to create AutoFigure-inspired arrow/control candidates, overlays, and editable PPT bindings.",
            "Use --arrow-style-mode reference to keep the reference image as the hard arrow-layout constraint while adding softer editable PPT connector styling.",
            "Default --prompt-plan-mode vlm uses one VLM call per slot to generate reference-aware image_prompt_core entries; --prompt-plan-workers controls parallelism.",
            "Use --asset-mode image2 for Yunwu OpenAI-compatible image generation; logical image-2 maps to gpt-image-2 unless RFS_IMAGE_MODEL overrides it.",
            "Use --asset-mode placeholder for offline engineering validation only.",
            "Use rfs presentations-qa as an optional inspection pass; RFS remains the authoritative PPTX compiler.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rfs", description="ResearchFigureStudio CLI")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check dependencies, PowerPoint, and auth env vars.")
    doctor.add_argument("--json", action="store_true", help="Emit JSON.")

    make = sub.add_parser("make-framework", help="Create a paper-grounded, reference-guided editable PPTX framework figure.")
    make.add_argument("--paper", required=True, help="Paper PDF/LaTeX/Markdown/Word/text path.")
    make.add_argument("--reference", required=True, help="User-provided visual reference image path.")
    make.add_argument("--out", required=True, help="Output directory.")
    make.add_argument("--profile", default="ai-ml-paper", help="Figure profile. Default: ai-ml-paper.")
    make.add_argument("--slot-count", type=int, default=36, help="Target slot count, clamped to 25-50. Default: 36.")
    make.add_argument("--slot-source", choices=["paper", "reference-primary"], default="reference-primary", help="Slot content source. Default reference-primary makes the reference figure drive visual objects, layout, color, and flow logic.")
    make.add_argument("--asset-mode", choices=["image2", "gemini", "placeholder"], default="image2", help="Slot asset generation mode. Default image2 uses Yunwu Images API.")
    make.add_argument("--candidates-per-slot", type=int, default=4, help="Candidate images per slot, clamped to 1-5. Default: 4.")
    make.add_argument("--asset-workers", type=int, default=1, help="Parallel asset generation workers, clamped to 1-12. Default: 1.")
    make.add_argument("--asset-retries", type=int, default=2, help="Retries per generated asset candidate, clamped to 0-5. Default: 2.")
    make.add_argument("--asset-review-mode", choices=["off", "heuristic", "vlm"], default="heuristic", help="Selected asset review mode. Default: heuristic.")
    make.add_argument("--locator-mode", choices=["heuristic", "vlm"], default="heuristic", help="Layout coordinate source. Use vlm to locate slots from the reference image.")
    make.add_argument("--locator-model", help="Optional VLM model for --locator-mode vlm. Defaults to RFS_LOCATOR_MODEL/MODEL_VLM.")
    make.add_argument("--control-localizer-mode", choices=["off", "heuristic", "hybrid"], default="hybrid", help="Arrow/connector localization mode. Default hybrid uses CV candidates plus optional VLM binding; falls back to heuristic without API keys.")
    make.add_argument("--arrow-style-mode", choices=["off", "reference", "aesthetic"], default="reference", help="Arrow styling/routing mode. Default reference preserves reference-image routes and adds softer PPT styling/QA metadata.")
    make.add_argument("--prompt-plan-mode", choices=["heuristic", "vlm", "vlm-batch"], default="vlm", help="Reference-aware per-slot prompt planning mode. Default vlm uses one VLM call per slot; vlm-batch uses one batch VLM call; heuristic is offline only.")
    make.add_argument("--prompt-plan-model", help="Optional VLM model for --prompt-plan-mode vlm/vlm-batch. Defaults to RFS_PROMPT_PLANNER_MODEL/MODEL_VLM.")
    make.add_argument("--prompt-plan-workers", type=int, default=4, help="Parallel VLM workers for per-slot prompt planning, clamped to 1-12. Default: 4.")
    make.add_argument("--complexity-profile", choices=["reference-dense", "balanced", "legend-simple"], default="reference-dense", help="Visual complexity policy for slot_visual_spec.json. Default reference-dense.")
    make.add_argument("--critic-mode", choices=["off", "heuristic", "vlm"], default="heuristic", help="Final reference-vs-render critic mode. Default: heuristic.")
    make.add_argument("--critic-model", help="Optional VLM model for asset review and final critic. Defaults to RFS_CRITIC_MODEL/MODEL_VLM.")
    make.add_argument("--critic-iterations", type=int, default=0, help="VLM layout correction iterations, clamped to 0-3. Default: 0.")
    make.add_argument("--text-extractor-mode", choices=["heuristic", "ocr"], default="ocr", help="Editable text layer source. Default ocr uses local OCR when available and falls back to heuristic.")
    make.add_argument("--ocr-engine", choices=["paddle", "easyocr", "off"], default="paddle", help="Local OCR engine for reference text extraction. Default: paddle.")
    make.add_argument("--ocr-lang", choices=["en", "ch", "en_ch"], default="en_ch", help="OCR language hint. Default: en_ch.")
    make.add_argument("--presentations-qa", action="store_true", help="Run optional Presentations plugin import/render/layout QA after export. This never mutates the PPTX.")
    make.add_argument("--presentations-workspace", help="Optional workspace for Presentations QA scratch artifacts.")
    make.add_argument("--presentations-scale", type=int, default=2, help="Preview render scale for Presentations QA. Default: 2.")
    make.add_argument("--no-export", action="store_true", help="Skip PDF/PNG export and only create PPTX/artifacts.")
    make.add_argument("--json", action="store_true", help="Emit JSON.")

    validate = sub.add_parser("validate", help="Validate an existing ResearchFigureStudio output directory.")
    validate.add_argument("--out", required=True, help="Output directory to validate.")
    validate.add_argument("--json", action="store_true", help="Emit JSON.")

    presentations_qa = sub.add_parser("presentations-qa", help="Run optional Presentations plugin QA for an existing RFS output directory.")
    presentations_qa.add_argument("--out", required=True, help="RFS output directory containing editable_composition.pptx.")
    presentations_qa.add_argument("--pptx", help="Optional PPTX path. Defaults to <out>/editable_composition.pptx.")
    presentations_qa.add_argument("--workspace", help="Optional Presentations QA workspace. Defaults to <out>/presentations_plugin_qa_workspace.")
    presentations_qa.add_argument("--scale", type=int, default=2, help="Preview render scale. Default: 2.")
    presentations_qa.add_argument("--skip-inspect", action="store_true", help="Write report from PPTX/package metadata without invoking the Presentations plugin.")
    presentations_qa.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def _print_human(data: dict) -> None:
    if "ok" in data:
        print(f"ok: {data['ok']}")
    for key in ["out_dir", "pptx", "pdf", "png", "asset_count", "slot_count", "slot_source", "asset_mode", "candidates_per_slot", "asset_workers", "asset_retries", "asset_review_mode", "locator_mode", "control_localizer_mode", "arrow_style_mode", "prompt_plan_mode", "prompt_plan_workers", "complexity_profile", "critic_mode", "critic_iterations", "text_extractor_mode", "ocr_engine", "ocr_lang"]:
        if key in data:
            print(f"{key}: {data[key]}")
    if data.get("presentations_qa"):
        qa = data["presentations_qa"]
        print(f"presentations_qa_status: {qa.get('presentations_plugin_qa', {}).get('status')}")
        print(f"presentations_qa_report: {qa.get('report_json') or qa.get('presentations_plugin_qa', {}).get('manifest')}")
    if data.get("validation"):
        val = data["validation"]
        print(f"validation_ok: {val.get('ok')}")
        for err in val.get("errors", []):
            print(f"error: {err}")
        for warn in val.get("warnings", []):
            print(f"warning: {warn}")
    elif data.get("errors"):
        for err in data.get("errors", []):
            print(f"error: {err}")
        for warn in data.get("warnings", []):
            print(f"warning: {warn}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_requested = False
    if "--json" in argv:
        json_requested = True
        argv = [arg for arg in argv if arg != "--json"]
    parser = build_parser()
    args = parser.parse_args(argv)
    json_requested = json_requested or getattr(args, "json", False)

    try:
        if args.command == "doctor":
            result = _doctor()
        elif args.command == "make-framework":
            result = make_framework(
                paper=args.paper,
                reference=args.reference,
                out=args.out,
                profile=args.profile,
                slot_count=args.slot_count,
                slot_source=args.slot_source,
                asset_mode=args.asset_mode,
                candidates_per_slot=args.candidates_per_slot,
                asset_workers=args.asset_workers,
                asset_retries=args.asset_retries,
                asset_review_mode=args.asset_review_mode,
                locator_mode=args.locator_mode,
                locator_model=args.locator_model,
                control_localizer_mode=args.control_localizer_mode,
                arrow_style_mode=args.arrow_style_mode,
                prompt_plan_mode=args.prompt_plan_mode,
                prompt_plan_model=args.prompt_plan_model,
                prompt_plan_workers=args.prompt_plan_workers,
                complexity_profile=args.complexity_profile,
                critic_mode=args.critic_mode,
                critic_model=args.critic_model,
                critic_iterations=args.critic_iterations,
                text_extractor_mode=args.text_extractor_mode,
                ocr_engine=args.ocr_engine,
                ocr_lang=args.ocr_lang,
                presentations_qa=args.presentations_qa,
                presentations_workspace=args.presentations_workspace,
                presentations_scale=args.presentations_scale,
                export=not args.no_export,
            )
        elif args.command == "validate":
            result = validate_output(args.out)
        elif args.command == "presentations-qa":
            result = run_presentations_qa(
                out_dir=args.out,
                pptx=args.pptx,
                workspace=args.workspace,
                scale=args.scale,
                run_inspect=not args.skip_inspect,
            )
            result["ok"] = result.get("presentations_plugin_qa", {}).get("status") not in {"failed"}
        else:
            parser.error("unknown command")
            return 2
    except Exception as exc:
        result = {"summary": "ResearchFigureStudio command failed.", "ok": False, "error": str(exc)}
        if json_requested:
            _json_print(result)
        else:
            print(f"error: {exc}")
        return 1

    if json_requested:
        _json_print(result)
    else:
        _print_human(result)
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
