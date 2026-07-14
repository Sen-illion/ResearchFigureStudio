import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from rfs.ppt_compiler import compile_ppt
from rfs.text_layer import build_text_layer


def _base_program() -> dict:
    return {
        "canvas": {"width_in": 10.0, "height_in": 5.0, "background": "#FFFFFF"},
        "style": {
            "palette": ["#FFFFFF", "#E17721", "#6B57C8", "#1B9A94"],
            "reference_palette": ["#FFFFFF", "#E17721", "#6B57C8", "#1B9A94"],
            "color_tokens": [{"token_id": "panel_header", "hex": "#336699", "usage": "header_fill"}],
        },
        "panels": [{
            "id": "panel_a",
            "title": "Fallback Panel",
            "bbox_percent": {"x": 0.05, "y": 0.05, "w": 0.90, "h": 0.80},
            "editable_in": "pptx",
        }],
        "slots": [],
        "assets": [],
        "labels": [],
        "arrows": [],
        "groups": [],
        "export_targets": [{"type": "pptx", "path": "editable_composition.pptx"}],
    }


def _style() -> dict:
    return {
        "color_tokens": [{"token_id": "panel_header", "hex": "#336699", "usage": "header_fill"}],
    }


class TextLayerOcrTests(unittest.TestCase):
    def test_fake_ocr_creates_reference_text_geometry_without_duplicate_panel_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reference = out / "reference.png"
            Image.new("RGB", (400, 200), "white").save(reference)

            def fake_ocr(_path, _lang):
                return [{
                    "text": "Detected Title",
                    "confidence": 0.97,
                    "quad": [[30, 18], [180, 18], [180, 42], [30, 42]],
                }]

            program = build_text_layer(reference, _base_program(), _style(), out, text_extractor_mode="ocr", ocr_adapter=fake_ocr)

            geometry = json.loads((out / "reference_text_geometry.json").read_text(encoding="utf-8"))
            self.assertEqual(geometry["detection_mode"], "ocr")
            self.assertEqual(len(geometry["text_regions"]), 1)
            self.assertEqual(geometry["text_regions"][0]["raw_text"], "Detected Title")
            self.assertEqual(geometry["text_regions"][0]["confidence"], 0.97)

            text_program = json.loads((out / "text_program.json").read_text(encoding="utf-8"))
            self.assertEqual(len(text_program["items"]), 1)
            self.assertEqual(text_program["items"][0]["text"], "Detected Title")
            self.assertEqual(text_program["items"][0]["fit_strategy"], "ocr_bbox_exact")
            self.assertEqual(program["text_program"]["items"][0]["font_family_guess"], "Arial")

    def test_ocr_unavailable_falls_back_to_heuristic_text_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reference = out / "reference.png"
            Image.new("RGB", (400, 200), "white").save(reference)

            def failing_ocr(_path, _lang):
                raise RuntimeError("missing engine")

            build_text_layer(reference, _base_program(), _style(), out, text_extractor_mode="ocr", ocr_adapter=failing_ocr)

            geometry = json.loads((out / "reference_text_geometry.json").read_text(encoding="utf-8"))
            report = json.loads((out / "ocr_text_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(geometry["detection_mode"], "reference_geometry_and_local_color_sampling")
            self.assertEqual(report["status"], "fallback")
            self.assertIn("missing engine", report["fallback_reason"])
            self.assertTrue(geometry["text_regions"])

    def test_ppt_compiler_renders_ocr_text_with_font_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reference = out / "reference.png"
            Image.new("RGB", (400, 200), "white").save(reference)

            def fake_ocr(_path, _lang):
                return [{
                    "text": "Editable OCR",
                    "confidence": 0.91,
                    "quad": [[30, 18], [190, 18], [190, 42], [30, 42]],
                }]

            program = build_text_layer(reference, _base_program(), _style(), out, text_extractor_mode="ocr", ocr_adapter=fake_ocr)
            pptx = compile_ppt(program, out)

            report = json.loads((out / "composition_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["text"][0]["fit_strategy"], "ocr_bbox_exact")
            self.assertEqual(report["text"][0]["ocr_confidence"], 0.91)

            with zipfile.ZipFile(pptx) as archive:
                slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertIn("Editable OCR", slide_xml)
            self.assertIn("Arial", slide_xml)


if __name__ == "__main__":
    unittest.main()
