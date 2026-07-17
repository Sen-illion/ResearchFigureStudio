from __future__ import annotations

import re
import sys
from pathlib import Path

from argostranslate import translate
from ftfy import fix_text


ROOT = Path(r"D:\ResearchFigureStudio")
SOURCE_DIR = ROOT / "tmp" / "pdfs"
OUTPUT_DIR = ROOT / "output" / "translations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PAPERS = [
    {
        "source": SOURCE_DIR / "scidoc.txt",
        "output": OUTPUT_DIR / "01_SciDoc2Diagrammer-MAF_中文全译初稿.md",
        "title_en": "SciDoc2Diagrammer-MAF: Towards Generation of Scientific Diagrams from Documents guided by Multi-Aspect Feedback Refinement",
        "title_zh": "SciDoc2Diagrammer-MAF：基于多维反馈精炼的科研文档科学图生成方法",
        "authors": "Ishani Mondal, Zongxia Li, Yufang Hou, Anandhavelu Natarajan, Aparna Garimella, Jordan Boyd-Graber",
    },
    {
        "source": SOURCE_DIR / "structured_ie.txt",
        "output": OUTPUT_DIR / "02_Structured_Information_Extraction_中文全译初稿.md",
        "title_en": "Structured information extraction from scientific text with large language models",
        "title_zh": "使用大语言模型从科学文本中抽取结构化信息",
        "authors": "论文作者及单位信息见原始 PDF",
    },
    {
        "source": SOURCE_DIR / "scirex.txt",
        "output": OUTPUT_DIR / "03_SciREX_中文全译初稿.md",
        "title_en": "SciREX: A Challenge Dataset for Document-Level Information Extraction",
        "title_zh": "SciREX：面向文档级信息抽取的挑战数据集",
        "authors": "论文作者及单位信息见原始 PDF",
    },
    {
        "source": SOURCE_DIR / "diagrammergpt.txt",
        "output": OUTPUT_DIR / "04_DiagrammerGPT_中文全译初稿.md",
        "title_en": "DiagrammerGPT: Generating Open-Domain, Open-Platform Diagrams via LLM Planning",
        "title_zh": "DiagrammerGPT：通过大语言模型规划生成开放领域、开放平台图示",
        "authors": "论文作者及单位信息见原始 PDF",
    },
]


SECTION_RE = re.compile(
    r"^(?:Abstract|Introduction|Background|Methodology|Methods?|Results?|Discussion|Conclusion|"
    r"Conclusions|Limitations|Ethics Statement|Acknowledgements?|References|Appendix|"
    r"\d+(?:\.\d+)*\s+\S.+|[A-Z]\.\s+\S.+)$",
    re.IGNORECASE,
)


def clean_lines(raw: str) -> list[str]:
    raw = fix_text(raw)
    raw = re.sub(r"([A-Za-z])\-\n([a-z])", r"\1\2", raw)
    lines: list[str] = []
    for original in raw.splitlines():
        line = original.strip()
        if not line:
            lines.append("")
            continue
        if re.fullmatch(r"--- PAGE \d+ ---", line):
            continue
        if re.fullmatch(r"\d{4,6}", line):
            continue
        if "Findings of the Association for Computational Linguistics" in line:
            continue
        if re.match(r"^(?:November|Proceedings of|©|Copyright)", line):
            continue
        lines.append(line)
    return lines


def is_heading(line: str) -> bool:
    if len(line) > 150:
        return False
    return bool(SECTION_RE.match(line))


def make_blocks(lines: list[str]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    buffer: list[str] = []
    in_references = False

    def flush() -> None:
        if buffer:
            text = " ".join(x for x in buffer if x).strip()
            if text:
                blocks.append(("reference" if in_references else "text", text))
            buffer.clear()

    for line in lines:
        if is_heading(line):
            flush()
            normalized = line.lower()
            if normalized == "references":
                in_references = True
            elif in_references and (
                normalized.startswith("appendix")
                or re.match(r"^(?:[9-9]|1[0-9])(?:\.\d+)*\s+", line)
                or re.match(r"^[A-Z]\.\s+", line)
            ):
                in_references = False
            blocks.append(("heading", line))
        elif not line:
            flush()
        else:
            buffer.append(line)
            if sum(len(x) for x in buffer) > 3200:
                flush()
    flush()
    return blocks


HEADING_MAP = {
    "abstract": "摘要",
    "introduction": "引言",
    "background": "背景",
    "method": "方法",
    "methods": "方法",
    "methodology": "方法",
    "results": "结果",
    "result": "结果",
    "discussion": "讨论",
    "conclusion": "结论",
    "conclusions": "结论",
    "limitations": "局限性",
    "ethics statement": "伦理声明",
    "acknowledgement": "致谢",
    "acknowledgements": "致谢",
    "references": "参考文献（保留英文原文）",
    "appendix": "附录",
}


def translate_heading(heading: str) -> str:
    key = heading.strip().lower()
    if key in HEADING_MAP:
        return HEADING_MAP[key]
    match = re.match(r"^(\d+(?:\.\d+)*|[A-Z]\.)\s+(.+)$", heading)
    if match:
        number, text = match.groups()
        return f"{number} {translate.translate(text, 'en', 'zh')}"
    return translate.translate(heading, "en", "zh")


def translate_paper(paper: dict[str, object]) -> None:
    source = Path(paper["source"])
    output = Path(paper["output"])
    lines = clean_lines(source.read_text(encoding="utf-8"))
    blocks = make_blocks(lines)
    rendered = [
        f"# {paper['title_zh']}",
        "",
        f"**英文标题：** {paper['title_en']}",
        "",
        f"**作者：** {paper['authors']}",
        "",
        "> 说明：本文档为离线机器翻译形成的中文全译初稿，已保留公式、数值、图表编号和参考文献引用。参考文献条目保留英文。关键术语与复杂句仍建议结合原 PDF 校对。",
        "",
    ]

    total = len(blocks)
    for index, (kind, content) in enumerate(blocks, start=1):
        if kind == "heading":
            rendered.extend([f"## {translate_heading(content)}", ""])
        elif kind == "reference":
            rendered.extend([content, ""])
        else:
            translated = translate.translate(content, "en", "zh")
            rendered.extend([translated.strip(), ""])
        if index % 10 == 0 or index == total:
            print(f"{output.name}: {index}/{total}", flush=True)

    output.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    print(f"WROTE {output}", flush=True)


def main() -> None:
    requested = set(sys.argv[1:])
    for index, paper in enumerate(PAPERS, start=1):
        if requested and str(index) not in requested:
            continue
        translate_paper(paper)


if __name__ == "__main__":
    main()
