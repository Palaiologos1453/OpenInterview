from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET


SUPPORTED_RESUME_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}


def extract_resume_text(filename: str, content: bytes) -> dict:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_RESUME_SUFFIXES:
        raise ValueError("仅支持 .txt、.md、.pdf、.docx 简历文件。")
    if len(content) > 8 * 1024 * 1024:
        raise ValueError("简历文件超过 8MB，请先导出为文本或压缩内容后再导入。")

    if suffix in {".txt", ".md"}:
        text = _decode_text(content)
    elif suffix == ".docx":
        text = _extract_docx_text(content)
    else:
        text = _extract_pdf_text(content)

    text = _normalize_text(text)
    if not text:
        raise ValueError("未能从文件中提取到文本，请确认不是扫描版图片简历。")
    return {
        "filename": filename,
        "type": suffix.lstrip("."),
        "text": text,
        "chars": len(text),
    }


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_docx_text(content: bytes) -> str:
    paragraphs: list[str] = []
    with ZipFile(BytesIO(content)) as archive:
        names = [
            name for name in archive.namelist()
            if name.startswith("word/") and name.endswith(".xml")
            and ("document" in name or "header" in name or "footer" in name)
        ]
        for name in names:
            root = ET.fromstring(archive.read(name))
            for node in root.iter():
                if node.tag.endswith("}t") and node.text:
                    paragraphs.append(node.text)
                elif node.tag.endswith("}tab"):
                    paragraphs.append("\t")
                elif node.tag.endswith("}br"):
                    paragraphs.append("\n")
            paragraphs.append("\n")
    return "".join(paragraphs)


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise ValueError(
            "PDF 简历解析需要可选依赖 pypdf。请运行 pip install pypdf，或先把简历复制为文本。"
        ) from exc

    reader = PdfReader(BytesIO(content))
    pages = []
    for page in reader.pages[:20]:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
