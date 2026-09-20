"""Pipeline stages in §5 order. Each exposes ``run(settings) -> None`` and is idempotent."""

STAGE_ORDER = ["fetch", "grid", "pop", "admin", "hazards", "dims", "score", "export", "tiles", "publish"]

# Stages not yet implemented, with the SPEC §16 session that delivers them.
PLANNED = {
    "hazards": 2,
    "dims": 4,
    "score": 4,
    "export": 4,
    "tiles": 5,
    "publish": 5,
}
