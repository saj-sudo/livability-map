"""CLI: ``python -m pipeline [--fixtures] [--res 4 --res 5] [--bbox minlng,minlat,maxlng,maxlat] <stage>``.

Global options come before the stage name (typer callback convention).

Stages run in SPEC §5 order. ``all`` runs every implemented stage and stops, with a clear
message, at the first stage that is still planned for a later session (SPEC §16).
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from . import timing
from .config import Settings, find_root, parse_bbox
from .stages import PLANNED, STAGE_ORDER, NotImplementedStage

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)


@app.callback()
def main(
    ctx: typer.Context,
    fixtures: bool = typer.Option(False, "--fixtures", help="Run against the synthetic fixture world (SPEC §11.1)."),
    res: list[int] = typer.Option(None, "--res", help="H3 resolution(s) from pipeline/resolution_plan.yaml; default: all of them."),
    bbox: str = typer.Option(None, "--bbox", help="minlng,minlat,maxlng,maxlat to run a subregion."),
    force: bool = typer.Option(False, "--force", help="Ignore stage caches and recompute."),
    root: Path = typer.Option(None, "--root", help="Repo root (auto-detected)."),
) -> None:
    settings = Settings(root=root.resolve() if root else find_root(), fixtures=fixtures, force=force)
    if res:
        unknown = sorted(set(res) - set(settings.plan.resolutions()))
        if unknown:
            raise typer.BadParameter(f"--res {unknown} is not in {settings.plan_path.name} (plan: {settings.plan.resolutions()})")
        settings.res = sorted(set(res))
    settings.bbox = parse_bbox(bbox)
    if fixtures:
        from .fixtures import make_fixtures

        make_fixtures.ensure(settings.fixture_data_dir)
        settings.iso_overrides = dict(make_fixtures.ISO_OVERRIDES)
    ctx.obj = settings
    print(f"pipeline {settings.describe()}")


def _settings(ctx: typer.Context) -> Settings:
    return ctx.obj


def _run_stage(name: str, settings: Settings, **kwargs) -> bool:
    """Run one stage. Returns False if the stage is still planned."""
    import importlib

    mod = importlib.import_module(f"pipeline.stages.{name}")
    try:
        with timing.timed(settings, name):  # SPEC §11: wall time and peak RSS per stage
            mod.run(settings, **kwargs)
    except NotImplementedStage as exc:
        print(f"{name:6s} {exc}")
        return False
    except RuntimeError as exc:
        if name in PLANNED and "planned for Session" in str(exc):
            print(f"{name:6s} {exc}")
            return False
        _fail(name, exc)
    except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
        _fail(name, exc)
    return True


def _fail(name: str, exc: Exception) -> None:
    """Workspace rule: a failed stage prints what went wrong in a sentence, never a traceback.
    Stage errors are written to be read (they name the missing file or the stage to run first);
    set PIPELINE_TRACEBACK=1 to see the full stack when debugging."""
    import os

    if os.environ.get("PIPELINE_TRACEBACK"):
        raise exc
    message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
    print(f"{name:6s} stopped: {message}", file=sys.stderr)
    raise typer.Exit(code=1)


@app.command()
def fetch(ctx: typer.Context, only: list[str] = typer.Option(None, "--only", help="Source id(s) to fetch.")) -> None:
    """Download and checksum sources (SPEC §5 fetch)."""
    from .stages import fetch as stage

    results = stage.run(_settings(ctx), only=only or None)
    if any(r.status in ("refused", "error") for r in results):
        raise typer.Exit(code=1)


@app.command()
def urban(ctx: typer.Context) -> None:
    """GHS-SMOD urban centres and clusters as saved polygons with ids (SPEC §13.31)."""
    _run_stage("urban", _settings(ctx))


@app.command()
def grid(ctx: typer.Context) -> None:
    """Land polygons -> H3 hexes (SPEC §5 grid)."""
    _run_stage("grid", _settings(ctx))


@app.command()
def pop(ctx: typer.Context) -> None:
    """GHSL population per hex, inhabited flag (SPEC §5 pop)."""
    _run_stage("pop", _settings(ctx))


@app.command()
def admin(ctx: typer.Context) -> None:
    """Country and admin1 per hex (SPEC §5 admin)."""
    _run_stage("admin", _settings(ctx))


@app.command()
def hazards(ctx: typer.Context) -> None:
    """Heat, riverine and coastal flood, water stress per hex with scores (SPEC §8.1-8.2)."""
    _run_stage("hazards", _settings(ctx))


@app.command()
def dims(ctx: typer.Context, only: list[str] = typer.Option(None, "--only", help="Recompute only these dimension ids and merge them into the existing dims parquet (adding a layer without redoing the tract overlays).")) -> None:
    """Wellbeing and life dimensions via the registry joiners (SPEC §20.2-20.3)."""
    _run_stage("dims", _settings(ctx), only=only or None)


@app.command()
def score(ctx: typer.Context) -> None:
    """Exposure, coverage, wellbeing score, bivariate class, per-domain percentiles (SPEC §8.2-8.4)."""
    _run_stage("score", _settings(ctx))


@app.command()
def export(ctx: typer.Context, geojson: bool = typer.Option(False, "--geojson", help="Also write hexes_r{res}.geojsonl for tippecanoe.")) -> None:
    """Final per-hex parquet and manifest.json (SPEC §6)."""
    _run_stage("export", _settings(ctx), geojson=geojson)


@app.command()
def tiles(
    ctx: typer.Context,
    backend: str = typer.Option("auto", "--backend", help="auto | python | tippecanoe (SPEC §13.18)."),
    workers: int = typer.Option(None, "--workers", help="Encoder processes (default: cores - 1; 0 = in-process)."),
    archive: str = typer.Option(None, "--archive", help="Build only this plan archive (hexes | hexes_nbhd | hexes_city)."),
) -> None:
    """hexes_r{res}.parquet -> one PMTiles archive per resolution-plan archive; zooms from the manifest (SPEC §9.1)."""
    _run_stage("tiles", _settings(ctx), backend=backend, workers=workers, archive=archive)


MAX_DROP_HELP = "Largest share of any layer's inhabited coverage a build may lose against the live one (default 0.05); raise it only for a drop you have explained."


@app.command()
def validate(
    ctx: typer.Context,
    max_drop: float = typer.Option(None, "--max-drop", help=MAX_DROP_HELP),
    release: bool = typer.Option(False, "--release", help="Also require a whole-world real build, as publish --target r2 does."),
) -> None:
    """Check the build before publish: archives match and are fresh, no layer came out empty, no coverage collapse (SPEC §13.38)."""
    from .stages import validate as stage

    _run_stage("validate", _settings(ctx), max_drop=stage.MAX_DROP if max_drop is None else max_drop, release=release)


@app.command()
def publish(
    ctx: typer.Context,
    target: str = typer.Option("auto", "--target", help="auto | local (web/public/data) | r2 (Cloudflare, .env credentials)."),
    local_dir: Path = typer.Option(None, "--local-dir", help="Override the local target directory."),
    max_drop: float = typer.Option(None, "--max-drop", help=MAX_DROP_HELP),
) -> None:
    """Validate, then ship every tile archive + manifest.json (SPEC §6.3, §13.24, §13.38)."""
    _run_stage("publish", _settings(ctx), target=target, local_dir=local_dir, max_drop=max_drop)


@app.command()
def sanity(ctx: typer.Context) -> None:
    """Print SPEC §8.5 counts and spot checks for whatever stages have run."""
    from . import sanity as mod

    settings = _settings(ctx)
    spots = None
    if settings.fixtures:
        from .fixtures import make_fixtures

        spots = make_fixtures.SPOT_CHECKS
    mod.run(settings, spots)


@app.command(name="all")
def run_all(ctx: typer.Context, stop_at: str = typer.Option(None, "--stop-at", help="Stop before this stage.")) -> None:
    """Run every implemented stage in order, then sanity checks."""
    settings = _settings(ctx)
    from .stages import fetch as fetch_stage

    for name in STAGE_ORDER:
        if stop_at and name == stop_at:
            print(f"all    stopping before {name} (--stop-at)")
            break
        if name == "fetch":
            results = fetch_stage.run(settings)
            if any(r.status == "error" for r in results):
                print("all    fetch reported errors; stopping", file=sys.stderr)
                raise typer.Exit(code=1)
            continue
        if not _run_stage(name, settings):
            print(f"all    stopped before '{name}': not implemented yet (SPEC §16 Session {PLANNED[name]})")
            break
    ctx.invoke(sanity, ctx=ctx)


if __name__ == "__main__":
    app()
