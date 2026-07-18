import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from rfs.ppt_compiler import compile_ppt


class PptTextboxWidthTests(unittest.TestCase):
    def test_text_program_textbox_width_is_scaled_by_one_point_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            program = {
                "canvas": {"width_in": 10.0, "height_in": 5.0, "background": "#FFFFFF"},
                "panels": [],
                "slots": [],
                "assets": [],
                "labels": [],
                "arrows": [],
                "groups": [],
                "export_targets": [{"type": "pptx", "path": "editable_composition.pptx"}],
                "text_program": {
                    "items": [{
                        "id": "text_a",
                        "text": "Scaled text",
                        "role": "free_text",
                        "target_id": "canvas",
                        "source_reference_text_id": "ref_text_a",
                        "reference_binding": "reference_ocr_text_region",
                        "bbox_percent": {"x": 0.30, "y": 0.20, "w": 0.20, "h": 0.10},
                        "font_size_pt": 12,
                        "color_hex": "#263747",
                        "font_family_guess": "Arial",
                        "fit_strategy": "ocr_bbox_exact",
                        "editable_in": "pptx",
                    }],
                },
            }

            pptx = compile_ppt(program, out)
            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))

            self.assertEqual(report["text"][0]["bbox_percent"]["w"], 0.20)
            self.assertEqual(report["text"][0]["rendered_bbox_percent"]["w"], 0.30)
            self.assertEqual(report["text"][0]["rendered_bbox_percent"]["x"], 0.25)
            self.assertEqual(report["text"][0]["textbox_width_scale"], 1.5)

            with zipfile.ZipFile(pptx) as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertIn("Scaled text", slide_xml)


if __name__ == "__main__":
    unittest.main()
