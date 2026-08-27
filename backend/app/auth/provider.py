from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthenticatedIdentity:
    provider: str
    subject: str
    user_id: str


class AuthenticationProvider(Protocol):
    """Boundary implemented by local auth now and future OIDC providers."""

    name: str

    def authenticate(self, subject: str, credential: str) -> AuthenticatedIdentity | None: ...
