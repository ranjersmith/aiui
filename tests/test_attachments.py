"""Tests for attachment handling (attachments.py)."""

import base64

import pytest

from attachments import (
    Attachment,
    attachment_name,
    decode_attachment_data_url,
    validate_attachments,
)


class TestAttachmentName:
    def test_with_name(self):
        att = Attachment(type="document", name="readme.md")
        assert attachment_name(att) == "readme.md"

    def test_without_name(self):
        att = Attachment(type="image")
        assert attachment_name(att) == "attachment"


class TestDecodeAttachmentDataUrl:
    def test_valid_data_url(self):
        content = base64.b64encode(b"hello world").decode()
        data_url = f"data:text/plain;base64,{content}"
        mime, raw = decode_attachment_data_url(data_url)
        assert raw == b"hello world"
        assert mime == "text/plain"

    def test_invalid_data_url_raises(self):
        with pytest.raises(ValueError):
            decode_attachment_data_url("not-a-data-url")

    def test_empty_data_url_raises(self):
        with pytest.raises(ValueError):
            decode_attachment_data_url("")


class TestValidateAttachments:
    def test_empty_list_is_ok(self):
        validate_attachments([])

    def test_valid_document_attachment(self):
        att = Attachment(type="document", name="file.txt")
        validate_attachments([att])

    def test_valid_image_attachment(self):
        att = Attachment(type="image", name="photo.png", data_url="data:image/png;base64,abc")
        validate_attachments([att])
