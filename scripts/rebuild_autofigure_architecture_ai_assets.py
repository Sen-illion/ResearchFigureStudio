from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
import shutil
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageStat
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(r"C:\Users\zhang\Documents\xwechat_files\wxid_h824xk1qpfoh22_adc2\temp\RWTemp\2026-06\860847045f7ccc2e7052eb182bab099b\8fc4985d14085a49b20f61b3d56d0bea.png")
OUT = ROOT / "output" / "autofigure_architecture_ai_rebuild"
CROP_DIR = OUT / "reference_slot_crops"
ASSET_DIR = OUT / "assets"
CANDIDATE_DIR = OUT / "asset_candidates"

REF_W = 1770
REF_H = 975
SLIDE_W = 15.60
SLIDE_H = SLIDE_W * REF_H / REF_W

FONT = "Arial"
TEXT_SIZE_SCALE = 1.08
TEXT_STYLES = {
    "title": {"font": FONT, "size": 23.0, "bold": True},
    "subtitle": {"font": FONT, "size": 10.8, "bold": False},
    "stage_title": {"font": FONT, "size": 13.0, "bold": True},
    "label": {"font": FONT, "size": 10.5, "bold": True},
    "body": {"font": FONT, "size": 8.6, "bold": False},
    "small": {"font": FONT, "size": 7.4, "bold": False},
    "callout": {"font": FONT, "size": 9.0, "bold": True},
    "legend": {"font": FONT, "size": 9.2, "bold": True},
}

SLOTS = [
    {
        "id": "input_text_stack",
        "bbox": (66, 254, 200, 400),
        "asset_bbox": (68, 255, 205, 398),
        "prompt": "a stack of off-white paper documents with simple abstract pseudo-lines and two tiny pseudo-number marks, cute academic flat illustration, no readable text",
        "background_color_hex": "#EAF3FF",
    },
    {
        "id": "vlm_agent_robot",
        "bbox": (280, 258, 458, 404),
        "asset_bbox": (294, 250, 454, 407),
        "prompt": "a cute round robot assistant head with small antennae and soft blue-gray casing, pastel academic diagram style, no text",
        "background_color_hex": "#EAF3FF",
    },
    {
        "id": "ai_designer",
        "bbox": (642, 441, 793, 629),
        "asset_bbox": (650, 425, 790, 627),
        "prompt": "a cute AI designer character wearing a beret and holding a blueprint tablet, pastel orange academic illustration, no readable text",
        "background_color_hex": "#FFF1DF",
    },
    {
        "id": "ai_critic",
        "bbox": (1059, 438, 1212, 632),
        "asset_bbox": (1062, 434, 1208, 632),
        "prompt": "a cute robot critic wearing round glasses and holding a clipboard, pastel academic illustration, no readable text",
        "background_color_hex": "#FFF1DF",
    },
    {
        "id": "synthesis_tools",
        "bbox": (1375, 132, 1625, 247),
        "asset_bbox": (1375, 126, 1628, 250),
        "prompt": "a magic wand and cheerful painter palette with soft sparkles, pastel scientific illustration, no text",
        "background_color_hex": "#ECF7E9",
    },
    {
        "id": "erase_text_tool",
        "bbox": (1288, 493, 1420, 604),
        "asset_bbox": (1290, 486, 1425, 606),
        "prompt": "a pink eraser removing blurred tiny pseudo-letters, cute academic diagram illustration, no readable text",
        "background_color_hex": "#ECF7E9",
    },
    {
        "id": "ocr_verify",
        "bbox": (1570, 492, 1712, 604),
        "asset_bbox": (1566, 490, 1718, 608),
        "prompt": "a magnifying glass inspecting pseudo-numbers with a green check badge and short gray pseudo-lines, clean pastel academic illustration, no readable text",
        "background_color_hex": "#ECF7E9",
    },
    {
        "id": "final_autofigure_card",
        "bbox": (1402, 682, 1590, 812),
        "asset_bbox": (1408, 686, 1588, 808),
        "prompt": "a small polished scientific figure card with abstract pie chart, smooth shapes, tiny pseudo-lines and pleasing pastel colors, no readable text",
        "background_color_hex": "#ECF7E9",
    },
]

CONTROL_SPECS = [
    {"id": "input_to_vlm", "kind": "line", "source_id": "input_text_stack", "target_id": "vlm_agent_robot", "points": [(222, 346), (278, 346)], "color": "#607998", "width_pt": 2.5, "arrow": True, "dash": False, "confidence": 0.92},
    {"id": "vlm_to_blueprint", "kind": "line", "source_id": "vlm_agent_robot", "target_id": "initial_blueprint", "points": [(365, 407), (365, 508)], "color": "#607998", "width_pt": 2.8, "arrow": True, "dash": False, "confidence": 0.91},
    {"id": "stage_i_to_stage_ii", "kind": "line", "source_id": "stage_i", "target_id": "stage_ii", "points": [(565, 493), (626, 493)], "color": "#555555", "width_pt": 4.0, "arrow": True, "dash": False, "confidence": 0.95},
    {"id": "stage_ii_to_stage_iii", "kind": "line", "source_id": "stage_ii", "target_id": "stage_iii", "points": [(1228, 493), (1270, 493)], "color": "#555555", "width_pt": 4.0, "arrow": True, "dash": False, "confidence": 0.95},
    {"id": "critique_refinement_loop", "kind": "oval", "source_id": "ai_critic", "target_id": "ai_designer", "bbox": (735, 335, 350, 382), "color": "#D99045", "width_pt": 2.0, "arrow": False, "dash": True, "flow": "clockwise", "confidence": 0.86},
    {"id": "designer_refine_arrow", "kind": "line", "source_id": "critique_refinement_loop", "target_id": "ai_designer", "points": [(814, 685), (774, 648)], "color": "#D99045", "width_pt": 2.0, "arrow": True, "dash": False, "confidence": 0.84},
    {"id": "critic_feedback_arrow", "kind": "line", "source_id": "critique_refinement_loop", "target_id": "ai_critic", "points": [(1038, 388), (1072, 430)], "color": "#D99045", "width_pt": 2.0, "arrow": True, "dash": False, "confidence": 0.84},
    {"id": "synthesis_to_raw", "kind": "line", "source_id": "synthesis_tools", "target_id": "raw_image", "points": [(1500, 280), (1500, 350)], "color": "#6F9A66", "width_pt": 3.0, "arrow": True, "dash": False, "confidence": 0.9},
    {"id": "raw_to_erase_route", "kind": "polyline", "source_id": "raw_image", "target_id": "erase_text_tool", "points": [(1428, 405), (1362, 405), (1348, 428), (1345, 462)], "color": "#6F9A66", "width_pt": 1.8, "arrow": True, "dash": True, "confidence": 0.9},
    {"id": "raw_to_ocr_route", "kind": "polyline", "source_id": "raw_image", "target_id": "ocr_verify", "points": [(1588, 405), (1652, 405), (1684, 426), (1692, 462)], "color": "#6F9A66", "width_pt": 1.8, "arrow": True, "dash": True, "confidence": 0.9},
    {"id": "erase_to_final_route", "kind": "polyline", "source_id": "erase_text_tool", "target_id": "final_autofigure_card", "points": [(1345, 624), (1350, 650), (1382, 680)], "color": "#6F9A66", "width_pt": 1.8, "arrow": True, "dash": True, "confidence": 0.88},
    {"id": "ocr_to_final_route", "kind": "polyline", "source_id": "ocr_verify", "target_id": "final_autofigure_card", "points": [(1644, 624), (1638, 650), (1608, 680)], "color": "#6F9A66", "width_pt": 1.8, "arrow": True, "dash": True, "confidence": 0.88},
    {"id": "finalization_arrow", "kind": "line", "source_id": "erase_text_tool", "target_id": "final_autofigure_card", "points": [(1306, 737), (1386, 737)], "color": "#6F9A66", "width_pt": 3.5, "arrow": True, "dash": False, "confidence": 0.86},
]


def px(v: float, total: float, slide_total: float) -> float:
    return v / total * slide_total


def x(v: float) -> float:
    return px(v, REF_W, SLIDE_W)


def y(v: float) -> float:
    return px(v, REF_H, SLIDE_H)


def w(v: float) -> float:
    return px(v, REF_W, SLIDE_W)


def h(v: float) -> float:
    return px(v, REF_H, SLIDE_H)


def rgb(value: str) -> RGBColor:
    text = value.strip().lstrip("#")
    return RGBColor(int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def hex_to_tuple(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def tuple_to_hex(value: tuple[int, int, int]) -> str:
    return f"#{value[0]:02X}{value[1]:02X}{value[2]:02X}"


def set_fill(shape, color: str, transparency: int = 0) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.fill.transparency = transparency


def no_fill(shape) -> None:
    shape.fill.background()


def set_line(shape, color: str, width_pt: float = 1.2, dash: bool = False) -> None:
    shape.line.color.rgb = rgb(color)
    shape.line.width = Pt(width_pt)
    if dash:
        shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH


def add_text(slide, text: str, left: float, top: float, width: float, height: float, *, style: str = "body", color: str = "#333333", align=PP_ALIGN.CENTER, size: float | None = None, bold: bool | None = None, valign=MSO_ANCHOR.MIDDLE):
    spec = TEXT_STYLES[style]
    font_size = float(size if size is not None else spec["size"]) * TEXT_SIZE_SCALE
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = valign
    tf.margin_left = Inches(0.01)
    tf.margin_right = Inches(0.01)
    tf.margin_top = Inches(0.0)
    tf.margin_bottom = Inches(0.0)
    for idx, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.name = str(spec["font"])
        r.font.size = Pt(font_size)
        r.font.bold = bool(bold if bold is not None else spec["bold"])
        r.font.color.rgb = rgb(color)
    return box


def add_round(slide, left_px, top_px, width_px, height_px, fill, stroke, width_pt=1.2, radius=True):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x(left_px)), Inches(y(top_px)), Inches(w(width_px)), Inches(h(height_px)))
    set_fill(shape, fill)
    set_line(shape, stroke, width_pt)
    shape.shadow.inherit = False
    return shape


def add_arrowhead(connector, size="med") -> None:
    ln = connector.line._get_or_add_ln()
    ln.append(parse_xml(f'<a:tailEnd xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" type="triangle" w="{size}" len="{size}"/>'))


def add_line(slide, x1, y1, x2, y2, color="#333333", width_pt=1.2, arrow=False, dash=False):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x(x1)), Inches(y(y1)), Inches(x(x2)), Inches(y(y2)))
    set_line(conn, color, width_pt, dash=dash)
    if arrow:
        add_arrowhead(conn)
    return conn


def add_poly(slide, points, color="#333333", width_pt=1.2, arrow=False, dash=False):
    for idx, (a, b) in enumerate(zip(points[:-1], points[1:])):
        add_line(slide, a[0], a[1], b[0], b[1], color=color, width_pt=width_pt, arrow=arrow and idx == len(points) - 2, dash=dash)


def bbox_percent_from_points(points: list[tuple[float, float]]) -> dict:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return {"x": round(left / REF_W, 4), "y": round(top / REF_H, 4), "w": round((right - left) / REF_W, 4), "h": round((bottom - top) / REF_H, 4)}


def direction_label(dx: float, dy: float) -> str:
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return "none"
    if abs(dx) >= abs(dy) * 1.8:
        return "right" if dx > 0 else "left"
    if abs(dy) >= abs(dx) * 1.8:
        return "down" if dy > 0 else "up"
    vertical = "down" if dy > 0 else "up"
    horizontal = "right" if dx > 0 else "left"
    return f"{vertical}_{horizontal}"


def anchor_from_direction(dx: float, dy: float, at_source: bool) -> str:
    if abs(dx) >= abs(dy):
        if dx > 0:
            return "right_center" if at_source else "left_center"
        return "left_center" if at_source else "right_center"
    if dy > 0:
        return "bottom_center" if at_source else "top_center"
    return "top_center" if at_source else "bottom_center"


def position_direction_metadata(control: dict) -> dict:
    if control["kind"] == "oval":
        left, top, width, height = control["bbox"]
        return {
            "position": {
                "bbox_px": [left, top, width, height],
                "center_px": [round(left + width / 2, 2), round(top + height / 2, 2)],
                "bbox_percent": {"x": round(left / REF_W, 4), "y": round(top / REF_H, 4), "w": round(width / REF_W, 4), "h": round(height / REF_H, 4)},
            },
            "direction": {
                "path_type": "closed_loop",
                "flow": control.get("flow", "clockwise"),
                "arrowhead_at": control.get("arrowhead_at", "none"),
                "direction_confidence": control.get("confidence", 0.0),
            },
            "source_anchor": control.get("source_anchor", "loop_right_side"),
            "target_anchor": control.get("target_anchor", "loop_left_side"),
        }

    points = control["points"]
    start = points[0]
    end = points[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
    angle = math.degrees(math.atan2(dy, dx))
    return {
        "position": {
            "start_px": [start[0], start[1]],
            "end_px": [end[0], end[1]],
            "points_px": [[px_, py_] for px_, py_ in points],
            "center_px": [round((start[0] + end[0]) / 2, 2), round((start[1] + end[1]) / 2, 2)],
            "bbox_percent": bbox_percent_from_points(points),
        },
        "direction": {
            "vector_px": [round(dx, 2), round(dy, 2)],
            "unit_vector": [round(dx / length, 4), round(dy / length, 4)],
            "angle_deg": round(angle, 2),
            "label": direction_label(dx, dy),
            "arrowhead_at": "end" if control.get("arrow") else "none",
            "direction_confidence": control.get("confidence", 0.0),
        },
        "source_anchor": control.get("source_anchor", anchor_from_direction(dx, dy, True)),
        "target_anchor": control.get("target_anchor", anchor_from_direction(dx, dy, False)),
    }


def normalize_control(control: dict) -> dict:
    item = dict(control)
    item.update(position_direction_metadata(control))
    if control["kind"] == "oval":
        left, top, width, height = control["bbox"]
        item["bbox_percent"] = {"x": round(left / REF_W, 4), "y": round(top / REF_H, 4), "w": round(width / REF_W, 4), "h": round(height / REF_H, 4)}
        item["path_percent"] = []
    else:
        item["bbox_percent"] = bbox_percent_from_points(control["points"])
        item["path_percent"] = [{"x": round(px_ / REF_W, 4), "y": round(py_ / REF_H, 4)} for px_, py_ in control["points"]]
    item["render_policy"] = "ppt_shape_not_image_asset"
    item["route_policy"] = "reference_locked"
    return item


def render_control(slide, control: dict):
    if control["kind"] == "oval":
        left, top, width, height = control["bbox"]
        shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x(left)), Inches(y(top)), Inches(w(width)), Inches(h(height)))
        no_fill(shape)
        set_line(shape, control["color"], control["width_pt"], dash=control["dash"])
        return shape
    if control["kind"] == "polyline":
        return add_poly(slide, control["points"], control["color"], control["width_pt"], arrow=control["arrow"], dash=control["dash"])
    start, end = control["points"]
    return add_line(slide, start[0], start[1], end[0], end[1], control["color"], control["width_pt"], arrow=control["arrow"], dash=control["dash"])


def render_controls(slide, control_ids: list[str]) -> None:
    lookup = {control["id"]: control for control in CONTROL_SPECS}
    for control_id in control_ids:
        render_control(slide, lookup[control_id])


def draw_dashed_line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color: str, width: int = 3, dash: int = 14, gap: int = 9) -> None:
    fill = hex_to_tuple(color)
    for start, end in zip(points[:-1], points[1:]):
        x1, y1 = start
        x2, y2 = end
        length = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1)
        steps = int(length // (dash + gap)) + 1
        for step in range(steps):
            a = step * (dash + gap) / length
            b = min((step * (dash + gap) + dash) / length, 1)
            if a >= 1:
                continue
            draw.line((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * b, y1 + (y2 - y1) * b), fill=fill, width=width)


def write_reference_overlays() -> None:
    with Image.open(REFERENCE).convert("RGB") as image:
        slot_overlay = image.copy()
        slot_draw = ImageDraw.Draw(slot_overlay)
        for slot in SLOTS:
            slot_draw.rectangle(slot["bbox"], outline=hex_to_tuple("#2A7BD1"), width=4)
            slot_draw.text((slot["bbox"][0] + 4, slot["bbox"][1] + 4), slot["id"], fill=hex_to_tuple("#2A7BD1"))
        slot_overlay.save(OUT / "slot_overlay.png")

        control_overlay = image.copy()
        control_draw = ImageDraw.Draw(control_overlay)
        for control in CONTROL_SPECS:
            color = control["color"]
            if control["kind"] == "oval":
                left, top, width, height = control["bbox"]
                control_draw.ellipse((left, top, left + width, top + height), outline=hex_to_tuple(color), width=5)
                label_xy = (left, top)
            else:
                points = control["points"]
                if control["dash"]:
                    draw_dashed_line(control_draw, points, color, width=5)
                else:
                    control_draw.line(points, fill=hex_to_tuple(color), width=5)
                label_xy = points[0]
            control_draw.text((label_xy[0] + 5, label_xy[1] + 5), control["id"], fill=hex_to_tuple("#111111"))
        control_overlay.save(OUT / "reference_control_overlay.png")


def crop_reference_slots() -> list[dict]:
    CROP_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(REFERENCE) as image:
        image = image.convert("RGB")
        for slot in SLOTS:
            crop = image.crop(slot["bbox"])
            crop_path = CROP_DIR / f"{slot['id']}.png"
            crop.save(crop_path)
            slot["crop_path"] = str(crop_path)
            x0, y0, x1, y1 = slot["bbox"]
            slot["bbox_percent"] = {"x": round(x0 / REF_W, 4), "y": round(y0 / REF_H, 4), "w": round((x1 - x0) / REF_W, 4), "h": round((y1 - y0) / REF_H, 4)}
    return SLOTS


def estimate_edge_background(image: Image.Image) -> tuple[int, int, int]:
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    strip = max(4, min(width, height) // 20)
    samples = []
    for crop_box in [
        (0, 0, width, strip),
        (0, height - strip, width, height),
        (0, 0, strip, height),
        (width - strip, 0, width, height),
    ]:
        crop = rgb_image.crop(crop_box)
        if hasattr(crop, "get_flattened_data"):
            samples.extend(crop.get_flattened_data())
        else:
            samples.extend(crop.getdata())
    samples.sort(key=lambda color: sum(color))
    mid = samples[len(samples) // 2]
    return int(mid[0]), int(mid[1]), int(mid[2])


def harmonize_asset_background(asset_path: Path, background_hex: str) -> dict:
    image = Image.open(asset_path).convert("RGB")
    target = hex_to_tuple(background_hex)
    source_bg = estimate_edge_background(image)
    mask = edge_connected_background_mask(image, source_bg, tolerance=42)
    output = image.copy()
    bg_layer = Image.new("RGB", image.size, target)
    output.paste(bg_layer, mask=mask)
    output.save(asset_path)
    stat = ImageStat.Stat(mask)
    replaced_percent = round(stat.mean[0] / 255 * 100, 2)
    return {
        "asset": str(asset_path),
        "estimated_source_background": tuple_to_hex(source_bg),
        "target_background": background_hex,
        "replaced_percent": replaced_percent,
    }


def edge_connected_background_mask(image: Image.Image, background: tuple[int, int, int], tolerance: int = 42) -> Image.Image:
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    pixels = rgb_image.load()
    visited = bytearray(width * height)
    mask = Image.new("L", (width, height), 0)
    mask_pixels = mask.load()
    queue: deque[tuple[int, int]] = deque()

    def close_to_background(px_: int, py_: int) -> bool:
        color = pixels[px_, py_]
        return abs(color[0] - background[0]) + abs(color[1] - background[1]) + abs(color[2] - background[2]) <= tolerance

    def push(px_: int, py_: int) -> None:
        index = py_ * width + px_
        if visited[index] or not close_to_background(px_, py_):
            return
        visited[index] = 1
        mask_pixels[px_, py_] = 255
        queue.append((px_, py_))

    for px_ in range(width):
        push(px_, 0)
        push(px_, height - 1)
    for py_ in range(height):
        push(0, py_)
        push(width - 1, py_)

    while queue:
        px_, py_ = queue.popleft()
        if px_ > 0:
            push(px_ - 1, py_)
        if px_ + 1 < width:
            push(px_ + 1, py_)
        if py_ > 0:
            push(px_, py_ - 1)
        if py_ + 1 < height:
            push(px_, py_ + 1)
    return mask


def latest_candidate_for_slot(slot_id: str) -> Path | None:
    slot_dir = CANDIDATE_DIR / slot_id
    if not slot_dir.exists():
        return None
    candidates = sorted(slot_dir.glob("candidate_*.png"))
    return candidates[-1] if candidates else None


def gemini_generate_from_crop(slot: dict, candidate_index: int = 1) -> Path:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    url = os.getenv("GEMINI_GEN_IMG_URL")
    if not api_key or not url:
        raise RuntimeError("GEMINI_API_KEY/API_KEY and GEMINI_GEN_IMG_URL are required")
    crop_path = Path(slot["crop_path"])
    mime = mimetypes.guess_type(crop_path.name)[0] or "image/png"
    image_b64 = base64.b64encode(crop_path.read_bytes()).decode("ascii")
    prompt = (
        "Use the provided crop as a visual reference. Recreate only the main object(s) from this crop as a clean standalone raster asset for a PowerPoint scientific architecture figure. "
        f"Asset id: {slot['id']}. Main request: {slot['prompt']}. "
        "Preserve the crop's object identity, approximate pose, pastel academic illustration style, soft shadows, rounded friendly shapes, and color family. "
        "Do not include any readable words, letters, numbers, stage title, labels, arrows, diagram frame, panel border, or white card background. "
        f"Keep the object large and centered with minimal empty margin. Use a perfectly flat background color matching {slot['background_color_hex']} so the asset blends into its stage panel. "
        "No watermark, no logo, no extra unrelated objects."
    )
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": mime, "data": image_b64}},
            ],
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"imageSize": "1K", "aspectRatio": "1:1"},
        },
    }
    out_path = CANDIDATE_DIR / slot["id"] / f"candidate_{candidate_index:02d}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, data=json.dumps(payload), timeout=240)
    response.raise_for_status()
    data = response.json()
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                out_path.write_bytes(base64.b64decode(inline["data"]))
                return out_path
    raise RuntimeError(f"No image returned for {slot['id']}")


def generate_one_asset_with_retries(slot: dict, retries: int = 3) -> dict:
    final_path = ASSET_DIR / f"{slot['id']}.png"
    if final_path.exists() and os.getenv("RFS_REUSE_ASSETS", "1") == "1":
        candidate_path = latest_candidate_for_slot(slot["id"])
        if candidate_path is not None:
            shutil.copyfile(candidate_path, final_path)
        background_report = harmonize_asset_background(final_path, slot["background_color_hex"])
        return {
            "slot_id": slot["id"],
            "status": "ok",
            "asset_source": "reused_existing",
            "candidate": str(candidate_path) if candidate_path is not None else None,
            "asset": str(final_path),
            "background": background_report,
        }

    errors = []
    for attempt in range(1, retries + 1):
        try:
            candidate_path = gemini_generate_from_crop(slot, attempt)
            Image.open(candidate_path).convert("RGB").save(final_path)
            background_report = harmonize_asset_background(final_path, slot["background_color_hex"])
            return {
                "slot_id": slot["id"],
                "status": "ok",
                "asset_source": "generated",
                "candidate": str(candidate_path),
                "asset": str(final_path),
                "attempt": attempt,
                "background": background_report,
            }
        except Exception as exc:
            errors.append(str(exc))
            time.sleep(min(2 * attempt, 6))

    fallback = ASSET_DIR / f"{slot['id']}.png"
    # Keep the pipeline deliverable if API has a repeated transient failure, but make the fallback explicit.
    Image.open(slot["crop_path"]).convert("RGB").save(fallback)
    background_report = harmonize_asset_background(fallback, slot["background_color_hex"])
    return {
        "slot_id": slot["id"],
        "status": "fallback_to_reference_crop",
        "errors": errors,
        "asset": str(fallback),
        "background": background_report,
    }


def generate_assets_parallel(workers: int = 6, retries: int = 3) -> dict:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(generate_one_asset_with_retries, slot, retries): slot for slot in SLOTS}
        for future in as_completed(futures):
            slot = futures[future]
            try:
                reports.append(future.result())
            except Exception as exc:
                fallback = ASSET_DIR / f"{slot['id']}.png"
                Image.open(slot["crop_path"]).convert("RGB").save(fallback)
                background_report = harmonize_asset_background(fallback, slot["background_color_hex"])
                reports.append({"slot_id": slot["id"], "status": "fallback_to_reference_crop", "errors": [str(exc)], "asset": str(fallback), "background": background_report})
    return {"summary": "AI asset generation report for AutoFigure Architecture rebuild.", "workers": workers, "retries": retries, "assets": sorted(reports, key=lambda item: item["slot_id"])}


def add_picture_contain(slide, image_path: Path, left_px, top_px, width_px, height_px):
    with Image.open(image_path) as img:
        ratio = img.width / max(img.height, 1)
    box_ratio = width_px / max(height_px, 1)
    if ratio > box_ratio:
        fit_w = width_px
        fit_h = width_px / ratio
    else:
        fit_h = height_px
        fit_w = height_px * ratio
    return slide.shapes.add_picture(str(image_path), Inches(x(left_px + (width_px - fit_w) / 2)), Inches(y(top_px + (height_px - fit_h) / 2)), width=Inches(w(fit_w)), height=Inches(h(fit_h)))


def draw_document_blueprint(slide):
    box = add_round(slide, 74, 514, 472, 248, "#F4F8FB", "#6D8BA4", 1.3)
    box.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    add_text(slide, "Initial Blueprint (S0, A0)", x(160), y(528), w(270), h(34), style="stage_title", color="#111111", size=12.5)
    code = '{\n  "nodes": [{\n    id: "v1",\n    pos: [x,y]...\n  }],\n  "style": "academic_flat"\n}'
    add_text(slide, code, x(98), y(574), w(220), h(150), style="small", color="#111111", align=PP_ALIGN.LEFT, size=8.3)
    add_line(slide, 336, 656, 421, 656, color="#A6C8DE", width_pt=2.0)
    brace = slide.shapes.add_shape(MSO_SHAPE.RIGHT_BRACE, Inches(x(388)), Inches(y(610)), Inches(w(55)), Inches(h(112)))
    no_fill(brace)
    set_line(brace, "#9FC6DE", 1.6)
    add_round(slide, 424, 585, 112, 54, "#E9EEF1", "#7A8790", 1.0)
    add_text(slide, "Node A", x(433), y(595), w(90), h(28), style="body", color="#333333", size=10.5)
    add_round(slide, 424, 676, 112, 54, "#E9EEF1", "#7A8790", 1.0)
    add_text(slide, "Node B", x(433), y(686), w(90), h(28), style="body", color="#333333", size=10.5)


def add_panel(slide, left, top, width, height, title, border, fill, header):
    add_round(slide, left, top, width, height, fill, border, 1.8)
    header_shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x(left + 2)), Inches(y(top + 2)), Inches(w(width - 4)), Inches(h(62)))
    set_fill(header_shape, header, 0)
    set_line(header_shape, header, 0.1)
    add_text(slide, title, x(left + 16), y(top + 16), w(width - 32), h(36), style="stage_title", color="#333333")


def draw_ppt() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb("#F3F1EC")

    add_text(slide, "AutoFigure Architecture", x(50), y(45), w(620), h(60), style="title", color="#333333", align=PP_ALIGN.LEFT)
    add_text(slide, "Decoupled Generative Paradigm: Reasoning, Refinement, and Layered Rendering", x(51), y(114), w(760), h(30), style="subtitle", color="#333333", align=PP_ALIGN.LEFT)

    add_panel(slide, 42, 170, 540, 650, "Stage I: Concept Extraction", "#8AA4BC", "#EAF3FF", "#D6E5F4")
    add_panel(slide, 615, 170, 610, 658, "Stage II: Critique-and-Refine", "#E1A45D", "#FFF1DF", "#F8D1A3")
    add_panel(slide, 1260, 48, 500, 892, "Stage III: Rendering Strategy", "#84A57F", "#ECF7E9", "#C9DFC1")

    asset = lambda name: ASSET_DIR / f"{name}.png"
    add_picture_contain(slide, asset("input_text_stack"), 70, 258, 145, 148)
    add_text(slide, "Input Text", x(92), y(421), w(105), h(26), style="label", color="#333333")
    render_controls(slide, ["input_to_vlm"])
    add_picture_contain(slide, asset("vlm_agent_robot"), 285, 252, 165, 160)
    add_text(slide, "VLM Agent", x(309), y(421), w(118), h(26), style="label", color="#333333")
    add_round(slide, 465, 258, 90, 90, "#EAF0F5", "#94A6B9", 1.2)
    add_text(slide, "Entities", x(476), y(293), w(68), h(24), style="body", color="#333333", bold=True)
    add_round(slide, 465, 355, 90, 90, "#EAF0F5", "#94A6B9", 1.2)
    add_text(slide, "Relations", x(474), y(389), w(72), h(24), style="body", color="#333333", bold=True)
    render_controls(slide, ["vlm_to_blueprint"])
    draw_document_blueprint(slide)
    add_text(slide, '"Map unstructured text to symbolic graph"', x(84), y(774), w(415), h(32), style="body", color="#111111", size=11.0)
    render_controls(slide, ["stage_i_to_stage_ii"])

    # Stage II
    add_round(slide, 700, 260, 440, 50, "#FFE7C8", "#D99045", 1.2)
    add_text(slide, "Critique: Alignment, Overlap, Balance", x(720), y(274), w(400), h(24), style="callout", color="#333333", size=10.6)
    add_round(slide, 638, 350, 104, 70, "#FFE7C8", "#D99045", 1.1)
    add_text(slide, "Refine\nLayout", x(657), y(360), w(64), h(42), style="callout", color="#333333", size=8.5)
    add_round(slide, 1092, 350, 110, 70, "#FFE7C8", "#D99045", 1.1)
    add_text(slide, "Feedback\nF(i)", x(1108), y(360), w(80), h(42), style="callout", color="#333333", size=8.5)
    render_controls(slide, ["critique_refinement_loop"])
    add_picture_contain(slide, asset("ai_designer"), 650, 433, 145, 185)
    add_text(slide, "AI Designer", x(670), y(642), w(120), h(24), style="label", color="#333333", size=8.7)
    add_picture_contain(slide, asset("ai_critic"), 1060, 430, 145, 190)
    add_text(slide, "AI Critic", x(1098), y(642), w(86), h(24), style="label", color="#333333", size=8.7)
    add_round(slide, 802, 480, 235, 90, "#FFE7C8", "#D99045", 1.3)
    add_text(slide, "Score Comparison", x(822), y(500), w(194), h(30), style="callout", color="#333333", size=10.0)
    add_text(slide, "q(cand)  >  q(best)", x(822), y(532), w(194), h(24), style="small", color="#333333", size=8.0)
    render_controls(slide, ["designer_refine_arrow", "critic_feedback_arrow"])
    add_round(slide, 690, 748, 460, 48, "#FFE7C8", "#D99045", 1.2)
    add_text(slide, "Update: Re-interpret method & improve", x(710), y(761), w(420), h(22), style="callout", color="#333333", size=10.5)
    render_controls(slide, ["stage_ii_to_stage_iii"])

    # Stage III
    add_picture_contain(slide, asset("synthesis_tools"), 1380, 128, 230, 120)
    add_text(slide, "Synthesis", x(1455), y(251), w(120), h(28), style="label", color="#333333")
    render_controls(slide, ["synthesis_to_raw"])
    add_round(slide, 1428, 346, 160, 108, "#F4F4EF", "#B5B5AC", 1.3)
    add_text(slide, "Raw Image", x(1450), y(364), w(116), h(26), style="label", color="#333333", size=10.2)
    add_text(slide, "Text Blur!", x(1460), y(404), w(96), h(24), style="callout", color="#E24D42", size=9.2)
    add_picture_contain(slide, asset("erase_text_tool"), 1290, 486, 140, 125)
    add_text(slide, "Erase Text", x(1320), y(595), w(108), h(28), style="label", color="#333333", size=9.5)
    add_text(slide, "ABC", x(1404), y(516), w(55), h(24), style="label", color="#333333", size=9.0)
    add_picture_contain(slide, asset("ocr_verify"), 1570, 490, 150, 125)
    add_text(slide, "OCR + Verify", x(1578), y(595), w(140), h(28), style="label", color="#333333", size=9.5)
    add_picture_contain(slide, asset("final_autofigure_card"), 1410, 684, 185, 128)
    add_text(slide, "Final AutoFigure", x(1418), y(815), w(178), h(28), style="label", color="#333333", size=10.0)
    add_text(slide, "A stunning, high-resolution scientific\ndiagram with crisp details and a pleasing\ncolor scheme, ready for publication.", x(1368), y(846), w(300), h(70), style="body", color="#333333", size=8.2)
    render_controls(slide, ["raw_to_erase_route", "raw_to_ocr_route", "erase_to_final_route", "ocr_to_final_route", "finalization_arrow"])

    # Bottom legend
    add_round(slide, 42, 858, 1180, 80, "#F4F2ED", "#D2CEC8", 1.2)
    add_text(slide, "Key Methodology:", x(105), y(890), w(210), h(24), style="legend", color="#333333", align=PP_ALIGN.LEFT)
    add_round(slide, 328, 875, 280, 50, "#DFECF8", "#8AA4BC", 1.2)
    add_text(slide, "Concept Extraction", x(380), y(890), w(180), h(22), style="legend", color="#333333")
    add_round(slide, 628, 875, 280, 50, "#FFE6C9", "#D99045", 1.2)
    add_text(slide, "Critique-and-Refine", x(670), y(890), w(200), h(22), style="legend", color="#333333")
    add_round(slide, 925, 875, 280, 50, "#DCEED7", "#84A57F", 1.2)
    add_text(slide, "Rendering Strategy", x(970), y(890), w(190), h(22), style="legend", color="#333333")

    target = OUT / "editable_composition.pptx"
    try:
        prs.save(target)
        return target
    except PermissionError:
        fallback = OUT / "editable_composition_controls_calibrated.pptx"
        prs.save(fallback)
        return fallback


def export_preview(pptx_path: Path) -> None:
    try:
        import win32com.client  # type: ignore
    except Exception as exc:
        (OUT / "preview_export_error.txt").write_text(str(exc), encoding="utf-8")
        return
    app = win32com.client.Dispatch("PowerPoint.Application")
    app.Visible = 1
    presentation = app.Presentations.Open(str(pptx_path), WithWindow=False)
    try:
        presentation.Slides(1).Export(str(OUT / "rebuild_preview.png"), "PNG", REF_W, REF_H)
    finally:
        presentation.Close()
        app.Quit()


def write_metadata(asset_report: dict) -> None:
    controls = [normalize_control(control) for control in CONTROL_SPECS]
    background_report = {
        "summary": "Background harmonization report for generated/reused AI assets.",
        "policy": "match_slot_local_background",
        "assets": [
            {
                "slot_id": item["slot_id"],
                **item.get("background", {}),
            }
            for item in asset_report.get("assets", [])
        ],
    }
    inventory = {
        "summary": "Slot inventory for AI-generated image assets in AutoFigure Architecture editable rebuild.",
        "reference": str(REFERENCE),
        "slots": [
            {
                "slot_id": slot["id"],
                "bbox_percent": slot["bbox_percent"],
                "asset_bbox_px": slot["asset_bbox"],
                "reference_crop_path": slot["crop_path"],
                "asset_path": str(ASSET_DIR / f"{slot['id']}.png"),
                "background_color_hex": slot["background_color_hex"],
                "prompt": slot["prompt"],
            }
            for slot in SLOTS
        ],
    }
    (OUT / "slot_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "asset_generation_report.json").write_text(json.dumps(asset_report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "asset_background_report.json").write_text(json.dumps(background_report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "reference_control_candidates.json").write_text(json.dumps({
        "summary": "Reference-derived candidate arrows, connector lines, and dashed loops for the AutoFigure Architecture rebuild.",
        "extraction_mode": "manual_reference_locked_first_pass",
        "note": "This is the structured control layer that will later be replaced/refined by image-processing or VLM control extraction.",
        "controls": controls,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "reference_controls.json").write_text(json.dumps({
        "summary": "Bound editable PPT control layer for arrows, connector lines, and dashed loops.",
        "controls": controls,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "arrow_style_profile.json").write_text(json.dumps({
        "summary": "Arrow and connector style profile.",
        "reference_image_hard_constraint": True,
        "control_localizer_mode": "manual_reference_locked_first_pass",
        "style_tokens": {
            "stage_transition": {"color": "#555555", "width_pt": 4.0, "arrow_head": "triangle"},
            "stage_i_flow": {"color": "#607998", "width_pt": 2.5, "arrow_head": "triangle"},
            "critique_loop": {"color": "#D99045", "width_pt": 2.0, "dash": True},
            "rendering_loop": {"color": "#6F9A66", "width_pt": 1.8, "dash": True},
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "selected_arrow_routes.json").write_text(json.dumps({
        "summary": "Selected editable PowerPoint routes for all reference controls.",
        "route_generation_status": "reference_locked_manual_seed",
        "routes": controls,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "arrow_quality_report.json").write_text(json.dumps({
        "summary": "First-pass arrow quality report.",
        "status": "improved_structured_controls",
        "known_limitations": [
            "This pass stores measured/control coordinates in JSON but does not yet run automatic computer-vision arrow extraction.",
            "Dashed closed loops are still approximated with PPT oval/polyline controls.",
        ],
        "control_count": len(controls),
        "fallback_routing_used": False,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "arrow_direction_report.json").write_text(json.dumps({
        "summary": "Arrow position and direction report. This file prioritizes arrow placement, target direction, anchors, and arrowhead endpoint over style details.",
        "status": "position_direction_fields_added",
        "direction_contract": {
            "start_px": "tail position in reference-image pixel coordinates",
            "end_px": "arrowhead target position in reference-image pixel coordinates",
            "direction.label": "dominant direction inferred from start_px -> end_px",
            "source_anchor": "inferred source edge from direction unless explicitly overridden",
            "target_anchor": "inferred target edge from direction unless explicitly overridden",
        },
        "arrows": [
            {
                "id": control["id"],
                "kind": control["kind"],
                "source_id": control["source_id"],
                "target_id": control["target_id"],
                "source_anchor": control.get("source_anchor"),
                "target_anchor": control.get("target_anchor"),
                "position": control.get("position"),
                "direction": control.get("direction"),
            }
            for control in controls
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "reference_style_profile.json").write_text(json.dumps({
        "summary": "Reference style profile for AutoFigure Architecture editable rebuild.",
        "canvas_background": "#F3F1EC",
        "stage_backgrounds": {"stage_i": "#EAF3FF", "stage_ii": "#FFF1DF", "stage_iii": "#ECF7E9"},
        "asset_background_policy": "match_slot_local_background",
        "font_family": FONT,
        "text_size_scale": TEXT_SIZE_SCALE,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "layout_plan.json").write_text(json.dumps({
        "summary": "Reference-guided layout plan for the AutoFigure Architecture editable rebuild.",
        "canvas": {"width_px": REF_W, "height_px": REF_H, "slide_width_in": SLIDE_W, "slide_height_in": SLIDE_H},
        "panels": [
            {"id": "stage_i", "bbox_px": [42, 170, 540, 650], "fill": "#EAF3FF"},
            {"id": "stage_ii", "bbox_px": [615, 170, 610, 658], "fill": "#FFF1DF"},
            {"id": "stage_iii", "bbox_px": [1260, 48, 500, 892], "fill": "#ECF7E9"},
        ],
        "slots": inventory["slots"],
        "controls": controls,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "reference_text_geometry.json").write_text(json.dumps({
        "summary": "Reference text geometry seed for editable PPT text.",
        "detection_mode": "manual_reference_seed",
        "font_size_estimation": "reference bbox height converted to PPT points, then calibrated with TEXT_SIZE_SCALE",
        "text_size_scale": TEXT_SIZE_SCALE,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "text_program.json").write_text(json.dumps({
        "summary": "Editable text program for AutoFigure Architecture rebuild.",
        "font_family_guess": FONT,
        "fit_strategy": "bbox_bound_with_global_scale",
        "text_style_tokens": TEXT_STYLES,
        "text_size_scale": TEXT_SIZE_SCALE,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "text_alignment_report.json").write_text(json.dumps({
        "summary": "Text alignment report for the AutoFigure Architecture editable rebuild.",
        "status": "scaled_up",
        "scale_applied": TEXT_SIZE_SCALE,
        "reason": "Prior preview text was visually small; this pass applies a uniform calibration factor while preserving editable PPT text boxes.",
        "next_recommended_step": "render-and-measure calibration against OCR/reference text masks.",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "figure_program.json").write_text(json.dumps({
        "summary": "PowerPoint-first reconstruction with AI-generated local illustration assets and editable PPT structure/text.",
        "reference_size_px": [REF_W, REF_H],
        "slide_size_in": [SLIDE_W, SLIDE_H],
        "editable_layers": ["text", "stage panels", "cards", "arrows", "dashed loops", "methodology legend"],
        "raster_asset_layers": [slot["id"] for slot in SLOTS],
        "controls": controls,
        "asset_background_policy": "match_slot_local_background",
        "text_style_tokens": TEXT_STYLES,
        "text_size_scale": TEXT_SIZE_SCALE,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "rebuild_notes.md").write_text(
        "# Summary\n"
        "AutoFigure Architecture was rebuilt as an editable PowerPoint composition with AI-generated local illustration assets.\n\n"
        "## Editable PPT Layers\n"
        "- All titles, labels, captions, callouts, methodology legend text, panels, cards, arrows, and dashed loops are PowerPoint objects.\n\n"
        "## AI Raster Asset Layers\n"
        "- Complex illustrations such as robot characters, document stack, synthesis tools, eraser, OCR magnifier, and final figure card were generated as local image assets from reference crops.\n"
        "- Critical text is not trusted to the generated images; it is added as editable PPT text.\n\n"
        "## Generation\n"
        f"- Parallel workers: {asset_report.get('workers')}\n"
        "- If an API asset failed, the report marks it explicitly and uses the reference crop as a temporary fallback.\n\n"
        "## Control Layer\n"
        "- Arrows, connector lines, and dashed loops are now recorded in reference_controls.json and selected_arrow_routes.json before PPT rendering.\n"
        "- reference_control_overlay.png visualizes the current reference-locked control layer for manual QA.\n\n"
        "## Background and Text Calibration\n"
        "- Each generated or reused AI asset is harmonized to the local slot background color recorded in slot_inventory.json.\n"
        f"- Editable PPT text uses TEXT_SIZE_SCALE={TEXT_SIZE_SCALE} as a first-pass visual calibration factor.\n",
        encoding="utf-8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    crop_reference_slots()
    write_reference_overlays()
    asset_report = generate_assets_parallel(workers=6)
    write_metadata(asset_report)
    pptx_path = draw_ppt()
    export_preview(pptx_path)


if __name__ == "__main__":
    main()
