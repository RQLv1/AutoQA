import base64
import tempfile
from pathlib import Path


_BLACK_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X1l8AAAAASUVORK5CYII="
)


def get_black_png_path() -> Path:
    path = Path(tempfile.gettempdir()) / "autoqa_black.png"
    if path.exists() and path.stat().st_size > 0:
        return path
    data = base64.b64decode(_BLACK_PNG_BASE64)
    path.write_bytes(data)
    return path

