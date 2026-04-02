"""AIUI document extraction — text extraction from attachments (PDF, DOCX, PPTX, etc.)."""

from __future__ import annotations

import io
import mimetypes
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from config import (
    DRAWINGML_TEXT_TAG,
    ENABLE_EXTERNAL_EXTRACTORS,
    MAX_ATTACHMENT_DATA_URL_CHARS,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_TEXT_CHARS,
    MAX_TOTAL_DOCUMENT_TEXT_CHARS,
    TEXT_DOCUMENT_EXTENSIONS,
    WORDPROCESSINGML_NAMESPACE,
)

from attachments import Attachment, attachment_name, decode_attachment_data_url


def normalize_document_text(text: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(text or "").splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max(1, max_chars - 1)].rstrip()}…"


def decode_text_document(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16le", "utf-16be", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def extract_docx_text(raw_bytes: bytes) -> str:
    paragraphs: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    for paragraph in root.findall(".//w:p", WORDPROCESSINGML_NAMESPACE):
        runs = [node.text for node in paragraph.findall(".//w:t", WORDPROCESSINGML_NAMESPACE) if node.text]
        if runs:
            paragraphs.append("".join(runs))
    return "\n".join(paragraphs)


def extract_pptx_text(raw_bytes: bytes) -> str:
    slides_out: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for index, slide_name in enumerate(slide_names, start=1):
            root = ET.fromstring(archive.read(slide_name))
            texts = [node.text for node in root.iter(DRAWINGML_TEXT_TAG) if node.text]
            if texts:
                slides_out.append(f"Slide {index}: {' '.join(texts)}")
    return "\n\n".join(slides_out)


def extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    reader = PdfReader(io.BytesIO(raw_bytes))
    pages: list[str] = []
    for page in reader.pages:
        extracted = str(page.extract_text() or "").strip()
        if extracted:
            pages.append(extracted)
    return "\n\n".join(pages)


def run_external_document_extractor(
    commands: list[list[str]],
    *,
    raw_bytes: bytes,
    suffix: str,
) -> str:
    for command in commands:
        executable = shutil.which(command[0])
        if not executable:
            continue
        with tempfile.NamedTemporaryFile(suffix=suffix) as temp_file:
            temp_file.write(raw_bytes)
            temp_file.flush()
            try:
                result = subprocess.run(
                    [executable, *command[1:], temp_file.name],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
        extracted = str(result.stdout or "").strip()
        if extracted:
            return extracted
    return ""


def extract_document_text(item: Attachment) -> str:
    data_url = str(item.data_url or "").strip()
    if not data_url:
        return ""
    if len(data_url) > max(1024, MAX_ATTACHMENT_DATA_URL_CHARS):
        return ""

    try:
        parsed_mime_type, raw_bytes = decode_attachment_data_url(data_url)
    except ValueError:
        return ""

    if len(raw_bytes) > max(1, MAX_DOCUMENT_BYTES):
        return ""

    mime_type = (item.mime_type or parsed_mime_type or "").strip().lower()
    name = attachment_name(item, fallback="document")
    suffix = Path(name).suffix.lower()
    guessed_mime_type, _encoding = mimetypes.guess_type(name)
    if not mime_type and guessed_mime_type:
        mime_type = guessed_mime_type.lower()

    try:
        if mime_type.startswith("text/") or suffix in TEXT_DOCUMENT_EXTENSIONS:
            return decode_text_document(raw_bytes)
        if mime_type == "application/pdf" or suffix == ".pdf":
            return extract_pdf_text(raw_bytes)
        if (
            mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or suffix == ".docx"
        ):
            return extract_docx_text(raw_bytes)
        if mime_type in {"application/vnd.ms-powerpoint", "application/mspowerpoint"} or suffix == ".ppt":
            if not ENABLE_EXTERNAL_EXTRACTORS:
                return ""
            return run_external_document_extractor([["catppt"]], raw_bytes=raw_bytes, suffix=".ppt")
        if suffix == ".doc" or mime_type == "application/msword":
            if not ENABLE_EXTERNAL_EXTRACTORS:
                return ""
            return run_external_document_extractor(
                [["catdoc"], ["antiword"]],
                raw_bytes=raw_bytes,
                suffix=".doc",
            )
        if (
            mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            or suffix == ".pptx"
        ):
            return extract_pptx_text(raw_bytes)
    except Exception:
        return ""

    return decode_text_document(raw_bytes) if suffix in TEXT_DOCUMENT_EXTENSIONS else ""


def build_document_context(attachments: list[Attachment]) -> str:
    blocks: list[str] = []
    remaining_chars = max(0, MAX_TOTAL_DOCUMENT_TEXT_CHARS)
    for item in attachments:
        if item.type != "document":
            continue
        if remaining_chars <= 0:
            break

        name = attachment_name(item, fallback="document")
        extracted = extract_document_text(item)
        guidance = "PDF, DOCX, PPTX, TXT, Markdown, CSV, and JSON work best."
        if extracted:
            normalized = normalize_document_text(
                extracted,
                max_chars=min(MAX_DOCUMENT_TEXT_CHARS, remaining_chars),
            )
            if normalized:
                blocks.append(f"[Attached document: {name}]\n{normalized}")
                remaining_chars -= len(normalized)
                continue

        blocks.append(
            f"[Attached document: {name}]\n"
            f"(The file was attached, but its text could not be extracted here. {guidance})"
        )
        remaining_chars -= min(remaining_chars, 240)

    if not blocks:
        return ""
    return "Attached documents:\n\n" + "\n\n".join(blocks)
