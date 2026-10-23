"""
Base64 Data-URI Image Exporter (MAN-008).
Converts screenshots and annotated review images into standard RFC 2397 Data URIs
for zero-friction direct pasting into web AI chat interfaces (ChatGPT, Claude, Gemini).
"""

from __future__ import annotations
import base64
import io
import mimetypes
from pathlib import Path
from typing import Optional, Union
from PIL import Image

try:
    from token_budget_downsampler import downsample_image
except ImportError:
    from .token_budget_downsampler import downsample_image


def image_to_data_uri(
    img: Image.Image,
    image_format: str = "PNG",
    max_dimension: Optional[int] = None
) -> str:
    """
    Converts a PIL Image to a Base64 data URI string: data:image/<format>;base64,<encoded>
    Optionally downsamples the image to max_dimension before encoding.
    """
    if max_dimension is not None:
        target_img = downsample_image(img, max_dimension=max_dimension)
    else:
        target_img = img

    buffer = io.BytesIO()
    fmt = image_format.upper()
    if fmt == "JPG":
        fmt = "JPEG"

    if fmt == "JPEG" and target_img.mode in ("RGBA", "P"):
        save_img = target_img.convert("RGB")
    else:
        save_img = target_img

    save_img.save(buffer, format=fmt)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    mime_type = f"image/{fmt.lower()}"
    return f"data:{mime_type};base64,{encoded}"


def file_to_data_uri(
    file_path: Union[str, Path],
    max_dimension: Optional[int] = None
) -> str:
    """
    Converts an image file on disk into a Base64 data URI.
    """
    in_p = Path(file_path)
    if not in_p.exists():
        raise FileNotFoundError(f"Image file not found: {in_p}")

    ext = in_p.suffix.lower().lstrip(".")
    fmt = "JPEG" if ext in ("jpg", "jpeg") else "PNG"

    if max_dimension is not None:
        with Image.open(in_p) as img:
            return image_to_data_uri(img, image_format=fmt, max_dimension=max_dimension)

    # Direct raw bytes encoding if no downsampling requested
    raw_bytes = in_p.read_bytes()
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    mime_type, _ = mimetypes.guess_type(str(in_p))
    if not mime_type:
        mime_type = f"image/{ext}" if ext else "image/png"

    return f"data:{mime_type};base64,{encoded}"


def generate_embedded_markdown(
    markdown_template: str,
    clean_image_path: Union[str, Path],
    annotated_image_path: Union[str, Path],
    max_dimension: Optional[int] = 1200
) -> str:
    """
    Produces a self-contained Markdown string with images embedded directly as Base64 data URIs.
    """
    clean_uri = file_to_data_uri(clean_image_path, max_dimension=max_dimension)
    annotated_uri = file_to_data_uri(annotated_image_path, max_dimension=max_dimension)

    output = markdown_template
    # Replace file references with data URIs
    clean_name = Path(clean_image_path).name
    annotated_name = Path(annotated_image_path).name

    output = output.replace(f"({clean_name})", f"({clean_uri})")
    output = output.replace(f"({annotated_name})", f"({annotated_uri})")

    return output
