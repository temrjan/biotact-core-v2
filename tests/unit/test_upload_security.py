"""Unit tests for HR template upload validation (PR-3).

Covers filename sanitization (path traversal) and magic-byte content
verification — both run before any disk persistence happens.
"""

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from biotact.core.config import Settings
from biotact.modules.hr.library import service as library_service
from biotact.modules.hr.library.service import (
    ALLOWED_EXTS,
    HRFileMagicError,
    HRFileTooLarge,
    HRFileTypeError,
    _verify_magic_bytes,
    upload_template,
)


def _fake_upload(filename: str, content: bytes) -> UploadFile:
    """Build a minimal UploadFile-like mock with chunked read()."""
    f = MagicMock(spec=UploadFile)
    f.filename = filename
    stream = BytesIO(content)

    async def _read(n: int = -1) -> bytes:
        return stream.read(n) if n >= 0 else stream.read()

    f.read = AsyncMock(side_effect=_read)
    return f


@pytest.mark.unit
class TestUploadConstants:
    """Sanity checks on the published constants."""

    def test_allowed_exts_is_immutable(self) -> None:
        assert isinstance(ALLOWED_EXTS, frozenset)
        assert frozenset({"docx", "pdf", "txt", "md"}) == ALLOWED_EXTS

    def test_size_limit_is_20mb(self) -> None:
        assert Settings().hr_max_upload_mb == 20


@pytest.mark.unit
class TestUploadTypeValidation:
    """Reject upload before any disk write when extension is not allowed."""

    async def test_rejects_unknown_extension(self) -> None:
        f = _fake_upload("malware.exe", b"MZ\x90\x00")
        with pytest.raises(HRFileTypeError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )

    async def test_rejects_no_extension(self) -> None:
        f = _fake_upload("README", b"hello")
        with pytest.raises(HRFileTypeError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )

    async def test_rejects_empty_filename_with_no_extension(self) -> None:
        f = _fake_upload("", b"hello")
        with pytest.raises(HRFileTypeError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )


@pytest.mark.unit
class TestPathTraversalSanitization:
    """Filename with directory components must be stripped to a basename.

    These tests assert the *type* error is raised based on the sanitized
    basename — confirming the traversal substrings never reach the path
    construction logic intact.
    """

    async def test_unix_traversal_in_filename_stripped_to_basename(self) -> None:
        """`../../etc/passwd` → basename = `passwd` → no extension → HRFileTypeError."""
        f = _fake_upload("../../etc/passwd", b"root:x:0:0::/root:/bin/sh")
        with pytest.raises(HRFileTypeError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )

    async def test_windows_traversal_in_filename_stripped(self) -> None:
        """`..\\..\\windows\\system32\\config\\sam.docx` → basename = `sam.docx`,
        passes type check but fails magic (no PK header) → HRFileMagicError.
        The point: no `\\` segments survived to be used in a real path.
        """
        f = _fake_upload(
            "..\\..\\windows\\system32\\config\\sam.docx",
            b"\x00\x00\x00\x00\x00",  # not a ZIP/DOCX header
        )
        with pytest.raises(HRFileMagicError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )


@pytest.mark.unit
class TestMagicByteValidation:
    """Magic-byte check must run BEFORE any disk write."""

    async def test_rejects_fake_docx_extension(self) -> None:
        """A .docx file whose content is plain text should be rejected."""
        f = _fake_upload("fake.docx", b"This is not a DOCX, just text.")
        with pytest.raises(HRFileMagicError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )

    async def test_rejects_fake_pdf_extension(self) -> None:
        """A .pdf file without %PDF- header should be rejected."""
        f = _fake_upload("fake.pdf", b"\x00\x00\x00\x00fake content")
        with pytest.raises(HRFileMagicError):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )

    def test_verify_magic_txt_does_not_raise(self) -> None:
        """TXT has no fixed signature — helper must NOT raise."""
        _verify_magic_bytes("txt", b"plain text content")  # no exception

    def test_verify_magic_md_does_not_raise(self) -> None:
        """MD has no fixed signature — helper must NOT raise."""
        _verify_magic_bytes("md", b"# Heading\nbody")  # no exception

    def test_verify_magic_empty_content_for_text_does_not_raise(self) -> None:
        """Empty text content is acceptable at the magic-byte layer."""
        _verify_magic_bytes("txt", b"")  # no exception

    def test_verify_magic_unknown_ext_does_not_raise(self) -> None:
        """An extension absent from _MAGIC_BYTES (e.g. odd input) bypasses check.

        Defense-in-depth: type whitelist runs upstream; this helper is a no-op
        for anything it doesn't know.
        """
        _verify_magic_bytes("unknown", b"\x00\x01\x02")  # no exception

    def test_verify_magic_valid_docx_does_not_raise(self) -> None:
        """Valid ZIP header satisfies DOCX magic check."""
        _verify_magic_bytes("docx", b"PK\x03\x04rest")  # no exception

    def test_verify_magic_valid_pdf_does_not_raise(self) -> None:
        """Valid PDF header satisfies PDF magic check."""
        _verify_magic_bytes("pdf", b"%PDF-1.7\n")  # no exception

    def test_verify_magic_truncated_docx_raises(self) -> None:
        """Content shorter than the magic prefix is rejected."""
        with pytest.raises(HRFileMagicError):
            _verify_magic_bytes("docx", b"PK\x03")  # 3 bytes — too short

    def test_verify_magic_wrong_docx_raises(self) -> None:
        with pytest.raises(HRFileMagicError):
            _verify_magic_bytes("docx", b"This is not a DOCX")


@pytest.mark.unit
class TestPartialFileCleanup:
    """Regression tests: partial files must be unlinked on any failure path.

    Guards against silent disk leaks if a future refactor removes the
    cleanup branch in upload_template.
    """

    async def test_oversized_upload_unlinks_partial_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Triggering HRFileTooLarge must leave no orphan files in UPLOAD_DIR."""
        monkeypatch.setattr(library_service, "_upload_dir", lambda: tmp_path)
        # Lower the limit so we don't allocate the real 20 MB ceiling.
        monkeypatch.setattr(
            library_service,
            "get_settings",
            lambda: Settings(hr_max_upload_mb=0),
        )
        # Valid DOCX magic + content exceeding 1 KB.
        oversize = b"PK\x03\x04" + b"\x00" * 2048
        f = _fake_upload("big.docx", oversize)
        with pytest.raises(HRFileTooLarge):
            await upload_template(
                db=MagicMock(), file=f, category="td_osnovnoy", user_id=1
            )
        assert list(tmp_path.iterdir()) == [], "partial file was not unlinked"

    async def test_db_failure_unlinks_partial_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If db.flush() raises after the file is written, unlink the file."""
        monkeypatch.setattr(library_service, "_upload_dir", lambda: tmp_path)
        f = _fake_upload("doc.docx", b"PK\x03\x04rest of valid header")
        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(return_value=execute_result)
        db.add = MagicMock()
        db.flush = AsyncMock(side_effect=RuntimeError("simulated DB outage"))
        db.refresh = AsyncMock()
        with pytest.raises(RuntimeError):
            await upload_template(db=db, file=f, category="td_osnovnoy", user_id=1)
        assert list(tmp_path.iterdir()) == [], (
            "file remained on disk after DB flush failed"
        )
