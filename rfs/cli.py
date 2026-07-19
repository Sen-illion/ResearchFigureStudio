from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .coevolution import analyze_coevolution_run, run_image_coevolution
from .editable_rebuild import rebuild_editable
from .paper_to_editable import run_paper_to_editable
from .paper_to_image import run_paper_to_image
from .presentations_qa import run_presentations_qa
from .rebuild_vlm_adapters import build_rebuild_vlm_adapters
from .rebuild_eval import evaluate_rebuild_vlm
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
        "RFS_REBUILD_LAYOUT_MODEL": {"present": env_present("RFS_REBUILD_LAYOUT_MODEL"), "value": os.getenv("RFS_REBUILD_LAYOUT_MODEL") if env_present("RFS_REBUILD_LAYOUT_MODEL") else None},
        "RFS_REBUILD_CONTROL_MODEL": {"present": env_present("RFS_REBUILD_CONTROL_MODEL"), "value": os.getenv("RFS_REBUILD_CONTROL_MODEL") if env_present("RFS_REBUILD_CONTROL_MODEL") else None},
        "RFS_REBUILD_SEMANTIC_MODEL": {"present": env_present("RFS_REBUILD_SEMANTIC_MODEL"), "value": os.getenv("RFS_REBUILD_SEMANTIC_MODEL") if env_present("RFS_REBUILD_SEMANTIC_MODEL") else None},
        "RFS_REBUILD_TEXT_MODEL": {"present": env_present("RFS_REBUILD_TEXT_MODEL"), "value": os.getenv("RFS_REBUILD_TEXT_MODEL") if env_present("RFS_REBUILD_TEXT_MODEL") else None},
        "RFS_PROMPT_PLANNER_MODEL": {"present": env_present("RFS_PROMPT_PLANNER_MODEL"), "value": os.getenv("RFS_PROMPT_PLANNER_MODEL") if env_present("RFS_PROMPT_PLANNER_MODEL") else None},
        "RFS_TEXT_ROLE_MODEL": {"present": env_present("RFS_TEXT_ROLE_MODEL"), "value": os.getenv("RFS_TEXT_ROLE_MODEL") if env_present("RFS_TEXT_ROLE_MODEL") else None},
        "RFS_PAPER_TO_IMAGE_MODEL": {"present": env_present("RFS_PAPER_TO_IMAGE_MODEL"), "value": os.getenv("RFS_PAPER_TO_IMAGE_MODEL") if env_present("RFS_PAPER_TO_IMAGE_MODEL") else None},
        "RFS_PAPER_TO_IMAGE_REVIEW_MODEL": {"present": env_present("RFS_PAPER_TO_IMAGE_REVIEW_MODEL"), "value": os.getenv("RFS_PAPER_TO_IMAGE_REVIEW_MODEL") if env_present("RFS_PAPER_TO_IMAGE_REVIEW_MODEL") else None},
        "RFS_PAPER_REVIEW_MODEL": {"present": env_present("RFS_PAPER_REVIEW_MODEL"), "value": os.getenv("RFS_PAPER_REVIEW_MODEL") if env_present("RFS_PAPER_REVIEW_MODEL") else None},
        "RFS_TEMPLATE_ANALYZER_MODEL": {"present": env_present("RFS_TEMPLATE_ANALYZER_MODEL"), "value": os.getenv("RFS_TEMPLATE_ANALYZER_MODEL") if env_present("RFS_TEMPLATE_ANALYZER_MODEL") else None},
        "RFS_ONLINE_JUDGE_MODEL": {"present": env_present("RFS_ONLINE_JUDGE_MODEL"), "value": os.getenv("RFS_ONLINE_JUDGE_MODEL") if env_present("RFS_ONLINE_JUDGE_MODEL") else None},
        "RFS_FROZEN_JUDGE_MODEL": {"present": env_present("RFS_FROZEN_JUDGE_MODEL"), "value": os.getenv("RFS_FROZEN_JUDGE_MODEL") if env_present("RFS_FROZEN_JUDGE_MODEL") else None},
        "RFS_IMAGE_EDIT_URL": {"present": env_present("RFS_IMAGE_EDIT_URL"), "value": os.getenv("RFS_IMAGE_EDIT_URL") if env_present("RFS_IMAGE_EDIT_URL") else None},
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
            "Use rfs coevolve-image to run whole-image Creator Agent and Online/Frozen Judge refinement before PPTX conversion.",
            "Use rfs paper-to-image for evidence-grounded paper summarization, whole-image prompt compilation, candidate generation, and selected_image.png without PPTX.",
            "Use rfs paper-to-editable to generate a paper image first, then rebuild it into editable_composition.pptx.",
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
    make.add_argument("--text-role-mode", choices=["heuristic", "vlm"], default="heuristic", help="Text role classification source. Default: heuristic. Use vlm to classify OCR text roles before median font-size clustering.")
    make.add_argument("--text-role-model", help="Optional VLM model for --text-role-mode vlm. Defaults to RFS_TEXT_ROLE_MODEL/MODEL_VLM.")
    make.add_argument("--presentations-qa", action="store_true", help="Run optional Presentations plugin import/render/layout QA after export. This never mutates the PPTX.")
    make.add_argument("--presentations-workspace", help="Optional workspace for Presentations QA scratch artifacts.")
    make.add_argument("--presentations-scale", type=int, default=2, help="Preview render scale for Presentations QA. Default: 2.")
    make.add_argument("--no-export", action="store_true", help="Skip PDF/PNG export and only create PPTX/artifacts.")
    make.add_argument("--json", action="store_true", help="Emit JSON.")

    paper_image = sub.add_parser("paper-to-image", help="Summarize a paper, plan a scientific framework figure, and generate raster image candidates without PPTX.")
    paper_image.add_argument("--paper", required=True, help="Paper PDF/LaTeX/Markdown/Word/text path.")
    paper_image.add_argument("--out", required=True, help="Output directory for review, templates, prompts, candidates, and production-only selected_image.png.")
    paper_image.add_argument("--preferences", help="Optional JSON file containing style and output preferences.")
    paper_image.add_argument("--positive-reference", action="append", default=[], help="Optional positive visual reference image. Repeat for multiple files.")
    paper_image.add_argument("--negative-reference", action="append", default=[], help="Optional negative visual reference image. Repeat for multiple files.")
    paper_image.add_argument("--planner-mode", choices=["vlm", "heuristic"], default="vlm", help="Paper summarization and figure planning mode. Default: vlm with heuristic fallback.")
    paper_image.add_argument("--planner-model", help="Optional planning VLM. Defaults to RFS_PAPER_TO_IMAGE_MODEL/RFS_PAPER_PLANNER_MODEL/MODEL_VLM.")
    paper_image.add_argument("--domain-profile", choices=["auto", "general", "ai-ml-method", "system-platform", "dataset-benchmark", "empirical-science", "survey-review"], default="auto", help="Universal review profile plus optional domain extension. Default: auto.")
    paper_image.add_argument("--template", choices=["auto", "arbor", "linear", "tripanel", "dense-multimodal"], default="auto", help="Reference architecture template. Default: auto selection.")
    paper_image.add_argument("--asset-mode", choices=["image2", "gemini", "placeholder"], default="image2", help="Whole-image generation backend. Placeholder is for offline validation only.")
    paper_image.add_argument("--candidates", type=int, default=3, help="Image candidate count, clamped to 1-4. Default: 3.")
    paper_image.add_argument("--aspect-ratio", default="auto", help="Target image aspect ratio or auto to inherit the selected template. Default: auto.")
    paper_image.add_argument("--language", default="English", help="Visible label language. Default: English.")
    paper_image.add_argument("--image-model", help="Optional image model. Defaults to RFS_IMAGE_MODEL/IMAGE_MODEL.")
    paper_image.add_argument("--image-retries", type=int, default=2, help="Retries per image candidate, clamped to 0-5. Default: 2.")
    paper_image.add_argument("--review-mode", choices=["off", "heuristic", "vlm"], default="vlm", help="Candidate review mode. Production Image2 requires VLM review. Default: vlm.")
    paper_image.add_argument("--review-model", help="Optional VLM candidate-review model. Defaults to RFS_PAPER_TO_IMAGE_REVIEW_MODEL/RFS_CRITIC_MODEL/MODEL_VLM.")
    paper_image.add_argument("--repair-rounds", type=int, default=1, help="Localized Image2 edit repair rounds, clamped to 0-1. Default: 1.")
    paper_image.add_argument("--ocr-engine", choices=["auto", "paddle", "easyocr", "vlm", "off"], default="auto", help="OCR source for exact-label validation. Auto tries local OCR and uses VLM review evidence. Default: auto.")
    paper_image.add_argument("--ocr-lang", choices=["en", "ch", "en_ch"], default="en_ch", help="OCR language hint. Default: en_ch.")
    paper_image.add_argument("--json", action="store_true", help="Emit JSON.")

    paper_editable = sub.add_parser("paper-to-editable", help="Generate a paper-grounded raster reference image, then rebuild it into editable PowerPoint.")
    paper_editable.add_argument("--paper", required=True, help="Paper PDF/LaTeX/Markdown/Word/text path.")
    paper_editable.add_argument("--out", required=True, help="Output directory containing paper_to_image artifacts and editable_composition.pptx.")
    paper_editable.add_argument("--preferences", help="Optional JSON file containing style and output preferences.")
    paper_editable.add_argument("--positive-reference", action="append", default=[], help="Optional positive visual reference image for paper-image generation. Repeat for multiple files.")
    paper_editable.add_argument("--negative-reference", action="append", default=[], help="Optional negative visual reference image for paper-image generation. Repeat for multiple files.")
    paper_editable.add_argument("--planner-mode", choices=["vlm", "heuristic"], default="vlm", help="Paper-image planning mode. Default: vlm.")
    paper_editable.add_argument("--planner-model", help="Optional paper-image planning VLM.")
    paper_editable.add_argument("--domain-profile", choices=["auto", "general", "ai-ml-method", "system-platform", "dataset-benchmark", "empirical-science", "survey-review"], default="auto", help="Paper review profile. Default: auto.")
    paper_editable.add_argument("--template", choices=["auto", "arbor", "linear", "tripanel", "dense-multimodal"], default="auto", help="Reference architecture template. Default: auto.")
    paper_editable.add_argument("--paper-image-asset-mode", choices=["image2", "gemini", "placeholder"], default="image2", help="Whole-image generation backend. Default: image2.")
    paper_editable.add_argument("--paper-image-candidates", type=int, default=3, help="Whole-image candidate count, clamped to 1-4. Default: 3.")
    paper_editable.add_argument("--aspect-ratio", default="auto", help="Target paper-image aspect ratio. Default: auto.")
    paper_editable.add_argument("--language", default="English", help="Visible label language. Default: English.")
    paper_editable.add_argument("--image-model", help="Optional whole-image model. Defaults to RFS_IMAGE_MODEL/IMAGE_MODEL.")
    paper_editable.add_argument("--image-retries", type=int, default=2, help="Whole-image retries per candidate. Default: 2.")
    paper_editable.add_argument("--paper-image-review-mode", choices=["off", "heuristic", "vlm"], default="vlm", help="Whole-image review mode. Default: vlm.")
    paper_editable.add_argument("--paper-image-review-model", help="Optional whole-image review VLM.")
    paper_editable.add_argument("--paper-image-repair-rounds", type=int, default=1, help="Whole-image repair rounds, clamped to 0-1. Default: 1.")
    paper_editable.add_argument("--paper-image-ocr-engine", choices=["auto", "paddle", "easyocr", "vlm", "off"], default="auto", help="OCR source for whole-image label validation. Default: auto.")
    paper_editable.add_argument("--paper-image-ocr-lang", choices=["en", "ch", "en_ch"], default="en_ch", help="OCR language hint for whole-image label validation. Default: en_ch.")
    paper_editable.add_argument("--require-paper-image-pass", action="store_true", help="Stop before rebuild if the generated paper image did not pass all production gates.")
    paper_editable.add_argument("--allow-engineering-preview", action="store_true", help="Allow placeholder/gemini engineering_preview.png to enter rebuild for offline checks.")
    paper_editable.add_argument("--rebuild-asset-mode", choices=["api", "crop", "placeholder"], default="crop", help="Slot asset source for editable rebuild. Default: crop.")
    paper_editable.add_argument("--rebuild-asset-workers", type=int, default=4, help="Parallel rebuild asset workers. Default: 4.")
    paper_editable.add_argument("--rebuild-asset-retries", type=int, default=1, help="Retries per rebuild slot. Default: 1.")
    paper_editable.add_argument("--economy-mode", dest="economy_mode", action="store_true", default=True, help="Reuse accepted/passing rebuild assets. Enabled by default.")
    paper_editable.add_argument("--no-economy-mode", dest="economy_mode", action="store_false", help="Disable rebuild economy reuse decisions.")
    paper_editable.add_argument("--text-mode", choices=["ocr", "manual", "off"], default="ocr", help="Editable text extraction mode for rebuild. Default: ocr.")
    paper_editable.add_argument("--text-grouping-mode", choices=["off", "heuristic", "vlm", "hybrid"], default="heuristic", help="OCR line grouping mode for rebuild. Default: heuristic.")
    paper_editable.add_argument("--text-grouping-model", help="Optional VLM model for rebuild text grouping.")
    paper_editable.add_argument("--text-role-mode", choices=["heuristic", "vlm"], default="vlm", help="Text role classification source for rebuild. Default: vlm.")
    paper_editable.add_argument("--text-role-model", help="Optional VLM model for rebuild text role classification.")
    paper_editable.add_argument("--text-intelligence-mode", choices=["off", "heuristic", "vlm"], default="vlm", help="Text intelligence source for rebuild. Default: vlm.")
    paper_editable.add_argument("--text-intelligence-model", help="Optional VLM model for rebuild text intelligence.")
    paper_editable.add_argument("--design-plan-mode", choices=["off", "heuristic", "vlm"], default="vlm", help="Global reference logic planning mode for rebuild. Default: vlm.")
    paper_editable.add_argument("--design-plan-model", help="Optional VLM model for rebuild design planning.")
    paper_editable.add_argument("--layout-mode", choices=["heuristic", "vlm", "hybrid"], default="hybrid", help="Layout extraction mode for rebuild. Default: hybrid.")
    paper_editable.add_argument("--control-mode", choices=["heuristic", "vlm", "hybrid", "manual"], default="hybrid", help="Arrow/control extraction mode for rebuild. Default: hybrid.")
    paper_editable.add_argument("--arrow-style-mode", choices=["off", "reference", "aesthetic"], default="reference", help="Arrow styling/routing mode for rebuild. Default: reference.")
    paper_editable.add_argument("--rebuild-critic-mode", choices=["off", "heuristic", "vlm"], default="off", help="Compiled-preview rebuild critic mode. Default off.")
    paper_editable.add_argument("--rebuild-critic-iterations", type=int, default=0, help="Compiled-preview critic correction iterations. Default: 0.")
    paper_editable.add_argument("--rebuild-critic-model", help="Optional VLM model for rebuild critic.")
    paper_editable.add_argument("--export-preview", action="store_true", help="Export a PNG preview when PowerPoint is available.")
    paper_editable.add_argument("--regenerate-slots", help="Comma-separated rebuild slot ids to regenerate.")
    paper_editable.add_argument("--strict-asset-regeneration", action="store_true", help="Use stricter rebuild asset thresholds and retries.")
    paper_editable.add_argument("--ocr-engine", choices=["paddle", "easyocr", "off"], default="paddle", help="OCR engine for rebuild text extraction. Default: paddle.")
    paper_editable.add_argument("--ocr-lang", choices=["en", "ch", "en_ch"], default="en_ch", help="OCR language hint for rebuild. Default: en_ch.")
    paper_editable.add_argument("--json", action="store_true", help="Emit JSON.")

    rebuild = sub.add_parser("rebuild-editable", help="Rebuild a reference image into a reusable editable PowerPoint composition.")
    rebuild.add_argument("--reference", required=True, help="Reference image path.")
    rebuild.add_argument("--out", required=True, help="Output directory.")
    rebuild.add_argument("--asset-mode", choices=["api", "crop", "placeholder"], default="api", help="Slot asset source. Default api uses GEMINI_GEN_IMG_URL.")
    rebuild.add_argument("--asset-workers", type=int, default=4, help="Parallel asset workers, clamped by the pipeline to 1-12. Default: 4.")
    rebuild.add_argument("--asset-retries", type=int, default=1, help="Retries per slot in strict mode. Default: 1.")
    rebuild.add_argument("--economy-mode", dest="economy_mode", action="store_true", default=True, help="Reuse accepted/passing assets and generate each failed slot once. Enabled by default.")
    rebuild.add_argument("--no-economy-mode", dest="economy_mode", action="store_false", help="Disable economy reuse decisions.")
    rebuild.add_argument("--text-mode", choices=["ocr", "manual", "off"], default="ocr", help="Editable text extraction mode. Default: ocr.")
    rebuild.add_argument("--text-grouping-mode", choices=["off", "heuristic", "vlm", "hybrid"], default="heuristic", help="OCR line grouping mode before text role classification. Default: heuristic.")
    rebuild.add_argument("--text-grouping-model", help="Optional VLM model for --text-grouping-mode vlm/hybrid. Defaults to RFS_TEXT_GROUPING_MODEL/RFS_TEXT_ROLE_MODEL/MODEL_VLM.")
    rebuild.add_argument("--text-role-mode", choices=["heuristic", "vlm"], default="vlm", help="Text role classification source. Default: vlm with heuristic fallback.")
    rebuild.add_argument("--text-role-model", help="Optional VLM model for --text-role-mode vlm. Defaults to RFS_TEXT_ROLE_MODEL/MODEL_VLM.")
    rebuild.add_argument("--text-intelligence-mode", choices=["off", "heuristic", "vlm"], default="vlm", help="Text intelligence source for font style, relationships, and layout intent reports. Default: vlm with heuristic fallback.")
    rebuild.add_argument("--text-intelligence-model", help="Optional VLM model for --text-intelligence-mode vlm. Defaults to RFS_REBUILD_TEXT_MODEL/RFS_TEXT_ROLE_MODEL/MODEL_VLM.")
    rebuild.add_argument("--design-plan-mode", choices=["off", "heuristic", "vlm"], default="vlm", help="Global reference logic planning mode. Default: vlm with heuristic fallback.")
    rebuild.add_argument("--design-plan-model", help="Optional VLM model for --design-plan-mode vlm. Defaults to RFS_REBUILD_DESIGN_MODEL/RFS_REBUILD_LAYOUT_MODEL/MODEL_VLM.")
    rebuild.add_argument("--layout-mode", choices=["heuristic", "vlm", "hybrid"], default="hybrid", help="Panel/card/slot layout extraction mode. Default: hybrid.")
    rebuild.add_argument("--control-mode", choices=["heuristic", "vlm", "hybrid", "manual"], default="hybrid", help="Arrow/control extraction mode. Default: hybrid.")
    rebuild.add_argument("--arrow-style-mode", choices=["off", "reference", "aesthetic"], default="reference", help="Arrow styling/routing mode for editable rebuild. Default: reference.")
    rebuild.add_argument("--rebuild-critic-mode", choices=["off", "heuristic", "vlm"], default="off", help="Compiled-preview rebuild critic mode. Default off.")
    rebuild.add_argument("--rebuild-critic-iterations", type=int, default=0, help="Compiled-preview critic correction iterations, clamped to 0-3. Default: 0.")
    rebuild.add_argument("--rebuild-critic-model", help="Optional VLM model for --rebuild-critic-mode vlm. Defaults to RFS_REBUILD_CRITIC_MODEL/RFS_CRITIC_MODEL/MODEL_VLM.")
    rebuild.add_argument("--export-preview", action="store_true", help="Export a PNG preview when PowerPoint is available.")
    rebuild.add_argument("--regenerate-slots", help="Comma-separated slot ids to regenerate even when an existing asset is present.")
    rebuild.add_argument("--strict-asset-regeneration", action="store_true", help="Use stricter asset thresholds and --asset-retries for high-cost regeneration.")
    rebuild.add_argument("--skip-analysis", action="store_true", help="Reuse existing JSON contracts in --out instead of re-running layout/control/semantic analysis.")
    rebuild.add_argument("--compile-only", action="store_true", help="Compile editable_composition.pptx from existing JSON contracts and assets without regenerating analysis or assets.")
    rebuild.add_argument("--ocr-engine", choices=["paddle", "easyocr", "off"], default="paddle", help="OCR engine for --text-mode ocr. Default: paddle.")
    rebuild.add_argument("--ocr-lang", choices=["en", "ch", "en_ch"], default="en_ch", help="OCR language hint. Default: en_ch.")
    rebuild.add_argument("--json", action="store_true", help="Emit JSON.")

    rebuild_eval = sub.add_parser("rebuild-editable-eval", help="Compare heuristic and hybrid VLM rebuild-editable outputs for one reference image.")
    rebuild_eval.add_argument("--reference", required=True, help="Reference image path.")
    rebuild_eval.add_argument("--out", required=True, help="Evaluation output directory.")
    rebuild_eval.add_argument("--asset-mode", choices=["api", "crop", "placeholder"], default="crop", help="Asset mode for both cases. Default: crop to avoid image generation cost.")
    rebuild_eval.add_argument("--text-mode", choices=["ocr", "manual", "off"], default="ocr", help="Text extraction mode for both cases. Default: ocr.")
    rebuild_eval.add_argument("--export-preview", action="store_true", help="Export PNG previews when PowerPoint is available.")
    rebuild_eval.add_argument("--json", action="store_true", help="Emit JSON.")

    coevolve = sub.add_parser("coevolve-image", help="Refine a complete scientific image through Creator Agent and Online/Frozen Judges.")
    coevolve.add_argument("--ground-truth", required=True, help="Structured Ground Truth JSON containing paper facts and human aesthetic preferences.")
    coevolve.add_argument("--out", required=True, help="Output directory for rounds, training trajectories, and approved_image.png.")
    coevolve.add_argument("--candidates", type=int, default=3, help="Initial whole-image candidate count. Default: 3.")
    coevolve.add_argument("--repair-candidates", type=int, default=2, help="Candidate count for each repair round. Default: 2.")
    coevolve.add_argument("--max-rounds", type=int, default=4, help="Maximum total rounds including initial generation. Default: 4.")
    coevolve.add_argument("--online-judge-model", help="Online feedback Judge model. Defaults to RFS_ONLINE_JUDGE_MODEL/RFS_CRITIC_MODEL/MODEL_VLM.")
    coevolve.add_argument("--frozen-judge-model", help="Independent acceptance Judge model. Defaults to RFS_FROZEN_JUDGE_MODEL/RFS_CRITIC_MODEL/MODEL_VLM.")
    coevolve.add_argument("--image-model", help="Whole-image generation model. Defaults to RFS_IMAGE_MODEL/IMAGE_MODEL.")
    coevolve.add_argument("--image-retries", type=int, default=2, help="Image request retries. Default: 2.")
    coevolve.add_argument("--json", action="store_true", help="Emit JSON.")

    coevolution_report = sub.add_parser("coevolution-report", help="Aggregate a co-evolution run into reproducible improvement metrics.")
    coevolution_report.add_argument("--run", required=True, help="Existing co-evolution output directory.")
    coevolution_report.add_argument("--json", action="store_true", help="Emit JSON.")

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
    for key in ["out_dir", "paper_to_image_out", "generated_reference_image", "generated_reference_source", "paper_image_delivery_mode", "paper_image_selected_candidate_id", "paper_image_selected_passed_all_checks", "paper_image_asset_mode", "paper_image_review_mode", "rebuild_asset_mode", "selected_image", "engineering_preview", "candidate_count", "selected_candidate_id", "selected_passed_all_checks", "planner_mode", "planner_model", "paper_review_mode", "domain_profile", "template_id", "review_mode", "approved_image", "thresholds_met", "stop_reason", "rounds_completed", "online_judge_model", "frozen_judge_model", "weak_judge_isolation", "pptx", "pdf", "png", "preview", "asset_count", "slot_count", "slot_source", "asset_mode", "asset_workers", "asset_retries", "economy_mode", "api_requests_attempted", "text_count", "connector_count", "text_mode", "layout_mode", "control_mode", "compile_only", "candidates_per_slot", "asset_review_mode", "locator_mode", "control_localizer_mode", "arrow_style_mode", "prompt_plan_mode", "prompt_plan_workers", "complexity_profile", "critic_mode", "critic_iterations", "rebuild_critic_mode", "rebuild_critic_iterations", "rebuild_critic_status", "rebuild_critic_model", "text_extractor_mode", "ocr_engine", "ocr_lang", "text_grouping_mode", "text_grouping_effective_mode", "text_grouping_model", "text_role_mode", "text_role_effective_mode", "text_role_model", "text_intelligence_mode", "text_intelligence_effective_mode", "text_intelligence_model", "design_plan_mode", "design_plan_effective_mode", "design_plan_model"]:
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
                text_grouping_mode=args.text_grouping_mode,
                text_grouping_model=args.text_grouping_model,
                text_role_mode=args.text_role_mode,
                text_role_model=args.text_role_model,
                presentations_qa=args.presentations_qa,
                presentations_workspace=args.presentations_workspace,
                presentations_scale=args.presentations_scale,
                export=not args.no_export,
            )
        elif args.command == "paper-to-image":
            result = run_paper_to_image(
                paper=args.paper,
                out=args.out,
                preferences_path=args.preferences,
                positive_references=args.positive_reference,
                negative_references=args.negative_reference,
                planner_mode=args.planner_mode,
                planner_model=args.planner_model,
                asset_mode=args.asset_mode,
                candidates=args.candidates,
                aspect_ratio=args.aspect_ratio,
                language=args.language,
                image_model=args.image_model,
                image_retries=args.image_retries,
                review_mode=args.review_mode,
                review_model=args.review_model,
                domain_profile=args.domain_profile,
                template=args.template,
                repair_rounds=args.repair_rounds,
                ocr_engine=args.ocr_engine,
                ocr_lang=args.ocr_lang,
            )
        elif args.command == "paper-to-editable":
            rebuild_adapters = build_rebuild_vlm_adapters(args.out)
            result = run_paper_to_editable(
                paper=args.paper,
                out=args.out,
                preferences_path=args.preferences,
                positive_references=args.positive_reference,
                negative_references=args.negative_reference,
                planner_mode=args.planner_mode,
                planner_model=args.planner_model,
                paper_image_asset_mode=args.paper_image_asset_mode,
                paper_image_candidates=args.paper_image_candidates,
                aspect_ratio=args.aspect_ratio,
                language=args.language,
                image_model=args.image_model,
                image_retries=args.image_retries,
                paper_image_review_mode=args.paper_image_review_mode,
                paper_image_review_model=args.paper_image_review_model,
                domain_profile=args.domain_profile,
                template=args.template,
                paper_image_repair_rounds=args.paper_image_repair_rounds,
                paper_image_ocr_engine=args.paper_image_ocr_engine,
                paper_image_ocr_lang=args.paper_image_ocr_lang,
                require_paper_image_pass=args.require_paper_image_pass,
                allow_engineering_preview=args.allow_engineering_preview,
                rebuild_asset_mode=args.rebuild_asset_mode,
                rebuild_asset_workers=args.rebuild_asset_workers,
                rebuild_asset_retries=args.rebuild_asset_retries,
                economy_mode=args.economy_mode,
                text_mode=args.text_mode,
                control_mode=args.control_mode,
                layout_mode=args.layout_mode,
                export_preview=args.export_preview,
                regenerate_slots=args.regenerate_slots,
                strict_asset_regeneration=args.strict_asset_regeneration,
                ocr_engine=args.ocr_engine,
                ocr_lang=args.ocr_lang,
                text_grouping_mode=args.text_grouping_mode,
                text_grouping_model=args.text_grouping_model,
                text_role_mode=args.text_role_mode,
                text_role_model=args.text_role_model,
                text_intelligence_mode=args.text_intelligence_mode,
                text_intelligence_model=args.text_intelligence_model,
                design_plan_mode=args.design_plan_mode,
                design_plan_model=args.design_plan_model,
                arrow_style_mode=args.arrow_style_mode,
                rebuild_critic_mode=args.rebuild_critic_mode,
                rebuild_critic_iterations=args.rebuild_critic_iterations,
                rebuild_critic_model=args.rebuild_critic_model,
                design_adapter=rebuild_adapters["design"] if args.design_plan_mode == "vlm" else None,
                text_intelligence_adapter=rebuild_adapters["text_intelligence"] if args.text_intelligence_mode == "vlm" else None,
                vlm_layout_adapter=rebuild_adapters["layout"] if args.layout_mode in {"vlm", "hybrid"} else None,
                control_adapter=rebuild_adapters["control"] if args.control_mode in {"vlm", "hybrid"} else None,
                semantic_adapter=rebuild_adapters["semantic"] if args.layout_mode in {"vlm", "hybrid"} or args.control_mode in {"vlm", "hybrid"} else None,
            )
        elif args.command == "rebuild-editable":
            rebuild_adapters = build_rebuild_vlm_adapters(args.out)
            result = rebuild_editable(
                reference=args.reference,
                out=args.out,
                asset_mode=args.asset_mode,
                asset_workers=args.asset_workers,
                asset_retries=args.asset_retries,
                economy_mode=args.economy_mode,
                text_mode=args.text_mode,
                control_mode=args.control_mode,
                layout_mode=args.layout_mode,
                export_preview=args.export_preview,
                regenerate_slots=args.regenerate_slots,
                strict_asset_regeneration=args.strict_asset_regeneration,
                skip_analysis=args.skip_analysis,
                compile_only=args.compile_only,
                ocr_engine=args.ocr_engine,
                ocr_lang=args.ocr_lang,
                text_role_mode=args.text_role_mode,
                text_role_model=args.text_role_model,
                text_intelligence_mode=args.text_intelligence_mode,
                text_intelligence_model=args.text_intelligence_model,
                design_plan_mode=args.design_plan_mode,
                design_plan_model=args.design_plan_model,
                arrow_style_mode=args.arrow_style_mode,
                rebuild_critic_mode=args.rebuild_critic_mode,
                rebuild_critic_iterations=args.rebuild_critic_iterations,
                rebuild_critic_model=args.rebuild_critic_model,
                design_adapter=rebuild_adapters["design"] if args.design_plan_mode == "vlm" else None,
                text_intelligence_adapter=rebuild_adapters["text_intelligence"] if args.text_intelligence_mode == "vlm" else None,
                vlm_layout_adapter=rebuild_adapters["layout"] if args.layout_mode in {"vlm", "hybrid"} else None,
                control_adapter=rebuild_adapters["control"] if args.control_mode in {"vlm", "hybrid"} else None,
                semantic_adapter=rebuild_adapters["semantic"] if args.layout_mode in {"vlm", "hybrid"} or args.control_mode in {"vlm", "hybrid"} else None,
            )
        elif args.command == "rebuild-editable-eval":
            result = evaluate_rebuild_vlm(
                reference=args.reference,
                out=args.out,
                asset_mode=args.asset_mode,
                text_mode=args.text_mode,
                export_preview=args.export_preview,
            )
        elif args.command == "coevolve-image":
            result = run_image_coevolution(
                ground_truth_path=args.ground_truth,
                out_dir=args.out,
                candidates=args.candidates,
                repair_candidates=args.repair_candidates,
                max_rounds=args.max_rounds,
                online_judge_model=args.online_judge_model,
                frozen_judge_model=args.frozen_judge_model,
                image_model=args.image_model,
                image_retries=args.image_retries,
            )
        elif args.command == "coevolution-report":
            result = analyze_coevolution_run(args.run)
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
