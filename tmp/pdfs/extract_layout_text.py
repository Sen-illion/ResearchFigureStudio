from pathlib import Path
import re

import fitz


FILES = [
    ("scidoc", Path(r"D:\Downloads\2024.findings-emnlp.780.pdf")),
    ("structured_ie", Path(r"D:\Downloads\s41467-024-45563-x.pdf")),
    ("scirex", Path(r"D:\Downloads\2020.acl-main.670.pdf")),
    ("diagrammergpt", Path(r"C:\Users\zhang\Downloads\2310.12128v2.pdf")),
]

OUT = Path(r"D:\ResearchFigureStudio\tmp\pdfs")


def block_text(block: tuple) -> str:
    text = block[4].strip()
    text = re.sub(r"([A-Za-z])\-\n([a-z])", r"\1\2", text)
    text = re.sub(r"(?<![.!?:;])\n", " ", text)
    return text.strip()


def page_text(page: fitz.Page) -> str:
    width = page.rect.width
    blocks = [b for b in page.get_text("blocks") if b[4].strip()]
    full, left, right = [], [], []
    for block in blocks:
        x0, y0, x1, _y1 = block[:4]
        block_width = x1 - x0
        if block_width > width * 0.60 or (x0 < width * 0.22 and x1 > width * 0.78):
            full.append(block)
        elif (x0 + x1) / 2 < width / 2:
            left.append(block)
        else:
            right.append(block)

    # Full-width title/section blocks precede the two reading columns. This is
    # imperfect for wide bottom tables but keeps academic two-column prose in
    # substantially better order than a flat y/x sort.
    ordered = (
        sorted(full, key=lambda b: (b[1], b[0]))
        + sorted(left, key=lambda b: (b[1], b[0]))
        + sorted(right, key=lambda b: (b[1], b[0]))
    )
    texts = [block_text(b) for b in ordered]
    return "\n\n".join(t for t in texts if t)


for name, pdf_path in FILES:
    doc = fitz.open(pdf_path)
    pages = [f"\n\n--- PAGE {i + 1} ---\n\n{page_text(page)}" for i, page in enumerate(doc)]
    output = OUT / f"{name}.txt"
    output.write_text("".join(pages), encoding="utf-8")
    print(name, len(doc), output.stat().st_size)
