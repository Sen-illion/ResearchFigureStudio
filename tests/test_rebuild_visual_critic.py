import tempfile
import unittest
from pathlib import Path

from rfs.rebuild_visual_critic import apply_rebuild_corrections, run_rebuild_visual_quality_check


class RebuildVisualCriticTests(unittest.TestCase):
    def test_deterministic_report_flags_text_overlap_bounds_and_missing_arrow_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "text_program": {
                    "items": [
                        {
                            "id": "text_a",
                            "source_reference_text_id": "ref_a",
                            "text": "A",
                            "bbox_percent": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.05},
                        },
                        {
                            "id": "text_b",
                            "source_reference_text_id": "ref_b",
                            "text": "B",
                            "bbox_percent": {"x": 0.12, "y": 0.11, "w": 0.20, "h": 0.05},
                        },
                        {
                            "id": "text_bad",
                            "source_reference_text_id": "ref_bad",
                            "text": "bad",
                            "bbox_percent": {"x": 0.98, "y": 0.10, "w": 0.10, "h": 0.05},
                        },
                    ]
                },
                "panels": [],
                "slots": [],
                "arrows": [{"id": "arrow_missing", "source_id": "a", "target_id": "b"}],
            }

            report = run_rebuild_visual_quality_check(out, program)

            self.assertEqual(report["status"], "blocked")
            issue_types = {item["type"] for item in report["issues"]}
            self.assertIn("text_overlap", issue_types)
            self.assertIn("text_bbox_out_of_bounds", issue_types)
            self.assertIn("arrow_missing_path", issue_types)
            self.assertTrue((out / "rebuild_visual_quality_report.json").exists())

    def test_ownership_conflict_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "text_program": {
                    "items": [{
                        "id": "text_a",
                        "source_reference_text_id": "ref_a",
                        "text": "A",
                        "bbox_percent": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.05},
                    }]
                },
                "panels": [],
                "slots": [],
                "arrows": [],
            }
            ownership = {
                "items": [{
                    "text_id": "ref_a",
                    "layer_ownership": "raster_asset_layer",
                    "included_in_text_program": False,
                }]
            }

            report = run_rebuild_visual_quality_check(out, program, ownership_report=ownership)

            self.assertEqual(report["ownership_issue_count"], 1)
            self.assertEqual(report["issues"][0]["type"], "text_layer_ownership_conflict")

    def test_same_target_role_without_group_id_is_not_forced_aligned(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "text_program": {
                    "items": [
                        {
                            "id": "text_a",
                            "target_id": "panel_a",
                            "role": "body_label",
                            "bbox_percent": {"x": 0.10, "y": 0.10, "w": 0.10, "h": 0.03},
                        },
                        {
                            "id": "text_b",
                            "target_id": "panel_a",
                            "role": "body_label",
                            "bbox_percent": {"x": 0.30, "y": 0.40, "w": 0.10, "h": 0.03},
                        },
                        {
                            "id": "text_c",
                            "target_id": "panel_a",
                            "role": "body_label",
                            "bbox_percent": {"x": 0.50, "y": 0.70, "w": 0.10, "h": 0.03},
                        },
                    ]
                },
                "panels": [],
                "slots": [],
                "arrows": [],
            }

            report = run_rebuild_visual_quality_check(out, program)

            self.assertEqual(report["status"], "pass")
            self.assertNotIn("text_group_misaligned", {item["type"] for item in report["issues"]})

    def test_apply_concrete_text_patch_with_limits_and_z_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "text_program": {
                    "items": [{
                        "id": "text_a",
                        "source_reference_text_id": "ref_a",
                        "text": "Score Comparison",
                        "bbox_percent": {"x": 0.50, "y": 0.50, "w": 0.10, "h": 0.04},
                        "center_percent": {"x": 0.55, "y": 0.52},
                        "width_percent": 0.10,
                        "height_percent": 0.04,
                        "font_size_pt": 10.0,
                        "align": "center",
                        "visible": True,
                    }]
                },
                "panels": [],
                "slots": [],
                "arrows": [],
            }
            critic = {
                "patches": [
                    {
                        "op": "update_text",
                        "text_id": "text_a",
                        "bbox_percent": {"x": 0.90, "y": 0.90, "w": 0.30, "h": 0.20},
                        "font_size_pt": 30,
                        "align": "left",
                        "z_index": 8,
                        "reason": "explicit drawing instruction",
                    },
                    {"op": "update_text", "text_id": "text_a", "reason": "optimize it"},
                ]
            }

            updated, report = apply_rebuild_corrections(out, program, critic, iteration=0)
            item = updated["text_program"]["items"][0]

            self.assertEqual(report["applied_count"], 1)
            self.assertEqual(report["rejected_count"], 1)
            self.assertEqual(item["font_size_pt"], 12.0)
            self.assertEqual(item["align"], "left")
            self.assertEqual(item["z_index"], 8)
            self.assertLessEqual(abs(item["center_percent"]["x"] - 0.55), 0.031)
            self.assertTrue((out / "rebuild_corrections_iter_0.json").exists())

    def test_apply_slot_and_arrow_patch_reports_changed_assets_and_arrows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "text_program": {"items": []},
                "panels": [],
                "slots": [{"id": "slot_a", "bbox_percent": {"x": 0.10, "y": 0.10, "w": 0.20, "h": 0.20}}],
                "arrows": [{"id": "arrow_a", "path_percent": [[0.1, 0.1], [0.2, 0.2]]}],
            }
            critic = {
                "patches": [
                    {"op": "update_slot", "slot_id": "slot_a", "bbox_percent": {"x": 0.20, "y": 0.20, "w": 0.22, "h": 0.22}},
                    {"op": "update_arrow", "arrow_id": "arrow_a", "path_percent": [[0.2, 0.2], [0.4, 0.2]], "render_style": "line_connector"},
                ]
            }

            updated, report = apply_rebuild_corrections(out, program, critic, iteration=1)

            self.assertEqual(report["changed_slot_ids"], ["slot_a"])
            self.assertTrue(report["changed_arrows"])
            self.assertEqual(updated["arrows"][0]["render_style"], "line_connector")
            self.assertEqual(updated["arrows"][0]["path_percent"], [[0.2, 0.2], [0.4, 0.2]])


if __name__ == "__main__":
    unittest.main()
