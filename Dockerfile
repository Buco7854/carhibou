# syntax=docker/dockerfile:1.7
ARG VEHINODE_VERSION=0.1.0

FROM --platform=$BUILDPLATFORM node:22.23.2-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=$BUILDPLATFORM golang:1.26.6-bookworm AS agent-build
ARG VEHINODE_VERSION
WORKDIR /src/agent
COPY agent/go.mod agent/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY agent/ ./
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    sh build-release.sh "$VEHINODE_VERSION" /out

FROM --platform=$BUILDPLATFORM python:3.13.15-slim-bookworm AS wheel-build
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

# Extra Python distributions importable from hooks, as a space-separated pinned
# list, for example: --build-arg VEHINODE_HOOK_PACKAGES="paho-mqtt==2.1.0".
#
# The runtime lock is applied as a constraint, so a package that would move a
# pinned dependency fails the build instead of silently shipping a runtime the
# application was never tested against. Pin what you add: an unpinned name makes
# the image unreproducible and widens its supply chain.
ARG VEHINODE_HOOK_PACKAGES=""
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "$VEHINODE_HOOK_PACKAGES" ]; then \
      pip install --prefix=/install --constraint requirements-backend.lock $VEHINODE_HOOK_PACKAGES; \
    fi

FROM python:3.13.15-slim-bookworm AS runtime
ARG VEHINODE_VERSION
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
COPY --from=agent-build /out/ /opt/vehinode-agent-releases/${VEHINODE_VERSION}/
COPY alembic.ini /app/alembic.ini
COPY backend/migrations/ /app/backend/migrations/
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/vehinode-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/vehinode-entrypoint \
    && chown -R vehinode:vehinode /app /opt/vehinode-agent-releases /var/lib/vehinode
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
ENTRYPOINT ["vehinode-entrypoint"]
CMD ["app"]
