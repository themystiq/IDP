"""PyMuPDF page-to-image rendering and base64 encoding for the vision extraction step."""
import base64
import io

import fitz  # PyMuPDF
from PIL import Image

from src.exceptions import DocumentProcessingError


def render_upload_to_images(file_bytes: bytes, filename: str, dpi: int = 200) -> list[Image.Image]:
    """Render an uploaded PDF/image into a list of PIL images, one per page."""
    ext = filename.lower().rsplit(".", 1)[-1]
    try:
        if ext == "pdf":
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            images = [
                Image.open(io.BytesIO(page.get_pixmap(matrix=mat).tobytes("png")))
                for page in doc
            ]
            doc.close()
            if not images:
                raise DocumentProcessingError("PDF contains no renderable pages.")
            return images
        elif ext in ("png", "jpg", "jpeg"):
            img = Image.open(io.BytesIO(file_bytes))
            img.load()
            return [img]
        else:
            raise DocumentProcessingError(f"Unsupported file type: .{ext}")
    except DocumentProcessingError:
        raise
    except Exception as e:
        raise DocumentProcessingError(f"Failed to render document: {e}") from e


def image_to_base64_png(image: Image.Image) -> str:
    """Encode a PIL image as a base64 PNG string for the LiteLLM vision payload."""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
