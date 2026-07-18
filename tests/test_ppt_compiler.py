import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from rfs.ppt_compiler import compile_ppt


class PptCompilerArrowTests(unittest.TestCase):
    def test_multisegment_and_dashed_arrows_are_rendered_as_ppt_connectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "canvas": {"width_in": 10.0, "height_in": 5.0, "background": "#FFFFFF"},
                "style": {
                    "palette": ["#FFFFFF", "#E17721", "#6B57C8", "#1B9A94"],
                    "reference_palette": ["#FFFFFF", "#E17721", "#6B57C8", "#1B9A94"],
                    "color_tokens": [{
                        "token_id": "arrow_orange_001",
                        "hex": "#E17721",
                        "usage": "arrow_or_connector_stroke",
                    }],
                    "arrow_weight_pt": 2.25,
                },
                "panels": [{
                    "id": "panel_a",
                    "title": "Panel A",
                    "bbox_percent": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.80},
                    "editable_in": "pptx",
                }],
                "slots": [
                    {
                        "id": "slot_a",
                        "asset_id": "asset_a",
                        "paper_concept": "A",
                        "bbox_percent": {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.10},
                        "composition_type": "full_frame_icon",
                    },
                    {
                        "id": "slot_b",
                        "asset_id": "asset_b",
                        "paper_concept": "B",
                        "bbox_percent": {"x": 0.70, "y": 0.55, "w": 0.10, "h": 0.10},
                        "composition_type": "full_frame_icon",
                    },
                ],
                "arrows": [
                    {
                        "id": "multi_a",
                        "source": "slot_a",
                        "target": "slot_b",
                        "source_id": "slot_a",
                        "target_id": "slot_b",
                        "source_anchor": "right_mid",
                        "target_anchor": "left_mid",
                        "control_kind": "elbow_connector",
                        "path_percent": [[0.20, 0.25], [0.45, 0.25], [0.45, 0.60], [0.70, 0.60]],
                        "style_token_id": "arrow_orange_001",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                    },
                    {
                        "id": "loop_a",
                        "source": "slot_a",
                        "target": "slot_b",
                        "source_id": "slot_a",
                        "target_id": "slot_b",
                        "source_anchor": "top_mid",
                        "target_anchor": "bottom_mid",
                        "control_kind": "dashed_loop",
                        "path_percent": [[0.30, 0.30], [0.40, 0.20], [0.50, 0.30], [0.40, 0.40], [0.30, 0.30]],
                        "style_token_id": "arrow_orange_001",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                    },
                ],
                "labels": [],
                "groups": [],
                "export_targets": [{"type": "pptx", "path": "editable_composition.pptx"}],
            }

            pptx = compile_ppt(program, out)
            self.assertTrue(pptx.exists())

            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))
            by_id = {item["arrow_id"]: item for item in report["arrows"]}
            self.assertEqual(by_id["multi_a"]["segment_count"], 3)
            self.assertEqual(by_id["loop_a"]["segment_count"], 4)

            with zipfile.ZipFile(pptx) as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertGreaterEqual(slide_xml.count("<p:cxnSp>"), 7)
            self.assertGreaterEqual(slide_xml.count("tailEnd"), 2)
            self.assertIn("prstDash", slide_xml)

    def test_block_and_branch_arrow_render_styles_are_editable_ppt_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "canvas": {"width_in": 10.0, "height_in": 5.0, "background": "#FFFFFF"},
                "style": {
                    "palette": ["#FFFFFF", "#AFC6DE", "#111827"],
                    "reference_palette": ["#FFFFFF", "#AFC6DE", "#111827"],
                    "color_tokens": [{
                        "token_id": "arrow_dark_001",
                        "hex": "#111827",
                        "usage": "arrow_or_connector_stroke",
                    }],
                    "arrow_weight_pt": 2.25,
                },
                "panels": [],
                "slots": [
                    {"id": "slot_a", "asset_id": "asset_a", "paper_concept": "A", "bbox_percent": {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.10}},
                    {"id": "slot_b", "asset_id": "asset_b", "paper_concept": "B", "bbox_percent": {"x": 0.40, "y": 0.20, "w": 0.10, "h": 0.10}},
                    {"id": "slot_c", "asset_id": "asset_c", "paper_concept": "C", "bbox_percent": {"x": 0.70, "y": 0.12, "w": 0.10, "h": 0.10}},
                    {"id": "slot_d", "asset_id": "asset_d", "paper_concept": "D", "bbox_percent": {"x": 0.70, "y": 0.48, "w": 0.10, "h": 0.10}},
                ],
                "arrows": [
                    {
                        "id": "block_a",
                        "source": "slot_a",
                        "target": "slot_b",
                        "source_id": "slot_a",
                        "target_id": "slot_b",
                        "control_kind": "transition_arrow",
                        "render_style": "filled_block_arrow",
                        "path_percent": [[0.20, 0.25], [0.40, 0.25]],
                        "style_token_id": "arrow_dark_001",
                        "fill_color": "#AFC6DE",
                        "outline_color": "#3F5063",
                        "outline_width_pt": 1.5,
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                    },
                    {
                        "id": "branch_a",
                        "source": "slot_b",
                        "target": "slot_c",
                        "source_id": "slot_b",
                        "target_id": "slot_c",
                        "control_kind": "branch_connector",
                        "render_style": "branch_line_connector",
                        "path_percent": [[0.50, 0.25], [0.58, 0.25], [0.70, 0.17]],
                        "trunk_path_percent": [[0.50, 0.25], [0.58, 0.25]],
                        "branches": [
                            {"target_id": "slot_c", "path_percent": [[0.58, 0.25], [0.70, 0.17]]},
                            {"target_id": "slot_d", "path_percent": [[0.58, 0.25], [0.58, 0.53], [0.70, 0.53]]},
                        ],
                        "style_token_id": "arrow_dark_001",
                        "stroke_width_pt": 2.4,
                        "arrowhead_size": "med",
                        "line_cap": "round",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                    },
                ],
                "labels": [],
                "groups": [],
                "export_targets": [{"type": "pptx", "path": "editable_composition.pptx"}],
            }

            pptx = compile_ppt(program, out)
            self.assertTrue(pptx.exists())

            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))
            by_id = {item["arrow_id"]: item for item in report["arrows"]}
            self.assertEqual(by_id["block_a"]["render_style"], "filled_block_arrow")
            self.assertEqual(by_id["block_a"]["connector_type"], "filled_block_arrow_shape")
            self.assertEqual(by_id["branch_a"]["render_style"], "branch_line_connector")
            self.assertEqual(by_id["branch_a"]["branch_count"], 2)
            self.assertEqual(by_id["branch_a"]["segment_count"], 4)

            with zipfile.ZipFile(pptx) as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertIn('prst="rightArrow"', slide_xml)
            self.assertGreaterEqual(slide_xml.count("<p:cxnSp>"), 4)
            self.assertEqual(slide_xml.count("tailEnd"), 2)


if __name__ == "__main__":
    unittest.main()
