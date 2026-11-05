"""Uploaded images are still processed properly by the installed Pillow."""
import io

from PIL import Image

from app.project_files import utils


def _png(size=(800, 400)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, "white").save(buffer, "PNG")
    return buffer.getvalue()


def test_a_thumbnail_is_made_from_an_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "UPLOAD_DIR", tmp_path)
    thumbnails = tmp_path / "thumbs"
    thumbnails.mkdir()
    monkeypatch.setattr(utils, "THUMBNAIL_DIR", thumbnails)
    (tmp_path / "art.png").write_bytes(_png())

    assert utils.generate_thumbnail("art.png") == "art.png"
    with Image.open(thumbnails / "art.png") as thumbnail:
        assert thumbnail.size == (300, 150)


def test_a_broken_image_doesnt_make_a_thumbnail(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "UPLOAD_DIR", tmp_path)
    thumbnails = tmp_path / "thumbs"
    thumbnails.mkdir()
    monkeypatch.setattr(utils, "THUMBNAIL_DIR", thumbnails)
    (tmp_path / "broken.png").write_bytes(b"this is not an image")
    assert utils.generate_thumbnail("broken.png") is None
