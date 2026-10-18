"""``publish`` stage (SPEC §5, §6.3, decision §13.24, §15.14): ship every tile archive the
manifest lists (``hexes.pmtiles``, ``hexes_nbhd.pmtiles``, ``hexes_city.pmtiles``) and ``manifest.json``.

Targets:
- ``local``  copy them into ``web/public/data/`` so the Next.js app reads them from the
             same origin during development.
- ``r2``     upload to the Cloudflare R2 bucket with S3-compatible credentials from ``.env``
             (``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY``, ``R2_BUCKET``,
             ``R2_PUBLIC_BASE_URL``, ``R2_ALLOWED_ORIGINS``). Release order (SPEC §13.38):
             1. refuse a fixture, ``--bbox`` or partial build and anything ``validate`` rejects,
                compared against the manifest that is live now;
             2. upload each archive under a content-addressed key (``hexes.<sha12>.pmtiles``,
                ``immutable``), skipping keys already there; old keys are never overwritten, so
                a deployed site keeps reading the archives its build named;
             3. set CORS and fetch the first 16 KB of a new archive with a ``Range`` header;
                stop before the manifest if byte ranges or CORS fail;
             4. upload ``manifest.json`` (``no-cache``, keys pointing at the new archives) last,
                plus a dated copy under ``manifests/`` for the record.
             The web build reads that manifest (``npm run deploy``), so tiles and app change
             together; rolling back is redeploying an earlier Pages build.
- ``auto``   ``r2`` when ``R2_ACCESS_KEY_ID`` is set and the build is a whole-world real build,
             else ``local`` (a fixture or ``--bbox`` run never reaches the bucket by default).

Invariant 4: publishing refuses when any real source is not ``verified: confirmed``.
Secrets are read from ``.env`` and never printed.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import shutil
from pathlib import Path

from .. import manifest, stage_cache
from ..config import Settings
from ..registry import load_dimensions, load_sources, used_source_ids

TARGETS = ("auto", "local", "r2")


def files_to_ship(m: dict) -> list[str]:
    """manifest.json plus every tile archive the manifest lists (SPEC §13.32: one per plan archive)."""
    return ["manifest.json"] + sorted(t["key"] for t in m.get("tiles", {}).values())


def r2_key(name: str, sha256: str) -> str:
    """Content-addressed object key: a new build never overwrites bytes a live site reads."""
    return f"{name}.{sha256[:12]}.pmtiles"


ARCHIVE_CACHE = "public, max-age=31536000, immutable"
MANIFEST_CACHE = "no-cache"
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


def _live_manifest(base_url: str) -> dict | None:
    """The manifest the bucket serves now (the regression baseline); None before the first release."""
    import requests

    try:
        resp = requests.get(f"{base_url}/manifest.json", timeout=60, headers={"Cache-Control": "no-cache"})
    except requests.RequestException as exc:
        raise RuntimeError(f"publish r2: could not read the live manifest at {base_url}/manifest.json ({exc}); check R2_PUBLIC_BASE_URL") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise RuntimeError(f"publish r2: the live manifest at {base_url}/manifest.json answered HTTP {resp.status_code}; check the bucket's public access")
    return resp.json()


def _partial(settings: Settings) -> bool:
    """A fixture or ``--bbox`` build: never the live map."""
    return bool(settings.fixtures or settings.bbox)


def _exists(client, bucket: str, key: str, size: int) -> bool:
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except Exception:  # noqa: BLE001 - botocore raises ClientError (404) for a missing key
        return False
    return int(head.get("ContentLength", -1)) == size


def run(settings: Settings, target: str = "auto", local_dir: Path | None = None, max_drop: float | None = None) -> dict:
    from . import validate

    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    out = settings.out_dir
    if not (out / "manifest.json").exists():
        raise FileNotFoundError(f"{out / 'manifest.json'} missing: run `export` and `tiles` first")
    archives = files_to_ship(manifest.load(settings))[1:]
    if not archives:
        raise FileNotFoundError("manifest.json lists no tile archive: run `tiles` first")
    for f in archives:
        if not (out / f).exists():
            raise FileNotFoundError(f"{out / f} missing: run `tiles` first")
    bad = unverified_sources(settings)
    if bad:
        raise RuntimeError(f"publish refused: {', '.join(bad)} are not first-hand verified (set verified: confirmed after checking, SPEC §15, invariant 4)")
    env = _env(settings.root)
    if target == "auto":
        partial = _partial(settings)
        target = "r2" if env.get("R2_ACCESS_KEY_ID") and not partial else "local"
        print(f"publish target auto -> {target}" + (" (fixture / --bbox builds never go to R2 by default)" if partial and env.get("R2_ACCESS_KEY_ID") else ""))
    if target == "r2" and _partial(settings):
        raise RuntimeError("publish refused: a fixture or --bbox build never goes to R2 (it would replace the live map); use --target local")
    drop = validate.MAX_DROP if max_drop is None else max_drop
    if target == "local":
        validate.report(settings, validate.check(settings, max_drop=drop))
        m = manifest.load(settings)
        dest = local_dir or (settings.root / "web" / "public" / "data")
        dest.mkdir(parents=True, exist_ok=True)
        for f in archives:
            shutil.copyfile(out / f, dest / f)
        # an archive an older plan listed (e.g. hexes_fine.pmtiles) would otherwise linger forever
        for stale in sorted(p for p in dest.glob("*.pmtiles") if p.name not in archives):
            stale.unlink()
            print(f"publish local: removed {stale.name} (no longer in the manifest)")
        stamp(m, "local", "/data")
        (dest / "manifest.json").write_text(manifest.json.dumps(m, indent=2, default=manifest._json_default, ensure_ascii=False), encoding="utf-8")
        sizes = ", ".join(f"{f} ({(out / f).stat().st_size / 1e6:.1f} MB)" for f in archives)
        print(f"publish local: {sizes} and manifest.json -> {dest}")
        return {"target": "local", "dest": str(dest)}
    bucket = env.get("R2_BUCKET", "")
    base_url = (env.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("publish to R2 needs R2_PUBLIC_BASE_URL in .env: the release checks byte ranges and compares with the live manifest there")
    origins = [o.strip() for o in (env.get("R2_ALLOWED_ORIGINS") or "").split(",") if o.strip()]
    client = _client(env)
    live = _live_manifest(base_url)
    print("publish r2: comparing with the live build of " + (live.get("built_at") or "?") if live else "publish r2: no live manifest yet (first release)")
    validate.report(settings, validate.check(settings, baseline=live, max_drop=drop, release=True))
    m = manifest.load(settings)
    shipped = copy.deepcopy(m)
    for name, entry in shipped["tiles"].items():
        key = r2_key(name, entry["sha256"])
        path = out / entry["key"]
        if _exists(client, bucket, key, path.stat().st_size):
            print(f"publish r2: {key} already in the bucket, not uploaded again")
        else:
            client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": "application/octet-stream", "CacheControl": ARCHIVE_CACHE})
            print(f"publish r2: uploaded {entry['key']} as {key} ({path.stat().st_size / 1e6:.1f} MB)")
        entry["key"] = key
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": cors_rules(origins)})
    first = sorted(shipped["tiles"].values(), key=lambda e: e["key"])[0]["key"]
    check = _range_check(f"{base_url}/{first}")
    diagnosis = _diagnose(check)
    print(f"publish r2 range check at {base_url}/{first}: {diagnosis}")
    if not diagnosis.startswith("ok"):
        raise RuntimeError(f"publish r2 stopped before switching manifest.json: {diagnosis}. The new archives are uploaded under new keys; the live map is unchanged.")
    stamp(shipped, "r2", base_url)
    body = json.dumps(shipped, indent=2, default=manifest._json_default, ensure_ascii=False)
    record = out / "published" / "manifest.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    stage_cache.write_atomic(record, body)
    history = f"manifests/{shipped['built_at'].replace(':', '')}.json"
    client.upload_file(str(record), bucket, history, ExtraArgs={"ContentType": "application/json", "CacheControl": ARCHIVE_CACHE})
    client.upload_file(str(record), bucket, "manifest.json", ExtraArgs={"ContentType": "application/json", "CacheControl": MANIFEST_CACHE})
    stamp(m, "r2", base_url)
    manifest.write(settings, m)
    print(f"publish r2: manifest.json now points at {', '.join(e['key'] for e in shipped['tiles'].values())} in bucket {bucket}; CORS origins {origins or ['*']}. Next: cd web && npm run deploy")
    return {"target": "r2", "bucket": bucket, "base_url": base_url, "range_check": check, "keys": {n: e["key"] for n, e in shipped["tiles"].items()}}
