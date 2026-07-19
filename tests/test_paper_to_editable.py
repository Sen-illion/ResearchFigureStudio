from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from rfs.cli import build_parser
from rfs.paper_to_editable import run_paper_to_editable


PAPER_TEXT = """
Evidence-Grounded Modular Reasoning for Scientific Documents

Abstract
We introduce ModularTrace, a method that converts scientific documents into an evidence graph and performs constrained reasoning over it.

1 Method
The Document Parser splits the paper into page-aware passages. The Evidence Graph Builder extracts entities and directed relations. The Constrained Reasoner produces answers with evidence identifiers.

2 Experiments
We evaluate answer accuracy and evidence precision.
""".strip()


def _write_paper(root: Path) -> Path:
    paper = root / "paper.md"
    paper.write_text(PAPER_TEXT, encoding="utf-8")
    return paper


class PaperToEditableTests(unittest.TestCase):
    def test_cli_defaults_parse(self):
        parser = build_parser()
        args = parser.parse_args(["paper-to-editable", "--paper", "paper.pdf", "--out", "output/run"])
        self.assertEqual(args.command, "paper-to-editable")
        self.assertEqual(args.paper_image_asset_mode, "image2")
        self.assertEqual(args.paper_image_candidates, 3)
        self.assertEqual(args.paper_image_review_mode, "vlm")
        self.assertEqual(args.paper_image_repair_rounds, 1)
        self.assertEqual(args.rebuild_asset_mode, "crop")
        self.assertEqual(args.layout_mode, "hybrid")
        self.assertEqual(args.control_mode, "hybrid")
        self.assertFalse(args.allow_engineering_preview)
        self.assertFalse(args.require_paper_image_pass)

    def test_placeholder_engineering_preview_can_drive_editable_rebuild(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "run"
            result = run_paper_to_editable(
                paper=_write_paper(root),
                out=out,
                planner_mode="heuristic",
                paper_image_asset_mode="placeholder",
                paper_image_review_mode="heuristic",
                paper_image_ocr_engine="off",
                allow_engineering_preview=True,
                rebuild_asset_mode="placeholder",
                text_mode="off",
                layout_mode="heuristic",
                control_mode="heuristic",
                text_role_mode="heuristic",
                text_intelligence_mode="off",
                design_plan_mode="heuristic",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["generated_reference_source"], "engineering_preview")
            self.assertEqual(result["paper_image_delivery_mode"], "engineering_preview")
            self.assertTrue((out / "generated_reference_image.png").exists())
            self.assertTrue((out / "paper_to_image" / "candidate_review.json").exists())
            self.assertTrue((out / "editable_composition.pptx").exists())
            self.assertTrue((out / "paper_to_editable_result.json").exists())

    def test_placeholder_engineering_preview_is_blocked_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "run"
            with self.assertRaisesRegex(RuntimeError, "allow-engineering-preview"):
                run_paper_to_editable(
                    paper=_write_paper(root),
                    out=out,
                    planner_mode="heuristic",
                    paper_image_asset_mode="placeholder",
                    paper_image_review_mode="heuristic",
                    paper_image_ocr_engine="off",
                    rebuild_asset_mode="placeholder",
                    text_mode="off",
                    layout_mode="heuristic",
                    control_mode="heuristic",
                    text_intelligence_mode="off",
                    design_plan_mode="heuristic",
                )
            self.assertFalse((out / "editable_composition.pptx").exists())

    def test_best_effort_selected_image_continues_to_rebuild(self):
        def fake_paper_to_image(*, out, **_kwargs):
            paper_out = Path(out)
            paper_out.mkdir(parents=True, exist_ok=True)
            image = paper_out / "selected_image.png"
            Image.new("RGB", (1200, 800), "white").save(image)
            (paper_out / "candidate_review.json").write_text(
                json.dumps(
                    {
                        "summary": "Mock candidate review.",
                        "selected_candidate_id": "candidate_02",
                        "selected_delivery_mode": "best_effort",
                        "selected_passed_all_checks": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return {
                "summary": "Mock paper-to-image.",
                "ok": True,
                "out_dir": str(paper_out),
                "selected_image": str(image),
                "engineering_preview": None,
                "selected_candidate_id": "candidate_02",
                "selected_passed_all_checks": False,
            }

        def fake_rebuild(reference, out, **_kwargs):
            out_path = Path(out)
            pptx = out_path / "editable_composition.pptx"
            pptx.write_bytes(b"mock pptx")
            self.assertTrue(Path(reference).exists())
            return {
                "summary": "Mock rebuild.",
                "ok": True,
                "out_dir": str(out_path),
                "reference": str(reference),
                "pptx": str(pptx),
                "preview": None,
                "asset_mode": "crop",
            }

        with tempfile.TemporaryDirectory() as temp, patch("rfs.paper_to_editable.run_paper_to_image", side_effect=fake_paper_to_image), patch("rfs.paper_to_editable.rebuild_editable", side_effect=fake_rebuild):
            root = Path(temp)
            out = root / "run"
            result = run_paper_to_editable(paper=_write_paper(root), out=out)

            self.assertTrue(result["ok"])
            self.assertEqual(result["paper_image_delivery_mode"], "best_effort")
            self.assertFalse(result["paper_image_selected_passed_all_checks"])
            self.assertEqual(result["paper_image_selected_candidate_id"], "candidate_02")
            self.assertTrue((out / "generated_reference_image.png").exists())
            self.assertTrue((out / "editable_composition.pptx").exists())


if __name__ == "__main__":
    unittest.main()
