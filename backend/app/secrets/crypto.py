from cryptography.fernet import Fernet, InvalidToken

from backend.app.common.settings import get_settings


class SecretDecryptionError(Exception):
    pass


def encrypt_secret(value: str) -> str:
    return Fernet(get_settings().master_key.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return Fernet(get_settings().master_key.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError(
            "secret cannot be decrypted; verify the application master key"
        ) from exc


def redact_text(text: str | None, secret_values: list[str]) -> str | None:
    if text is None:
        return None
    redacted = text
    for value in sorted((item for item in secret_values if item), key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted
