"""Pipeline stages in SPEC §5 order. Each exposes ``run(settings)`` and is idempotent."""

STAGE_ORDER = ["fetch", "grid", "pop", "admin", "hazards", "dims", "score", "export", "tiles", "publish"]


class NotImplementedStage(RuntimeError):
    """Raised by stages that are still planned for a later session (SPEC §16)."""


# Stages not yet implemented, with the SPEC §16 session that delivers them (none left).
PLANNED: dict[str, int] = {}
