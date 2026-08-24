from dataclasses import dataclass

MAX_PHOTO_BYTES = 25 * 1024 * 1024
MAX_PHOTO_EDGE = 12_000
MAX_PHOTO_PIXELS = 40_000_000
ALLOWED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class PhotoValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedPhoto:
    media_type: str
    width: int
    height: int


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:3] != b"\xff\xd8\xff":
        return None
    position = 2
    start_of_frame = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in {0xD8, 0xD9}:
            continue
        if position + 2 > len(data):
            break
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            break
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return width, height
        position += segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    codec = data[12:16]
    if codec == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if codec == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return (
            int.from_bytes(data[26:28], "little") & 0x3FFF,
            int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    if codec == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def validate_photo(data: bytes, declared_media_type: str) -> ValidatedPhoto:
    media_type = declared_media_type.partition(";")[0].strip().lower()
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise PhotoValidationError("photo must be a JPEG, PNG, or WebP image")
    if not data:
        raise PhotoValidationError("photo is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("photo must not exceed 25 MiB")

    parsers = {
        "image/jpeg": _jpeg_dimensions,
        "image/png": _png_dimensions,
        "image/webp": _webp_dimensions,
    }
    dimensions = parsers[media_type](data)
    if not dimensions:
        raise PhotoValidationError("photo content does not match its media type")
    width, height = dimensions
    if (
        width < 1
        or height < 1
        or width > MAX_PHOTO_EDGE
        or height > MAX_PHOTO_EDGE
        or width * height > MAX_PHOTO_PIXELS
    ):
        raise PhotoValidationError("photo dimensions are not supported")
    return ValidatedPhoto(media_type=media_type, width=width, height=height)
