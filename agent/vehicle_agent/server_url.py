from urllib.parse import urlsplit


def validate_server_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("agent server URL must be an origin without credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("agent server URL cannot contain a path, query, or fragment")
    if parsed.scheme == "https":
        return value.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return value.rstrip("/")
    raise ValueError("agent server URL must use HTTPS except on localhost")
