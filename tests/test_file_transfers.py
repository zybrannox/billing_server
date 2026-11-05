"""Downloads and large uploads: what reaches the browser, when a file counts as
downloaded, and how the chunked upload copes with bad or repeated requests."""
import io
import os
import time
import zipfile

import pytest
from fastapi import HTTPException
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import ProjectFile, User, UserRole
from app.entities.project import Project
from app.project_files import chunked
from app.project_files.upload_rules import GB, check_size

# Compressible on purpose: gzip would happily shrink this, which is what makes
# an accidentally compressed download detectable.
CONTENT = b"0" * 5000


@pytest.fixture
def logged_in(client, db):
    from app.security import create_access_token

    db.add(User(username="alan", email="a@example.com", phone="9876543210",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "alan", "role": "admin", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr("app.project_files.controller.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.entities.project_file.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(chunked, "UPLOAD_DIR", tmp_path)
    parts = tmp_path / ".chunked"
    parts.mkdir()
    monkeypatch.setattr(chunked, "CHUNK_UPLOAD_DIR", parts)
    return tmp_path


def _project(db):
    project = Project(project_type="Flex", assigned_to="a", priority="Normal", client_status="Confirmed",
                      start_date=utcnow(), delivery_date=utcnow())
    db.add(project)
    db.commit()
    return project


def _file(db, uploads, project, path, *, on_disk=True, **kw):
    if on_disk:
        (uploads / path).write_bytes(CONTENT)
    row = ProjectFile(project_id=project.id, path=path, original_name=f"named-{path}", **kw)
    db.add(row)
    db.commit()
    return row


def _is_downloaded(db, row):
    db.refresh(row)
    return row.downloaded


# --- single file download ---------------------------------------------------


def test_download_is_sent_uncompressed_with_its_real_size(client, db, logged_in, uploads):
    _file(db, uploads, _project(db), "a.psd")
    res = client.get("/files/download/a.psd", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert res.content == CONTENT
    # Compressing on the fly removes Content-Length (no real progress, no way
    # to detect a truncated transfer) and burns CPU on incompressible files.
    assert "content-encoding" not in res.headers
    assert res.headers["content-length"] == str(len(CONTENT))


def test_download_is_never_stored_by_a_shared_cache(client, db, logged_in, uploads):
    _file(db, uploads, _project(db), "a.jpg")
    cache_control = client.get("/files/download/a.jpg").headers["cache-control"]
    assert "public" not in cache_control
    assert "no-store" in cache_control


def test_serving_a_file_does_not_mark_it_downloaded(client, db, logged_in, uploads):
    row = _file(db, uploads, _project(db), "a.psd")
    assert client.get("/files/download/a.psd").status_code == 200
    assert _is_downloaded(db, row) is False


def test_confirming_a_download_marks_only_that_file(client, db, logged_in, uploads):
    project = _project(db)
    row, other = _file(db, uploads, project, "a.psd"), _file(db, uploads, project, "b.psd")
    assert client.post("/files/download/a.psd/confirm").status_code == 200
    assert _is_downloaded(db, row) is True
    assert _is_downloaded(db, other) is False


def test_confirming_an_unknown_file_is_a_404(client, db, logged_in, uploads):
    assert client.post("/files/download/nope.psd/confirm").status_code == 404


def test_confirming_requires_a_login(client, db, uploads):
    assert client.post("/files/download/a.psd/confirm").status_code == 401


# --- download all -----------------------------------------------------------


def test_serving_the_zip_does_not_mark_files_until_confirmed(client, db, logged_in, uploads):
    project = _project(db)
    row = _file(db, uploads, project, "a.psd")
    res = client.get(f"/files/download/project/{project.id}")
    assert res.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == ["named-a.psd"]
    assert _is_downloaded(db, row) is False

    assert client.post(f"/files/download/project/{project.id}/confirm").status_code == 200
    assert _is_downloaded(db, row) is True


def test_confirming_the_zip_skips_files_that_were_not_in_it(client, db, logged_in, uploads):
    project = _project(db)
    present = _file(db, uploads, project, "a.psd")
    purged = _file(db, uploads, project, "gone.psd", on_disk=False, original_deleted_at=utcnow())
    missing = _file(db, uploads, project, "lost.psd", on_disk=False)

    names = zipfile.ZipFile(io.BytesIO(client.get(f"/files/download/project/{project.id}").content)).namelist()
    assert names == ["named-a.psd"]

    client.post(f"/files/download/project/{project.id}/confirm")
    assert _is_downloaded(db, present) is True
    assert _is_downloaded(db, purged) is False
    assert _is_downloaded(db, missing) is False


def test_zip_with_nothing_left_on_disk_fails_clearly(client, db, logged_in, uploads):
    project = _project(db)
    _file(db, uploads, project, "gone.psd", on_disk=False, original_deleted_at=utcnow())
    assert client.get(f"/files/download/project/{project.id}").status_code == 410


def test_abandoned_temp_zips_are_cleared_by_the_next_download(client, db, logged_in, uploads):
    project = _project(db)
    _file(db, uploads, project, "a.psd")
    temp = uploads / ".tmp_zips"
    temp.mkdir()
    old, recent = temp / "old.zip", temp / "recent.zip"
    old.write_bytes(b"x")
    recent.write_bytes(b"x")
    long_ago = time.time() - 7 * 60 * 60
    os.utime(old, (long_ago, long_ago))

    client.get(f"/files/download/project/{project.id}")
    assert not old.exists()
    assert recent.exists()  # may still be going out to someone else


# --- file size for the tooltip ----------------------------------------------


def test_project_files_report_their_size(client, db, logged_in, uploads):
    project = _project(db)
    _file(db, uploads, project, "a.psd")
    _file(db, uploads, project, "gone.psd", on_disk=False, original_deleted_at=utcnow())
    files = client.get(f"/projects/{project.id}").json()["file_paths"]
    assert {f["path"]: f["size_bytes"] for f in files} == {"a.psd": len(CONTENT), "gone.psd": None}


# --- size limits ------------------------------------------------------------


@pytest.mark.parametrize("name", ["big.pdf", "big.jpg", "big.pptx", "big.psd"])
def test_every_type_can_use_the_full_one_gb(name):
    check_size(name, 1 * GB)
    with pytest.raises(HTTPException) as err:
        check_size(name, 1 * GB + 1)
    assert err.value.status_code == 413


# --- chunked upload ---------------------------------------------------------


def _start(client, size, name="big.psd"):
    total_chunks = -(-size // chunked.CHUNK_SIZE)
    res = client.post("/files/upload/init", json={"filename": name, "total_size": size, "total_chunks": total_chunks})
    assert res.status_code == 200, res.text
    return res.json()["upload_id"]


def _send(client, upload_id, index, data):
    return client.post("/files/upload/chunk", data={"upload_id": upload_id, "chunk_index": index},
                       files={"chunk": ("blob", data)})


@pytest.fixture
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunked, "CHUNK_SIZE", 10)


def test_chunks_reassemble_in_any_order(client, logged_in, uploads, small_chunks):
    upload_id = _start(client, 25)
    for index, data in [(2, b"c" * 5), (0, b"a" * 10), (1, b"b" * 10)]:
        assert _send(client, upload_id, index, data).status_code == 200
    res = client.post("/files/upload/complete", json={"upload_id": upload_id, "filename": "big.psd"})
    assert res.status_code == 200
    assert (uploads / res.json()["path"]).read_bytes() == b"a" * 10 + b"b" * 10 + b"c" * 5


def test_a_truncated_chunk_is_rejected_and_can_be_resent(client, logged_in, uploads, small_chunks):
    upload_id = _start(client, 20)
    assert _send(client, upload_id, 0, b"a" * 4).status_code == 400
    assert _send(client, upload_id, 1, b"b" * 10).status_code == 200
    res = client.post("/files/upload/complete", json={"upload_id": upload_id, "filename": "big.psd"})
    assert res.status_code == 400  # chunk 0 never validly arrived

    assert _send(client, upload_id, 0, b"a" * 10).status_code == 200
    assert client.post("/files/upload/complete", json={"upload_id": upload_id, "filename": "big.psd"}).status_code == 200


def test_resending_a_chunk_is_harmless(client, logged_in, uploads, small_chunks):
    upload_id = _start(client, 10)
    assert _send(client, upload_id, 0, b"a" * 10).status_code == 200
    assert _send(client, upload_id, 0, b"a" * 10).status_code == 200
    assert client.post("/files/upload/complete", json={"upload_id": upload_id, "filename": "big.psd"}).status_code == 200


def test_chunk_count_must_match_the_file_size(client, logged_in, uploads, small_chunks):
    res = client.post("/files/upload/init", json={"filename": "big.psd", "total_size": 25, "total_chunks": 2})
    assert res.status_code == 400


def test_retrying_complete_returns_the_same_file(client, logged_in, uploads, small_chunks):
    """The response to `complete` can be lost after the server has already
    finished; the client's retry must not turn that into a failed upload."""
    upload_id = _start(client, 10)
    _send(client, upload_id, 0, b"a" * 10)
    payload = {"upload_id": upload_id, "filename": "big.psd"}
    first = client.post("/files/upload/complete", json=payload)
    second = client.post("/files/upload/complete", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["path"] == second.json()["path"]


def test_a_slow_upload_that_is_still_sending_is_not_expired(client, logged_in, uploads, small_chunks):
    upload_id = _start(client, 20)
    session = chunked._sessions[upload_id]
    session.created_at = session.last_activity = time.time() - chunked.SESSION_TTL_SECONDS + 5
    assert _send(client, upload_id, 0, b"a" * 10).status_code == 200

    _start(client, 10)  # any new upload triggers the clean-up
    assert upload_id in chunked._sessions
    assert session.temp_path.exists()


def test_parts_left_behind_by_a_restart_are_cleaned_up(client, logged_in, uploads, small_chunks):
    orphan = chunked.CHUNK_UPLOAD_DIR / "from-before-restart.part"
    orphan.write_bytes(b"x")
    long_ago = time.time() - chunked.SESSION_TTL_SECONDS - 60
    os.utime(orphan, (long_ago, long_ago))

    live = _start(client, 10)
    assert not orphan.exists()
    assert chunked._sessions[live].temp_path.exists()


# --- large files, via the browser's own download manager ----------------------


def test_direct_download_is_marked_once_the_last_byte_has_gone_out(client, db, logged_in, uploads):
    row = _file(db, uploads, _project(db), "a.psd")
    res = client.get("/files/download/a.psd?direct=1")
    assert res.content == CONTENT
    assert _is_downloaded(db, row) is True


def test_downloads_are_saved_under_their_real_name(client, db, logged_in, uploads):
    _file(db, uploads, _project(db), "a.psd")
    res = client.get("/files/download/a.psd?direct=1")
    assert "attachment" in res.headers["content-disposition"]
    assert "named-a.psd" in res.headers["content-disposition"]


def test_a_partial_range_does_not_count_as_downloaded(client, db, logged_in, uploads):
    row = _file(db, uploads, _project(db), "a.psd")
    res = client.get("/files/download/a.psd?direct=1", headers={"Range": "bytes=0-99"})
    assert res.status_code == 206
    assert _is_downloaded(db, row) is False


def test_resuming_through_to_the_end_counts_as_downloaded(client, db, logged_in, uploads):
    row = _file(db, uploads, _project(db), "a.psd")
    res = client.get("/files/download/a.psd?direct=1", headers={"Range": "bytes=4000-"})
    assert res.status_code == 206
    assert len(res.content) == len(CONTENT) - 4000
    assert _is_downloaded(db, row) is True


def test_direct_zip_marks_only_what_it_contained(client, db, logged_in, uploads):
    project = _project(db)
    present = _file(db, uploads, project, "a.psd")
    purged = _file(db, uploads, project, "gone.psd", on_disk=False, original_deleted_at=utcnow())
    res = client.get(f"/files/download/project/{project.id}?direct=1")
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == ["named-a.psd"]
    assert _is_downloaded(db, present) is True
    assert _is_downloaded(db, purged) is False


# --- previews and thumbnails ------------------------------------------------


@pytest.fixture
def preview(db, uploads, monkeypatch):
    monkeypatch.setattr("app.project_files.utils.THUMBNAIL_DIR", uploads)
    _file(db, uploads, _project(db), "a.png")
    return "a.png"


def _assert_only_the_viewers_browser_may_cache(res):
    assert res.status_code in (200, 206)
    cache_control = res.headers["cache-control"]
    assert "private" in cache_control
    assert "public" not in cache_control
    assert "immutable" not in cache_control
    assert "max-age" in cache_control  # still cached by the viewer's own browser


def test_thumbnails_are_never_stored_by_a_shared_cache(client, logged_in, preview):
    _assert_only_the_viewers_browser_may_cache(client.get(f"/files/thumbnail/{preview}"))


def test_previews_are_never_stored_by_a_shared_cache(client, logged_in, preview):
    _assert_only_the_viewers_browser_may_cache(client.get(f"/files/view/{preview}"))
    _assert_only_the_viewers_browser_may_cache(
        client.get(f"/files/view/{preview}", headers={"Range": "bytes=0-99"})
    )


@pytest.mark.parametrize("route", ["thumbnail", "view"])
def test_previews_still_require_a_login(client, preview, route):
    assert client.get(f"/files/{route}/{preview}").status_code == 401


# --- how much of how much, for large downloads --------------------------------

PROGRESS_ID = "0123456789abcdef0123456789abcdef"


def _progress(client):
    return client.get(f"/files/download/progress/{PROGRESS_ID}")


@pytest.fixture(autouse=True)
def _clear_progress():
    from app.project_files import download_progress

    download_progress._entries.clear()


def test_a_finished_large_download_reports_all_its_bytes(client, db, logged_in, uploads):
    row = _file(db, uploads, _project(db), "a.psd")
    client.get(f"/files/download/a.psd?direct=1&progress_id={PROGRESS_ID}")
    res = _progress(client)
    assert res.json() == {"state": "done", "sent": len(CONTENT), "total": len(CONTENT)}
    assert res.headers["cache-control"] == "no-store"
    assert _is_downloaded(db, row) is True


def test_a_resumed_download_counts_what_was_already_sent(client, db, logged_in, uploads):
    _file(db, uploads, _project(db), "a.psd")
    client.get(f"/files/download/a.psd?direct=1&progress_id={PROGRESS_ID}", headers={"Range": "bytes=4000-"})
    assert _progress(client).json() == {"state": "done", "sent": len(CONTENT), "total": len(CONTENT)}


def test_a_large_zip_reports_its_real_size(client, db, logged_in, uploads):
    project = _project(db)
    _file(db, uploads, project, "a.psd")
    res = client.get(f"/files/download/project/{project.id}?direct=1&progress_id={PROGRESS_ID}")
    assert _progress(client).json() == {"state": "done", "sent": len(res.content), "total": len(res.content)}


def test_a_download_cut_off_part_way_reports_stopped_and_stays_unmarked(db, uploads):
    import anyio

    from app.project_files import download_progress
    from app.project_files.tracked_response import TrackedFileResponse

    (uploads / "big.psd").write_bytes(b"0" * 300_000)
    marked = []
    response = TrackedFileResponse(uploads / "big.psd", on_complete=lambda: marked.append(True), progress_id=PROGRESS_ID)
    scope = {"type": "http", "method": "GET", "headers": [], "extensions": {}}
    sent_bodies = 0

    async def send(message):
        nonlocal sent_bodies
        if message["type"] == "http.response.body":
            sent_bodies += 1
            if sent_bodies == 2:
                raise OSError("client went away")

    async def receive():
        await anyio.sleep_forever()

    async def run():
        scope["asgi"] = {"spec_version": "2.4"}
        try:
            await response(scope, receive, send)
        except Exception:
            pass

    anyio.run(run)
    progress = download_progress.read(PROGRESS_ID)
    assert progress["state"] == "stopped"
    assert 0 < progress["sent"] < 300_000
    assert progress["total"] == 300_000
    assert marked == []


def test_unknown_download_progress_is_a_404(client, logged_in):
    assert _progress(client).status_code == 404


def test_download_progress_requires_a_login(client):
    assert _progress(client).status_code == 401


def test_a_malformed_progress_id_is_rejected(client, db, logged_in, uploads):
    _file(db, uploads, _project(db), "a.psd")
    assert client.get("/files/download/a.psd?direct=1&progress_id=../../etc").status_code == 422
