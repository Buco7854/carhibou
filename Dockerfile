# syntax=docker/dockerfile:1.7
FROM node:22.23.2-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13.15-slim-bookworm AS wheel-build
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache/pip pip install build==1.3.0 setuptools==80.9.0
COPY pyproject.toml README.md ./
COPY backend/ backend/
COPY agent/ agent/
RUN python -m build --wheel --no-isolation

FROM python:3.13.15-slim-bookworm AS python-deps
WORKDIR /install
COPY requirements-backend.lock ./
COPY --from=wheel-build /src/dist/*.whl /tmp/dist/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements-backend.lock \
    && pip install --prefix=/install --no-deps /tmp/dist/*.whl

FROM python:3.13.15-slim-bookworm AS runtime
ARG VEHINODE_VERSION=0.1.0
LABEL org.opencontainers.image.title="VehiNode" \
      org.opencontainers.image.description="Self-hosted vehicle telemetry and programmability platform"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VEHINODE_FRONTEND_DIR=/app/frontend/dist \
    VEHINODE_MEDIA_DIR=/var/lib/vehinode/media \
    VEHINODE_AGENT_RELEASE_DIR=/opt/vehinode-agent-releases
WORKDIR /app
RUN groupadd --system --gid 10001 vehinode \
    && useradd --system --uid 10001 --gid vehinode --home-dir /app --shell /usr/sbin/nologin vehinode \
    && mkdir -p /app/frontend/dist /var/lib/vehinode/media "/opt/vehinode-agent-releases/${VEHINODE_VERSION}"
COPY --from=python-deps /install/ /usr/local/
COPY --from=frontend-build /src/frontend/dist/ /app/frontend/dist/
COPY --from=wheel-build /src/dist/vehinode-${VEHINODE_VERSION}-py3-none-any.whl /tmp/agent.whl
COPY alembic.ini /app/alembic.ini
COPY backend/migrations/ /app/backend/migrations/
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/vehinode-entrypoint
RUN cp /tmp/agent.whl "/opt/vehinode-agent-releases/${VEHINODE_VERSION}/vehinode-${VEHINODE_VERSION}-py3-none-any.whl" \
    && cd "/opt/vehinode-agent-releases/${VEHINODE_VERSION}" \
    && sha256sum "vehinode-${VEHINODE_VERSION}-py3-none-any.whl" > "vehinode-${VEHINODE_VERSION}-py3-none-any.whl.sha256" \
    && rm /tmp/agent.whl \
    && chown -R vehinode:vehinode /app /opt/vehinode-agent-releases /var/lib/vehinode
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
ENTRYPOINT ["vehinode-entrypoint"]
CMD ["app"]
