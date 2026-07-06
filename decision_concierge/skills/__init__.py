"""Skill registry with progressive disclosure (Day 3): only frontmatter
metadata is loaded at startup. A skill's full SKILL.md body (its system
instructions) is read from disk only at the moment it is triggered, and its
skill.py module is imported lazily the same way — keeps idle skills out of
context/token budget entirely.
"""

import importlib
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent


@dataclass
class SkillMeta:
    name: str
    description: str
    folder: Path


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.strip()


class SkillRegistry:
    def __init__(self):
        self._meta: dict[str, SkillMeta] = {}
        for folder in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
            skill_md = folder / "SKILL.md"
            if not skill_md.exists():
                continue
            fm, _ = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            name = fm.get("name", folder.name)
            self._meta[name] = SkillMeta(
                name=name, description=fm.get("description", ""), folder=folder
            )

    def list_metadata(self) -> list[SkillMeta]:
        return list(self._meta.values())

    def instructions(self, name: str) -> str:
        """Full SKILL.md body — loaded only when the skill actually fires."""
        meta = self._meta[name]
        text = (meta.folder / "SKILL.md").read_text(encoding="utf-8")
        _, body = _parse_frontmatter(text)
        return body

    def run(self, name: str, *args, **kwargs):
        """Lazily imports skill.py and calls its run(...) entrypoint."""
        module = importlib.import_module(f"decision_concierge.skills.{name}.skill")
        return module.run(*args, **kwargs)
