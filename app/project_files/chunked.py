"""
Large files (e.g. 1GB) can't go through /files/upload in one request when the
app is served through Cloudflare - Cloudflare's own proxy rejects any request
body over ~100MB with a 413, before it ever reaches this server. That's a
platform limit, not something any backend/tunnel config can raise.

This splits an upload into fixed-size chunks client-side (see
chunkedUpload.ts), each safely under that cap, uploaded independently and
reassembled here.
"""
import math
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Dict, Optional, Set

from fastapi import HTTPException
from app.errors import BadRequest

from .service import BLOCKED_EXTENSIONS, UPLOAD_DIR
from .upload_rules import check_size, verify_file

# Must match CHUNK_SIZE in src/utils/chunkedUpload.ts - the client computes
# each chunk's byte range from it, and this is where those ranges are
# written back to, so the two sides have to agree without either passing it
# over the wire.
CHUNK_SIZE = 20 * 1024 * 1024  # 20MB

MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB - matches the existing per-file cap

# Abandoned sessions (browser closed mid-upload, etc.) are cleaned up after
# this long without a chunk arriving, rather than lingering on disk forever.
# Measured from the last activity, not the start: a 1GB file on a slow uplink
# can legitimately take longer than this overall.
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
        "last_activity",
        "stored_name",
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
        self.last_activity = self.created_at
        # Set once complete_upload has moved the file into place, so a retried
        # /complete (its response got lost) returns the same file.
        self.stored_name: Optional[str] = None
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
        if now - s.last_activity > SESSION_TTL_SECONDS
    ]
    for uid in stale:
        s = _sessions.pop(uid, None)
        if s and s.temp_path.exists():
            s.temp_path.unlink()

    # Sessions live in memory, so a restart forgets them and leaves their
    # (up to 1GB) part files behind with nothing else to ever remove them.
    live = {s.temp_path for s in _sessions.values()}
    for part in CHUNK_UPLOAD_DIR.glob("*.part"):
        if part not in live and now - part.stat().st_mtime > SESSION_TTL_SECONDS:
            part.unlink(missing_ok=True)


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
    check_size(filename, total_size)
    if total_size < 1 or total_chunks != math.ceil(total_size / CHUNK_SIZE):
        raise BadRequest("Invalid chunk count")

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
        raise BadRequest("Invalid chunk index")

    # A chunk cut short in transit must not count as received: the file would
    # be reported as uploaded with part of it silently left as zeros.
    offset = chunk_index * CHUNK_SIZE
    expected = min(CHUNK_SIZE, session.total_size - offset)
    if len(data) != expected:
        raise BadRequest(f"Chunk {chunk_index} is incomplete, please resend it")

    with session.lock:
        if session.stored_name:
            raise BadRequest("Upload already completed")
        with session.temp_path.open("r+b") as f:
            f.seek(offset)
            f.write(data)
        session.received.add(chunk_index)
        session.last_activity = time.time()


def complete_upload(upload_id: str) -> str:
    session = _sessions.get(upload_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )
    with session.lock:
        if session.stored_name:
            return session.stored_name

        if len(session.received) != session.total_chunks:
            missing = session.total_chunks - len(session.received)
            raise BadRequest(f"Upload incomplete: {missing} chunk(s) missing")

        # The bytes must match what the name claims (see upload_rules.py).
        try:
            verify_file(session.temp_path, session.filename)
        except HTTPException:
            with _sessions_lock:
                _sessions.pop(upload_id, None)
            session.temp_path.unlink(missing_ok=True)
            raise

        stored_name = f"{uuid.uuid4().hex}{session.ext}"
        # Same filesystem (uploads/.chunked -> uploads/), so this is a fast
        # rename, not a second full data copy of a file that was already
        # written to disk chunk by chunk.
        session.temp_path.rename(UPLOAD_DIR / stored_name)
        # The session stays until the normal clean-up so a retry can find it.
        session.stored_name = stored_name
        session.last_activity = time.time()

    return stored_name
