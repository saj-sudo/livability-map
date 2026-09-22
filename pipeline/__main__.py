"""CLI: ``python -m pipeline [--fixtures] [--res 4 --res 5] [--bbox minlng,minlat,maxlng,maxlat] <stage>``.

Global options come before the stage name (typer callback convention).

Stages run in SPEC §5 order. ``all`` runs every implemented stage and stops, with a clear
message, at the first stage that is still planned for a later session (SPEC §16).
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from .config import Settings, find_root, parse_bbox
from .stages import PLANNED, STAGE_ORDER, NotImplementedStage

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)


@app.callback()
def main(
    ctx: typer.Context,
    fixtures: bool = typer.Option(False, "--fixtures", help="Run against the synthetic fixture world (SPEC §11.1)."),
    res: list[int] = typer.Option(None, "--res", help="H3 resolution(s); default from config (4, 5)."),
    bbox: str = typer.Option(None, "--bbox", help="minlng,minlat,maxlng,maxlat to run a subregion."),
    force: bool = typer.Option(False, "--force", help="Ignore stage caches and recompute."),
    root: Path = typer.Option(None, "--root", help="Repo root (auto-detected)."),
) -> None:
    settings = Settings(root=root.resolve() if root else find_root(), fixtures=fixtures, force=force)
    if res:
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
        mod.run(settings, **kwargs)
    except NotImplementedStage as exc:
        print(f"{name:6s} {exc}")
        return False
    except RuntimeError as exc:
        if name in PLANNED and "planned for Session" in str(exc):
            print(f"{name:6s} {exc}")
            return False
        raise
    return True


@app.command()
def fetch(ctx: typer.Context, only: list[str] = typer.Option(None, "--only", help="Source id(s) to fetch.")) -> None:
    """Download and checksum sources (SPEC §5 fetch)."""
    from .stages import fetch as stage

    results = stage.run(_settings(ctx), only=only or None)
    if any(r.status in ("refused", "error") for r in results):
        raise typer.Exit(code=1)


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
def dims(ctx: typer.Context) -> None:
    """Wellbeing and life dimensions via the registry joiners (SPEC §20.2-20.3)."""
    _run_stage("dims", _settings(ctx))


def _planned_command(name: str):
    def cmd(ctx: typer.Context) -> None:
        if not _run_stage(name, _settings(ctx)):
            raise typer.Exit(code=3)

    cmd.__name__ = name
    cmd.__doc__ = f"{name} stage (planned for Session {PLANNED[name]}, SPEC §16)."
    return cmd


for _name in ("score", "export", "tiles", "publish"):
    app.command(name=_name)(_planned_command(_name))


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
