import logging
import re
import time
from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.common.logging import request_id_context
from backend.app.common.settings import get_settings

logger = logging.getLogger(__name__)
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class PayloadTooLarge(Exception):
    pass


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        supplied = headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID.fullmatch(supplied) else str(uuid4())
        token = request_id_context.set(request_id)
        started = time.monotonic()
        limit = get_settings().max_request_bytes
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise PayloadTooLarge
            return message

        async def secured_send(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
                response_headers["X-Content-Type-Options"] = "nosniff"
                response_headers["Referrer-Policy"] = "same-origin"
                response_headers["X-Frame-Options"] = "DENY"
                response_headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            await send(message)

        async def reject(message: str) -> None:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": {"code": "payload_too_large", "message": message},
                    "request_id": request_id,
                },
            )
            await response(scope, receive, secured_send)

        try:
            content_length = headers.get("content-length")
            try:
                declared = int(content_length) if content_length else None
            except ValueError:
                await reject("Content-Length is invalid")
                return
            if declared is not None and declared > limit:
                await reject("request body is too large")
                return
            try:
                await self.app(scope, limited_receive, secured_send)
            except PayloadTooLarge:
                await reject("request body is too large")
        finally:
            elapsed_ms = round((time.monotonic() - started) * 1000, 2)
            logger.debug("request complete", extra={"duration_ms": elapsed_ms})
            request_id_context.reset(token)
