from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Protocol

import requests


class ImageProvider(Protocol):
    @property
    def supports_edit(self) -> bool: ...

    def generate(self, prompt: str, output_path: Path, aspect_ratio: str) -> dict: ...

    def edit(self, source_path: Path, prompt: str, output_path: Path, aspect_ratio: str) -> dict: ...


def _size(aspect_ratio: str) -> str:
    try:
        left, right = aspect_ratio.split(":", 1)
        ratio = float(left) / float(right)
    except Exception:
        ratio = 16 / 9
    if ratio >= 1.25:
        return "1536x1024"
    if ratio <= 0.80:
        return "1024x1536"
    return "1024x1024"


def _save_openai_image(data: dict, output_path: Path) -> None:
    items = data.get("data") if isinstance(data.get("data"), list) else []
    if not items:
        raise RuntimeError("Image response did not contain data")
    item = items[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if item.get("b64_json"):
        output_path.write_bytes(base64.b64decode(item["b64_json"]))
        return
    if item.get("url"):
        response = requests.get(item["url"], timeout=180)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return
    raise RuntimeError("Image response did not contain b64_json or url")


def _save_gemini_image(data: dict, output_path: Path) -> None:
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            encoded = inline.get("data")
            if encoded:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(base64.b64decode(encoded))
                return
    raise RuntimeError("Gemini image response did not contain inline image data")


class OpenAICompatibleImageProvider:
    def __init__(self, model: str | None = None, retries: int = 2):
        self.api_base = os.getenv("API_BASE", "https://yunwu.ai/v1").rstrip("/")
        self.api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("RFS_IMAGE_MODEL") or os.getenv("IMAGE_MODEL") or "image-2"
        if self.model == "image-2":
            self.model = "gpt-image-2"
        self.edit_url = os.getenv("RFS_IMAGE_EDIT_URL", "").strip()
        self.edit_model = os.getenv("RFS_IMAGE_EDIT_MODEL") or self.model
        self.gemini_url = os.getenv("GEMINI_GEN_IMG_URL", "").strip()
        self.retries = max(0, min(5, int(retries)))
        if not self.api_key:
            raise RuntimeError("Image provider requires API_KEY/GEMINI_API_KEY")

    @property
    def supports_edit(self) -> bool:
        return bool(self.edit_url or self.gemini_url)

    def _post_json(self, url: str, payload: dict, timeout: int = 300) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    data=json.dumps(payload),
                    timeout=timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise RuntimeError(f"Image request returned HTTP {response.status_code}")
                response.raise_for_status()
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
                time.sleep(min(20.0, 2.0 * (2**attempt)))
        raise RuntimeError(str(last_error))

    def generate(self, prompt: str, output_path: Path, aspect_ratio: str) -> dict:
        payload = {"model": self.model, "prompt": prompt, "n": 1, "size": _size(aspect_ratio)}
        response = self._post_json(f"{self.api_base}/images/generations", payload)
        _save_openai_image(response.json(), output_path)
        return {"mode": "generate", "model": self.model, "endpoint": "images/generations"}

    def edit(self, source_path: Path, prompt: str, output_path: Path, aspect_ratio: str) -> dict:
        if self.edit_url:
            with source_path.open("rb") as image_handle:
                response = requests.post(
                    self.edit_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"model": self.edit_model, "prompt": prompt, "n": "1", "size": _size(aspect_ratio)},
                    files={"image": (source_path.name, image_handle, "image/png")},
                    timeout=300,
                )
            response.raise_for_status()
            _save_openai_image(response.json(), output_path)
            return {"mode": "edit", "model": self.edit_model, "endpoint": self.edit_url}
        if self.gemini_url:
            encoded = base64.b64encode(source_path.read_bytes()).decode("utf-8")
            payload = {
                "contents": [{"role": "user", "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "image/png", "data": encoded}},
                ]}],
                "generationConfig": {"responseModalities": ["IMAGE"]},
            }
            response = self._post_json(self.gemini_url, payload)
            _save_gemini_image(response.json(), output_path)
            return {"mode": "edit", "model": "gemini-image", "endpoint": self.gemini_url}
        raise NotImplementedError("No image editing endpoint is configured")
