"""``export`` stage: planned, see SPEC §16 and pipeline.stages.PLANNED."""

from __future__ import annotations

from ..config import Settings
from . import PLANNED, NotImplementedStage


def run(settings: Settings) -> None:
    raise NotImplementedStage(f"stage 'export' is planned for Session {PLANNED['export']} (SPEC §16)")
