from __future__ import annotations

import base64
import io
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Protocol

import requests
from PIL import Image


class Judge(Protocol):
    model_name: str

    def evaluate(self, ground_truth: dict, candidates: list[dict], memory: list[dict] | None = None) -> dict: ...


def _extract_json(text: str) -> dict:
    cleaned = text.strip().replace("```json", "```")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _score(value: object) -> float:
    number = float(value or 0)
    if number > 1:
        number /= 100.0
    return round(max(0.0, min(1.0, number)), 4)


def _image_data_url(path: Path, max_side: int = 1600) -> str:
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_side, max_side), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def normalize_judgement(raw: dict, aliases: list[str], weights: dict, allow_feedback: bool) -> dict:
    raw_items = raw.get("evaluations") if isinstance(raw.get("evaluations"), list) else []
    by_id = {str(item.get("candidate_id")): item for item in raw_items if isinstance(item, dict)}
    evaluations = []
    for alias in aliases:
        item = by_id.get(alias, {})
        scientific = _score(item.get("scientific_score"))
        aesthetic = _score(item.get("aesthetic_score"))
        visual = _score(item.get("visual_quality_score"))
        calculated = scientific * weights["scientific"] + aesthetic * weights["aesthetic"] + visual * weights["visual_quality"]
        reported_total = _score(item.get("total_score")) if item.get("total_score") is not None else None
        total = round(calculated, 4)
        evaluations.append({
            "candidate_id": alias,
            "scientific_score": scientific,
            "aesthetic_score": aesthetic,
            "visual_quality_score": visual,
            "total_score": total,
            "reported_total_score": reported_total,
            "blocking_issues": [str(value) for value in item.get("blocking_issues", [])] if isinstance(item.get("blocking_issues"), list) else [],
            "preserve": [str(value) for value in item.get("preserve", [])] if allow_feedback and isinstance(item.get("preserve"), list) else [],
            "repair": item.get("repair", []) if allow_feedback and isinstance(item.get("repair"), list) else [],
            "confidence": _score(item.get("confidence", 0.5)),
            "summary": str(item.get("summary") or ""),
        })
    ranked = sorted(evaluations, key=lambda item: (not item["blocking_issues"], item["total_score"]), reverse=True)
    return {
        "ranking": [item["candidate_id"] for item in ranked],
        "evaluations": evaluations,
        "summary": str(raw.get("summary") or "Judge evaluation completed."),
    }


class VLMJudge:
    def __init__(self, model: str | None = None, frozen: bool = False):
        self.api_base = os.getenv("API_BASE", "").rstrip("/")
        self.api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
        default_env = "RFS_FROZEN_JUDGE_MODEL" if frozen else "RFS_ONLINE_JUDGE_MODEL"
        self.model_name = model or os.getenv(default_env) or os.getenv("RFS_CRITIC_MODEL") or os.getenv("MODEL_VLM") or "gemini-3-pro-preview-thinking"
        self.frozen = frozen
        if not self.api_base or not self.api_key:
            raise RuntimeError("Judge requires API_BASE and API_KEY/GEMINI_API_KEY")

    def evaluate(self, ground_truth: dict, candidates: list[dict], memory: list[dict] | None = None) -> dict:
        shuffled = list(candidates)
        random.SystemRandom().shuffle(shuffled)
        alias_map = {f"image_{index + 1:02d}": item for index, item in enumerate(shuffled)}
        role = "frozen independent acceptance judge" if self.frozen else "online creator-feedback judge"
        feedback_rules = (
            "Do not provide preserve or repair advice. You only score independently."
            if self.frozen else
            "For every candidate provide preserve plus actionable repair entries with region, problem, ground_truth_basis, and instruction."
        )
        memory_text = json.dumps((memory or [])[-8:], ensure_ascii=False) if not self.frozen else "[]"
        prompt = f"""
You are a {role} for complete scientific framework images.
Judge only against the supplied Ground Truth. Candidate aliases are randomized and contain no creator metadata.
{feedback_rules}
Scientific errors and invented content are blocking issues. Human aesthetic preferences are part of Ground Truth.
Scores must be numbers from 0 to 1. Output JSON only.

Schema:
{{
  "summary": "...",
  "evaluations": [{{
    "candidate_id": "image_01",
    "scientific_score": 0.0,
    "aesthetic_score": 0.0,
    "visual_quality_score": 0.0,
    "total_score": 0.0,
    "blocking_issues": [],
    "preserve": [],
    "repair": [{{"region":"...","problem":"...","ground_truth_basis":"...","instruction":"..."}}],
    "confidence": 0.0,
    "summary": "..."
  }}]
}}

Ground Truth:
{json.dumps(ground_truth, ensure_ascii=False)}

Prior critique-outcome memory (effective/ineffective advice only):
{memory_text}
""".strip()
        content = [{"type": "text", "text": prompt}]
        aesthetics = ground_truth.get("aesthetic_preferences", {})
        for label, key in (("Positive aesthetic reference", "positive_references"), ("Negative aesthetic reference", "negative_references")):
            for reference in aesthetics.get(key, []) if isinstance(aesthetics.get(key), list) else []:
                path = Path(reference)
                content.extend([
                    {"type": "text", "text": label},
                    {"type": "image_url", "image_url": {"url": _image_data_url(path)}},
                ])
        for alias, item in alias_map.items():
            path = Path(item["path"])
            content.extend([
                {"type": "text", "text": f"Candidate alias: {alias}"},
                {"type": "image_url", "image_url": {"url": _image_data_url(path)}},
            ])
        payload = {"model": self.model_name, "messages": [{"role": "user", "content": content}], "temperature": 0.0 if self.frozen else 0.1}
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    data=json.dumps(payload),
                    timeout=240,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise RuntimeError(f"Judge request returned HTTP {response.status_code}")
                response.raise_for_status()
                break
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    raise
                time.sleep(2.0 * (2**attempt))
        if response is None:
            raise RuntimeError(str(last_error))
        raw = _extract_json(response.json()["choices"][0]["message"]["content"])
        normalized = normalize_judgement(raw, list(alias_map), ground_truth["weights"], allow_feedback=not self.frozen)
        normalized["model"] = self.model_name
        normalized["frozen"] = self.frozen
        normalized["alias_to_candidate"] = {alias: item["candidate_id"] for alias, item in alias_map.items()}
        return normalized
