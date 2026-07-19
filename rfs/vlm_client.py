from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_VLM_MODEL = "gemini-3-pro-preview-thinking"


def extract_json(text: str) -> dict:
    cleaned = str(text or "").strip().replace("```json", "```")
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


def vlm_credentials_available() -> bool:
    return bool(os.getenv("API_BASE", "").strip()) and bool((os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip())


def resolve_vlm_model(*env_names: str, explicit_model: str | None = None) -> str:
    if explicit_model:
        return explicit_model
    for name in env_names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return os.getenv("MODEL_VLM", "").strip() or DEFAULT_VLM_MODEL


def call_vlm_json(prompt: str, image_paths: list[str | Path], model: str | None = None, timeout: int = 180, retries: int = 1) -> dict:
    api_base = os.getenv("API_BASE", "").rstrip("/")
    api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_base or not api_key:
        raise RuntimeError("VLM call requires API_BASE and API_KEY/GEMINI_API_KEY environment variables")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for path in image_paths:
        p = Path(path)
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

    payload = {
        "model": model or resolve_vlm_model(),
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }
    last_error: Exception | None = None
    for attempt in range(max(1, int(retries) + 1)):
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=timeout,
            )
            response.raise_for_status()
            content_text = response.json()["choices"][0]["message"]["content"]
            return extract_json(content_text)
        except Exception as exc:
            last_error = exc
            if attempt < max(1, int(retries) + 1) - 1:
                time.sleep(1.5)
    raise last_error or RuntimeError("VLM call failed")
