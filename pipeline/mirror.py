"""Raw-input mirror (SPEC §13.41): a private R2 bucket that holds every raw file recorded in
``data/raw/CHECKSUMS``, keyed by its sha256 (``raw/<sha256>``), so a clean machine can rebuild the
same map after an upstream file moves, changes or disappears.

- ``python -m pipeline mirror`` uploads every recorded raw file the bucket does not hold yet.
- ``fetch`` restores any file with a recorded checksum from the mirror *before* going upstream
  (missing on this machine, or moved upstream), and checks the bytes against the recorded digest.
  A source with no recorded checksum (a new source, or a vintage refreshed on purpose by deleting
  its CHECKSUMS line) still comes from upstream.

The bucket must be private and separate from the public tiles bucket: some inputs may be kept for
reproducibility but not redistributed (SHDI is non-commercial, the Tanzania census has no open
licence, SPEC §13.13, docs/manual-steps.md). Configure ``R2_RAW_BUCKET`` in ``.env``; the R2
credentials are the ones ``publish`` uses. Fixture runs never touch it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .checksums import read_checksums, sha256_of
from .config import Settings
from .envfile import read_env

PREFIX = "raw/"


def key(digest: str) -> str:
    return f"{PREFIX}{digest}"


def _missing(exc: Exception) -> bool:
    code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return code in ("404", "NoSuchKey", "NotFound")


@dataclass
class Mirror:
    client: object
    bucket: str

    def size_of(self, digest: str) -> int | None:
        """Bytes stored under the digest, or None when the mirror does not hold it."""
        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key(digest))["ContentLength"])
        except Exception as exc:  # noqa: BLE001 - botocore ClientError; anything else is re-raised
            if _missing(exc):
                return None
            raise

    def push(self, path: Path, digest: str, source_id: str, filename: str) -> bool:
        """Upload unless already held at the same size. True when bytes were sent."""
        if self.size_of(digest) == path.stat().st_size:
            return False
        self.client.upload_file(str(path), self.bucket, key(digest), ExtraArgs={"Metadata": {"source": source_id, "file": filename}})
        return True

    def restore(self, digest: str, dest: Path) -> bool:
        """Download the file with this digest to ``dest``. False when the mirror does not hold it
        or its bytes do not match (the caller then goes upstream); never leaves a partial file."""
        if self.size_of(digest) is None:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".mirror.part")
        try:
            self.client.download_file(self.bucket, key(digest), str(tmp))
            if sha256_of(tmp) != digest:
                print(f"mirror {key(digest)} does not match its own digest; ignoring it")
                return False
            tmp.replace(dest)
            return True
        finally:
            tmp.unlink(missing_ok=True)


def from_env(settings: Settings, required: bool = False) -> Mirror | None:
    """The configured mirror, or None (fixture runs, or no ``R2_RAW_BUCKET``)."""
    if settings.fixtures:
        if required:
            raise RuntimeError("the raw mirror is for real data; fixture runs never use it")
        return None
    env = read_env(settings.root)
    bucket = env.get("R2_RAW_BUCKET", "")
    if not bucket:
        if required:
            raise RuntimeError("set R2_RAW_BUCKET in .env to a private R2 bucket (see docs/deploy.md, raw mirror)")
        return None
    if bucket == env.get("R2_BUCKET"):
        raise RuntimeError("R2_RAW_BUCKET must be a separate, private bucket: the tiles bucket is public and some raw inputs may not be redistributed")
    missing = [k for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY") if not env.get(k)]
    if missing:
        raise RuntimeError(f"the raw mirror needs {', '.join(missing)} in .env")
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    return Mirror(client, bucket)


def push_all(settings: Settings, mirror: Mirror, only: list[str] | None = None) -> dict[str, int]:
    """Upload every raw file recorded in CHECKSUMS whose bytes on disk match the record."""
    counts = {"uploaded": 0, "held": 0, "missing": 0, "changed": 0}
    for (sid, fname), digest in sorted(read_checksums(settings.raw_dir / "CHECKSUMS").items()):
        if only and sid not in only:
            continue
        path = settings.raw(sid) / fname
        if not path.exists():
            counts["missing"] += 1
            print(f"mirror missing  {sid}/{fname}: not on this machine")
            continue
        if mirror.size_of(digest) == path.stat().st_size:
            counts["held"] += 1
            continue
        if sha256_of(path) != digest:
            counts["changed"] += 1
            print(f"mirror changed  {sid}/{fname}: differs from CHECKSUMS; run `fetch` first")
            continue
        mirror.push(path, digest, sid, fname)
        counts["uploaded"] += 1
        print(f"mirror uploaded {sid}/{fname} ({path.stat().st_size / 1e6:.1f} MB) as {key(digest)}")
    print(f"mirror summary: {counts}")
    return counts


def missing_from(settings: Settings, mirror: Mirror) -> list[str]:
    """``source/file`` entries of CHECKSUMS the mirror does not hold (publish warns about them)."""
    return [f"{sid}/{fname}" for (sid, fname), digest in sorted(read_checksums(settings.raw_dir / "CHECKSUMS").items()) if mirror.size_of(digest) is None]
