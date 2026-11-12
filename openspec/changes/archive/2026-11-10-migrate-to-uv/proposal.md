# Proposal

## Why

Dependencies are currently installed with pip without a lockfile, and development commands are tied to a personal pyenv environment. uv will allow reproducing the environment from the repository and using the same dependency versions locally and in Docker builds.

## What Changes

- Move to the uv project workflow: existing local environment `/home/mikhail/venvs/olympic_boinc_uv` through `UV_PROJECT_ENVIRONMENT`, `.python-version` with Python 3.13, and version-controlled `uv.lock`. Retain the standard `.venv` for other developers.
- Move development tools from the `dev` extra to the `dev` dependency group; preserve the `load` extra.
- Move the quality gate and instructions to uv, preserving the three checks and current 90% coverage threshold.
- Build the Docker environment from the lockfile without dev/load dependencies or package installation on startup.
- Update development instructions and OpenSpec context; do not automatically remove the existing pyenv and its environment.

## Capabilities

### New Capabilities

None. This changes development and build tools; `skip_specs: true`.

### Modified Capabilities

None. API, data, and container behavior requirements remain unchanged.

## Impact

uv is already installed by the user; the external environment was created in advance. Reinstalling uv and recreating the environment are unnecessary. The personal path is set through an environment variable rather than a project setting in Git.

`pyproject.toml`, new `uv.lock` and `.python-version`, `quality-gate.sh`, `Dockerfile`, `.dockerignore` if necessary, `README.md`, `load_tests/README.md`, `AGENTS.md`, `openspec/config.yaml`. Installation commands change from `pip install -e '.[dev]'` to `uv sync --locked`. Database migrations and application code do not change.
