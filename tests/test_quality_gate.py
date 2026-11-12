"""Exercise gate orchestration without running scanners, network calls or nested pytest."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKS = ["ruff", "ruff-format", "mypy", "pytest", "bandit", "export", "pip-audit", "semgrep"]
STUB = """
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
name = Path(sys.argv[0]).name
stage = args[3] if name == "uv" and args[0] == "run" else args[0] if name == "uv" else name
if stage == "ruff" and args[4] == "format":
    stage = "ruff-format"
with open(os.environ["GATE_CALLS"], "a") as log:
    log.write(json.dumps({"stage": stage, "args": args, "cwd": os.getcwd()}) + "\\n")
if stage == "export":
    Path(args[args.index("--output-file") + 1]).write_text("example==1.0\\n")
sys.exit(1 if stage == os.environ.get("GATE_FAIL_STAGE") else 0)
"""


@pytest.mark.parametrize("failure", [None, "sync", *CHECKS, "missing-semgrep"])
def test_gate_runs_all_checks_and_propagates_failures(tmp_path, failure):
    binaries = tmp_path / "bin"
    binaries.mkdir()

    for utility in ("dirname", "mktemp", "rm"):
        executable = shutil.which(utility)

        assert executable is not None

        (binaries / utility).symlink_to(executable)

    for name in ("uv", "semgrep"):
        if name == "semgrep" and failure == "missing-semgrep":
            continue
        executable = binaries / name
        executable.write_text(f"#!{sys.executable}\n{STUB}")
        executable.chmod(0o755)

    calls_path = tmp_path / "calls.jsonl"
    env = {
        **os.environ,
        "PATH": str(binaries),
        "GATE_CALLS": str(calls_path),
        "GATE_FAIL_STAGE": failure or "",
        "UV_PROJECT_ENVIRONMENT": str(tmp_path / "external-env"),
    }
    bash = shutil.which("bash")

    assert bash is not None

    result = subprocess.run(
        [bash, str(ROOT / "quality-gate.sh")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    expected = ["sync", *CHECKS]
    if failure == "sync":
        expected = ["sync"]
    elif failure == "export":
        expected.remove("pip-audit")
    elif failure == "missing-semgrep":
        expected.remove("semgrep")

        assert "Semgrep is not available on PATH" in result.stderr

    assert [call["stage"] for call in calls] == expected
    assert all(call["cwd"] == str(ROOT) for call in calls)
    assert calls[0]["args"] == ["sync", "--locked", "--extra", "load", "--group", "security"]
    assert result.returncode == (0 if failure is None else 1), result.stderr

    for call in calls:
        args = call["args"]
        if call["stage"] == "export":
            assert "--no-emit-project" in args and "--locked" in args
            assert not Path(args[args.index("--output-file") + 1]).exists()
        elif call["stage"] == "pip-audit":
            assert {"--disable-pip", "--require-hashes"} <= set(args)
        elif call["stage"] == "semgrep":
            assert "--error" in args and "--strict" in args
            assert "--no-git-ignore" in args
            assert args[args.index("--config") + 1] == "p/security-audit"
