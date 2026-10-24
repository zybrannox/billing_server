"""Per-type size limits and content sniffing for uploads.

The extension denylist in service.py stops obviously dangerous names, but a
name is just a label: `invoice.pdf` can hold a Windows executable, and a
"photo.jpg" that is really an HTML page is how stored-XSS and malware
distribution usually start. These checks look at the bytes.

Deliberately conservative - design work arrives in every format imaginable
(PSD, AI, CDR, EPS, HEIC, ...), so a type is only *verified* when it has a
reliable signature; everything else is accepted unless its bytes are a native
executable.
"""
from pathlib import Path

from fastapi import HTTPException

MB = 1024 * 1024
GB = 1024 * MB

# Largest accepted file per extension; anything not listed gets DEFAULT_MAX.
DEFAULT_MAX = 1 * GB
_MAX_BY_EXT: dict[str, int] = {
    **dict.fromkeys((".pdf",), 200 * MB),
    **dict.fromkeys((".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".rtf"), 50 * MB),
    **dict.fromkeys((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"), 300 * MB),
}


def max_size_for(ext: str) -> int:
    return _MAX_BY_EXT.get(ext.lower(), DEFAULT_MAX)


def check_size(filename: str, size: int) -> None:
    ext = Path(filename).suffix.lower()
    limit = max_size_for(ext)
    if size > limit:
        raise HTTPException(
            status_code=413,
            detail=f"File '{filename}' exceeds the {limit // MB} MB limit for {ext or 'this'} files",
        )


# Native executables, whatever they're named: Windows PE, Linux ELF, Mach-O.
_EXECUTABLE_MAGIC = (
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe",
)

# Any genuine raster image is accepted under any raster-image extension: a
# WebP or PNG saved as "photo.jpg" is extremely common (browsers and chat apps
# do it), and rejecting it would block honest uploads. What matters is that the
# bytes are an image and not something else wearing an image's name.
_IMAGE_SIGNATURES: tuple[tuple[int, bytes], ...] = (
    (0, b"\xff\xd8\xff"),
    (0, b"\x89PNG\r\n\x1a\n"),
    (0, b"GIF87a"), (0, b"GIF89a"),
    (0, b"BM"),
    (0, b"II*\x00"), (0, b"MM\x00*"),
)
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff"}
_ZIP_SIGNATURES = ((0, b"PK\x03\x04"), (0, b"PK\x05\x06"))
_SIGNATURES: dict[str, tuple[tuple[int, bytes], ...]] = {
    ".zip": _ZIP_SIGNATURES,
    ".docx": _ZIP_SIGNATURES,
    ".xlsx": _ZIP_SIGNATURES,
    ".pptx": _ZIP_SIGNATURES,
}

HEADER_BYTES = 1024


def sniff_problem(header: bytes, ext: str) -> str | None:
    """Why `header` (the file's first bytes) can't be a genuine `ext` file, or None."""
    if not header:
        return None
    if header.startswith(_EXECUTABLE_MAGIC):
        return "looks like a program, not a document or image"
    ext = ext.lower()
    if ext == ".pdf":
        return None if b"%PDF-" in header else "isn't a valid PDF"
    is_webp = header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if ext == ".webp" or ext in _IMAGE_EXTENSIONS:
        genuine = is_webp or any(header[off : off + len(sig)] == sig for off, sig in _IMAGE_SIGNATURES)
        return None if genuine else "isn't a valid image"
    signatures = _SIGNATURES.get(ext)
    if signatures and not any(header[off : off + len(sig)] == sig for off, sig in signatures):
        return f"doesn't contain a valid {ext} file"
    return None


def verify_file(path: Path, display_name: str) -> None:
    """Raises 400 if the stored bytes don't match what the name claims."""
    with path.open("rb") as fh:
        header = fh.read(HEADER_BYTES)
    problem = sniff_problem(header, Path(display_name).suffix)
    if problem:
        raise HTTPException(status_code=400, detail=f"'{display_name}' {problem}.")
