"""French IRIS statistics on IGN IRIS contours (SPEC §13.34, §15).

- ``base-ic-activite-residents-2021`` (INSEE RP 2021, geography of 1 Jan 2023; `;`, decimal
  point): ``P21_ACTOCC1564`` employed and ``P21_POP1564`` people aged 15-64 per IRIS ->
  ``emp_rate`` (missing where the 15-64 count is 0).
- ``BASE_TD_FILO_IRIS_2021_DISP`` (INSEE Filosofi 2021; `;`, decimal comma; IRIS of communes
  with 5,000+ inhabitants only): ``DISP_TP6021`` poverty rate at 60% of the median, in percent
  -> ``poverty_rate``. ``ns`` / ``nd`` / ``s`` / ``so`` are missing, never 0.
- IGN Contours...IRIS 2023 (a .7z of one shapefile per territory, each in its own CRS): every
  code in both INSEE files matches ``CODE_IRIS`` (checked 2026-09-23). Reprojected to WGS84 and
  concatenated.

The ``area_weighted_overlay`` joiner weights both rates by ``pop_1564``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

INSEE_NA = ["ns", "nd", "s", "so", ""]


def _read_zip_csv(path, member: str, decimal: str, usecols: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf, zf.open(member) as fh:
        df = pd.read_csv(fh, sep=";", decimal=decimal, dtype={"IRIS": str}, na_values=INSEE_NA, keep_default_na=False, usecols=lambda c: c in usecols, encoding="utf-8")
    missing = [c for c in usecols if c not in df.columns]
    if missing:
        raise KeyError(f"INSEE IRIS file {member}: columns {missing} not found; the published layout may have changed (SPEC §15)")
    return df


def load_frames(activity_zip, activity_member: str, filo_zip, filo_member: str, contours: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    act = _read_zip_csv(activity_zip, activity_member, ".", ["IRIS", "P21_POP1564", "P21_ACTOCC1564"])
    filo = _read_zip_csv(filo_zip, filo_member, ",", ["IRIS", "DISP_TP6021"])
    pop = pd.to_numeric(act["P21_POP1564"], errors="coerce")
    table = pd.DataFrame(
        {
            "CODE_IRIS": act["IRIS"],
            "pop_1564": pop,
            "emp_rate": (pd.to_numeric(act["P21_ACTOCC1564"], errors="coerce") / pop.where(pop > 0)).clip(0, 1),
        }
    ).merge(pd.DataFrame({"CODE_IRIS": filo["IRIS"], "poverty_rate": pd.to_numeric(filo["DISP_TP6021"], errors="coerce")}), on="CODE_IRIS", how="left")
    shapes = contours[["CODE_IRIS", "geometry"]].to_crs(4326) if contours.crs and contours.crs.to_epsg() != 4326 else contours[["CODE_IRIS", "geometry"]]
    out = shapes.merge(table, on="CODE_IRIS", how="left")  # contours without census rows (Mayotte ...) stay missing
    return gpd.GeoDataFrame(out, geometry="geometry", crs=4326)


def read_contours(archive: Path, extract_to: Path) -> gpd.GeoDataFrame:
    """Every territory's CONTOURS-IRIS.shp from the IGN .7z, reprojected to WGS84 and concatenated.
    The archive is extracted once into ``extract_to``."""
    if not any(extract_to.rglob("CONTOURS-IRIS.shp")):
        import py7zr

        extract_to.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(archive, "r") as z:
            z.extractall(extract_to)
    parts = [gpd.read_file(shp, columns=["CODE_IRIS"]).to_crs(4326) for shp in sorted(extract_to.rglob("CONTOURS-IRIS.shp"))]
    if not parts:
        raise FileNotFoundError(f"{archive.name}: no CONTOURS-IRIS.shp inside; the IGN layout may have changed (SPEC §15)")
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)


FILOSOFI_SOURCE = "fr_insee_filosofi_iris_2021"


def load(settings, source, sources) -> gpd.GeoDataFrame:
    geo = sources[source.extra["geometry"]]
    filo = sources[FILOSOFI_SOURCE]
    contours = read_contours(settings.raw(geo.id) / geo.files[0], settings.cache_dir / "unzipped" / geo.id)
    return load_frames(
        settings.raw(source.id) / source.files[0], source.extra["member"],
        settings.raw(filo.id) / filo.files[0], filo.extra["member"],
        contours,
    )
