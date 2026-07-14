from __future__ import annotations

from pathlib import Path

from .asset_generator import generate_assets
from .asset_reviewer import review_assets
from .arrow_router import style_and_route_arrows
from .exporter import export_outputs
from .input_archive import archive_inputs
from .input_loader import load_text
from .paper_analyzer import analyze_paper
from .presentations_qa import run_presentations_qa
from .ppt_compiler import compile_ppt
from .prompt_planner import plan_slot_prompts
from .layout_locator import locate_layout
from .program_builder import build_figure_program
from .reference_analyzer import analyze_reference
from .stylist import build_style_sheet
from .text_layer import build_text_layer
from .utils import ensure_dir, write_json, write_text
from .validator import validate_output
from .visual_critic import apply_layout_corrections, run_visual_critic


def _write_alignment_review(out_dir: Path, paper_brief: dict, inventory: dict, layout_plan: dict, export_result: dict) -> None:
    text = "\n".join([
        "# Summary",
        "Alignment review for the paper-grounded, reference-guided PPT composition.",
        "",
        "## Grounding",
        f"- Paper title guess: {paper_brief.get('title_guess')}",
        f"- Figure goal: {paper_brief.get('figure_goal')}",
        f"- Reference image: {inventory.get('reference_path')}",
        f"- Slot count: {inventory.get('slot_count')}",
        f"- Locator mode: {layout_plan.get('locator_mode')}",
        f"- Control localizer: {inventory.get('control_localizer', {}).get('effective_mode')}",
        "",
        "## Layout Checks",
        "- Reference image was parameterized into slot bboxes before asset generation.",
        "- Layout coordinates come from layout_plan.json, not from generated PPT code.",
        "- Slots are inserted into PPT with contain-fit behavior.",
        "- Critical labels, formulas, arrows, panel titles, and group frames are editable PPT elements.",
        "",
        "## Export",
        f"- Export status: {export_result.get('status')}",
        f"- PDF: {export_result.get('pdf')}",
        f"- PNG: {export_result.get('png')}",
    ])
    write_text(out_dir / "alignment_review.md", text + "\n")


def _write_critic_report(out_dir: Path, validation: dict, asset_mode: str, locator_mode: str, control_localizer_mode: str = "hybrid", asset_review: dict | None = None, visual_critic: dict | None = None) -> None:
    status = "PASS" if validation.get("ok") else "FAIL"
    lines = [
        "# Summary",
        "Critic review for workflow compliance before delivery.",
        "",
        "## Result",
        f"- Status: {status}",
        f"- Asset mode: {asset_mode}",
        f"- Locator mode: {locator_mode}",
        f"- Control localizer mode: {control_localizer_mode}",
        "- Arrow style mode: reference-first",
        f"- Generated asset count: {validation.get('asset_count')}",
        "",
        "## Checks",
        "- Paper brief exists before layout generation.",
        "- Slot inventory exists before image prompts.",
        "- Figure program is the layout source for PPT composition.",
        "- Main editable source is PPTX.",
        "- Slot images are complete and inserted without semantic trimming.",
        "- Scientific labels and formulas are controlled by the PPT layer.",
    ]
    if asset_review:
        lines.extend(["", "## Asset Visual Review", f"- Mode: {asset_review.get('mode')}", f"- Status: {asset_review.get('status', 'unknown')}", f"- Issues: {len(asset_review.get('issues', []))}"])
    if visual_critic:
        lines.extend(["", "## Layout Visual Critic", f"- Mode: {visual_critic.get('mode')}", f"- Status: {visual_critic.get('status', 'unknown')}", f"- Layout corrections: {len(visual_critic.get('layout_corrections', []))}", f"- Blocking issues: {len(visual_critic.get('blocking_issues', []))}"])
    if validation.get("errors"):
        lines.extend(["", "## Blocking Issues"])
        lines.extend(f"- {item}" for item in validation["errors"])
    if validation.get("warnings"):
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {item}" for item in validation["warnings"])
    write_text(out_dir / "critic_report.md", "\n".join(lines) + "\n")


def make_framework(
    paper: str | Path,
    reference: str | Path,
    out: str | Path,
    profile: str = "ai-ml-paper",
    slot_count: int = 36,
    slot_source: str = "reference-primary",
    asset_mode: str = "image2",
    candidates_per_slot: int = 4,
    asset_workers: int = 1,
    asset_retries: int = 2,
    asset_review_mode: str = "heuristic",
    locator_mode: str = "heuristic",
    locator_model: str | None = None,
    control_localizer_mode: str = "hybrid",
    arrow_style_mode: str = "reference",
    prompt_plan_mode: str = "vlm",
    prompt_plan_model: str | None = None,
    prompt_plan_workers: int = 4,
    complexity_profile: str = "reference-dense",
    critic_mode: str = "heuristic",
    critic_model: str | None = None,
    critic_iterations: int = 0,
    text_extractor_mode: str = "ocr",
    ocr_engine: str = "paddle",
    ocr_lang: str = "en_ch",
    presentations_qa: bool = False,
    presentations_workspace: str | Path | None = None,
    presentations_scale: int = 2,
    export: bool = True,
) -> dict:
    out_dir = ensure_dir(out)
    prompt_plan_workers = max(1, min(12, int(prompt_plan_workers)))
    input_manifest = archive_inputs(paper, reference, out_dir)
    archived_paper = input_manifest.get("paper_archived") or str(paper)
    archived_reference = input_manifest.get("reference_archived") or str(reference)
    loaded = load_text(archived_paper)
    paper_brief = analyze_paper(loaded, out_dir)
    inventory = analyze_reference(
        archived_reference,
        paper_brief,
        out_dir,
        slot_count=slot_count,
        slot_source=slot_source,
        control_localizer_mode=control_localizer_mode,
    )
    style = build_style_sheet(paper_brief, inventory, out_dir)
    layout_plan = locate_layout(archived_reference, inventory, style, out_dir, mode=locator_mode, model=locator_model)
    program = build_figure_program(paper_brief, inventory, style, out_dir, layout_plan=layout_plan)
    program = style_and_route_arrows(program, out_dir, mode=arrow_style_mode)
    _slot_prompt_plan, program = plan_slot_prompts(
        archived_reference,
        paper_brief,
        inventory,
        style,
        out_dir,
        program,
        mode=prompt_plan_mode,
        model=prompt_plan_model,
        workers=prompt_plan_workers,
        complexity_profile=complexity_profile,
    )
    program = style_and_route_arrows(program, out_dir, mode=arrow_style_mode)
    program = build_text_layer(
        archived_reference,
        program,
        style,
        out_dir,
        text_extractor_mode=text_extractor_mode,
        ocr_engine=ocr_engine,
        ocr_lang=ocr_lang,
    )
    generate_assets(
        program,
        style,
        out_dir,
        asset_mode=asset_mode,
        candidates_per_slot=candidates_per_slot,
        asset_workers=asset_workers,
        asset_retries=asset_retries,
    )
    asset_review = review_assets(out_dir, mode=asset_review_mode, model=critic_model)
    pptx = compile_ppt(program, out_dir)
    export_result = {"status": "skipped", "pdf": None, "png": None}
    if export:
        export_result = export_outputs(pptx, out_dir)

    visual_critic = run_visual_critic(
        out_dir=out_dir,
        reference_path=archived_reference,
        final_png_path=export_result.get("png"),
        layout_plan=layout_plan,
        program=program,
        mode=critic_mode,
        model=critic_model,
        iteration=0,
    )

    for iteration in range(1, max(0, min(3, int(critic_iterations))) + 1):
        if critic_mode != "vlm":
            break
        layout_plan, changed = apply_layout_corrections(layout_plan, visual_critic)
        if changed == 0:
            break
        write_json(out_dir / "layout_plan.json", layout_plan)
        program = build_figure_program(paper_brief, inventory, style, out_dir, layout_plan=layout_plan)
        program = style_and_route_arrows(program, out_dir, mode=arrow_style_mode)
        program = build_text_layer(
            archived_reference,
            program,
            style,
            out_dir,
            text_extractor_mode=text_extractor_mode,
            ocr_engine=ocr_engine,
            ocr_lang=ocr_lang,
        )
        pptx = compile_ppt(program, out_dir)
        if export:
            export_result = export_outputs(pptx, out_dir)
        visual_critic = run_visual_critic(
            out_dir=out_dir,
            reference_path=archived_reference,
            final_png_path=export_result.get("png"),
            layout_plan=layout_plan,
            program=program,
            mode=critic_mode,
            model=critic_model,
            iteration=iteration,
        )
    _write_alignment_review(out_dir, paper_brief, inventory, layout_plan, export_result)
    write_text(out_dir / "critic_report.md", "# Summary\nCritic review placeholder created before final validation.\n")
    validation_for_critic = validate_output(out_dir)
    _write_critic_report(out_dir, validation_for_critic, asset_mode, locator_mode, control_localizer_mode=control_localizer_mode, asset_review=asset_review, visual_critic=visual_critic)
    validation = validate_output(out_dir)
    presentations_report = None
    if presentations_qa:
        presentations_report = run_presentations_qa(
            out_dir=out_dir,
            pptx=pptx,
            workspace=presentations_workspace,
            scale=presentations_scale,
            run_inspect=True,
        )
    return {
        "summary": "ResearchFigureStudio make-framework run result.",
        "ok": validation.get("ok", False),
        "out_dir": str(out_dir),
        "pptx": str(pptx),
        "pdf": export_result.get("pdf"),
        "png": export_result.get("png"),
        "asset_mode": asset_mode,
        "candidates_per_slot": candidates_per_slot,
        "asset_workers": asset_workers,
        "asset_retries": asset_retries,
        "asset_review_mode": asset_review_mode,
        "locator_mode": locator_mode,
        "control_localizer_mode": control_localizer_mode,
        "arrow_style_mode": arrow_style_mode,
        "prompt_plan_mode": prompt_plan_mode,
        "prompt_plan_workers": prompt_plan_workers,
        "complexity_profile": complexity_profile,
        "critic_mode": critic_mode,
        "critic_iterations": critic_iterations,
        "text_extractor_mode": text_extractor_mode,
        "ocr_engine": ocr_engine,
        "ocr_lang": ocr_lang,
        "presentations_qa": presentations_report,
        "slot_count": inventory.get("slot_count"),
        "slot_source": slot_source,
        "validation": validation,
    }
