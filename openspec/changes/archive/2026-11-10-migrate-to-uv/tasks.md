# Tasks

## 1. Preparation and lockfile

- [x] 1.1 Save the old environment baseline: Python, installed versions without local paths, and `./quality-gate.sh` result; verify the initial state and coverage are recorded without secrets.
- [x] 1.2 Check installed uv and existing `/home/mikhail/venvs/olympic_boinc_uv`, record uv and Python versions; choose a specific Docker uv tag and verify its availability. Reinstalling uv is unnecessary.
- [x] 1.3 Move extra dev to dependency group dev, preserve runtime/load and Hatchling; add `.python-version` with the verified Python 3.13 patch version of the new environment; check TOML and no lost dependencies.
- [x] 1.4 Create `uv.lock` with temporary constraints from the baseline, remove constraints, and update lock metadata without `--upgrade`; check `uv lock --check` and compare key versions with the original environment, explaining differences.
- [x] 1.5 Export `UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv` and install dependencies into the existing environment through `uv sync --locked --extra load` without recreation; check interpreter path, Python version, and application import; ensure the pyenv environment is preserved.

## 2. Development commands and quality gate

- [x] 2.1 Migrate `quality-gate.sh` to inherit `UV_PROJECT_ENVIRONMENT` without a personal path in the script, shared `uv sync --locked --extra load` preparation, and three independent `uv run --locked --no-sync` calls; preserve 90% coverage, check `bash -n` and a nonzero result on preparation error.
- [x] 2.2 Update README, load_tests/README, AGENTS, and OpenSpec context: installation, dependency management, server/Xvfb, migrations, CSV, tests, Locust, quality gate, PyCharm, and rollback; verify no active instructions use old pyenv/pip paths except migration and rollback descriptions.
- [x] 2.3 Run the full gate with `UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv`; verify successful Ruff/mypy/pytest and coverage of at least 90%; separately run `uv run --locked --extra load python -m unittest discover -s load_tests -v` and check all Locust tests.
- [x] 2.4 In an isolated temporary copy with a separate temporary `UV_PROJECT_ENVIRONMENT`, verify that failure of each of the three checks yields a nonzero gate code, other checks continue, and the coverage threshold applies; do not modify working sources for verification.

## 3. Docker

- [x] 3.1 Replace pip installation in Dockerfile with uv from an image with a pinned tag and two `uv sync --locked --no-dev` layers, the final one with `--no-editable`; use system Python without downloading another, add `.venv/bin` to PATH; verify the build with `uv.lock` in the build context.
- [x] 3.2 Check the built image: application import without dependence on the src directory, absence of dev/load tools, execution as the existing non-root user; ensure the entrypoint installs no dependencies on startup.
- [x] 3.3 In a separate compose project with test configuration, check migrations, health, CSV import/export, and absence of the scheduler; compare container-deployment scenarios and preserve existing dev volumes.

## 4. Acceptance

- [x] 4.1 In a clean temporary copy without active pyenv, run `uv sync --locked --extra load` and the gate with a separate temporary `UV_PROJECT_ENVIRONMENT`, then check standard `.venv` without this variable; verify code 0, `uv lock --check`, and an unchanged lockfile.
- [x] 4.2 In a separate copy with a separate temporary `UV_PROJECT_ENVIRONMENT`, make manifest and lock inconsistent and verify `uv sync --locked` refuses; restore the copy and confirm the working lock is unchanged.
- [x] 4.3 Check `git diff --check`, modified file scope, and absence of secrets/local paths in the lock; record coverage, test, and Docker smoke test results, and the manual step of switching PyCharm to `/home/mikhail/venvs/olympic_boinc_uv/bin/python`.
