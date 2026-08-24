from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from backend.app.auth.dependencies import CurrentUser, CurrentUserWrite, Db
from backend.app.auth.models import BrowserSession
from backend.app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RegisterRequest,
    SessionResponse,
    SetupStatusResponse,
    UserResponse,
)
from backend.app.auth.services import (
    AuthenticationError,
    LocalAuthenticationProvider,
    RegistrationClosedError,
    change_password,
    create_session,
    register_first_local_admin,
    registration_is_open,
    revoke_other_sessions,
)
from backend.app.common.settings import get_settings
from backend.app.common.time import utcnow
from backend.app.users.models import User

router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    seconds = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=seconds,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _login_response(response: Response, db: Db, request: Request, user: User) -> LoginResponse:
    new_session = create_session(
        db,
        user,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    db.commit()
    _set_session_cookies(response, new_session.token, new_session.csrf_token)
    return LoginResponse(user=UserResponse.model_validate(user), csrf_token=new_session.csrf_token)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, request: Request, response: Response, db: Db) -> LoginResponse:
    try:
        user = register_first_local_admin(db, data.email, data.password, data.display_name)
    except RegistrationClosedError as exc:
        raise HTTPException(status_code=403, detail="initial registration is closed") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _login_response(response, db, request, user)


@router.get("/setup", response_model=SetupStatusResponse)
def setup_status(db: Db) -> SetupStatusResponse:
    return SetupStatusResponse(registration_open=registration_is_open(db))


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, request: Request, response: Response, db: Db) -> LoginResponse:
    identity = LocalAuthenticationProvider(db).authenticate(data.email, data.password)
    if not identity:
        raise HTTPException(status_code=401, detail="invalid email or password")
    user = db.get(User, identity.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="account unavailable")
    return _login_response(response, db, request, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: Db, auth: CurrentUserWrite) -> None:
    auth.session.revoked_at = utcnow()
    db.commit()
    _clear_session_cookies(response)


@router.get("/me", response_model=UserResponse)
def me(db: Db, auth: CurrentUser) -> User:
    db.commit()
    return auth.user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(data: PasswordChangeRequest, db: Db, auth: CurrentUserWrite) -> None:
    try:
        change_password(db, auth.user.id, data.current_password, data.new_password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    revoke_other_sessions(db, auth.user.id, auth.session.id)
    db.commit()


@router.get("/sessions", response_model=list[SessionResponse])
def sessions(db: Db, auth: CurrentUser) -> list[SessionResponse]:
    rows = db.scalars(
        select(BrowserSession)
        .where(
            BrowserSession.user_id == auth.user.id,
            BrowserSession.revoked_at.is_(None),
            BrowserSession.expires_at > utcnow(),
        )
        .order_by(BrowserSession.created_at.desc())
    )
    return [
        SessionResponse(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            current=row.id == auth.session.id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, db: Db, auth: CurrentUserWrite) -> None:
    target = db.scalar(
        select(BrowserSession).where(
            BrowserSession.id == session_id, BrowserSession.user_id == auth.user.id
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail="session not found")
    target.revoked_at = utcnow()
    db.commit()
