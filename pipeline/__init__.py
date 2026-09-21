"""livability-map offline pipeline (SPEC §5).

Run with ``python -m pipeline <stage>``. Stages read and write parquet under ``data/`` (or the
fixture run directory when ``--fixtures`` is set) and never touch the web app.
"""

__version__ = "0.1.0"
