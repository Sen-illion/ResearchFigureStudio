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
            self.assertEqual(text_program["items"][0]["estimated_font_ratio"], 0.108)
            self.assertEqual(text_program["items"][0]["font_size_pt"], 38.88)
            self.assertEqual(text_program["items"][0]["raw_font_size_pt"], 38.88)
            self.assertEqual(text_program["items"][0]["text_size_level_id"], "text_size_level_01")
            self.assertEqual(program["text_program"]["items"][0]["font_family_guess"], "Arial")

            size_report = json.loads((out / "text_size_normalization_report.json").read_text(encoding="utf-8"))
            self.assertEqual(size_report["level_count"], 1)

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

    def test_vlm_same_role_clusters_similar_ocr_sizes_to_one_median_font(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reference = out / "reference.png"
            Image.new("RGB", (400, 200), "white").save(reference)

            def fake_ocr(_path, _lang):
                return [
                    {"text": "Input", "confidence": 0.95, "quad": [[20, 20], [90, 20], [90, 40], [20, 40]]},
                    {"text": "Encoder", "confidence": 0.95, "quad": [[110, 20], [210, 20], [210, 41], [110, 41]]},
                    {"text": "Output", "confidence": 0.95, "quad": [[230, 20], [320, 20], [320, 43], [230, 43]]},
                ]

            def fake_roles(_path, regions, _program, _model):
                return {
                    "summary": "fake",
                    "items": [
                        {
                            "text_id": region["id"],
                            "role": "body_label",
                            "hierarchy_level": "body",
                            "size_class": "medium",
                            "group_hint": "body_labels",
                            "confidence": 0.9,
                            "reason": "same label tier",
                        }
                        for region in regions
                    ],
                }

            build_text_layer(
                reference,
                _base_program(),
                _style(),
                out,
                text_extractor_mode="ocr",
                ocr_adapter=fake_ocr,
                text_role_mode="vlm",
                text_role_adapter=fake_roles,
            )

            text_program = json.loads((out / "text_program.json").read_text(encoding="utf-8"))
            font_sizes = {item["font_size_pt"] for item in text_program["items"]}
            raw_font_sizes = {item["raw_font_size_pt"] for item in text_program["items"]}
            levels = {item["text_size_level_id"] for item in text_program["items"]}
            self.assertEqual(len(font_sizes), 1)
            self.assertGreater(len(raw_font_sizes), 1)
            self.assertEqual(levels, {"text_size_level_01"})
            self.assertTrue(all(item["role"] == "body_label" for item in text_program["items"]))

    def test_vlm_different_roles_keep_separate_size_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reference = out / "reference.png"
            Image.new("RGB", (400, 200), "white").save(reference)

            def fake_ocr(_path, _lang):
                return [
                    {"text": "Stage I", "confidence": 0.95, "quad": [[20, 20], [100, 20], [100, 42], [20, 42]]},
                    {"text": "Input", "confidence": 0.95, "quad": [[120, 20], [190, 20], [190, 42], [120, 42]]},
                ]

            def fake_roles(_path, regions, _program, _model):
                return {
                    "summary": "fake",
                    "items": [
                        {
                            "text_id": regions[0]["id"],
                            "role": "section_title",
                            "hierarchy_level": "title",
                            "size_class": "large",
                            "group_hint": "section_titles",
                            "confidence": 0.9,
                            "reason": "header",
                        },
                        {
                            "text_id": regions[1]["id"],
                            "role": "body_label",
                            "hierarchy_level": "body",
                            "size_class": "medium",
                            "group_hint": "body_labels",
                            "confidence": 0.9,
                            "reason": "body",
                        },
                    ],
                }

            build_text_layer(
                reference,
                _base_program(),
                _style(),
                out,
                text_extractor_mode="ocr",
                ocr_adapter=fake_ocr,
                text_role_mode="vlm",
                text_role_adapter=fake_roles,
            )

            text_program = json.loads((out / "text_program.json").read_text(encoding="utf-8"))
            self.assertNotEqual(text_program["items"][0]["text_size_level_id"], text_program["items"][1]["text_size_level_id"])
            self.assertEqual(text_program["items"][0]["role"], "section_title")
            self.assertEqual(text_program["items"][1]["role"], "body_label")

    def test_low_confidence_or_invalid_vlm_role_falls_back_per_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reference = out / "reference.png"
            Image.new("RGB", (400, 200), "white").save(reference)

            def fake_ocr(_path, _lang):
                return [{"text": "Detected Title", "confidence": 0.95, "quad": [[30, 18], [180, 18], [180, 42], [30, 42]]}]

            def bad_roles(_path, regions, _program, _model):
                return {
                    "summary": "fake",
                    "items": [{
                        "text_id": regions[0]["id"],
                        "role": "not_a_role",
                        "hierarchy_level": "title",
                        "size_class": "large",
                        "group_hint": "bad",
                        "confidence": 0.2,
                        "reason": "bad test item",
                    }],
                }

            build_text_layer(
                reference,
                _base_program(),
                _style(),
                out,
                text_extractor_mode="ocr",
                ocr_adapter=fake_ocr,
                text_role_mode="vlm",
                text_role_adapter=bad_roles,
            )

            classification = json.loads((out / "text_role_classification.json").read_text(encoding="utf-8"))
            text_program = json.loads((out / "text_program.json").read_text(encoding="utf-8"))
            self.assertEqual(classification["fallback_count"], 1)
            self.assertEqual(text_program["items"][0]["role"], "panel_title")
            self.assertEqual(text_program["items"][0]["text_role_source"], "heuristic_fallback")


if __name__ == "__main__":
    unittest.main()
