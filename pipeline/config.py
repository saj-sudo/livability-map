"""Pipeline settings (SPEC §6, §11, §13).

One ``Settings`` object is built by the CLI and threaded through every stage. Defaults here are
the §13 decisions; nothing else in the pipeline hardcodes a resolution, threshold or path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# H3 resolutions come from pipeline/resolution_plan.yaml (SPEC §9.1); see Settings.plan
POP_MIN: int = 100  # people; §13.9
DEPTH_MIN: float = 0.15  # metres; §13.9
SCENARIO: str = "rcp45_ssp245"  # §13.3
HORIZON: str = "2050"  # §13.3
NON_COMMERCIAL: bool = True  # §13.13

# invariant 2 (SPEC §6.1). hex = computed per hex from a raster or point set; basin = a
# hydrological sub-basin polygon (Aqueduct) sampled at the hex centroid
# grid = a statistical grid (Eurostat 1 km census cells) aggregated per hex (Session 8, SPEC §13.34)
RES_TAGS = ("hex", "grid", "basin", "admin1", "county", "tract", "national", "none")

BBox = tuple[float, float, float, float]  # minlng, minlat, maxlng, maxlat


def find_root(start: Path | None = None) -> Path:
    """Repo root: the nearest ancestor containing ``pipeline/sources.yaml``."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pipeline" / "sources.yaml").exists():
            return candidate
    raise FileNotFoundError("could not locate repo root (pipeline/sources.yaml)")


@dataclass
class Settings:
    root: Path = field(default_factory=find_root)
    fixtures: bool = False
    res: list[int] = field(default_factory=list)  # empty -> every resolution in the plan
    bbox: BBox | None = None
    pop_min: int = POP_MIN
    depth_min: float = DEPTH_MIN
    scenario: str = SCENARIO
    horizon: str = HORIZON
    force: bool = False  # ignore stage cache
    # ISO3 -> ISO2 overrides for codes pycountry does not know (fixtures use user-assigned codes)
    iso_overrides: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.res:
            self.res = self.plan.resolutions()

    # ---- resolution plan (SPEC §9.1) ---------------------------------------------------
    @property
    def plan_path(self) -> Path:
        if self.fixtures:
            return self.root / "pipeline" / "fixtures" / "resolution_plan.yaml"
        return self.root / "pipeline" / "resolution_plan.yaml"

    @property
    def plan(self):
        """The resolution plan, loaded once per Settings (a plain attribute, not a dataclass
        field, so `Settings(...)` keeps its signature)."""
        from . import resplan  # local import: config stays import-light

        if getattr(self, "_plan", None) is None:
            self._plan = resplan.load_plan(self.plan_path)
        return self._plan

    # ---- paths -------------------------------------------------------------------------
    @property
    def data_dir(self) -> Path:
        if self.fixtures:
            return self.root / "pipeline" / "fixtures" / "_run"
        return self.root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    def _bbox_tag(self) -> str:
        """Directory name for a --bbox run so subregion runs never clobber the global outputs."""
        assert self.bbox is not None
        return "bbox_" + "_".join(f"{v:g}" for v in self.bbox).replace("-", "m").replace(".", "p")

    @property
    def interim_dir(self) -> Path:
        base = self.data_dir / "interim"
        return base / self._bbox_tag() if self.bbox else base

    @property
    def out_dir(self) -> Path:
        base = self.data_dir / "out"
        return base / self._bbox_tag() if self.bbox else base

    @property
    def cache_dir(self) -> Path:
        """Shared across global and bbox runs: extracted archives and prepared source layers."""
        return self.data_dir / "interim"

    @property
    def sources_path(self) -> Path:
        if self.fixtures:
            return self.root / "pipeline" / "fixtures" / "sources.yaml"
        return self.root / "pipeline" / "sources.yaml"

    @property
    def dimensions_path(self) -> Path:
        return self.root / "pipeline" / "dimensions.yaml"

    @property
    def fixture_data_dir(self) -> Path:
        return self.root / "pipeline" / "fixtures" / "data"

    def raw(self, source_id: str) -> Path:
        return self.raw_dir / source_id

    def hexes_path(self, res: int) -> Path:
        return self.interim_dir / f"hexes_r{res}.parquet"

    @property
    def urban_path(self) -> Path:
        """Urban centre / cluster polygons from the `urban` stage (SPEC §13.31)."""
        return self.interim_dir / "urban.parquet"

    def stage_path(self, stage: str, res: int) -> Path:
        return self.interim_dir / f"{stage}_r{res}.parquet"

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.interim_dir, self.out_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- helpers -----------------------------------------------------------------------
    def bbox_or_none(self) -> BBox | None:
        return self.bbox

    def describe(self) -> str:
        where = "fixtures" if self.fixtures else "data"
        bbox = f" bbox={self.bbox}" if self.bbox else ""
        return f"[{where}] res={self.res}{bbox} scenario={self.scenario} horizon={self.horizon}"


def parse_bbox(text: str | None) -> BBox | None:
    if not text:
        return None
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minlng,minlat,maxlng,maxlat")
    minlng, minlat, maxlng, maxlat = parts
    if not (minlng < maxlng and minlat < maxlat):
        raise ValueError("bbox must have min < max on both axes")
    return (minlng, minlat, maxlng, maxlat)


def h3_backend() -> str:
    """'h3ronpy' (default when importable) or 'fallback' (pure rasterio + h3). SPEC §14.11."""
    forced = os.environ.get("PIPELINE_H3_BACKEND")
    if forced in ("h3ronpy", "fallback"):
        return forced
    try:
        import h3ronpy.raster  # noqa: F401

        return "h3ronpy"
    except Exception:  # pragma: no cover - depends on environment
        return "fallback"
