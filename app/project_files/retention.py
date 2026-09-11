"""Weekly storage-retention job for uploaded project files.

Design print files (banners, flex artwork, etc.) can be large, and once a
job is fully wrapped up there's rarely a reason to keep the full-resolution
original around indefinitely - the thumbnail is enough for anyone to see
what it was. This module permanently deletes the *original* file from disk
for anything old enough and done enough (see _is_eligible_project below),
while keeping the thumbnail and the ProjectFile row (path, original_name,
dimensions) so the UI can still show the file with its real name - just
without an original left to download.

Scheduled weekly in app/main.py (see start_retention_scheduler). Also
reachable on demand via POST /files/purge-stale (admin only) - handy for
ops and for verifying the job actually works without waiting a week.
"""

from datetime import datetime, timedelta

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.entities import Invoice, Project, ProjectFile

from .service import UPLOAD_DIR
from .utils import THUMBNAIL_DIR, generate_thumbnail

# How long an original survives after upload before it's eligible for
# removal, on a project whose work is done. Not "how often the job runs" -
# the job itself runs on a fixed weekly schedule (see app/main.py); this is
# the age threshold it checks against each time, so a slightly late or
# early run never changes which files qualify.
RETENTION_DAYS = 7


def _eligible_project_filter():
    """A project counts as "done" - and its files become eligible for
    purge - once it meets ANY of: print work fully completed, the order
    was delivered, or it's been invoiced. Anything still active (not yet
    completed/delivered/invoiced) is never touched, so nobody loses a file
    they're still mid-revision on."""
    has_invoice = exists().where(Invoice.project_id == Project.id)
    return (Project.print_status == "Completed") | Project.delivered_at.isnot(None) | has_invoice


def purge_stale_originals(db: Session) -> dict:
    """Deletes the on-disk original for every ProjectFile that is:
      - on an eligible (done) project - see _eligible_project_filter
      - older than RETENTION_DAYS
      - not already purged
      - has (or can generate) a thumbnail

    A file with no thumbnail and no way to make one (a PDF, a design file
    with no image preview, etc.) is left alone - deleting the only copy of
    something with nothing left to show for it isn't what "keep the
    thumbnail" means. It'll simply be picked up again next run once/if a
    thumbnail becomes available.

    Returns counts for logging/observability, not raised as an error -
    one bad file (e.g. already missing from disk) shouldn't abort the
    whole run; each file is handled independently.
    """
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)

    candidates = (
        db.query(ProjectFile)
        .join(Project, Project.id == ProjectFile.project_id)
        .filter(
            ProjectFile.original_deleted_at.is_(None),
            ProjectFile.created_at <= cutoff,
            _eligible_project_filter(),
        )
        .all()
    )

    purged = 0
    skipped_no_thumbnail = 0

    for f in candidates:
        source_path = UPLOAD_DIR / f.path
        thumb_path = THUMBNAIL_DIR / f.path

        # A thumbnail is the one non-negotiable precondition for marking
        # anything "purged" - it's what "only the thumbnail should be
        # available" actually depends on. This must be checked the same
        # way whether the source is still on disk or already gone (e.g. a
        # pre-existing orphaned row from before this feature existed): a
        # missing source is NOT itself grounds to mark a row purged, only
        # a present thumbnail is. Getting this backwards was a real bug
        # here - it briefly marked 22 already-orphaned, thumbnail-less
        # rows as "purged" without ever checking for a thumbnail, which
        # would have made the UI claim a fallback existed when it didn't.
        if source_path.exists():
            # Must run *before* the original is deleted - generate_thumbnail
            # reads from the source file and can't produce anything once
            # it's gone. A no-op (returns None) if one already exists and
            # is current, so this is cheap for the common case.
            generate_thumbnail(f.path)

        if not thumb_path.exists():
            skipped_no_thumbnail += 1
            continue

        if source_path.exists():
            try:
                source_path.unlink()
            except OSError as e:
                print(f"[retention] Failed to delete original for {f.path}: {e}")
                continue

        f.original_deleted_at = datetime.utcnow()
        purged += 1

    db.commit()
    return {
        "checked": len(candidates),
        "purged": purged,
        "skipped_no_thumbnail": skipped_no_thumbnail,
    }
