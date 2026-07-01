# Hermia — Docker image
#
# Multi-stage build. Stage 1 installs hermia into an isolated venv so the
# runtime image ships only the artifacts pip actually needs. Stage 2 is a
# slim runtime with the venv copied in.
#
# Usage (headless fleet mode is the intended container path — the TUI needs
# a real terminal and is not the primary Docker use case):
#
#   docker run --rm \
#     --network host \
#     -v $PWD/fleets:/workspace/fleets:ro \
#     -v $PWD/results:/workspace/results \
#     ghcr.io/scottblydotcom/hermia:latest \
#     --fleet fleets/quick-local.yaml
#
# On Docker Desktop (macOS/Windows) use --add-host host.docker.internal:host-gateway
# and point the fleet YAML `host:` at http://host.docker.internal:11434.

FROM python:3.11-slim AS builder

# Build the wheel inside an isolated venv.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip \
 && pip install .


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user — hermia doesn't need any elevated privileges at runtime.
RUN groupadd --system --gid 1000 hermia \
 && useradd  --system --uid 1000 --gid hermia --home /workspace --shell /usr/sbin/nologin hermia \
 && mkdir -p /workspace/results \
 && chown -R hermia:hermia /workspace

COPY --from=builder /opt/venv /opt/venv

USER hermia
WORKDIR /workspace

# results/ should be bind-mounted by the caller so output persists.
VOLUME ["/workspace/results"]

# Version + basic smoke work with no args. Actual eval requires --fleet.
ENTRYPOINT ["hermia"]
CMD ["--help"]
