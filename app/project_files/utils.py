from PIL import Image
from pathlib import Path
import os

UPLOAD_DIR = Path("./uploads")
THUMBNAIL_DIR = UPLOAD_DIR / "thumbnails"
THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

def generate_thumbnail(filename: str, size=(300, 300)):
    """
    Generates a thumbnail for an image if it doesn't already exist.
    """
    source_path = UPLOAD_DIR / filename
    if not source_path.exists():
        return None
    
    # Check if the file is an image
    ext = source_path.suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        return None
    
    thumb_path = THUMBNAIL_DIR / filename
    
    # If thumbnail already exists and is newer than source, return it
    if thumb_path.exists() and thumb_path.stat().st_mtime >= source_path.stat().st_mtime:
        return filename
    
    try:
        with Image.open(source_path) as img:
            # Convert to RGB if necessary (e.g. for RGBA pngs to jpeg, though we keep original format usually)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            img.thumbnail(size)
            img.save(thumb_path, optimize=True, quality=85)
        return filename
    except Exception as e:
        print(f"Error generating thumbnail for {filename}: {e}")
        return None

def get_cache_headers(max_age: int = 31536000):
    """
    Returns standard cache headers for static assets.
    """
    return {
        "Cache-Control": f"public, max-age={max_age}, immutable",
        "Pragma": "cache",
    }
