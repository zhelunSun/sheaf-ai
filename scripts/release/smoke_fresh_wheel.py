#!/usr/bin/env python3
"""Smoke-test a built Sheaf wheel from an isolated, non-editable install.

The script is intentionally standard-library-only so the release workflow can
run it before Sheaf (or its development dependencies) is installed globally.
It creates a temporary virtual environment, installs the supplied wheel, then
checks the installed distribution metadata, both CLI entry points, and a real
JSON-RPC exchange with the stdio MCP server.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile
from email.parser import Parser


CORE_TOOLS = {
    "sheaf_collect",
    "sheaf_search",
    "sheaf_crystallize",
    "sheaf_get_card",
}


class SmokeFailure(RuntimeError):
    """Raised when a release-artifact assertion fails."""


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        rendered = " ".join(command)
        raise SmokeFailure(
            f"Command failed ({completed.returncode}): {rendered}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed


def _wheel_metadata(wheel: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_files = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                raise SmokeFailure(
                    f"Expected one dist-info/METADATA in {wheel}, found "
                    f"{len(metadata_files)}"
                )
            raw = archive.read(metadata_files[0]).decode("utf-8")
    except (OSError, zipfile.BadZipFile) as exc:
        raise SmokeFailure(f"Cannot read wheel {wheel}: {exc}") from exc

    metadata = Parser().parsestr(raw)
    name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    if not name or not version:
        raise SmokeFailure(f"Wheel metadata is missing Name or Version: {wheel}")
    return name, version


def _venv_paths(venv_dir: Path) -> tuple[Path, Path, Path]:
    if os.name == "nt":
        scripts = venv_dir / "Scripts"
        return (
            scripts / "python.exe",
            scripts / "sheaf.exe",
            scripts / "sheaf-mcp.exe",
        )
    scripts = venv_dir / "bin"
    return scripts / "python", scripts / "sheaf", scripts / "sheaf-mcp"


def _isolated_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("SHEAF_MCP_TOOLS", None)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "SHEAF_DATA_DIR": str(home / "sheaf-data"),
            "NO_COLOR": "1",
            "PYTHONUTF8": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    return env


def _assert_installed_version(
    python: Path,
    expected_version: str,
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    completed = _run(
        [
            str(python),
            "-c",
            (
                "from importlib.metadata import version; "
                "print(version('sheaf-ai'))"
            ),
        ],
        cwd=cwd,
        env=env,
    )
    actual = completed.stdout.strip()
    if actual != expected_version:
        raise SmokeFailure(
            f"Installed version mismatch: expected {expected_version}, got {actual}"
        )


def _assert_cli(
    cli: Path,
    expected_version: str,
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    version_result = _run([str(cli), "--version"], cwd=cwd, env=env)
    expected_output = f"Sheaf v{expected_version}"
    if version_result.stdout.strip() != expected_output:
        raise SmokeFailure(
            f"CLI version mismatch: expected {expected_output!r}, "
            f"got {version_result.stdout.strip()!r}"
        )

    help_result = _run([str(cli), "--help"], cwd=cwd, env=env)
    if "usage:" not in help_result.stdout.lower():
        raise SmokeFailure("CLI --help output does not contain a usage line")


def _assert_stdio_mcp(
    mcp_cli: Path,
    expected_version: str,
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "release-smoke", "version": "1.0"},
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    input_text = "".join(json.dumps(request) + "\n" for request in requests)
    completed = _run(
        [str(mcp_cli)],
        cwd=cwd,
        env=env,
        input_text=input_text,
        timeout=30,
    )

    responses: dict[object, dict] = {}
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SmokeFailure(f"MCP emitted non-JSON stdout: {line!r}") from exc
        if "id" in response:
            responses[response["id"]] = response

    if set(responses) != {1, 2}:
        raise SmokeFailure(
            f"Expected MCP responses for request ids 1 and 2, got {set(responses)}"
        )
    for request_id, response in responses.items():
        if "error" in response:
            raise SmokeFailure(f"MCP request {request_id} failed: {response['error']}")

    initialize = responses[1].get("result", {})
    server_info = initialize.get("serverInfo", {})
    if server_info.get("name") != "sheaf":
        raise SmokeFailure(f"Unexpected MCP server info: {server_info}")
    if server_info.get("version") != expected_version:
        raise SmokeFailure(
            "MCP version mismatch: "
            f"expected {expected_version}, got {server_info.get('version')}"
        )

    tools = responses[2].get("result", {}).get("tools", [])
    tool_names = {tool.get("name") for tool in tools}
    if tool_names != CORE_TOOLS:
        raise SmokeFailure(
            f"Default MCP tool surface mismatch: expected {sorted(CORE_TOOLS)}, "
            f"got {sorted(name for name in tool_names if name)}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install a Sheaf wheel in a fresh venv and smoke-test its entry points."
    )
    parser.add_argument("--wheel", required=True, type=Path, help="Path to one .whl file")
    parser.add_argument(
        "--expected-version",
        help="Expected distribution/CLI/MCP version (defaults to wheel metadata)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wheel = args.wheel.expanduser().resolve()
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise SmokeFailure(f"--wheel must name an existing .whl file: {wheel}")

    distribution_name, wheel_version = _wheel_metadata(wheel)
    if distribution_name.lower().replace("_", "-") != "sheaf-ai":
        raise SmokeFailure(f"Expected sheaf-ai wheel, found {distribution_name!r}")
    expected_version = args.expected_version or wheel_version
    if wheel_version != expected_version:
        raise SmokeFailure(
            f"Wheel version mismatch: expected {expected_version}, got {wheel_version}"
        )

    print(f"[smoke] artifact: {wheel.name} ({distribution_name} {wheel_version})")
    with tempfile.TemporaryDirectory(prefix="sheaf-wheel-smoke-") as temp:
        temp_dir = Path(temp)
        venv_dir = temp_dir / "venv"
        run_dir = temp_dir / "run"
        home_dir = temp_dir / "home"
        run_dir.mkdir()
        home_dir.mkdir()

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        python, cli, mcp_cli = _venv_paths(venv_dir)
        env = _isolated_env(home_dir)
        _run(
            [str(python), "-m", "pip", "install", "--no-cache-dir", str(wheel)],
            cwd=run_dir,
            env=env,
            timeout=300,
        )

        missing = [path for path in (python, cli, mcp_cli) if not path.is_file()]
        if missing:
            raise SmokeFailure(
                "Wheel did not install the expected entry points: "
                + ", ".join(str(path) for path in missing)
            )

        _assert_installed_version(
            python, expected_version, cwd=run_dir, env=env
        )
        print("[smoke] installed metadata: PASS")
        _assert_cli(cli, expected_version, cwd=run_dir, env=env)
        print("[smoke] sheaf CLI: PASS")
        _assert_stdio_mcp(mcp_cli, expected_version, cwd=run_dir, env=env)
        print("[smoke] sheaf-mcp stdio: PASS")

    print("[smoke] fresh-wheel gate: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeFailure, subprocess.TimeoutExpired) as exc:
        print(f"[smoke] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
