"""PyMuPDF page-to-image rendering and base64 encoding for the vision extraction step."""
import base64
import io

import fitz  # PyMuPDF
from PIL import Image

from src.exceptions import DocumentProcessingError

# Anthropic's own vision docs recommend capping the long edge at 1568px — anything larger
# gets resized server-side anyway before Claude ever looks at it. Re-encoding an uploaded
# photo (e.g. a 12MP phone-camera JPEG, comfortably under the app's 10MB upload guardrail)
# as a *lossless* PNG at full resolution can inflate the base64 payload to 30-40MB, which
# blows past Anthropic's request-size limit (`request_too_large`) even though the original
# upload was well within bounds. Downscaling before encoding fixes this without any quality
# loss, since Claude would've downsampled it anyway.
MAX_VISION_DIMENSION = 1568


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
    """Encode a PIL image as a base64 PNG string for the LiteLLM vision payload.

    Downscales to MAX_VISION_DIMENSION on the long edge first — see that constant's
    comment for why this matters beyond just saving bandwidth."""
    rgb_image = image.convert("RGB")
    if max(rgb_image.size) > MAX_VISION_DIMENSION:
        rgb_image.thumbnail((MAX_VISION_DIMENSION, MAX_VISION_DIMENSION), Image.LANCZOS)
    buf = io.BytesIO()
    rgb_image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
