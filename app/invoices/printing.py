"""Sends an invoice straight to the printer connected to this machine.

A web page can't print without showing the browser's dialog, but the server runs
on the Mac the printer is plugged into, so it can hand the job to macOS itself.
The printer is whichever one macOS has as its default.
"""
import logging
import subprocess

from fastapi import HTTPException

logger = logging.getLogger(__name__)

COMMAND_TIMEOUT_SECONDS = 30


def _unavailable(detail: str) -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


def _run(command: list[str], data: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, input=data, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("Printing failed running %s: %s", command[0], type(exc).__name__)
        raise _unavailable("Couldn't reach the printer.")


def _connected_printer() -> str:
    default = _run(["lpstat", "-d"]).stdout.decode(errors="replace")
    _, found, name = default.strip().partition("system default destination: ")
    if not found or not name:
        raise _unavailable("No printer is set up on the server.")

    # Checked first because a paused printer still accepts jobs, which would then
    # come out whenever someone resumes it, long after this invoice was needed.
    state = _run(["lpstat", "-p", name]).stdout.decode(errors="replace")
    if not state or " disabled" in state:
        raise _unavailable("The printer is off or paused.")
    return name


def print_pdf(data: bytes, title: str) -> str:
    """Prints the PDF and says which printer it went to."""
    printer = _connected_printer()
    result = _run(["lp", "-d", printer, "-t", title, "-o", "fit-to-page"], data)
    if result.returncode != 0:
        logger.error("Printing failed: %s", result.stderr.decode(errors="replace")[:500])
        raise _unavailable("Couldn't reach the printer.")
    return printer
