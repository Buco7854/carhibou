# syntax=docker/dockerfile:1.7
ARG CARHIBOU_VERSION=0.1.0

FROM --platform=$BUILDPLATFORM node:24.19.0-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=$BUILDPLATFORM golang:1.27.0-bookworm AS agent-build
ARG CARHIBOU_VERSION
WORKDIR /src/agent
COPY agent/go.mod agent/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY agent/ ./
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    sh build-release.sh "$CARHIBOU_VERSION" /out

# Collect every top-level implementation manifest independently of the Python
# wheel. A non-Python implementation is therefore discoverable without any
# backend packaging changes.
FROM --platform=$BUILDPLATFORM python:3.14.7-slim-bookworm AS agent-manifests
WORKDIR /src
COPY . .
RUN mkdir -p /manifests \
    && for manifest in */agent.toml; do \
         [ -e "$manifest" ] || continue; \
         mkdir -p "/manifests/$(dirname "$manifest")" \
         && cp "$manifest" "/manifests/$manifest"; \
       done

FROM --platform=$BUILDPLATFORM python:3.14.7-slim-bookworm AS wheel-build
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache/pip pip install build==1.5.0 setuptools==84.0.0
COPY pyproject.toml README.md ./
COPY backend/ backend/
COPY agent/ agent/
RUN python -m build --wheel --no-isolation

FROM python:3.14.7-slim-bookworm AS python-deps
WORKDIR /install
COPY requirements-backend.lock ./
COPY --from=wheel-build /src/dist/*.whl /tmp/dist/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements-backend.lock \
    && pip install --prefix=/install --no-deps /tmp/dist/*.whl

# Extra Python distributions importable from hooks, as a space-separated pinned
# list, for example: --build-arg CARHIBOU_HOOK_PACKAGES="paho-mqtt==2.1.0".
#
# The runtime lock is applied as a constraint, so a package that would move a
# pinned dependency fails the build instead of silently shipping a runtime the
# application was never tested against. Pin what you add: an unpinned name makes
# the image unreproducible and widens its supply chain.
ARG CARHIBOU_HOOK_PACKAGES=""
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "$CARHIBOU_HOOK_PACKAGES" ]; then \
      pip install --prefix=/install --constraint requirements-backend.lock $CARHIBOU_HOOK_PACKAGES; \
    fi

FROM python:3.14.7-slim-bookworm AS runtime
ARG CARHIBOU_VERSION
LABEL org.opencontainers.image.title="Carhibou" \
      org.opencontainers.image.description="Self-hosted vehicle telemetry and programmability platform"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CARHIBOU_FRONTEND_DIR=/app/frontend/dist \
    CARHIBOU_MEDIA_DIR=/var/lib/carhibou/media \
    CARHIBOU_AGENT_RELEASE_DIR=/opt/carhibou-agent-releases
WORKDIR /app
RUN groupadd --system --gid 10001 carhibou \
    && useradd --system --uid 10001 --gid carhibou --home-dir /app --shell /usr/sbin/nologin carhibou \
    && mkdir -p /app/frontend/dist /var/lib/carhibou/media "/opt/carhibou-agent-releases/${CARHIBOU_VERSION}"
COPY --from=python-deps /install/ /usr/local/
COPY --from=frontend-build /src/frontend/dist/ /app/frontend/dist/
COPY --from=agent-build /out/ /opt/carhibou-agent-releases/${CARHIBOU_VERSION}/
COPY --from=agent-manifests /manifests/ /app/agent-manifests/
COPY alembic.ini /app/alembic.ini
COPY backend/migrations/ /app/backend/migrations/
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/carhibou-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/carhibou-entrypoint \
    && chown -R carhibou:carhibou /app /opt/carhibou-agent-releases /var/lib/carhibou
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
ENTRYPOINT ["carhibou-entrypoint"]
CMD ["app"]
