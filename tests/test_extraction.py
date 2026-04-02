"""Tests for document extraction (extraction.py)."""

import io
import zipfile

from extraction import (
    decode_text_document,
    extract_docx_text,
    extract_pptx_text,
    normalize_document_text,
)


class TestNormalizeDocumentText:
    def test_collapses_whitespace(self):
        result = normalize_document_text("  hello   world  ", max_chars=100)
        assert result == "hello world"

    def test_strips_blank_lines(self):
        result = normalize_document_text("line1\n\n\n\nline2", max_chars=100)
        assert result == "line1\nline2"

    def test_truncates_with_ellipsis(self):
        result = normalize_document_text("abcdefghij", max_chars=5)
        assert len(result) <= 5
        assert result.endswith("…")

    def test_empty_returns_empty(self):
        assert normalize_document_text("", max_chars=100) == ""
        assert normalize_document_text("   \n  \n  ", max_chars=100) == ""

    def test_zero_max_chars(self):
        assert normalize_document_text("anything", max_chars=0) == ""


class TestDecodeTextDocument:
    def test_utf8(self):
        raw = "Hello café".encode("utf-8")
        assert decode_text_document(raw) == "Hello café"

    def test_replace_on_invalid_bytes(self):
        # Bytes that aren't valid UTF-8 still decode without raising
        raw = b"\xff\xfe\x00\x01"
        result = decode_text_document(raw)
        assert isinstance(result, str)


class TestExtractDocxText:
    def _make_docx(self, paragraphs: list[str]) -> bytes:
        """Create a minimal .docx in memory."""
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        body_parts = []
        for text in paragraphs:
            body_parts.append(
                f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
            )
        doc_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<w:document xmlns:w="{ns}"><w:body>'
            + "".join(body_parts)
            + "</w:body></w:document>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", doc_xml)
        return buf.getvalue()

    def test_single_paragraph(self):
        docx = self._make_docx(["Hello World"])
        assert extract_docx_text(docx) == "Hello World"

    def test_multiple_paragraphs(self):
        docx = self._make_docx(["First", "Second", "Third"])
        result = extract_docx_text(docx)
        assert "First" in result
        assert "Third" in result

    def test_empty_document(self):
        docx = self._make_docx([])
        assert extract_docx_text(docx) == ""


class TestExtractPptxText:
    def _make_pptx(self, slides: list[list[str]]) -> bytes:
        """Create a minimal .pptx in memory."""
        a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i, texts in enumerate(slides, start=1):
                text_elems = "".join(f'<a:t>{t}</a:t>' for t in texts)
                slide_xml = (
                    f'<?xml version="1.0"?>'
                    f'<p:sld xmlns:p="{p_ns}" xmlns:a="{a_ns}">'
                    f'{text_elems}</p:sld>'
                )
                zf.writestr(f"ppt/slides/slide{i}.xml", slide_xml)
        return buf.getvalue()

    def test_single_slide(self):
        pptx = self._make_pptx([["Hello Slide"]])
        result = extract_pptx_text(pptx)
        assert "Hello Slide" in result

    def test_multiple_slides(self):
        pptx = self._make_pptx([["Slide 1 text"], ["Slide 2 text"]])
        result = extract_pptx_text(pptx)
        assert "Slide 1" in result
        assert "Slide 2" in result
