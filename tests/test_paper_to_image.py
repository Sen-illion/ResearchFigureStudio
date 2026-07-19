from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from rfs.cli import build_parser
from rfs.paper_to_image import run_paper_to_image
from rfs.paper_to_image.critics import review_candidate
from rfs.paper_to_image.generator import generate_and_select
from rfs.paper_to_image.planner import validate_plan_grounding
from rfs.paper_to_image.review import detect_domain_profile, validate_review_coverage
from rfs.paper_to_image.templates import build_template_profiles, render_layout_blueprint, select_template


PAPER_TEXT = """
Evidence-Grounded Modular Reasoning for Scientific Documents

Abstract
We introduce ModularTrace, a method that converts scientific documents into an evidence graph and then performs constrained reasoning over the graph. The method reduces unsupported conclusions while preserving exact paper terminology.

1 Introduction
Scientific document assistants often generate claims without traceable evidence. ModularTrace addresses this problem by linking every extracted fact to a source passage.

2 Method
The Document Parser splits the input paper into page-aware passages. The Evidence Graph Builder extracts entities and directed relations. The Constrained Reasoner consumes the graph and produces an answer with evidence identifiers. During training, a consistency loss penalizes unsupported relations. During inference, only retrieved evidence nodes may support an answer.

3 Experiments
We evaluate on three scientific question-answering datasets using answer accuracy and evidence precision.

4 Conclusion
ModularTrace improves evidence precision while maintaining answer accuracy.
""".strip()


def _png_b64(size=(1536, 1024), color=(235, 242, 247)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"b64_json": _png_b64()}]}


def _passing_critic(_path, _blueprint, _prompt):
    return {
        "summary": "Mock passing critic.",
        "ocr": {"detected_labels": ["Document Parser", "Evidence Graph Builder"], "missing_labels": [], "misspelled_labels": [], "duplicate_labels": [], "forbidden_labels_found": [], "score": 1.0, "passed": True},
        "scientific": {"missing_modules": [], "missing_relations": [], "reversed_relations": [], "invented_items": [], "innovation_visible": True, "score": 1.0, "passed": True},
        "template": {"macro_panel_match": 0.9, "reading_order_match": 0.9, "connector_rhythm_match": 0.9, "visual_density_match": 0.9, "copied_reference_content": [], "score": 0.9, "passed": True},
        "aesthetic": {"hierarchy": 0.9, "balance": 0.9, "whitespace": 0.9, "color": 0.9, "icon_consistency": 0.9, "readability": 0.9, "score": 0.9, "passed": True},
        "preserve": ["macro layout"],
        "repair": [],
        "remove": [],
        "repair_regions": [],
        "hard_errors": [],
    }


def _plan() -> dict:
    modules = [
        {"id": "parser", "name": "Document Parser", "role": "module", "evidence_ids": ["E0001"]},
        {"id": "graph", "name": "Evidence Graph Builder", "role": "module", "evidence_ids": ["E0001"]},
    ]
    return {
        "paper_summary": {"summary": "Paper summary.", "title": "ModularTrace"},
        "figure_specification": {"summary": "Scientific contract.", "figure_goal": "Show the method.", "modules": modules, "relations": [{"source": "parser", "target": "graph", "type": "data_flow", "evidence_ids": ["E0001"]}], "terminology": {"Document Parser": "Document Parser", "Evidence Graph Builder": "Evidence Graph Builder"}, "forbidden_inventions": []},
        "design_plan": {"summary": "Design.", "reading_order": ["parser", "graph"]},
        "layout_intent": {"summary": "Layout.", "pattern": "left_to_right"},
        "visual_metaphors": {"summary": "Metaphors.", "items": []},
        "style_plan": {"summary": "Style.", "medium": "academic"},
    }


class PaperToImageTests(unittest.TestCase):
    def test_offline_workflow_is_engineering_only(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"API_KEY": "known-test-secret"}, clear=False):
            root = Path(temp)
            paper = root / "paper.md"
            paper.write_text(PAPER_TEXT, encoding="utf-8")
            out = root / "run"
            result = run_paper_to_image(paper=paper, out=out, planner_mode="heuristic", asset_mode="placeholder", candidates=2, aspect_ratio="auto", review_mode="heuristic", ocr_engine="off")

            self.assertTrue(result["ok"])
            self.assertFalse(result["pptx_generated"])
            self.assertEqual(result["candidate_count"], 2)
            self.assertIsNone(result["selected_image"])
            self.assertTrue((out / "engineering_preview.png").exists())
            self.assertFalse((out / "selected_image.png").exists())
            for name in ["document_index.json", "paper_review.json", "review_coverage_report.json", "domain_profile.json", "selected_template.json", "layout_blueprint.png", "image2_request_manifest.json", "ocr_review.json", "template_alignment_report.json", "scientific_critic_report.json", "aesthetic_critic_report.json"]:
                self.assertTrue((out / name).exists(), name)
            document_index = json.loads((out / "document_index.json").read_text(encoding="utf-8"))
            self.assertTrue(document_index["sections"])
            manifest = json.loads((out / "image2_request_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["requests"][0]["model"], "offline-placeholder")
            self.assertIn("api_key_present", manifest)
            self.assertNotIn("known-test-secret", json.dumps(manifest))

    def test_cli_production_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["paper-to-image", "--paper", "paper.pdf", "--out", "output/run"])
        self.assertEqual(args.command, "paper-to-image")
        self.assertEqual(args.asset_mode, "image2")
        self.assertEqual(args.candidates, 3)
        self.assertEqual(args.review_mode, "vlm")
        self.assertEqual(args.aspect_ratio, "auto")
        self.assertEqual(args.domain_profile, "auto")
        self.assertEqual(args.template, "auto")
        self.assertEqual(args.repair_rounds, 1)

    def test_domain_profiles_detect_method_and_survey(self):
        method = {"evidence": [{"text": "A neural model is optimized with a training loss and used during inference."}]}
        survey = {"evidence": [{"text": "This systematic survey presents a taxonomy and review of the landscape."}]}
        self.assertEqual(detect_domain_profile(method)["id"], "ai-ml-method")
        self.assertEqual(detect_domain_profile(survey)["id"], "survey-review")

    def test_strict_review_rejects_ungrounded_relation(self):
        parsed = {"evidence": [{"id": "E0001"}]}
        profile = {"id": "general", "required_sections": ["research_questions", "central_claims", "contributions", "modules", "limitations"]}
        fact = {"id": "f1", "statement": "fact", "status": "required", "evidence_ids": ["E0001"]}
        review = {"research_questions": [fact], "central_claims": [fact], "contributions": [fact], "modules": [{**fact, "id": "m1"}], "limitations": [fact], "research_objects": [], "relations": [{"id": "r1", "source_id": "m1", "target_id": "missing", "evidence_ids": []}], "workflows": {"training": [], "inference": []}, "experiments": {}}
        report = validate_review_coverage(review, parsed, profile, strict=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("unknown endpoint" in item for item in report["errors"]))

    def test_review_relations_accept_input_module_output_endpoints(self):
        parsed = {"evidence": [{"id": "E0001"}]}
        profile = {"id": "general", "required_sections": ["research_questions", "central_claims", "inputs", "outputs", "modules", "relations"]}
        fact = {"id": "f1", "statement": "fact", "status": "required", "evidence_ids": ["E0001"]}
        review = {
            "research_questions": [fact],
            "central_claims": [fact],
            "inputs": [{**fact, "id": "input_text"}],
            "outputs": [{**fact, "id": "output_figure"}],
            "modules": [{**fact, "id": "module_parser"}],
            "relations": [
                {**fact, "id": "r1", "source_id": "input_text", "target_id": "module_parser"},
                {**fact, "id": "r2", "source_id": "module_parser", "target_id": "output_figure"},
            ],
            "workflows": {"training": [], "inference": []},
            "experiments": {},
        }
        report = validate_review_coverage(review, parsed, profile, strict=True)
        self.assertTrue(report["ok"], report["errors"])

    def test_plan_relations_accept_input_and_output_endpoints(self):
        parsed = {"evidence": [{"id": "E0001"}]}
        plan = {
            "figure_specification": {
                "modules": [{"id": "module_parser", "name": "Parser", "evidence_ids": ["E0001"]}],
                "inputs": ["input_text"],
                "outputs": ["output_figure"],
                "relations": [
                    {"source": "input_text", "target": "module_parser", "evidence_ids": ["E0001"]},
                    {"source": "module_parser", "target": "output_figure", "evidence_ids": ["E0001"]},
                ],
                "must_show": [],
                "innovations": [],
            }
        }
        report = validate_plan_grounding(plan, parsed)
        self.assertTrue(report["ok"], report["errors"])

    def test_four_reference_ratios_map_to_expected_templates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            refs = []
            for name, size in [("arbor", (1831, 979)), ("linear", (1336, 306)), ("tripanel", (804, 277)), ("dense", (2498, 1086))]:
                path = root / f"{name}.png"
                Image.new("RGB", size, "white").save(path)
                refs.append(str(path))
            profiles = build_template_profiles(refs, root / "profiles", mode="heuristic")
            self.assertEqual([item["template_id"] for item in profiles], ["arbor", "linear", "tripanel", "dense-multimodal"])
            selected = select_template(profiles, {"modules": [{"statement": "multimodal retrieval"}] * 10, "inputs": [], "relations": [], "workflows": {"feedback": []}}, requested="auto", target_ratio="auto")
            self.assertEqual(selected["template_id"], "dense-multimodal")
            report = render_layout_blueprint(selected, root / "blueprint.png", "auto")
            self.assertFalse(report["contains_reference_text"])
            self.assertTrue((root / "blueprint.png").exists())

    @patch("rfs.paper_to_image.generator.requests.post", return_value=FakeResponse())
    def test_mock_image2_generates_three_candidates_and_safe_manifest(self, _post):
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"API_BASE": "https://example.test/v1", "API_KEY": "secret-value", "RFS_IMAGE_MODEL": "image-2"}, clear=False):
            root = Path(temp)
            template = {"template_id": "linear", "profile_id": "builtin_linear", "panels": [], "connectors": [], "visual_density": "high", "style": {}, "forbidden_copy_terms": []}
            render_layout_blueprint({**template, "source_aspect_ratio": 1.5}, root / "layout_blueprint.png", "1.5:1")
            result = generate_and_select(_plan(), {"aspect_ratio": "1.5:1", "language": "English"}, template, root / "layout_blueprint.png", root, asset_mode="image2", candidates=3, review_mode="vlm", repair_rounds=1, ocr_engine="vlm", critic_adapter=_passing_critic)
            self.assertTrue(result["selected_passed_all_checks"])
            self.assertEqual(result["successful_candidates"], 3)
            self.assertTrue((root / "selected_image.png").exists())
            manifest_text = (root / "image2_request_manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["model"], "gpt-image-2")
            self.assertEqual(len(manifest["requests"]), 3)
            self.assertNotIn("secret-value", manifest_text)
            self.assertTrue(all(item["endpoint"].endswith("/images/edits") for item in manifest["requests"]))

    @patch("rfs.paper_to_image.generator.requests.post", return_value=FakeResponse())
    def test_failed_candidates_get_one_repair(self, _post):
        calls = {"count": 0}
        def critic(path, blueprint, prompt):
            calls["count"] += 1
            if calls["count"] <= 3:
                result = _passing_critic(path, blueprint, prompt)
                result["ocr"].update({"missing_labels": ["Document Parser"], "score": 0.5, "passed": False})
                result["repair"] = ["Correct the Document Parser label"]
                result["repair_regions"] = ["left panel"]
                result["hard_errors"] = ["missing critical label"]
                return result
            return _passing_critic(path, blueprint, prompt)
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"API_BASE": "https://example.test/v1", "API_KEY": "secret-value", "RFS_IMAGE_MODEL": "image-2"}, clear=False):
            root = Path(temp)
            template = {"template_id": "linear", "profile_id": "builtin_linear", "panels": [], "connectors": [], "visual_density": "high", "style": {}, "forbidden_copy_terms": []}
            render_layout_blueprint({**template, "source_aspect_ratio": 1.5}, root / "layout_blueprint.png", "1.5:1")
            result = generate_and_select(_plan(), {"aspect_ratio": "1.5:1", "language": "English"}, template, root / "layout_blueprint.png", root, asset_mode="image2", candidates=3, review_mode="vlm", repair_rounds=1, ocr_engine="vlm", critic_adapter=critic)
            self.assertEqual(result["repair_candidates"], 1)
            self.assertEqual(result["selected_candidate_id"], "repair_01")

    @patch("rfs.paper_to_image.generator.requests.post", return_value=FakeResponse())
    def test_image2_failed_gates_deliver_best_effort_selected_image(self, _post):
        def critic(path, blueprint, prompt):
            result = _passing_critic(path, blueprint, prompt)
            if Path(path).name == "candidate_02.png":
                result["scientific"].update({"invented_items": ["Unsupported shortcut flow"], "score": 0.9, "passed": False})
                result["repair"] = ["Remove unsupported shortcut flow"]
                return result
            result["ocr"].update({"missing_labels": ["Document Parser"], "score": 0.5, "passed": False})
            result["hard_errors"] = ["missing critical label"]
            return result

        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"API_BASE": "https://example.test/v1", "API_KEY": "secret-value", "RFS_IMAGE_MODEL": "image-2"}, clear=False):
            root = Path(temp)
            template = {"template_id": "linear", "profile_id": "builtin_linear", "panels": [], "connectors": [], "visual_density": "high", "style": {}, "forbidden_copy_terms": []}
            render_layout_blueprint({**template, "source_aspect_ratio": 1.5}, root / "layout_blueprint.png", "1.5:1")
            result = generate_and_select(_plan(), {"aspect_ratio": "1.5:1", "language": "English"}, template, root / "layout_blueprint.png", root, asset_mode="image2", candidates=2, review_mode="vlm", repair_rounds=0, ocr_engine="vlm", critic_adapter=critic)

            self.assertEqual(result["selected_candidate_id"], "candidate_02")
            self.assertEqual(result["selected_delivery_mode"], "best_effort")
            self.assertFalse(result["selected_passed_all_checks"])
            self.assertFalse(result["delivery_blocked"])
            self.assertTrue((root / "selected_image.png").exists())
            self.assertIn("Unsupported shortcut flow", json.dumps(result["selected_issues"]))

    @patch("rfs.paper_to_image.generator.requests.post", return_value=FakeResponse())
    @patch("rfs.paper_to_image.planner.call_vlm_json")
    @patch("rfs.paper_to_image.review.call_vlm_json")
    def test_mock_full_production_workflow(self, review_call, planner_call, _post):
        fact = {"id": "fact_01", "statement": "Evidence-grounded reasoning", "status": "required", "importance": "critical", "confidence": 1.0, "evidence_ids": ["E0001"], "must_appear_in_figure": True, "visual_role": "module"}
        review_call.return_value = {
            "summary": "Universal structured paper review.",
            "paper_identity": {"title": "ModularTrace", "paper_type": "method", "field": "AI"},
            "research_questions": [fact],
            "central_claims": [{**fact, "id": "claim_01"}],
            "inputs": [], "outputs": [], "research_objects": [], "concepts": [],
            "modules": [{**fact, "id": "parser", "statement": "Document Parser"}, {**fact, "id": "graph", "statement": "Evidence Graph Builder"}],
            "relations": [{**fact, "id": "relation_01", "source_id": "parser", "target_id": "graph", "relation_type": "data_flow", "visual_role": "relation"}],
            "workflows": {"training": [], "inference": [], "offline": [], "online": [], "feedback": []},
            "contributions": [{**fact, "id": "contribution_01"}], "innovations": [], "assumptions": [], "limitations": [{**fact, "id": "limitation_01"}],
            "experiments": {"datasets": [], "settings": [], "metrics": [], "baselines": [], "ablations": []}, "results": [],
            "terminology": [{**fact, "id": "term_01", "statement": "Document Parser", "visible_label": "Document Parser"}, {**fact, "id": "term_02", "statement": "Evidence Graph Builder", "visible_label": "Evidence Graph Builder"}],
            "forbidden_inventions": [], "unknowns": [], "contradictions": [], "ambiguities": [], "human_review_required": [], "figure_candidates": [],
        }
        planner_call.return_value = {"summary": "Planning result.", **_plan()}
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"API_BASE": "https://example.test/v1", "API_KEY": "known-test-secret", "RFS_IMAGE_MODEL": "image-2"}, clear=False):
            root = Path(temp)
            paper = root / "paper.md"
            paper.write_text(PAPER_TEXT, encoding="utf-8")
            out = root / "run"
            result = run_paper_to_image(paper=paper, out=out, planner_mode="vlm", domain_profile="general", template="linear", asset_mode="image2", candidates=3, aspect_ratio="1.5:1", review_mode="vlm", repair_rounds=1, ocr_engine="vlm", critic_adapter=_passing_critic)
            self.assertTrue(result["ok"])
            self.assertEqual(result["paper_review_mode"], "vlm")
            self.assertEqual(result["template_id"], "linear")
            self.assertTrue((out / "selected_image.png").exists())
            self.assertFalse(any(out.glob("*.pptx")))
            self.assertEqual(json.loads((out / "image2_request_manifest.json").read_text(encoding="utf-8"))["model"], "gpt-image-2")

    def test_local_ocr_can_block_vlm_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "candidate.png"
            blueprint = root / "blueprint.png"
            Image.new("RGB", (800, 600), "white").save(image)
            Image.new("RGB", (800, 600), "white").save(blueprint)
            review = review_candidate(image, blueprint, _plan(), {"template_id": "linear", "forbidden_copy_terms": []}, mode="vlm", ocr_engine="paddle", ocr_adapter=lambda _p, _l: [{"text": "Evidence Graph Builder"}], critic_adapter=_passing_critic)
            self.assertFalse(review["ocr"]["passed"])
            self.assertIn("Document Parser", review["ocr"]["missing_labels"])
            self.assertFalse(review["production_pass"])


if __name__ == "__main__":
    unittest.main()
