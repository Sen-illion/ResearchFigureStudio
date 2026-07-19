import unittest

from rfs.text_grouping import group_text_regions_heuristic


def _region(text: str, text_id: str, x: float, y: float, w: float, h: float, target_id: str = "card_a", role: str = "body_label") -> dict:
    return {
        "id": text_id,
        "text": text,
        "raw_text": text,
        "role": role,
        "ocr_role_guess": role,
        "target_id": target_id,
        "bbox_percent": {"x": x, "y": y, "w": w, "h": h},
        "center_percent": {"x": x + w / 2, "y": y + h / 2},
        "width_percent": w,
        "height_percent": h,
        "estimated_font_ratio": h * 0.9,
        "raw_estimated_font_ratio": h * 0.9,
        "font_size_pt": 8.0,
        "raw_font_size_pt": 8.0,
        "font_family_guess": "Arial",
        "confidence": 0.95,
        "color_hex": "#222222",
        "source": "reference_ocr_text_region",
        "editable_in": "pptx",
    }


class TextGroupingTests(unittest.TestCase):
    def test_multiline_body_text_is_merged_to_one_paragraph_region(self):
        raw = [
            _region("first line of body", "ocr_1", 0.10, 0.20, 0.24, 0.030),
            _region("second line continues", "ocr_2", 0.101, 0.234, 0.25, 0.031),
            _region("third line continues", "ocr_3", 0.100, 0.269, 0.22, 0.030),
        ]

        grouped, plan, report = group_text_regions_heuristic(raw)

        self.assertEqual(report["paragraph_group_count"], 1)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["ocr_member_ids"], ["ocr_1", "ocr_2", "ocr_3"])
        self.assertEqual(grouped[0]["text"], "first line of body\nsecond line continues\nthird line continues")
        self.assertLess(grouped[0]["raw_estimated_font_ratio"], grouped[0]["height_percent"])
        self.assertEqual(plan["groups"][0]["group_id"], grouped[0]["id"])

    def test_panel_titles_are_not_heuristically_paragraph_merged(self):
        raw = [
            _region("Graph-based Textual", "ocr_title_1", 0.20, 0.04, 0.20, 0.030, target_id="panel_a", role="panel_title"),
            _region("Knowledge Grounding", "ocr_title_2", 0.20, 0.075, 0.22, 0.030, target_id="panel_a", role="panel_title"),
        ]

        grouped, _plan, report = group_text_regions_heuristic(raw)

        self.assertEqual(report["paragraph_group_count"], 0)
        self.assertEqual(len(grouped), 2)
        self.assertTrue(all(item["ocr_member_count"] == 1 for item in grouped))

    def test_text_from_different_targets_does_not_merge(self):
        raw = [
            _region("card A line one", "ocr_a1", 0.10, 0.20, 0.20, 0.030, target_id="card_a"),
            _region("card B line one", "ocr_b1", 0.10, 0.234, 0.20, 0.030, target_id="card_b"),
        ]

        grouped, _plan, report = group_text_regions_heuristic(raw)

        self.assertEqual(report["paragraph_group_count"], 0)
        self.assertEqual(len(grouped), 2)
        self.assertEqual({item["target_id"] for item in grouped}, {"card_a", "card_b"})


if __name__ == "__main__":
    unittest.main()
