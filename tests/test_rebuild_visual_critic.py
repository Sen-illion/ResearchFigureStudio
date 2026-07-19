import tempfile
import unittest
from pathlib import Path

from rfs.rebuild_visual_critic import run_rebuild_visual_quality_check


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


if __name__ == "__main__":
    unittest.main()
