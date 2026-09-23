"""German Zensus 2022 100 m grid: average net cold rent per m² (SPEC §13.34, §15).

The download (``Durchschnittliche_Nettokaltmiete_und_Anzahl_der_Wohnungen.zip``, Destatis,
dl-de/by-2-0) holds one semicolon-separated CSV per grid size with a decimal comma. The 100 m
file has one row per cell that has rented dwellings: ``x_mp_100m`` / ``y_mp_100m`` are the cell
centre in ETRS89-LAEA (EPSG:3035), ``durchschnMieteQM`` the average net cold rent in EUR per m²
and ``AnzahlWohnungen`` the dwelling count, used as the weight when ``point_mean`` averages the
cells inside a hex. Cells without rented dwellings, or suppressed by statistical secrecy, are
simply absent from the file, so hexes with no cell stay missing (never 0). Values are perturbed
by the Cell-Key method; ``KLAMMERN`` rows (statistically uncertain) are kept, as Destatis
publishes them.
"""

from __future__ import annotations

import zipfile

import pandas as pd

from .eurostat_grid import to_wgs84

MEMBER = "Durchschnittliche_Nettokaltmiete_und_Anzahl_der_Wohnungen/Zensus2022_Durchschn_Nettokaltmiete_Anzahl_der_Wohnungen_100m-Gitter.csv"
NEEDED = ["x_mp_100m", "y_mp_100m", "durchschnMieteQM", "AnzahlWohnungen"]


def load_csv(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer, sep=";", decimal=",", usecols=lambda c: c in NEEDED, encoding="utf-8")
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise KeyError(f"Zensus 2022 rent grid: columns {missing} not found; the published layout may have changed (SPEC §15)")
    lat, lng = to_wgs84(df["x_mp_100m"].to_numpy(dtype="float64"), df["y_mp_100m"].to_numpy(dtype="float64"))
    return pd.DataFrame(
        {
            "lat": lat,
            "lng": lng,
            "rent_eur_m2": pd.to_numeric(df["durchschnMieteQM"], errors="coerce"),
            "dwellings": pd.to_numeric(df["AnzahlWohnungen"], errors="coerce"),
        }
    )


def load(settings, source, sources) -> pd.DataFrame:
    raw = settings.raw(source.id) / source.files[0]
    with zipfile.ZipFile(raw) as zf, zf.open(source.extra.get("member", MEMBER)) as fh:
        return load_csv(fh)
