import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

assert version("tg-harness")
executable = Path(sys.executable).with_name("tg")

result = subprocess.run(
    [executable, "--help"],
    check=True,
    capture_output=True,
    text=True,
)
assert "login" in result.stdout
assert "doctor" in result.stdout
assert "skill" in result.stdout

skill = subprocess.run(
    [executable, "skill"],
    check=True,
    capture_output=True,
    text=True,
)
assert "name: tg" in skill.stdout
