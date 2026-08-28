from __future__ import annotations

import subprocess
from importlib.metadata import version

assert version("tg-harness")

result = subprocess.run(
    ["tg", "--help"],
    check=True,
    capture_output=True,
    text=True,
)
assert "login" in result.stdout
assert "doctor" in result.stdout
assert "skill" in result.stdout

skill = subprocess.run(
    ["tg", "skill"],
    check=True,
    capture_output=True,
    text=True,
)
assert "name: tg" in skill.stdout
