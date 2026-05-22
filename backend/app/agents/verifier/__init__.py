"""Verifier agent — fact-checks AI-generated content at every pipeline stage.

Three checkpoints:
  1. Idea verification  — rationale/why_now against research sources
  2. Script verification — talking_points against research_snapshot
  3. Scene verification  — scene text cross-check against script + structure check
"""

from app.agents.verifier.service import (
    run_idea_verification,
    run_script_verification,
)

__all__ = [
    "run_idea_verification",
    "run_script_verification",
]
