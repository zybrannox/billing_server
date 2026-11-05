"""Tells us how far a file has got, and when it has really finished going out.

Large downloads are handed to the browser's own download manager (a blob in page
memory can't reliably hold a 1GB file), so there's no page code left to report
back when one finishes. The last byte leaving this server is the best signal
available: a transfer cut off part-way never gets there.
"""
import os
import re
from typing import Callable, Optional

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import FileResponse
from starlette.types import Message, Receive, Scope, Send

from . import download_progress

# "bytes=N-": a browser resuming a download, which runs through to the end of
# the file. Any other range only covers part of it, so it doesn't count.
_RESUME_RANGE = re.compile(r"^bytes=(\d+)-$")


class TrackedFileResponse(FileResponse):
    def __init__(self, *args, on_complete: Callable[[], None], progress_id: Optional[str] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_complete = on_complete
        self.progress_id = progress_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        requested_range = Headers(scope=scope).get("range")
        resume = _RESUME_RANGE.match(requested_range) if requested_range else None
        reached_the_end = requested_range is None or resume is not None
        progress_id = self.progress_id

        if progress_id:
            download_progress.sending(
                progress_id, os.stat(self.path).st_size, int(resume.group(1)) if resume else 0
            )

        finished = False

        async def tracking_send(message: Message) -> None:
            nonlocal finished
            await send(message)
            if message["type"] == "http.response.body":
                if progress_id:
                    download_progress.add(progress_id, len(message.get("body", b"")))
                if not message.get("more_body", False):
                    finished = True

        completed = False
        try:
            await super().__call__(scope, receive, tracking_send)
            if finished and reached_the_end:
                await run_in_threadpool(self.on_complete)
                completed = True
        finally:
            # Also reached when the connection drops or the user cancels.
            if progress_id:
                (download_progress.finished if completed else download_progress.stopped)(progress_id)
