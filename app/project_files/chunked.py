"""
Large files (e.g. 1GB) can't go through /files/upload in one request when the
app is served through Cloudflare - Cloudflare's own proxy rejects any request
body over ~100MB with a 413, before it ever reaches this server. That's a
platform limit, not something any backend/tunnel config can raise.

This splits an upload into fixed-size chunks client-side (see
chunkedUpload.ts), each safely under that cap, uploaded independently and
reassembled here.
"""
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Dict, Set

from fastapi import HTTPException

from .service import BLOCKED_EXTENSIONS, UPLOAD_DIR

# Must match CHUNK_SIZE in src/utils/chunkedUpload.ts - the client computes
# each chunk's byte range from it, and this is where those ranges are
# written back to, so the two sides have to agree without either passing it
# over the wire.
CHUNK_SIZE = 20 * 1024 * 1024  # 20MB

MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB - matches the existing per-file cap

# Abandoned sessions (browser closed mid-upload, etc.) are cleaned up after
# this long rather than lingering on disk forever.
SESSION_TTL_SECONDS = 2 * 60 * 60

CHUNK_UPLOAD_DIR = UPLOAD_DIR / ".chunked"
CHUNK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class ChunkedUploadSession:
    __slots__ = (
        "upload_id",
        "filename",
        "ext",
        "total_size",
        "total_chunks",
        "received",
        "temp_path",
        "created_at",
        "lock",
    )

    def __init__(self, filename: str, total_size: int, total_chunks: int):
        self.upload_id = uuid.uuid4().hex
        self.filename = filename
        self.ext = Path(filename).suffix.lower()
        self.total_size = total_size
        self.total_chunks = total_chunks
        self.received: Set[int] = set()
        self.temp_path = CHUNK_UPLOAD_DIR / f"{self.upload_id}.part"
        self.created_at = time.time()
        # Guards writes to this session's temp file - chunks can arrive
        # concurrently (the client uploads several in parallel), and each
        # write is a seek+write pair that must not interleave with another.
        self.lock = Lock()


# In-memory only - fine for this single-process deployment. A backend
# restart mid-upload loses in-flight sessions, same tradeoff as any
# resumable-upload implementation without a persisted session store; the
# client just re-inits and starts over, which is rare enough not to be
# worth the added complexity of persisting this.
_sessions: Dict[str, ChunkedUploadSession] = {}
_sessions_lock = Lock()


def _gc_stale_sessions() -> None:
    now = time.time()
    stale = [
        uid
        for uid, s in _sessions.items()
        if now - s.created_at > SESSION_TTL_SECONDS
    ]
    for uid in stale:
        s = _sessions.pop(uid, None)
        if s and s.temp_path.exists():
            s.temp_path.unlink()


def init_upload(filename: str, total_size: int, total_chunks: int) -> str:
    ext = Path(filename).suffix.lower()
    if not ext or ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext or 'unknown'}' isn't allowed.",
        )
    if total_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, detail="File exceeds maximum size of 1GB"
        )
    if total_chunks < 1:
        raise HTTPException(status_code=400, detail="Invalid chunk count")

    with _sessions_lock:
        _gc_stale_sessions()
        session = ChunkedUploadSession(filename, total_size, total_chunks)
        # Pre-allocate the full size up front (sparse on APFS/most
        # filesystems, so this doesn't actually cost 1GB of disk until
        # chunks are written) so each chunk can be written to its absolute
        # offset independently, in any order or concurrently, rather than
        # needing to serialize writes through a single append point.
        with session.temp_path.open("wb") as f:
            if total_size > 0:
                f.seek(total_size - 1)
                f.write(b"\0")
        _sessions[session.upload_id] = session

    return session.upload_id


def write_chunk(upload_id: str, chunk_index: int, data: bytes) -> None:
    session = _sessions.get(upload_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )
    if chunk_index < 0 or chunk_index >= session.total_chunks:
        raise HTTPException(status_code=400, detail="Invalid chunk index")

    offset = chunk_index * CHUNK_SIZE
    with session.lock:
        with session.temp_path.open("r+b") as f:
            f.seek(offset)
            f.write(data)
        session.received.add(chunk_index)


def complete_upload(upload_id: str) -> str:
    session = _sessions.get(upload_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )
    if len(session.received) != session.total_chunks:
        missing = session.total_chunks - len(session.received)
        raise HTTPException(
            status_code=400, detail=f"Upload incomplete: {missing} chunk(s) missing"
        )

    stored_name = f"{uuid.uuid4().hex}{session.ext}"
    final_path = UPLOAD_DIR / stored_name
    # Same filesystem (uploads/.chunked -> uploads/), so this is a fast
    # rename, not a second full data copy of a file that was already
    # written to disk chunk by chunk.
    session.temp_path.rename(final_path)

    with _sessions_lock:
        _sessions.pop(upload_id, None)

    return stored_name
