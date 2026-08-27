import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.types import Scope

from backend.app.access.routes import router as access_router
from backend.app.agents.protocol import registered_implementations, setup_steps
from backend.app.agents.routes import agent_router, human_router
from backend.app.api.agent_distribution import router as agent_distribution_router
from backend.app.api.errors import install_error_handlers
from backend.app.api.events import router as event_router
from backend.app.api.health import router as health_router
from backend.app.auth.routes import router as auth_router
from backend.app.auth.services import bootstrap_local_admin
from backend.app.branding import APP_DESCRIPTION, APP_NAME, APP_VERSION
from backend.app.common.database import SessionLocal
from backend.app.common.logging import configure_logging
from backend.app.common.middleware import RequestContextMiddleware
from backend.app.common.settings import get_settings
from backend.app.connectors.routes import router as connector_router
from backend.app.dashboards.routes import router as dashboard_router
from backend.app.history.routes import router as history_router
from backend.app.hooks.routes import router as hook_router
from backend.app.secrets.routes import router as secret_router
from backend.app.telemetry.routes import router as telemetry_router
from backend.app.users.routes import router as user_router
from backend.app.vehicle_profiles.routes import router as vehicle_profile_router
from backend.app.vehicles.routes import router as vehicle_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


class SpaStaticFiles(StaticFiles):
    """Serve Vite assets and fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def _bootstrap_configured_admin() -> None:
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return
    with SessionLocal() as db:
        user = bootstrap_local_admin(
            db,
            str(settings.bootstrap_admin_email),
            settings.bootstrap_admin_password.get_secret_value(),
            settings.bootstrap_admin_display_name,
        )
        db.commit()
    if user:
        logger.info("bootstrap administrator created", extra={"user_id": user.id})


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    for implementation in registered_implementations():
        setup_steps(implementation, "catalog-validation-token")
    _bootstrap_configured_admin()
    yield


app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_pepper,
    session_cookie="carhibou_oidc",
    max_age=600,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)
app.add_middleware(RequestContextMiddleware)
install_error_handlers(app)
app.include_router(health_router)
app.include_router(agent_distribution_router)
for api_router in (
    auth_router,
    access_router,
    event_router,
    vehicle_router,
    connector_router,
    human_router,
    agent_router,
    telemetry_router,
    history_router,
    vehicle_profile_router,
    dashboard_router,
    hook_router,
    secret_router,
    user_router,
):
    app.include_router(api_router, prefix="/api/v1")

frontend_dist = (
    Path(settings.frontend_dir)
    if settings.frontend_dir
    else Path(__file__).resolve().parents[2] / "frontend" / "dist"
)
if frontend_dist.is_dir():
    app.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")


def create_app() -> FastAPI:
    return app
