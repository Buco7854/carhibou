from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.models import Agent
from backend.app.auth.models import BrowserSession
from backend.app.auth.security import hash_token, tokens_equal
from backend.app.common.database import get_db
from backend.app.common.settings import get_settings
from backend.app.common.time import as_utc, utcnow
from backend.app.users.models import User

Db = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    session: BrowserSession


def current_user(
    db: Db,
    raw_token: Annotated[str | None, Cookie(alias=get_settings().session_cookie_name)] = None,
) -> AuthenticatedUser:
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    browser_session = db.scalar(
        select(BrowserSession).where(BrowserSession.token_hash == hash_token(raw_token))
    )
    now = utcnow()
    if (
        not browser_session
        or browser_session.revoked_at is not None
        or as_utc(browser_session.expires_at) < now
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    user = db.get(User, browser_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account unavailable")
    browser_session.last_seen_at = now
    return AuthenticatedUser(user=user, session=browser_session)


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]


def current_user_write(
    request: Request,
    authenticated: CurrentUser,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthenticatedUser:
    cookie_csrf = request.cookies.get(get_settings().csrf_cookie_name)
    if not csrf_token or not cookie_csrf or csrf_token != cookie_csrf:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    if not tokens_equal(authenticated.session.csrf_hash, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return authenticated


CurrentUserWrite = Annotated[AuthenticatedUser, Depends(current_user_write)]


def current_agent(
    db: Db,
    authorization: Annotated[str | None, Header()] = None,
) -> Agent:
    if not authorization or not authorization.startswith("Agent "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="agent credential required"
        )
    raw = authorization.removeprefix("Agent ").strip()
    agent = db.scalar(select(Agent).where(Agent.credential_hash == hash_token(raw)))
    if not agent or agent.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent credential"
        )
    return agent


CurrentAgent = Annotated[Agent, Depends(current_agent)]
