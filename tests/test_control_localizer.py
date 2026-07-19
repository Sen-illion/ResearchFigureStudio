import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rfs.control_localizer import localize_reference_controls


class ControlLocalizerTests(unittest.TestCase):
    def test_hybrid_control_binding_accepts_reference_cards_as_arrow_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference.png"
            Image.new("RGB", (400, 240), "#FFFFFF").save(reference)
            out = root / "out"
            out.mkdir()
            (out / "reference_geometry.json").write_text(json.dumps({
                "summary": "geometry",
                "cards": [{
                    "id": "card_raw_image",
                    "title": "Raw Image",
                    "bbox_percent": {"x": 0.55, "y": 0.20, "w": 0.22, "h": 0.18},
                }],
            }), encoding="utf-8")
            slots = [{
                "id": "slot_synthesis",
                "bbox_percent": {"x": 0.20, "y": 0.20, "w": 0.18, "h": 0.18},
            }]

            def fake_control_adapter(_reference, bindable, _heuristic):
                self.assertIn("card_raw_image", {item["id"] for item in bindable})
                return {"arrows": [{
                    "id": "synthesis_to_raw",
                    "source_id": "slot_synthesis",
                    "target_id": "card_raw_image",
                    "render_style": "filled_block_arrow",
                    "route_intent": "straight",
                    "path_percent": [[0.38, 0.29], [0.55, 0.29]],
                    "confidence": 0.95,
                }]}

            result = localize_reference_controls(
                reference,
                slots,
                ["#FFFFFF", "#4A90C2", "#79A66D"],
                out,
                mode="hybrid",
                control_adapter=fake_control_adapter,
            )

            self.assertEqual(result["vlm_status"], "used")
            self.assertEqual(result["bindable_object_count"], 2)
            self.assertEqual(result["vlm_arrow_count"], 1)
            self.assertEqual(result["merged_arrow_count"], 1)
            self.assertEqual(result["arrows"][0]["target_id"], "card_raw_image")
            self.assertEqual(result["arrows"][0]["path_percent"], [[0.38, 0.29], [0.55, 0.29]])


if __name__ == "__main__":
    unittest.main()
