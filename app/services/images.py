from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
import re

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings


SUPPORTED_FORMATS = {
    "JPEG": ("image/jpeg", "JPEG"),
    "PNG": ("image/png", "PNG"),
    "WEBP": ("image/webp", "WEBP"),
}


class ImageProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class SanitizedImage:
    data: bytes
    mime_type: str
    width: int
    height: int


def safe_image_filename(filename: str | None, mime_type: str) -> str:
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime_type]
    name = PurePath((filename or f"image{extension}").replace("\\", "/")).name
    name = re.sub(r"[^\w.()\- ]", "_", name, flags=re.UNICODE).strip(" .")
    stem = PurePath(name).stem[:240] or "image"
    return f"{stem}{extension}"


def sanitize_image(data: bytes, content_type: str | None) -> SanitizedImage:
    if not data:
        raise ImageProcessingError("The uploaded image is empty")
    if len(data) > settings.image_max_bytes:
        maximum_mb = settings.image_max_bytes // (1024 * 1024)
        raise ImageProcessingError(f"Images are limited to {maximum_mb} MB")
    if content_type not in {None, "", "image/jpeg", "image/png", "image/webp"}:
        raise ImageProcessingError("Only JPEG, PNG, and WebP images are supported")

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = settings.image_max_pixels
    try:
        with Image.open(BytesIO(data)) as source:
            actual_format = (source.format or "").upper()
            if actual_format not in SUPPORTED_FORMATS:
                raise ImageProcessingError("Only JPEG, PNG, and WebP images are supported")
            mime_type, output_format = SUPPORTED_FORMATS[actual_format]
            source.load()
            image = ImageOps.exif_transpose(source)
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width > settings.image_max_dimension
                or height > settings.image_max_dimension
                or width * height > settings.image_max_pixels
            ):
                raise ImageProcessingError("The image dimensions are too large")

            if output_format == "JPEG":
                image = image.convert("RGB")
            elif image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")

            output = BytesIO()
            if output_format == "JPEG":
                image.save(output, format=output_format, quality=90, optimize=True)
            elif output_format == "WEBP":
                image.save(output, format=output_format, quality=90, method=4)
            else:
                image.save(output, format=output_format, optimize=True)
            sanitized = output.getvalue()
    except Image.DecompressionBombError as exc:
        raise ImageProcessingError("The image dimensions are too large") from exc
    except ImageProcessingError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageProcessingError("The uploaded file is not a valid image") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    if len(sanitized) > settings.image_max_bytes:
        raise ImageProcessingError("The sanitized image is too large")
    return SanitizedImage(sanitized, mime_type, width, height)
