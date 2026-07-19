import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from rfs.cli import main
from rfs.editable_rebuild import economy_acceptance_decision, rebuild_editable, _make_asset_specs
from rfs.rebuild_eval import evaluate_rebuild_vlm
from rfs.rebuild_vlm_validation import build_rebuild_vlm_validation_report
from rfs.rebuild_vlm_adapters import build_rebuild_vlm_adapters, vlm_control_adapter_factory, vlm_design_adapter, vlm_layout_adapter, vlm_semantic_adapter, vlm_text_intelligence_adapter


def _fixture(path: Path) -> Path:
    image = Image.new("RGB", (640, 360), "#F7F3EA")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 50, 610, 315), radius=20, fill="#FFFFFF", outline="#4A90C2", width=4)
    draw.rectangle((42, 72, 170, 170), fill="#DCEEFF", outline="#4A90C2", width=3)
    draw.ellipse((265, 88, 365, 188), fill="#F8D7A8", outline="#D28A2E", width=3)
    draw.rounded_rectangle((470, 78, 575, 178), radius=12, fill="#DDEEDB", outline="#4D9A57", width=3)
    draw.line((175, 120, 260, 120), fill="#333333", width=4)
    draw.polygon([(260, 120), (246, 112), (246, 128)], fill="#333333")
    draw.line((370, 130, 465, 130), fill="#333333", width=4)
    draw.polygon([(465, 130), (451, 122), (451, 138)], fill="#333333")
    draw.text((42, 22), "Pipeline Demo", fill="#1E2A33")
    draw.text((60, 190), "Input", fill="#1E2A33")
    draw.text((288, 205), "Agent", fill="#1E2A33")
    draw.text((492, 192), "Output", fill="#1E2A33")
    image.save(path)
    return path


class RebuildEditableTests(unittest.TestCase):
    def test_cli_placeholder_run_writes_required_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"
            with patch.dict("os.environ", {"API_BASE": "", "API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
                code = main([
                    "rebuild-editable",
                    "--reference", str(reference),
                    "--out", str(out),
                    "--asset-mode", "placeholder",
                    "--text-mode", "off",
                    "--text-role-mode", "vlm",
                    "--text-role-model", "fake-text-role-model",
                    "--arrow-style-mode", "reference",
                    "--export-preview",
                ])
            self.assertEqual(code, 0)
            required = [
                "input_manifest.json",
                "reference_logic_plan.json",
                "reference_logic_plan.md",
                "reference_layer_plan.json",
                "reference_generation_plan.json",
                "reference_flow_graph.json",
                "reference_geometry.json",
                "reference_geometry_overlay.png",
                "rebuild_vlm_validation_report.json",
                "reference_text_geometry.json",
                "reference_controls_raw.json",
                "reference_controls.json",
                "reference_controls_overlay.png",
                "slot_inventory.json",
                "slot_semantic_report.json",
                "asset_generation_specs.json",
                "asset_generation_report.json",
                "asset_economy_report.json",
                "asset_ratio_fit_report.json",
                "figure_program.json",
                "composition_quality_report.json",
                "editable_composition.pptx",
                "text_intelligence_report.json",
                "text_relationships.json",
                "text_style_profile.json",
                "text_layout_intent_report.json",
            ]
            for name in required:
                self.assertTrue((out / name).exists(), name)
            self.assertTrue((out / "rebuild_preview.png").exists() or (out / "preview_export_error.txt").exists())
            with zipfile.ZipFile(out / "editable_composition.pptx") as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertNotIn("inputs/pipeline.png", slide_xml)
            self.assertIn("<p:pic>", slide_xml)
            self.assertIn("<p:cxnSp>", slide_xml)
            text_intel = json.loads((out / "text_intelligence_report.json").read_text(encoding="utf-8"))
            self.assertEqual(text_intel["status"], "skipped")
            logic = json.loads((out / "reference_logic_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(logic["mode"], "vlm")
            self.assertEqual(logic["effective_mode"], "heuristic")

    def test_fake_global_design_adapter_writes_design_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_design(_path, _model):
                return {
                    "summary": "global plan",
                    "narrative": {"figure_type": "workflow", "main_story": "Input to output", "key_message": "Demo flow"},
                    "reading_order": ["slot_input", "slot_agent", "slot_output"],
                    "layers": [
                        {"id": "slot_input", "kind": "visual_slot", "bbox_percent": {"x": 0.08, "y": 0.20, "w": 0.16, "h": 0.24}, "asset_source_policy": "api_generate", "prompt_subject": "input document"},
                        {"id": "text_title", "kind": "text", "bbox_percent": {"x": 0.08, "y": 0.02, "w": 0.40, "h": 0.08}, "asset_source_policy": "editable_text"},
                    ],
                    "asset_policies": [{"slot_id": "slot_input", "policy": "api_generate", "reason": "illustration"}],
                    "flow_graph": {"edges": [{"id": "flow_1", "source_id": "slot_input", "target_id": "slot_output", "relation": "feeds_into"}]},
                }

            result = rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", design_adapter=fake_design, design_plan_model="fake-design-model")
            self.assertTrue(result["ok"])
            self.assertEqual(result["design_plan_effective_mode"], "vlm")
            self.assertEqual(result["design_plan_model"], "fake-design-model")
            logic = json.loads((out / "reference_logic_plan.json").read_text(encoding="utf-8"))
            layers = json.loads((out / "reference_layer_plan.json").read_text(encoding="utf-8"))
            generation = json.loads((out / "reference_generation_plan.json").read_text(encoding="utf-8"))
            flow = json.loads((out / "reference_flow_graph.json").read_text(encoding="utf-8"))
            self.assertEqual(logic["narrative"]["key_message"], "Demo flow")
            self.assertEqual(layers["layers"][0]["id"], "slot_input")
            self.assertEqual(generation["asset_policies"][0]["policy"], "api_generate")
            self.assertEqual(flow["edges"][0]["source_id"], "slot_input")

    def test_fake_vlm_text_intelligence_writes_style_relationship_and_layout_reports_without_mutating_text_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "slot_agent", "asset_id": "slot_agent", "bbox_percent": {"x": 0.40, "y": 0.20, "w": 0.18, "h": 0.30}}]}

            def fake_ocr(_path, _lang):
                return [{"text": "AI Critic", "confidence": 0.99, "quad": [[260, 80], [370, 80], [370, 112], [260, 112]]}]

            def fake_text_intelligence(_path, _program, text_geometry, text_program, _model):
                text_id = text_program["items"][0]["id"]
                return {
                    "summary": "fake text intelligence",
                    "items": [{
                        "text_id": text_id,
                        "font_style_guess": {
                            "family_class": "display",
                            "weight": "bold",
                            "italic": True,
                            "case_style": "title_case",
                            "visual_style": "rounded friendly title label",
                        },
                        "layout_intent": {
                            "alignment": "center",
                            "anchor": "top_center",
                            "belongs_to": "slot_agent",
                            "row_group": "agent_label_row",
                            "column_group": "agent_column",
                        },
                        "confidence": 0.94,
                        "reason": "label above the agent slot",
                    }],
                    "text_relations": [{
                        "source_text_id": text_id,
                        "target_object_id": "slot_agent",
                        "relation": "label_for_visual_object",
                        "confidence": 0.93,
                        "reason": "caption labels the agent illustration",
                    }],
                }

            rebuild_editable(
                reference,
                out,
                asset_mode="placeholder",
                text_mode="ocr",
                text_role_mode="heuristic",
                vlm_layout_adapter=fake_layout,
                ocr_adapter=fake_ocr,
                text_intelligence_mode="vlm",
                text_intelligence_adapter=fake_text_intelligence,
            )
            style = json.loads((out / "text_style_profile.json").read_text(encoding="utf-8"))
            relationships = json.loads((out / "text_relationships.json").read_text(encoding="utf-8"))
            layout = json.loads((out / "text_layout_intent_report.json").read_text(encoding="utf-8"))
            program = json.loads((out / "figure_program.json").read_text(encoding="utf-8"))
            self.assertEqual(style["items"][0]["font_style_guess"]["family_class"], "display")
            self.assertEqual(relationships["relations"][0]["relation"], "label_for_visual_object")
            self.assertEqual(layout["items"][0]["layout_intent"]["belongs_to"], "slot_agent")
            self.assertEqual(program["text_program"]["items"][0]["font_family_guess"], "Arial")
            self.assertEqual(program["text_program"]["items"][0]["bbox_percent"], json.loads((out / "text_program.json").read_text(encoding="utf-8"))["items"][0]["bbox_percent"])

    def test_text_intelligence_failure_falls_back_to_heuristic_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_ocr(_path, _lang):
                return [{"text": "Pipeline Demo", "confidence": 0.98, "quad": [[40, 20], [210, 20], [210, 45], [40, 45]]}]

            def failing_text_intelligence(*_args):
                raise RuntimeError("text intelligence unavailable")

            result = rebuild_editable(
                reference,
                out,
                asset_mode="placeholder",
                text_mode="ocr",
                ocr_adapter=fake_ocr,
                text_role_mode="heuristic",
                text_intelligence_mode="vlm",
                text_intelligence_adapter=failing_text_intelligence,
            )
            self.assertEqual(result["text_intelligence_effective_mode"], "heuristic")
            report = json.loads((out / "text_intelligence_report.json").read_text(encoding="utf-8"))
            validation = json.loads((out / "rebuild_vlm_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "fallback_to_heuristic")
            self.assertIn("text intelligence unavailable", report["fallback_reason"])
            self.assertEqual(validation["text_intelligence"]["effective_mode"], "heuristic")

    def test_fake_ocr_text_becomes_editable_textbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_ocr(_path, _lang):
                return [{
                    "text": "Pipeline Demo",
                    "confidence": 0.98,
                    "quad": [[40, 20], [210, 20], [210, 45], [40, 45]],
                }]

            result = rebuild_editable(reference, out, asset_mode="placeholder", text_mode="ocr", export_preview=False, ocr_adapter=fake_ocr, text_role_mode="heuristic")
            self.assertTrue(result["ok"])
            text_geometry = json.loads((out / "reference_text_geometry.json").read_text(encoding="utf-8"))
            self.assertEqual(text_geometry["detection_mode"], "ocr")
            self.assertEqual(text_geometry["text_regions"][0]["raw_text"], "Pipeline Demo")
            with zipfile.ZipFile(out / "editable_composition.pptx") as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertIn("Pipeline Demo", slide_xml)

    def test_default_vlm_text_role_falls_back_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_ocr(_path, _lang):
                return [{
                    "text": "Pipeline Demo",
                    "confidence": 0.98,
                    "quad": [[40, 20], [210, 20], [210, 45], [40, 45]],
                }]

            with patch.dict("os.environ", {"API_BASE": "", "API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
                result = rebuild_editable(reference, out, asset_mode="placeholder", text_mode="ocr", ocr_adapter=fake_ocr)
            self.assertEqual(result["text_role_mode"], "vlm")
            self.assertEqual(result["text_role_effective_mode"], "heuristic")
            classification = json.loads((out / "text_role_classification.json").read_text(encoding="utf-8"))
            self.assertEqual(classification["status"], "fallback_to_heuristic")
            validation = json.loads((out / "rebuild_vlm_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["text_role"]["effective_mode"], "heuristic")

    def test_fake_vlm_text_role_drives_rebuild_size_clustering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_ocr(_path, _lang):
                return [
                    {"text": "Input stage", "confidence": 0.99, "quad": [[50, 190], [160, 190], [160, 212], [50, 212]]},
                    {"text": "Output stage", "confidence": 0.99, "quad": [[470, 190], [590, 190], [590, 214], [470, 214]]},
                ]

            def fake_roles(_path, regions, _program, _model):
                return {
                    "summary": "fake roles",
                    "items": [
                        {
                            "text_id": region["id"],
                            "role": "body_label",
                            "hierarchy_level": "body",
                            "size_class": "medium",
                            "group_hint": "stage_labels",
                            "confidence": 0.96,
                        }
                        for region in regions
                        if str(region.get("source", "")).startswith("reference_ocr")
                    ],
                }

            result = rebuild_editable(
                reference,
                out,
                asset_mode="placeholder",
                text_mode="ocr",
                ocr_adapter=fake_ocr,
                text_role_mode="vlm",
                text_role_adapter=fake_roles,
            )
            self.assertEqual(result["text_role_effective_mode"], "vlm")
            program = json.loads((out / "figure_program.json").read_text(encoding="utf-8"))
            ocr_items = [item for item in program["text_program"]["items"] if item["text"] in {"Input stage", "Output stage"}]
            self.assertEqual({item["role"] for item in ocr_items}, {"body_label"})
            self.assertEqual(len({item["font_size_pt"] for item in ocr_items}), 1)

    def test_fake_vlm_layout_enters_geometry_and_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {
                    "confidence": 0.93,
                    "panels": [{"id": "stage_a", "title": "Stage A", "bbox_percent": {"x": 0.04, "y": 0.10, "w": 0.92, "h": 0.78}}],
                    "slots": [
                        {"id": "input_doc", "asset_id": "input_doc", "bbox_percent": {"x": 0.08, "y": 0.25, "w": 0.18, "h": 0.24}, "prompt_subject": "input document"},
                        {"id": "ai_critic", "asset_id": "ai_critic", "bbox_percent": {"x": 0.42, "y": 0.24, "w": 0.16, "h": 0.28}, "prompt_subject": "AI Critic robot"},
                        {"id": "output_card", "asset_id": "output_card", "bbox_percent": {"x": 0.72, "y": 0.25, "w": 0.18, "h": 0.24}, "prompt_subject": "output card"},
                    ],
                }

            result = rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", vlm_layout_adapter=fake_layout)
            self.assertTrue(result["ok"])
            geometry = json.loads((out / "reference_geometry.json").read_text(encoding="utf-8"))
            program = json.loads((out / "figure_program.json").read_text(encoding="utf-8"))
            self.assertEqual(geometry["vlm_status"], "used")
            self.assertEqual(geometry["confidence"], 0.93)
            self.assertEqual([slot["id"] for slot in program["slots"]], ["input_doc", "ai_critic", "output_card"])

    def test_fake_control_localizer_path_is_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {
                    "slots": [
                        {"id": "slot_a", "asset_id": "slot_a", "bbox_percent": {"x": 0.10, "y": 0.25, "w": 0.16, "h": 0.22}},
                        {"id": "slot_b", "asset_id": "slot_b", "bbox_percent": {"x": 0.70, "y": 0.25, "w": 0.16, "h": 0.22}},
                    ]
                }

            def fake_controls(_path, _slots, _heuristic):
                return {"arrows": [{
                    "id": "detected_arrow",
                    "source_id": "slot_a",
                    "target_id": "slot_b",
                    "control_kind": "elbow_connector",
                    "path_percent": [[0.26, 0.36], [0.50, 0.36], [0.50, 0.50], [0.70, 0.50]],
                    "stroke_color": "#D94141",
                    "stroke_width_pt": 2.0,
                    "dash_style": "solid",
                    "confidence": 0.91,
                }]}

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", vlm_layout_adapter=fake_layout, control_adapter=fake_controls, arrow_style_mode="off")
            controls = json.loads((out / "reference_controls.json").read_text(encoding="utf-8"))
            raw_controls = json.loads((out / "reference_controls_raw.json").read_text(encoding="utf-8"))
            self.assertEqual(controls["vlm_status"], "used")
            self.assertEqual(raw_controls["arrows"][0]["path_percent"][1], [0.5, 0.36])
            self.assertFalse(controls["routing_applied"])
            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))
            rendered = {item["arrow_id"]: item for item in report["arrows"]}
            self.assertEqual(rendered["detected_arrow"]["segment_count"], 3)
            self.assertEqual(rendered["detected_arrow"]["render_style"], "line_connector")

    def test_rebuild_arrow_router_renders_block_and_branch_styles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [
                    {"id": "slot_a", "asset_id": "slot_a", "bbox_percent": {"x": 0.08, "y": 0.25, "w": 0.16, "h": 0.22}},
                    {"id": "slot_b", "asset_id": "slot_b", "bbox_percent": {"x": 0.42, "y": 0.18, "w": 0.16, "h": 0.22}},
                    {"id": "slot_c", "asset_id": "slot_c", "bbox_percent": {"x": 0.70, "y": 0.42, "w": 0.16, "h": 0.22}},
                ]}

            def fake_controls(_path, _slots, _heuristic):
                return {"arrows": [
                    {
                        "id": "block_arrow",
                        "source_id": "slot_a",
                        "target_id": "slot_b",
                        "render_style": "filled_block_arrow",
                        "route_intent": "straight",
                        "visual_weight": "chunky",
                        "path_percent": [[0.24, 0.36], [0.42, 0.29]],
                        "fill_color": "#BFD5EA",
                        "outline_color": "#3F5063",
                    },
                    {
                        "id": "branch_arrow",
                        "source_id": "slot_a",
                        "target_id": "slot_b",
                        "target_ids": ["slot_b", "slot_c"],
                        "render_style": "branch_line_connector",
                        "route_intent": "branch",
                        "preferred_axis": "horizontal_first",
                        "path_percent": [[0.24, 0.36], [0.42, 0.29]],
                    },
                ]}

            rebuild_editable(
                reference,
                out,
                asset_mode="placeholder",
                text_mode="off",
                vlm_layout_adapter=fake_layout,
                control_adapter=fake_controls,
                arrow_style_mode="reference",
            )
            program = json.loads((out / "figure_program.json").read_text(encoding="utf-8"))
            arrows = {item["id"]: item for item in program["arrows"]}
            raw = json.loads((out / "reference_controls_raw.json").read_text(encoding="utf-8"))
            final = json.loads((out / "reference_controls.json").read_text(encoding="utf-8"))
            raw_arrows = {item["id"]: item for item in raw["arrows"]}
            self.assertEqual(arrows["block_arrow"]["render_style"], "filled_block_arrow")
            self.assertEqual(arrows["branch_arrow"]["render_style"], "branch_line_connector")
            self.assertEqual(len(arrows["branch_arrow"]["branches"]), 2)
            self.assertEqual(raw_arrows["block_arrow"]["path_percent"], [[0.24, 0.36], [0.42, 0.29]])
            self.assertTrue(final["routing_applied"])
            self.assertEqual(final["raw_arrow_count"], 2)
            self.assertEqual(final["routed_arrow_count"], 2)
            self.assertEqual(final["raw_controls_path"], "reference_controls_raw.json")
            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))
            rendered = {item["arrow_id"]: item for item in report["arrows"]}
            self.assertEqual(rendered["block_arrow"]["connector_type"], "filled_block_arrow_shape")
            self.assertEqual(rendered["branch_arrow"]["branch_count"], 2)
            validation = json.loads((out / "rebuild_vlm_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["control"]["render_style_counts"]["filled_block_arrow"], 1)
            self.assertEqual(validation["control"]["raw_arrow_count"], 2)
            self.assertEqual(validation["control"]["routed_arrow_count"], 2)
            self.assertGreaterEqual(validation["control"]["routed_path_changed_count"], 1)

    def test_global_flow_graph_is_passed_to_control_adapter_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"
            seen = {}

            def fake_design(_path, _model):
                return {
                    "layers": [
                        {"id": "slot_a", "kind": "visual_slot", "bbox_percent": {"x": 0.08, "y": 0.25, "w": 0.16, "h": 0.22}},
                        {"id": "slot_b", "kind": "visual_slot", "bbox_percent": {"x": 0.62, "y": 0.25, "w": 0.16, "h": 0.22}},
                    ],
                    "flow_graph": {"edges": [{"id": "flow_good", "source_id": "slot_a", "target_id": "slot_b"}, {"id": "flow_bad", "source_id": "slot_a", "target_id": "missing"}]},
                }

            def fake_layout(_path, _base):
                return {"slots": [
                    {"id": "slot_a", "asset_id": "slot_a", "bbox_percent": {"x": 0.08, "y": 0.25, "w": 0.16, "h": 0.22}},
                    {"id": "slot_b", "asset_id": "slot_b", "bbox_percent": {"x": 0.62, "y": 0.25, "w": 0.16, "h": 0.22}},
                ]}

            def fake_controls(_path, _slots, _heuristic, flow_graph):
                seen["edge_ids"] = [item["id"] for item in flow_graph["edges"]]
                return {"arrows": [{"id": "flow_arrow", "source_id": "slot_a", "target_id": "slot_b", "path_percent": [[0.24, 0.36], [0.62, 0.36]]}]}

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", design_adapter=fake_design, vlm_layout_adapter=fake_layout, control_adapter=fake_controls)

            self.assertEqual(seen["edge_ids"], ["flow_good", "flow_bad"])
            controls = json.loads((out / "reference_controls.json").read_text(encoding="utf-8"))
            self.assertTrue(controls["flow_graph_used"])
            self.assertEqual(controls["invalid_flow_edge_count"], 1)
            validation = json.loads((out / "rebuild_vlm_validation_report.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["control"]["flow_graph_used"])
            self.assertEqual(validation["control"]["invalid_flow_edge_ids"], ["flow_bad"])

    def test_rebuild_preserves_dashed_multipoint_reference_arrow_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"
            raw_path = [[0.42, 0.44], [0.46, 0.32], [0.56, 0.32], [0.60, 0.44]]

            def fake_layout(_path, _base):
                return {"slots": [
                    {"id": "ai_designer_icon", "asset_id": "ai_designer_icon", "bbox_percent": {"x": 0.34, "y": 0.40, "w": 0.08, "h": 0.12}},
                    {"id": "ai_critic_icon", "asset_id": "ai_critic_icon", "bbox_percent": {"x": 0.60, "y": 0.40, "w": 0.08, "h": 0.12}},
                ]}

            def fake_controls(_path, _slots, _heuristic):
                return {"arrows": [{
                    "id": "stage_ii_loop",
                    "source_id": "ai_designer_icon",
                    "target_id": "ai_critic_icon",
                    "path_percent": raw_path,
                    "dash_style": "dashed",
                    "line_pattern": "dash",
                    "render_style": "line_connector",
                    "route_intent": "loop",
                    "preferred_axis": "horizontal",
                    "bend_side": "above",
                    "binding_source": "vlm",
                    "route_policy": "preserve_reference_path",
                }]}

            rebuild_editable(
                reference,
                out,
                asset_mode="placeholder",
                text_mode="off",
                vlm_layout_adapter=fake_layout,
                control_adapter=fake_controls,
                arrow_style_mode="reference",
            )

            raw = json.loads((out / "reference_controls_raw.json").read_text(encoding="utf-8"))
            final = json.loads((out / "reference_controls.json").read_text(encoding="utf-8"))
            raw_arrow = raw["arrows"][0]
            final_arrow = final["arrows"][0]
            self.assertEqual(raw_arrow["path_percent"], raw_path)
            self.assertEqual(final_arrow["path_percent"], raw_path)
            self.assertEqual(final_arrow["route_style"], "dashed_spline_like")
            self.assertEqual(final_arrow["line_pattern"], "dash")
            self.assertEqual(final_arrow["route_generation_status"], "reference_locked")
            self.assertTrue(final_arrow["reference_path_preserved"])
            self.assertEqual(final["routed_path_changed_count"], 0)

            validation = json.loads((out / "rebuild_vlm_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["control"]["routed_path_changed_count"], 0)
            rendered = {item["arrow_id"]: item for item in json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))["arrows"]}
            self.assertEqual(rendered["stage_ii_loop"]["route_style"], "dashed_spline_like")
            self.assertEqual(rendered["stage_ii_loop"]["segment_count"], 3)

    def test_skip_analysis_prefers_raw_controls_for_rerouting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [
                    {"id": "slot_a", "asset_id": "slot_a", "bbox_percent": {"x": 0.08, "y": 0.25, "w": 0.16, "h": 0.22}},
                    {"id": "slot_b", "asset_id": "slot_b", "bbox_percent": {"x": 0.62, "y": 0.25, "w": 0.16, "h": 0.22}},
                ]}

            def fake_controls(_path, _slots, _heuristic):
                return {"arrows": [{
                    "id": "raw_arrow",
                    "source_id": "slot_a",
                    "target_id": "slot_b",
                    "render_style": "line_connector",
                    "path_percent": [[0.24, 0.36], [0.62, 0.36]],
                }]}

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", vlm_layout_adapter=fake_layout, control_adapter=fake_controls, arrow_style_mode="off")
            raw = json.loads((out / "reference_controls_raw.json").read_text(encoding="utf-8"))
            raw["arrows"][0]["render_style"] = "filled_block_arrow"
            raw["arrows"][0]["visual_weight"] = "chunky"
            (out / "reference_controls_raw.json").write_text(json.dumps(raw), encoding="utf-8")

            def should_not_run(*_args, **_kwargs):
                raise AssertionError("skip-analysis should not relocalize controls")

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", skip_analysis=True, control_adapter=should_not_run, arrow_style_mode="reference")
            final = json.loads((out / "reference_controls.json").read_text(encoding="utf-8"))
            self.assertEqual(final["controls_source"], "reference_controls_raw.json")
            self.assertEqual(final["arrows"][0]["render_style"], "filled_block_arrow")
            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))
            rendered = {item["arrow_id"]: item for item in report["arrows"]}
            self.assertEqual(rendered["raw_arrow"]["connector_type"], "filled_block_arrow_shape")

    def test_ocr_nearby_text_influences_slot_semantics_and_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "critic_icon", "asset_id": "critic_icon", "bbox_percent": {"x": 0.40, "y": 0.20, "w": 0.18, "h": 0.30}}]}

            def fake_ocr(_path, _lang):
                return [{"text": "AI Critic", "confidence": 0.99, "quad": [[260, 80], [370, 80], [370, 112], [260, 112]]}]

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="ocr", vlm_layout_adapter=fake_layout, ocr_adapter=fake_ocr, text_role_mode="heuristic")
            inventory = json.loads((out / "slot_inventory.json").read_text(encoding="utf-8"))
            slot = inventory["slots"][0]
            self.assertEqual(slot["asset_type"], "character")
            self.assertIn("AI Critic", slot["prompt_subject"])
            specs = json.loads((out / "asset_generation_specs.json").read_text(encoding="utf-8"))
            self.assertEqual(specs["specs"][0]["asset_type"], "character")
            self.assertIn("AI Critic", specs["specs"][0]["prompt"])

    def test_text_relationship_overrides_nearest_ocr_text_for_slot_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "critic_icon", "asset_id": "critic_icon", "bbox_percent": {"x": 0.10, "y": 0.20, "w": 0.18, "h": 0.30}}]}

            def fake_ocr(_path, _lang):
                return [
                    {"text": "Input", "confidence": 0.99, "quad": [[60, 80], [120, 80], [120, 108], [60, 108]]},
                    {"text": "AI Critic", "confidence": 0.99, "quad": [[460, 80], [560, 80], [560, 108], [460, 108]]},
                ]

            def fake_text_intelligence(_path, _program, text_geometry, _text_program, _model):
                text_id = text_geometry["text_regions"][1]["id"]
                return {
                    "summary": "fake relationships",
                    "items": [
                        {
                            "text_id": region["id"],
                            "font_style_guess": {"family_class": "sans_serif", "weight": "regular", "italic": False, "case_style": "title_case", "visual_style": "label"},
                            "layout_intent": {"alignment": "center", "anchor": "top_center", "belongs_to": "canvas", "row_group": "row", "column_group": "col"},
                            "confidence": 0.9,
                        }
                        for region in text_geometry["text_regions"]
                    ],
                    "text_relations": [{
                        "source_text_id": text_id,
                        "target_object_id": "critic_icon",
                        "relation": "label_for_visual_object",
                        "confidence": 0.96,
                    }],
                }

            rebuild_editable(
                reference,
                out,
                asset_mode="placeholder",
                text_mode="ocr",
                vlm_layout_adapter=fake_layout,
                ocr_adapter=fake_ocr,
                text_role_mode="heuristic",
                text_intelligence_mode="vlm",
                text_intelligence_adapter=fake_text_intelligence,
            )
            inventory = json.loads((out / "slot_inventory.json").read_text(encoding="utf-8"))
            slot = inventory["slots"][0]
            self.assertEqual(slot["text_relation_source"], "text_intelligence")
            self.assertEqual(slot["nearby_text"], ["AI Critic"])
            self.assertIn("AI Critic", slot["prompt_subject"])

    def test_economy_policy_is_type_aware_for_thin_tools(self):
        decision = economy_acceptance_decision("thin_tool", 0.62, strict=False)
        self.assertTrue(decision["accepted"])
        strict = economy_acceptance_decision("thin_tool", 0.62, strict=True)
        self.assertFalse(strict["accepted"])

    def test_accepted_existing_assets_avoid_api_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"
            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off")
            first = json.loads((out / "asset_generation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(first["api_requests_attempted"], 0)
            accepted = {item["slot_id"]: {"accepted": True} for item in first["assets"]}
            (out / "accepted_assets.json").write_text(json.dumps(accepted), encoding="utf-8")
            rebuild_editable(reference, out, asset_mode="api", text_mode="off")
            second = json.loads((out / "asset_generation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(second["api_requests_attempted"], 0)

    def test_compile_only_rebuilds_from_existing_contracts_without_assets_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"
            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off")
            report_before = json.loads((out / "asset_generation_report.json").read_text(encoding="utf-8"))
            result = rebuild_editable(reference, out, asset_mode="api", text_mode="off", compile_only=True)
            self.assertTrue(result["compile_only"])
            self.assertEqual(result["controls_source"], "reference_controls_raw.json")
            self.assertEqual(result["raw_controls_path"], "reference_controls_raw.json")
            self.assertTrue(result["routing_applied"])
            report_after = json.loads((out / "asset_generation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report_before["api_requests_attempted"], report_after["api_requests_attempted"])
            self.assertTrue((out / "editable_composition.pptx").exists())

    def test_vlm_validation_report_flags_bad_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            geometry = {
                "layout_mode": "hybrid",
                "vlm_status": "used",
                "panels": [{"id": "panel_a", "bbox_percent": {"x": 0, "y": 0, "w": 1, "h": 1}}],
                "slots": [
                    {"id": "slot_a", "bbox_percent": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}, "bbox_was_clamped": True},
                    {"id": "slot_a", "bbox_percent": {"x": 1.2, "y": 0.1, "w": 0.2, "h": 0.2}},
                ],
                "cards": [],
                "legend_regions": [],
            }
            controls = {"mode": "hybrid", "vlm_status": "used", "arrows": [{"id": "bad_arrow", "source_id": "missing", "target_id": "slot_a", "path_percent": [[0.1, 0.1]]}]}
            semantic = {"semantic_vlm_status": "used", "slots": [{"slot_id": "slot_a", "asset_type": "not_real", "prompt_subject": ""}]}
            report = build_rebuild_vlm_validation_report(out, geometry, controls, semantic, {"asset_mode": "crop", "api_requests_attempted": 0})
            self.assertEqual(report["status"], "warning")
            self.assertIn("slot_a", report["layout"]["duplicate_slot_ids"])
            self.assertIn("slot_a", report["layout"]["clamped_bbox_ids"])
            self.assertIn("bad_arrow", report["control"]["invalid_arrow_ids"])
            self.assertIn("slot_a", report["semantic"]["invalid_asset_type_ids"])

    def test_real_vlm_layout_adapter_uses_shared_client_and_model_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            with patch.dict("os.environ", {"RFS_REBUILD_LAYOUT_MODEL": "layout-model"}, clear=False):
                with patch("rfs.rebuild_vlm_adapters.call_vlm_json") as call:
                    call.return_value = {"confidence": 0.9, "panels": [], "slots": []}
                    result = vlm_layout_adapter(reference, {"slots": []})
            self.assertEqual(result["confidence"], 0.9)
            self.assertEqual(call.call_args.kwargs["model"], "layout-model")
            self.assertEqual(call.call_args.args[1], [reference])

    def test_real_vlm_design_adapter_uses_shared_client_and_model_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            with patch.dict("os.environ", {"RFS_REBUILD_DESIGN_MODEL": "design-model"}, clear=False):
                with patch("rfs.rebuild_vlm_adapters.call_vlm_json") as call:
                    call.return_value = {"summary": "ok", "layers": [], "asset_policies": [], "flow_graph": {}}
                    result = vlm_design_adapter(reference)
            self.assertEqual(result["_vlm_model"], "design-model")
            self.assertEqual(call.call_args.kwargs["model"], "design-model")
            self.assertEqual(call.call_args.args[1], [reference])

    def test_real_vlm_control_adapter_prompt_includes_flow_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            adapter = vlm_control_adapter_factory(root)
            flow_graph = {"edges": [{"id": "flow_prior", "source_id": "slot_a", "target_id": "slot_b"}]}
            with patch.dict("os.environ", {"RFS_REBUILD_CONTROL_MODEL": "control-model"}, clear=False):
                with patch("rfs.rebuild_vlm_adapters.call_vlm_json") as call:
                    call.return_value = {"summary": "ok", "arrows": []}
                    adapter(reference, [{"id": "slot_a"}, {"id": "slot_b"}], [], flow_graph)
            self.assertIn("flow_prior", call.call_args.args[0])
            self.assertEqual(call.call_args.kwargs["model"], "control-model")

    def test_real_vlm_semantic_adapter_output_can_drive_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "slot_robot", "asset_id": "slot_robot", "bbox_percent": {"x": 0.35, "y": 0.20, "w": 0.18, "h": 0.30}}]}

            def fake_semantic(_path, _slots, _panels, _controls, _text_geometry):
                return {"slots": [{"slot_id": "slot_robot", "asset_type": "character", "semantic_role": "robot_agent", "prompt_subject": "friendly robot agent", "nearby_text": ["Agent"]}]}

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", vlm_layout_adapter=fake_layout, semantic_adapter=fake_semantic)
            spec = json.loads((out / "asset_generation_specs.json").read_text(encoding="utf-8"))["specs"][0]
            self.assertEqual(spec["asset_type"], "character")
            self.assertIn("friendly robot agent", spec["prompt"])

    def test_rebuild_asset_specs_use_canvas_aspect_ratio_and_preserve_screenshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "wide.png")
            out = root / "rebuild"
            program = {
                "canvas": {"width_px": 804, "height_px": 277, "background": "#FFFFFF"},
                "slots": [
                    {
                        "id": "slot_video",
                        "asset_id": "slot_video",
                        "asset_type": "screenshot_card",
                        "semantic_role": "video_thumbnail",
                        "bbox_percent": {"x": 0.037, "y": 0.072, "w": 0.141, "h": 0.235},
                        "prompt_subject": "video thumbnail",
                    },
                    {
                        "id": "slot_icon",
                        "asset_id": "slot_icon",
                        "asset_type": "tool_icon",
                        "semantic_role": "llm_icon",
                        "bbox_percent": {"x": 0.25, "y": 0.56, "w": 0.025, "h": 0.072},
                        "prompt_subject": "ChatGPT icon",
                    },
                    {
                        "id": "slot_graph",
                        "asset_id": "slot_graph",
                        "asset_type": "generic",
                        "semantic_role": "sub_knowledge_graph",
                        "bbox_percent": {"x": 0.296, "y": 0.534, "w": 0.159, "h": 0.217},
                        "prompt_subject": "sub-knowledge graph",
                    },
                ],
            }

            specs = {item["slot_id"]: item for item in _make_asset_specs(program, reference, out)}
            spec = specs["slot_video"]

            self.assertGreater(spec["slot_aspect_ratio"], 1.5)
            self.assertEqual(spec["generation_aspect_ratio"], "16:9")
            self.assertEqual(spec["asset_source_policy"], "reference_crop")
            self.assertTrue(spec["preserve_reference_crop"])
            self.assertEqual(specs["slot_icon"]["asset_source_policy"], "reference_crop")
            self.assertEqual(specs["slot_graph"]["asset_source_policy"], "reference_crop")

    def test_generation_policy_skips_non_raster_asset_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"
            program = {
                "canvas": {"width_px": 640, "height_px": 360, "background": "#FFFFFF"},
                "slots": [
                    {"id": "slot_visual", "asset_id": "slot_visual", "bbox_percent": {"x": 0.10, "y": 0.20, "w": 0.20, "h": 0.20}},
                    {"id": "slot_text", "asset_id": "slot_text", "bbox_percent": {"x": 0.40, "y": 0.20, "w": 0.20, "h": 0.10}},
                ],
            }
            generation_plan = {
                "asset_policies": [
                    {"slot_id": "slot_visual", "policy": "api_generate", "reason": "illustrative visual"},
                    {"slot_id": "slot_text", "policy": "editable_text", "reason": "text stays editable"},
                ]
            }

            specs = _make_asset_specs(program, reference, out, generation_plan=generation_plan)
            self.assertEqual([item["slot_id"] for item in specs], ["slot_visual"])
            self.assertTrue(program["slots"][1]["skip_raster_asset"])
            self.assertEqual(program["slots"][1]["asset_source_policy"], "editable_text")

    def test_global_generation_policy_preserves_reference_crop_without_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "slot_ui", "asset_id": "slot_ui", "bbox_percent": {"x": 0.05, "y": 0.10, "w": 0.25, "h": 0.22}}]}

            def fake_design(_path, _model):
                return {
                    "layers": [{"id": "slot_ui", "kind": "visual_slot", "bbox_percent": {"x": 0.05, "y": 0.10, "w": 0.25, "h": 0.22}, "asset_source_policy": "reference_crop"}],
                    "asset_policies": [{"slot_id": "slot_ui", "policy": "reference_crop", "reason": "UI evidence crop"}],
                    "flow_graph": {},
                }

            with patch("rfs.editable_rebuild._api_generate_asset") as api_call:
                rebuild_editable(reference, out, asset_mode="api", text_mode="off", vlm_layout_adapter=fake_layout, design_adapter=fake_design)

            api_call.assert_not_called()
            specs = json.loads((out / "asset_generation_specs.json").read_text(encoding="utf-8"))["specs"]
            self.assertEqual(specs[0]["asset_source_policy"], "reference_crop")
            self.assertEqual(specs[0]["policy_source"], "design_plan")

    def test_api_mode_preserves_screenshot_crop_without_image_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "slot_video", "asset_id": "slot_video", "bbox_percent": {"x": 0.05, "y": 0.10, "w": 0.25, "h": 0.22}}]}

            def fake_semantic(_path, _slots, _panels, _controls, _text_geometry):
                return {"slots": [{"slot_id": "slot_video", "asset_type": "screenshot_card", "semantic_role": "video_thumbnail", "prompt_subject": "video thumbnail"}]}

            with patch("rfs.editable_rebuild._api_generate_asset") as api_call:
                rebuild_editable(reference, out, asset_mode="api", text_mode="off", vlm_layout_adapter=fake_layout, semantic_adapter=fake_semantic)

            api_call.assert_not_called()
            report = json.loads((out / "asset_generation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["api_requests_attempted"], 0)
            self.assertEqual(report["assets"][0]["status"], "reference_crop_preserved")

    def test_real_vlm_text_intelligence_adapter_uses_text_model_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            text_geometry = {"text_regions": [{"id": "t1", "text": "Title", "bbox_percent": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05}}]}
            text_program = {"items": [{"id": "text_t1", "source_reference_text_id": "t1", "text": "Title"}]}
            program = {"panels": [], "slots": [], "arrows": []}
            with patch.dict("os.environ", {"RFS_REBUILD_TEXT_MODEL": "text-model"}, clear=False):
                with patch("rfs.rebuild_vlm_adapters.call_vlm_json") as call:
                    call.return_value = {"summary": "ok", "items": [], "text_relations": []}
                    result = vlm_text_intelligence_adapter(reference, program, text_geometry, text_program)
            self.assertEqual(result["_vlm_model"], "text-model")
            self.assertEqual(call.call_args.kwargs["model"], "text-model")

    def test_invalid_semantic_asset_type_falls_back_to_generic_and_reports_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [{"id": "slot_unknown", "asset_id": "slot_unknown", "bbox_percent": {"x": 0.35, "y": 0.20, "w": 0.18, "h": 0.30}}]}

            def fake_semantic(_path, _slots, _panels, _controls, _text_geometry):
                return {"slots": [{"slot_id": "slot_unknown", "asset_type": "nonsense_type", "prompt_subject": "unknown object"}]}

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", vlm_layout_adapter=fake_layout, semantic_adapter=fake_semantic)
            inventory = json.loads((out / "slot_inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(inventory["slots"][0]["asset_type"], "generic")
            semantic = json.loads((out / "slot_semantic_report.json").read_text(encoding="utf-8"))
            self.assertEqual(semantic["invalid_asset_type_count"], 1)

    def test_invalid_vlm_control_arrow_is_dropped_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            out = root / "rebuild"

            def fake_layout(_path, _base):
                return {"slots": [
                    {"id": "slot_a", "asset_id": "slot_a", "bbox_percent": {"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.2}},
                    {"id": "slot_b", "asset_id": "slot_b", "bbox_percent": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.2}},
                ]}

            def fake_controls(_path, _slots, _heuristic):
                return {"arrows": [
                    {"id": "invalid", "source_id": "missing", "target_id": "slot_b", "path_percent": [[0.1, 0.1], [0.2, 0.2]]},
                    {"id": "valid", "source_id": "slot_a", "target_id": "slot_b", "path_percent": [[0.3, 0.3], [0.6, 0.3]]},
                ]}

            rebuild_editable(reference, out, asset_mode="placeholder", text_mode="off", vlm_layout_adapter=fake_layout, control_adapter=fake_controls)
            controls = json.loads((out / "reference_controls.json").read_text(encoding="utf-8"))
            self.assertEqual([arrow["id"] for arrow in controls["arrows"]], ["valid"])
            self.assertTrue(any("invalid_vlm_control" in warning for warning in controls["warnings"]))

    def test_rebuild_editable_eval_runs_crop_without_image_api_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = _fixture(root / "pipeline.png")
            with patch.dict("os.environ", {"API_BASE": "", "API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
                summary = evaluate_rebuild_vlm(reference, root / "eval", asset_mode="crop", text_mode="off", export_preview=False)
            self.assertTrue(summary["ok"])
            self.assertFalse(summary["image_generation_api_expected"])
            self.assertEqual(summary["cases"]["heuristic"]["api_requests_attempted"], 0)
            self.assertEqual(summary["cases"]["vlm"]["api_requests_attempted"], 0)
            self.assertTrue((root / "eval" / "rebuild_vlm_eval_summary.json").exists())

    def test_rebuild_vlm_adapter_factory_requires_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"API_BASE": "", "API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
                adapters = build_rebuild_vlm_adapters(tmp)
            self.assertIsNone(adapters["design"])
            self.assertIsNone(adapters["layout"])
            self.assertIsNone(adapters["text_intelligence"])
            with patch.dict("os.environ", {"API_BASE": "https://example.test/v1", "API_KEY": "key"}, clear=False):
                adapters = build_rebuild_vlm_adapters(tmp)
            self.assertIsNotNone(adapters["layout"])
            self.assertIsNotNone(adapters["control"])
            self.assertIsNotNone(adapters["semantic"])
            self.assertIsNotNone(adapters["text_intelligence"])


if __name__ == "__main__":
    unittest.main()
