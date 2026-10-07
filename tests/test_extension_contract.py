"""Run dependency-free JavaScript checks when Node is available."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_extension_response_and_background_contract():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for extension contract checks")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/extension_contract.test.cjs",
         "tests/extension_receipts.test.cjs"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
