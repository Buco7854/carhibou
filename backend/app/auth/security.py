import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from backend.app.common.settings import get_settings

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_opaque_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    pepper = get_settings().session_pepper.encode()
    return hmac.new(pepper, token.encode(), hashlib.sha256).hexdigest()


def tokens_equal(expected_hash: str, raw_token: str) -> bool:
    return hmac.compare_digest(expected_hash, hash_token(raw_token))
