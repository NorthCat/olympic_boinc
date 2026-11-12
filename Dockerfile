FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# The host user's UID, so that files in the mounted dumps/ belong to them.
ARG UID=1000
RUN useradd --uid "$UID" --create-home app

WORKDIR /app
# Dependencies have their own layer; source edits only reinstall the application.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable --no-cache && rm -rf src
COPY alembic.ini ./
COPY migrations/ migrations/
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN mkdir dumps && chown app:app dumps

USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
