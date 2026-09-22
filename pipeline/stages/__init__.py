"""Pipeline stages in SPEC §5 order. Each exposes ``run(settings)`` and is idempotent."""

STAGE_ORDER = ["fetch", "grid", "pop", "admin", "hazards", "dims", "score", "export", "tiles", "publish"]


class NotImplementedStage(RuntimeError):
    """Raised by stages that are still planned for a later session (SPEC §16)."""


# Stages not yet implemented, with the SPEC §16 session that delivers them.
PLANNED = {
    "score": 4,
    "export": 4,
    "tiles": 5,
    "publish": 5,
}
