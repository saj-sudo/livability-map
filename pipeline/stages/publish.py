"""``publish`` stage (SPEC §5, §6.3, decision §13.24, §15.14): ship ``hexes.pmtiles`` and
``manifest.json``.

Targets:
- ``local``  copy both files into ``web/public/data/`` so the Next.js app reads them from the
             same origin during development.
- ``r2``     upload to the Cloudflare R2 bucket with S3-compatible credentials from ``.env``
             (``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY``, ``R2_BUCKET``,
             ``R2_PUBLIC_BASE_URL``, ``R2_ALLOWED_ORIGINS``), set the CORS rules PMTiles range
             requests need, then fetch the first 16 KB with a ``Range`` header to prove the bucket
             serves byte ranges with CORS headers.
- ``auto``   ``r2`` when ``R2_ACCESS_KEY_ID`` is set, else ``local``.

Invariant 4: publishing refuses when any real source is not ``verified: confirmed``.
Secrets are read from ``.env`` and never printed.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
from pathlib import Path

from .. import manifest
from ..config import Settings
from ..registry import load_dimensions, load_sources, used_source_ids

TARGETS = ("auto", "local", "r2")
FILES = ("hexes.pmtiles", "manifest.json")
PMTILES_MAGIC = b"PMTiles"


def _env(root: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
    env.update({k: v for k, v in os.environ.items() if k.startswith(("R2_", "CLOUDFLARE_"))})
    return env


def unverified_sources(settings: Settings) -> list[str]:
    """Ids of sources the pipeline uses whose verification is not first-hand (invariant 4)."""
    sources = load_sources(settings.sources_path)
    used = used_source_ids(sources, load_dimensions(settings.dimensions_path, sources))
    return sorted(s.id for s in sources.values() if s.id in used and s.access != "fixture" and str(s.extra.get("verified", "none")) != "confirmed")


def cors_rules(origins: list[str]) -> list[dict]:
    """S3-style CORS rules for browser range requests (SPEC §15.14)."""
    return [
        {
            "AllowedOrigins": origins or ["*"],
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["range", "if-match", "if-none-match"],
            "ExposeHeaders": ["etag", "content-length", "content-range", "accept-ranges"],
            "MaxAgeSeconds": 86400,
        }
    ]


def _client(env: dict[str, str]):
    import boto3

    missing = [k for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET") if not env.get(k)]
    if missing:
        raise RuntimeError(f"publish to R2 needs {', '.join(missing)} in .env (see .env.example)")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _range_check(url: str) -> dict:
    """Fetch the first 16 KB with Range + Origin headers and report what a browser would see."""
    import requests

    resp = requests.get(url, headers={"Range": "bytes=0-16383", "Origin": "https://example.org"}, timeout=60)
    return {
        "status": resp.status_code,
        "magic": resp.content[: len(PMTILES_MAGIC)] == PMTILES_MAGIC,
        "acao": resp.headers.get("access-control-allow-origin"),
        "cf_cache": resp.headers.get("cf-cache-status"),
        "content_range": resp.headers.get("content-range"),
    }


def _diagnose(check: dict) -> str:
    if check["status"] != 206:
        return f"expected HTTP 206 for a range request, got {check['status']}: the bucket or its custom domain is not serving byte ranges"
    if not check["magic"]:
        return "the response does not start with the PMTiles magic bytes: wrong key or a cached HTML error page"
    if not check["acao"]:
        hint = " (no cf-cache-status header: this looks like Hotlink Protection or a missing CORS policy, SPEC §15.14)" if not check["cf_cache"] else ""
        return "no Access-Control-Allow-Origin header: browsers will refuse the tiles" + hint
    return "ok: byte ranges and CORS headers are served"


def stamp(m: dict, target: str, base_url: str | None) -> dict:
    m["published_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    m["publish_target"] = target
    m["public_base_url"] = base_url
    return m


def run(settings: Settings, target: str = "auto", local_dir: Path | None = None) -> dict:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    out = settings.out_dir
    for f in FILES:
        if not (out / f).exists():
            raise FileNotFoundError(f"{out / f} missing: run `tiles` (and `export`) first")
    bad = unverified_sources(settings)
    if bad:
        raise RuntimeError(f"publish refused: {', '.join(bad)} are not first-hand verified (set verified: confirmed after checking, SPEC §15, invariant 4)")
    env = _env(settings.root)
    if target == "auto":
        target = "r2" if env.get("R2_ACCESS_KEY_ID") else "local"
        print(f"publish target auto -> {target}")
    m = manifest.load(settings)
    if target == "local":
        dest = local_dir or (settings.root / "web" / "public" / "data")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out / "hexes.pmtiles", dest / "hexes.pmtiles")
        stamp(m, "local", "/data")
        (dest / "manifest.json").write_text(manifest.json.dumps(m, indent=2, default=manifest._json_default, ensure_ascii=False), encoding="utf-8")
        print(f"publish local: hexes.pmtiles ({(out / 'hexes.pmtiles').stat().st_size / 1e6:.1f} MB) and manifest.json -> {dest}")
        return {"target": "local", "dest": str(dest)}
    bucket = env.get("R2_BUCKET", "")
    base_url = (env.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    origins = [o.strip() for o in (env.get("R2_ALLOWED_ORIGINS") or "").split(",") if o.strip()]
    client = _client(env)
    stamp(m, "r2", base_url or None)
    manifest.write(settings, m)
    client.upload_file(str(out / "hexes.pmtiles"), bucket, "hexes.pmtiles", ExtraArgs={"ContentType": "application/octet-stream", "CacheControl": "public, max-age=3600"})
    client.upload_file(str(out / "manifest.json"), bucket, "manifest.json", ExtraArgs={"ContentType": "application/json", "CacheControl": "public, max-age=300"})
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": cors_rules(origins)})
    print(f"publish r2: uploaded hexes.pmtiles and manifest.json to bucket {bucket}; CORS origins {origins or ['*']}")
    result = {"target": "r2", "bucket": bucket, "base_url": base_url}
    if base_url:
        check = _range_check(f"{base_url}/hexes.pmtiles")
        result["range_check"] = check
        print(f"publish r2 range check at {base_url}/hexes.pmtiles: {_diagnose(check)}")
    else:
        print("publish r2: set R2_PUBLIC_BASE_URL to verify range requests from the public URL")
    return result
