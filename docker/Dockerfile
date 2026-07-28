# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

ENV POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

RUN apt-get update && \
    apt-get install -yq --no-install-recommends \
        build-essential \
        git \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Keep dependency installation cached when only application source changes.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY README.md ./
COPY src/ ./src/
RUN poetry install --only main


FROM python:3.12-slim-bookworm AS runtime

ARG USERNAME=pdp-station
ARG USER_UID=10001

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && \
    apt-get install -yq --no-install-recommends \
        curl \
        libpq5 && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid ${USER_UID} ${USERNAME}

WORKDIR /app

COPY --from=builder --chown=${USERNAME}:${USERNAME} /app/.venv /app/.venv
COPY --from=builder --chown=${USERNAME}:${USERNAME} /app/src /app/src

# Poetry installs the project in editable mode, so its .pth file points here.
RUN python -c "import pdp_station"

USER ${USERNAME}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/readyz || exit 1

CMD ["pdp-station-api"]
