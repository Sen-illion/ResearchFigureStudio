from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", str(text or "")).strip()


def _read_pages(path: Path, max_chars: int) -> tuple[list[dict[str, Any]], str]:
    suffix = path.suffix.lower()
    pages: list[dict[str, Any]] = []
    loader = "plain"
    if suffix == ".pdf":
        loader = "pymupdf"
        try:
            import fitz

            document = fitz.open(str(path))
            used = 0
            for index, page in enumerate(document, 1):
                text = page.get_text("text")
                remaining = max_chars - used
                if remaining <= 0:
                    break
                text = text[:remaining]
                pages.append({"page": index, "text": text})
                used += len(text)
            document.close()
        except Exception as exc:
            raise RuntimeError(f"PDF extraction failed: {exc}") from exc
    elif suffix == ".docx":
        loader = "python-docx"
        try:
            import docx

            document = docx.Document(str(path))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)[:max_chars]
            pages.append({"page": 1, "text": text})
        except Exception as exc:
            raise RuntimeError(f"DOCX extraction failed: {exc}") from exc
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        pages.append({"page": 1, "text": text})
    return pages, loader


def _chunk_page(text: str, target_chars: int = 2200) -> list[str]:
    paragraphs = [_clean(item) for item in re.split(r"\n\s*\n", text) if _clean(item)]
    if not paragraphs:
        paragraphs = [_clean(item) for item in text.splitlines() if _clean(item)]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if current and size + len(paragraph) > target_chars:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(paragraph)
        size += len(paragraph) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _heading_candidates(text: str) -> list[str]:
    headings: list[str] = []
    for raw in text.splitlines():
        line = _clean(raw)
        if not 3 <= len(line) <= 100:
            continue
        if re.match(r"^(?:\d+(?:\.\d+)*[.)]?\s+|[IVX]+[.)]\s+|第[一二三四五六七八九十]+[章节])", line):
            value = re.sub(r"^(?:\d+(?:\.\d+)*[.)]?\s+|[IVX]+[.)]\s+)", "", line).strip()
            if value and value not in headings:
                headings.append(value)
    return headings[:30]


def _document_index(pages: list[dict[str, Any]], headings: list[str]) -> dict:
    sections = []
    formulas = []
    tables = []
    figures = []
    seen_sections = set()
    formula_pattern = re.compile(r"(?:[A-Za-zΑ-Ωα-ω][A-Za-z0-9_{}^\-]*\s*=\s*[^=\n]{3,}|[∑∫∂∇≈≤≥]\s*[^\n]{3,}|\([^\n]{2,80}\)\s*\(\d+\)\s*$)")
    table_pattern = re.compile(r"^(?:Table|TABLE|表)\s*[A-Za-z0-9一二三四五六七八九十.：: -]+", re.IGNORECASE)
    figure_pattern = re.compile(r"^(?:Figure|FIGURE|Fig\.|图)\s*[A-Za-z0-9一二三四五六七八九十.：: -]+", re.IGNORECASE)
    for page in pages:
        for raw in page.get("text", "").splitlines():
            line = _clean(raw)
            if not line:
                continue
            for heading in headings:
                if heading.lower() in line.lower() and heading not in seen_sections:
                    sections.append({"id": f"section_{len(sections) + 1:03d}", "title": heading, "page": page["page"]})
                    seen_sections.add(heading)
                    break
            if len(formulas) < 120 and 4 <= len(line) <= 240 and formula_pattern.search(line):
                formulas.append({"id": f"formula_{len(formulas) + 1:03d}", "page": page["page"], "text": line})
            if len(tables) < 80 and table_pattern.match(line):
                tables.append({"id": f"table_{len(tables) + 1:03d}", "page": page["page"], "caption": line})
            if len(figures) < 80 and figure_pattern.match(line):
                figures.append({"id": f"figure_{len(figures) + 1:03d}", "page": page["page"], "caption": line})
    return {
        "summary": "Page-aware section, formula, table-caption, and figure-caption index.",
        "sections": sections,
        "formulas": formulas,
        "tables": tables,
        "figures": figures,
    }


def parse_paper(path: str | Path, max_chars: int = 90000) -> dict:
    source = Path(path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Paper does not exist: {source}")
    pages, loader = _read_pages(source, max_chars=max_chars)
    evidence: list[dict[str, Any]] = []
    for page in pages:
        for chunk in _chunk_page(page["text"]):
            if not chunk:
                continue
            evidence_id = f"E{len(evidence) + 1:04d}"
            evidence.append({
                "id": evidence_id,
                "page": page["page"],
                "section_hint": None,
                "text": chunk,
                "char_count": len(chunk),
            })

    all_text = "\n".join(page["text"] for page in pages)
    headings = _heading_candidates(all_text)
    document_index = _document_index(pages, headings)
    for item in evidence:
        low = item["text"].lower()
        item["section_hint"] = next((heading for heading in headings if heading.lower() in low), None)

    if not evidence:
        raise ValueError("No readable paper text was extracted")
    return {
        "summary": "Paper parsed into page-aware evidence chunks.",
        "source_path": str(source),
        "source_name": source.name,
        "source_type": source.suffix.lower(),
        "loader": loader,
        "page_count": len(pages),
        "char_count": len(all_text),
        "headings": headings,
        "document_index": document_index,
        "evidence": evidence,
    }


def evidence_excerpt(parsed: dict, max_chars: int = 58000) -> str:
    lines: list[str] = []
    used = 0
    for item in parsed.get("evidence", []):
        block = f"[{item['id']} | page {item['page']} | {item.get('section_hint') or 'unknown section'}]\n{item['text']}"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n\n".join(lines)
