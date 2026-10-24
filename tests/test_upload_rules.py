from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.project_files import service
from app.project_files.upload_rules import MB, check_size, max_size_for, sniff_problem

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32
PDF = b"%PDF-1.7\n" + b"\0" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
EXE = b"MZ\x90\x00" + b"\0" * 60


@pytest.mark.parametrize(
    "header,ext",
    [(PNG, ".png"), (JPEG, ".jpg"), (JPEG, ".JPEG"), (PDF, ".pdf"), (WEBP, ".webp"), (b"PK\x03\x04..", ".docx"),
     (b"8BPS....", ".psd"), (b"", ".png"), (b"#!/bin/sh\n", ".sh"),
     (WEBP, ".jpg"), (PNG, ".jpg"), (JPEG, ".png")]  # mislabelled but genuine images are fine,
)
def test_genuine_files_pass(header, ext):
    assert sniff_problem(header, ext) is None


@pytest.mark.parametrize(
    "header,ext",
    [(EXE, ".pdf"), (EXE, ".jpg"), (EXE, ".psd"), (b"\x7fELF....", ".txt"), (b"<html><script>", ".png"),
     (JPEG, ".pdf"), (b"not a zip", ".docx"), (EXE, ".webp"), (b"<svg onload=x>", ".jpg")],
)
def test_disguised_or_mismatched_files_are_flagged(header, ext):
    assert sniff_problem(header, ext)


def test_size_limits_depend_on_the_type():
    assert max_size_for(".pdf") < max_size_for(".psd")
    check_size("a.psd", 500 * MB)  # large design file: fine
    with pytest.raises(HTTPException) as err:
        check_size("a.pdf", 500 * MB)
    assert err.value.status_code == 413


def test_a_rejected_upload_is_not_left_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    upload = UploadFile(file=BytesIO(EXE), filename="logo.png")
    with pytest.raises(HTTPException) as err:
        service.save_streaming_file(upload, "logo.png")
    assert err.value.status_code == 400
    assert list(Path(tmp_path).iterdir()) == []

    ok = service.save_streaming_file(UploadFile(file=BytesIO(PNG), filename="logo.png"), "logo.png")
    assert (tmp_path / ok).exists()
