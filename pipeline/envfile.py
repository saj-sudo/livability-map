"""``.env`` reading for the steps that talk to Cloudflare (publish, the raw mirror). Values from
the process environment win for ``R2_*`` and ``CLOUDFLARE_*``; secrets are never printed.
"""

from __future__ import annotations

import os
from pathlib import Path


def read_env(root: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
    env.update({k: v for k, v in os.environ.items() if k.startswith(("R2_", "CLOUDFLARE_"))})
    return env
