"""Filesystem skill loader for the visual agent.

CrewAI 1.x agents accept a ``skills=[Path | Skill, ...]`` field. CrewAI's
``discover_skills(path)`` (called automatically when the agent boots, see
``crewai/skills/loader.py``) walks **the children** of each given path looking
for ``<child>/SKILL.md``. So one ``skills/`` parent folder discovers all three
of our system skills in one entry.

System skills live in ``backend/skills/`` (this repo). Per-user uploaded
skills (the ``skill_files`` table) are pulled out of Supabase Storage at
session boot — see ``flow_sharpen`` for that path.

Per the PRD §11.7 budget, total skill injection is capped at 10KB combined.
We don't enforce that here yet; the cap will land when per-user skills come
online in PR3.
"""

from __future__ import annotations

from pathlib import Path

# Repo-relative root for system skills. Resolved against the backend
# directory so it works regardless of cwd.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
SYSTEM_SKILLS_ROOT = _BACKEND_ROOT / "skills"

# Names live here for documentation + sanity checks; CrewAI's discoverer
# walks the parent folder and picks up everything under it.
SYSTEM_SKILLS = (
    "excalidraw-canvas",
    "excalidraw-diagram",
    "ladder-voice",
)


def system_skill_paths() -> list[Path]:
    """Return the parent folder(s) to hand to ``Agent(skills=...)``.

    CrewAI's ``discover_skills`` enumerates child directories under each path,
    not the path itself, so one entry covers our three system skills. Returns
    an empty list when the folder is missing — caller passes ``None`` instead
    of an empty list (CrewAI's ``skills`` field has ``min_length=1``).
    """
    if not SYSTEM_SKILLS_ROOT.is_dir():
        return []
    # Sanity check: at least one valid skill must be present, otherwise the
    # caller may as well pass None. CrewAI logs warnings on bad SKILL.md
    # files and silently drops them; a folder with zero good skills won't
    # crash but also won't add anything.
    has_any = any(
        (SYSTEM_SKILLS_ROOT / name / "SKILL.md").is_file()
        for name in SYSTEM_SKILLS
    )
    return [SYSTEM_SKILLS_ROOT] if has_any else []


__all__ = ["SYSTEM_SKILLS_ROOT", "SYSTEM_SKILLS", "system_skill_paths"]
