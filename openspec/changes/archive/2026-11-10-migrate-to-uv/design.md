# Design

## Context

See the motivation in `proposal.md`. The project already has `pyproject.toml` with Hatchling, runtime dependencies, and `dev`/`load` extras, but no lockfile. README uses a regular venv; AGENTS and load instructions use a personal pyenv. The quality gate invokes binaries from pyenv and checks line coverage with a **90%** threshold. Dockerfile separately extracts dependencies from TOML and installs them through pip; the entrypoint invokes `alembic`, `python`, and `uvicorn` through PATH.

The user has already installed uv and created `/home/mikhail/venvs/olympic_boinc_uv`. According to `pyvenv.cfg`, it uses uv-managed CPython 3.13 and was created with uv 0.13.7; verify the exact patch version during implementation.

## Goals / Non-Goals

**Goals:** reproducible local and Docker environments, portable commands, project independence from the pyenv path; preservation of quality checks and container behavior.

**Non-Goals:** updating application dependencies for newer versions, changing API/database/browser synchronization, removing pyenv from the computer, creating a new CI system. Archived OpenSpec artifacts and shared skill templates are not rewritten.

## Decisions

1. **uv project workflow.** Use `uv sync`, `uv run`, `uv.lock`, rather than merely replacing `pip` with `uv pip`: one mechanism for resolution, installation, and execution is needed. Preserve Hatchling and `requires-python >=3.13`. Pin the existing new environment's Python 3.13 patch version in `.python-version`, verifying it before implementation. Use `/home/mikhail/venvs/olympic_boinc_uv` without recreation: in the local shell, set `export UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv` before uv commands and the quality gate. All uv calls inherit the value; do not hardcode the personal path in code or pyproject. Simply activating a venv does not replace this setting. Other developers without the variable retain the standard `.venv`; Docker uses `/app/.venv`. README should describe both options and selecting `/home/mikhail/venvs/olympic_boinc_uv/bin/python` in local PyCharm. Do not remove existing pyenv; do not reinstall uv.

2. **Dependency groups.** Move the entire `dev` extra to standard `[dependency-groups].dev`; keep `load` as an optional extra. Regular `uv sync --locked` installs the dev group; load tools are added with `uv sync --locked --extra load`. Since mypy also checks `load_tests`, the full gate prepares the environment with the `load` extra. `uv add`, `uv add --dev`, `uv add --optional load`, `uv remove` become dependency management commands; manifest and lock are committed together.

3. **First lock without intentional package upgrades.** Before migration, save installed distributions from the old environment without the project's editable entry or local paths. Temporarily transfer compatible version pins to `tool.uv.constraint-dependencies` and run `uv lock`; then remove temporary constraints and repeat `uv lock` without `--upgrade`, comparing key package versions. Do not commit temporary constraints. Let the resolver resolve missing project packages. On conflict, investigate the specific dependency and record a justified difference; do not upgrade the entire environment. The lockfile is universal; an identical lock does not imply an identical set of platform wheels.

4. **Quality gate.** Keep the entry command `./quality-gate.sh`. After resolving the root, run `uv sync --locked --extra load`; on preparation error, exit nonzero with a clear message. Then independently run `uv run --locked --no-sync ruff check .`, `uv run --locked --no-sync mypy`, and `uv run --locked --no-sync pytest --cov=olympic_boinc --cov-report=term-missing --cov-fail-under=90`. All three checks run even if one fails. Remove dependence on `V` and pyenv; uv manages the environment, inheriting `UV_PROJECT_ENVIRONMENT`. The script does not override it or contain a personal absolute path. `--no-sync` after shared preparation prevents intermediate runs from removing extra load. Do not use `uvx`, so tools come from the project lock.

5. **Other commands.** Use `uv run --locked ...` in README/AGENTS/load instructions; for Locust, `uv run --locked --extra load ...`. Update context in `openspec/config.yaml`. Preserve the Xvfb execution order `xvfb-run uv run --locked uvicorn ...`. Do not automatically edit private systemd/cron/PyCharm configurations outside the repository; describe how to replace old paths.

6. **Docker.** Do not pass local `UV_PROJECT_ENVIRONMENT` into builds or containers; use a separate `/app/.venv`. Preserve `python:3.13-slim` and the image runtime interpreter; uv does not download a second Python during the build. Copy the uv binary from the official image with a specific tag chosen during implementation, without `latest`. Copy `pyproject.toml` and `uv.lock`, install dependencies in a separate layer with `uv sync --locked --no-dev --no-install-project`, then after copying `src`, `uv sync --locked --no-dev --no-editable`. Do not select extra load. Add `/app/.venv/bin` to PATH so the entrypoint and `docker compose exec app python ...` continue to work without uv or network on startup. Preserve the user, UID, dumps, Alembic, and scheduler settings. Remove previous requirements preparation and pip install; the lock enters the Docker build context. Verify package import after removing `src` if that step is retained.

## Risks / Trade-offs

- [Package differences in the first lock] → temporary constraints, version comparison, full gate, and Docker verification.
- [uv selects another environment] → explicitly export `UV_PROJECT_ENVIRONMENT` locally, deactivate pyenv if necessary, and check `uv run --locked python -c 'import sys; print(sys.executable, sys.version)'`.
- [Sync needs network and writes to cache/the selected environment] → prepare the environment with registry access; authorize necessary operations separately in the sandbox. `--locked` prevents silent lock changes, not network access.
- [External venv is shared by multiple projects] → dedicate `/home/mikhail/venvs/olympic_boinc_uv` to this project only: sync removes extra packages. For temporary checks, specify a separate path rather than inheriting the working venv.
- [Runtime image accidentally includes dev/load] → check environment contents and absence of Ruff, mypy, pytest, and Locust in the image.
- [Dev database data during Docker smoke test] → use an isolated compose project and test settings; do not delete existing volumes.

## Migration Plan

1. Record the baseline: Python/package versions and the current gate result. Check the already installed uv and new environment, record versions; reinstall nothing without a need.
2. Prepare the manifest, Python pin, and lock; export `UV_PROJECT_ENVIRONMENT` and install dev + load in the existing external venv; check paths and key versions. Keep the old environment.
3. Migrate the gate and current documentation; run all checks, including the separate 5 Locust unittest tests.
4. Migrate Dockerfile; build the image and verify health, migrations, CSV import/export, and absence of the scheduler in an isolated environment. Compare previous container-deployment scenarios.
5. Verify reproducibility in a clean temporary checkout: with a separate temporary `UV_PROJECT_ENVIRONMENT`, run `uv sync --locked --extra load` and the gate; additionally check standard `.venv` without this variable; `uv lock --check` and no lock changes after runs. Check failure for a mismatched manifest/lock.
6. After successful verification, switch PyCharm to `/home/mikhail/venvs/olympic_boinc_uv/bin/python`, and personal commands to uv with `UV_PROJECT_ENVIRONMENT`. Rollback: revert manifest/Dockerfile/gate/documentation changes and use the preserved pyenv; the database requires no rollback.

## References

- [Astral: migrating to the uv project workflow](https://docs.astral.sh/uv/guides/migration/pip-to-project/).
- [Astral: locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/).
- [Astral: uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/).

- [Astral: selecting the environment path](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).
