from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from .errors import SkillError


def read_skill() -> str:
    try:
        return files("tg").joinpath("SKILL.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        source_path = Path(__file__).resolve().parents[2] / "skills" / "tg" / "SKILL.md"
        try:
            return source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SkillError(f"cannot read bundled skill: {exc}") from exc
