#!/usr/bin/env bash
set -uo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1

echo 'Syncing the locked environment (dev + security + load)...'
if ! uv sync --locked --extra load --group security; then
    echo 'Quality gate failed: could not prepare the environment.' >&2
    exit 1
fi

status=0

echo 'Running Ruff...'
uv run --locked --no-sync ruff check . || status=1
uv run --locked --no-sync ruff format --check . || status=1

echo 'Running mypy...'
uv run --locked --no-sync mypy || status=1

echo 'Running pytest with coverage (minimum 90%)...'
uv run --locked --no-sync pytest --cov=olympic_boinc --cov-report=term-missing --cov-fail-under=90 || status=1

echo 'Running Bandit...'
uv run --locked --no-sync bandit --recursive src migrations scripts docker load_tests || status=1

echo 'Running pip-audit against locked dependencies (dev + security + load)...'
if audit_requirements=$(mktemp); then
    trap 'rm -f -- "$audit_requirements"' EXIT
    if uv export --locked --extra load --group security --no-emit-project \
        --format requirements.txt --output-file "$audit_requirements" > /dev/null; then
        uv run --locked --no-sync pip-audit --requirement "$audit_requirements" \
            --require-hashes --disable-pip || status=1
    else
        echo 'Could not export locked dependencies for pip-audit.' >&2
        status=1
    fi
else
    echo 'Could not create a temporary requirements file for pip-audit.' >&2
    status=1
fi

echo 'Running system Semgrep...'
if command -v semgrep > /dev/null 2>&1; then
    semgrep scan --config p/security-audit --error --strict --metrics=off --disable-version-check --no-git-ignore \
        src migrations scripts docker load_tests tests Dockerfile quality-gate.sh || status=1
else
    echo 'Semgrep is not available on PATH; install it separately from the project environment.' >&2
    status=1
fi

if (( status == 0 )); then
    echo 'Quality gate passed.'
else
    echo 'Quality gate failed.' >&2
fi

exit "$status"
