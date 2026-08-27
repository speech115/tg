from __future__ import annotations

import subprocess
from importlib.metadata import version

assert version("tg-runtime")

result = subprocess.run(
    ["tg", "--help"],
    check=True,
    capture_output=True,
    text=True,
)
assert "login" in result.stdout
assert "doctor" in result.stdout
assert "run" in result.stdout
