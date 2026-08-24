import os
import tempfile
from contextlib import suppress
from pathlib import Path

from backend.app.common.settings import get_settings

EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def media_root() -> Path:
    root = Path(get_settings().media_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def photo_path(storage_key: str) -> Path:
    root = media_root()
    target = (root / storage_key).resolve()
    if target == root or root not in target.parents:
        raise ValueError("invalid vehicle photo storage key")
    return target


def store_photo(vehicle_id: str, data: bytes, media_type: str, etag: str) -> str:
    extension = EXTENSIONS[media_type]
    directory = media_root() / "vehicle-photos" / vehicle_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / f"{etag}{extension}"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=directory)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return destination.relative_to(media_root()).as_posix()


def remove_photo_file(storage_key: str) -> None:
    target = photo_path(storage_key)
    target.unlink(missing_ok=True)
    with suppress(OSError):
        target.parent.rmdir()
