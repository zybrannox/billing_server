from datetime import timedelta
from app.datetime_utils import utcnow

import pytest

from app.shared_documents import repository, service
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def isolated_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, "UPLOAD_DIR", tmp_path)
    return tmp_path


def test_new_link_works_and_expires_30_days_out(db, isolated_upload_dir):
    doc = repository.upsert(db, "invoice", 1, b"%PDF-1", "Invoice-1.pdf")
    assert repository.get_active_by_token(db, doc.token) is not None
    days = (doc.expires_at - utcnow()).days
    assert 28 <= days <= 30
    assert (isolated_upload_dir / doc.filename).read_bytes() == b"%PDF-1"


def test_expired_link_stops_working(db):
    doc = repository.upsert(db, "invoice", 1, b"x", "a.pdf")
    doc.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert repository.get_active_by_token(db, doc.token) is None
    with pytest.raises(HTTPException) as err:
        service.service_get_document_path(db, doc.token)
    assert err.value.status_code == 404


def test_revoking_kills_the_link_and_deletes_the_file(db, isolated_upload_dir):
    doc = repository.upsert(db, "quotation", 7, b"x", "q.pdf")
    assert repository.revoke(db, "quotation", 7) is True
    assert repository.get_active_by_token(db, doc.token) is None
    assert not (isolated_upload_dir / doc.filename).exists()


def test_revoking_something_never_shared_reports_false(db):
    assert repository.revoke(db, "invoice", 999) is False
    with pytest.raises(HTTPException) as err:
        service.service_revoke_share_link(db, "invoice", 999)
    assert err.value.status_code == 404


def test_sharing_again_reopens_a_revoked_link_and_refreshes_expiry(db):
    first = repository.upsert(db, "invoice", 3, b"v1", "a.pdf")
    repository.revoke(db, "invoice", 3)
    first.expires_at = utcnow() - timedelta(days=5)
    db.commit()

    again = repository.upsert(db, "invoice", 3, b"v2", "a.pdf")
    assert again.token == first.token  # same stable link
    assert again.revoked_at is None
    assert repository.get_active_by_token(db, again.token) is not None


def test_unknown_token_is_indistinguishable_from_expired(db):
    with pytest.raises(HTTPException) as unknown:
        service.service_get_document_path(db, "no-such-token")
    doc = repository.upsert(db, "invoice", 5, b"x", "a.pdf")
    repository.revoke(db, "invoice", 5)
    with pytest.raises(HTTPException) as revoked:
        service.service_get_document_path(db, doc.token)
    assert unknown.value.detail == revoked.value.detail


def test_public_endpoint_serves_then_refuses(client, db):
    doc = repository.upsert(db, "invoice", 9, b"%PDF-1.4 hello", "Invoice-9.pdf")
    ok = client.get(f"/public/documents/{doc.token}")
    assert ok.status_code == 200 and ok.content.startswith(b"%PDF")
    assert ok.headers["x-content-type-options"] == "nosniff"

    repository.revoke(db, "invoice", 9)
    assert client.get(f"/public/documents/{doc.token}").status_code == 404


def test_revoke_endpoint_requires_admin(client):
    # No session at all: refused before reaching the handler.
    r = client.delete("/invoices/1/share-link")
    assert r.status_code in (401, 403)
