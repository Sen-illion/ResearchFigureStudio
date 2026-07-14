import json
import tempfile
import unittest
from pathlib import Path

from rfs.arrow_router import AESTHETIC_ROUTER_VERSION, _segment_bbox_overlap, _segments, style_and_route_arrows


class ArrowRouterTests(unittest.TestCase):
    def test_reference_paths_are_preserved_and_styled(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "summary": "Figure program.",
                "canvas": {"width_in": 10, "height_in": 5},
                "style": {"color_tokens": [{"token_id": "arrow_001", "hex": "#111111"}]},
                "panels": [],
                "slots": [
                    {"id": "a", "bbox_percent": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}},
                    {"id": "b", "bbox_percent": {"x": 0.4, "y": 0.1, "w": 0.1, "h": 0.1}},
                    {"id": "c", "bbox_percent": {"x": 0.4, "y": 0.3, "w": 0.1, "h": 0.1}},
                ],
                "arrows": [
                    {
                        "id": "flow_a",
                        "source_id": "a",
                        "target_id": "b",
                        "path_percent": [[0.2, 0.15], [0.4, 0.15]],
                        "style_token_id": "arrow_001",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                        "binding_source": "reference_control_candidates",
                    },
                    {
                        "id": "flow_b",
                        "source_id": "a",
                        "target_id": "c",
                        "path_percent": [[0.2, 0.15], [0.3, 0.15], [0.3, 0.35], [0.4, 0.35]],
                        "style_token_id": "arrow_001",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                        "binding_source": "reference_control_candidates",
                    },
                ],
            }

            result = style_and_route_arrows(program, out, mode="reference")
            by_id = {item["id"]: item for item in result["arrows"]}

            self.assertEqual(by_id["flow_a"]["path_percent"], [[0.2, 0.15], [0.4, 0.15]])
            self.assertTrue(by_id["flow_a"]["reference_locked"])
            self.assertTrue(by_id["flow_a"]["reference_path_preserved"])
            self.assertEqual(by_id["flow_a"]["semantic_role"], "branch")
            self.assertEqual(by_id["flow_a"]["route_style"], "bundled_elbow")
            self.assertEqual(result["style"]["arrow_style_profile_path"], "arrow_style_profile.json")

            quality = json.loads((out / "arrow_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["summary"], "Arrow routing and styling quality report.")
            self.assertEqual(quality["arrow_count"], 2)
            self.assertFalse(quality["reference_path_overrides"])

    def test_fallback_route_avoids_slot_obstacle_without_changing_reference_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "summary": "Figure program.",
                "canvas": {"width_in": 10, "height_in": 5},
                "style": {"color_tokens": [{"token_id": "arrow_001", "hex": "#111111"}]},
                "panels": [],
                "slots": [
                    {"id": "source", "bbox_percent": {"x": 0.10, "y": 0.42, "w": 0.10, "h": 0.12}},
                    {"id": "target", "bbox_percent": {"x": 0.78, "y": 0.42, "w": 0.10, "h": 0.12}},
                    {"id": "obstacle", "bbox_percent": {"x": 0.42, "y": 0.38, "w": 0.14, "h": 0.20}},
                    {"id": "locked_a", "bbox_percent": {"x": 0.10, "y": 0.12, "w": 0.10, "h": 0.10}},
                    {"id": "locked_b", "bbox_percent": {"x": 0.78, "y": 0.12, "w": 0.10, "h": 0.10}},
                ],
                "arrows": [
                    {
                        "id": "locked_flow",
                        "source_id": "locked_a",
                        "target_id": "locked_b",
                        "path_percent": [[0.20, 0.17], [0.78, 0.17]],
                        "style_token_id": "arrow_001",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                        "binding_source": "reference_control_candidates",
                    },
                    {
                        "id": "fallback_flow",
                        "source_id": "source",
                        "target_id": "target",
                        "path_percent": [],
                        "style_token_id": "arrow_001",
                        "editable_in": "pptx",
                        "render_policy": "ppt_shape_not_image_asset",
                        "route_policy": "fallback_reroute_allowed",
                    },
                ],
            }

            result = style_and_route_arrows(program, out, mode="reference")
            by_id = {item["id"]: item for item in result["arrows"]}

            self.assertEqual(by_id["locked_flow"]["path_percent"], [[0.2, 0.17], [0.78, 0.17]])
            self.assertTrue(by_id["locked_flow"]["reference_locked"])
            self.assertTrue(by_id["locked_flow"]["reference_path_preserved"])

            fallback = by_id["fallback_flow"]
            self.assertFalse(fallback["reference_locked"])
            self.assertEqual(fallback["route_generation_status"], "fallback_route_selected")
            self.assertEqual(fallback["routing_algorithm"], "reference-constrained-orthogonal-v1")
            self.assertGreaterEqual(len(fallback["path_percent"]), 3)
            obstacle_box = by_id.get("obstacle", {}).get("bbox_percent") or {"x": 0.42, "y": 0.38, "w": 0.14, "h": 0.20}
            self.assertFalse(any(_segment_bbox_overlap(a, b, obstacle_box) for a, b in _segments(fallback["path_percent"])))

            routes = json.loads((out / "selected_arrow_routes.json").read_text(encoding="utf-8"))["routes"]
            route_by_id = {item["id"]: item for item in routes}
            self.assertEqual(route_by_id["fallback_flow"]["route_generation_status"], "fallback_route_selected")
            self.assertGreater(route_by_id["fallback_flow"]["candidate_count"], 1)

    def test_aesthetic_mode_uses_reference_tunnel_for_bundle_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            arrows = []
            for index, y in enumerate([0.18, 0.30, 0.42], start=1):
                arrows.append({
                    "id": f"branch_{index}",
                    "source_id": "source",
                    "target_id": f"target_{index}",
                    "path_percent": [[0.20, 0.30], [0.70, y]],
                    "style_token_id": "arrow_001",
                    "editable_in": "pptx",
                    "render_policy": "ppt_shape_not_image_asset",
                    "binding_source": "reference_control_candidates",
                    "aesthetic_offset_allowed": True,
                })
            program = {
                "summary": "Figure program.",
                "canvas": {"width_in": 10, "height_in": 5},
                "style": {"color_tokens": [{"token_id": "arrow_001", "hex": "#111111"}]},
                "panels": [],
                "slots": [
                    {"id": "source", "bbox_percent": {"x": 0.10, "y": 0.25, "w": 0.10, "h": 0.10}},
                    {"id": "target_1", "bbox_percent": {"x": 0.70, "y": 0.13, "w": 0.10, "h": 0.10}},
                    {"id": "target_2", "bbox_percent": {"x": 0.70, "y": 0.25, "w": 0.10, "h": 0.10}},
                    {"id": "target_3", "bbox_percent": {"x": 0.70, "y": 0.37, "w": 0.10, "h": 0.10}},
                ],
                "arrows": arrows,
            }

            result = style_and_route_arrows(program, out, mode="aesthetic")
            by_id = {item["id"]: item for item in result["arrows"]}
            adjusted = 0
            for arrow_id, arrow in by_id.items():
                self.assertEqual(arrow["semantic_role"], "branch")
                self.assertEqual(arrow["route_style"], "metro_bundle")
                self.assertEqual(arrow["routing_algorithm"], AESTHETIC_ROUTER_VERSION)
                self.assertIn(arrow["route_generation_status"], {"aesthetic_tunnel_adjusted", "aesthetic_style_only"})
                self.assertTrue(arrow["reference_tunnel_preserved"], arrow_id)
                self.assertLessEqual(arrow["reference_path_delta_max"], arrow["reference_tunnel_percent"])
                self.assertTrue(arrow["reference_path_preserved"])
                self.assertTrue(arrow["reference_original_path_percent"])
                self.assertGreater(float(arrow["halo_width_pt"]), 0)
                if arrow["route_generation_status"] == "aesthetic_tunnel_adjusted":
                    adjusted += 1
            self.assertGreaterEqual(adjusted, 2)

            quality = json.loads((out / "arrow_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["mode"], "aesthetic")
            self.assertEqual(quality["reference_tunnel_violations"], [])
            self.assertGreaterEqual(quality["aesthetic_tunnel_adjusted_count"], 2)


if __name__ == "__main__":
    unittest.main()
