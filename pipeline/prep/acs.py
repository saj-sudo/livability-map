"""US Census ACS 2020-2024 5-year table-based Summary File -> tract polygons with the derived
fields every US life dimension reads (SPEC §20.6, §13.20).

The ``.dat`` files are pipe-delimited with a header ``GEO_ID|B23001_E001|B23001_M001|...``
(E = estimate, M = margin) and contain every summary level; tract rows start with
``1400000US``. Column meanings are asserted against the published table shells so a
re-numbered table fails loudly instead of silently shifting a column. The cartographic tract
polygons carry ``GEOIDFQ`` which equals ``GEO_ID`` byte for byte.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source

TRACT_PREFIX = "1400000US"
COUNTY_PREFIX = "0500000US"
NA_VALUES = ["", ".", "-", "(X)", "**", "***", "N", "null", "-666666666", "-999999999", "-888888888", "-222222222", "-333333333", "-555555555"]

# B23001: (total, employed, unemployed) per sex x age band for ages 16-29
B23001_BANDS = {
    "m16_19": ("003", "007", "008"),
    "m20_21": ("010", "014", "015"),
    "m22_24": ("017", "021", "022"),
    "m25_29": ("024", "028", "029"),
    "f16_19": ("089", "093", "094"),
    "f20_21": ("096", "100", "101"),
    "f22_24": ("103", "107", "108"),
    "f25_29": ("110", "114", "115"),
}
INCOME_BRACKETS = [f"{i:03d}" for i in range(2, 18)]  # B19001_002 .. _017

# label checks against the table shells (unique id -> label prefix)
EXPECTED_LABELS = {
    "B23001_002": "Male:",
    "B23001_003": "16 to 19 years:",
    "B23001_007": "Employed",
    "B23001_008": "Unemployed",
    "B23001_024": "25 to 29 years:",
    "B23001_088": "Female:",
    "B23001_089": "16 to 19 years:",
    "B23001_110": "25 to 29 years:",
    "B23001_114": "Employed",
    "B23001_115": "Unemployed",
    "B03002_001": "Total:",
    "B03002_003": "White alone",
    "B03002_004": "Black or African American alone",
    "B03002_006": "Asian alone",
    "B03002_007": "Native Hawaiian and Other Pacific Islander alone",
    "B03002_012": "Hispanic or Latino:",
    "B09019_011": "Same-sex spouse",
    "B09019_013": "Same-sex unmarried partner",
    "B11001_001": "Total:",
    "B19001_002": "Less than $10,000",
    "B19001_017": "$200,000 or more",
    "B19083_001": "Gini Index",
    "B25003_003": "Renter occupied",
    "B25071_001": "Median gross rent as a percentage of household income",
}


def needed_columns() -> dict[str, list[str]]:
    """table -> unique ids (without the E) the pipeline reads."""
    cols: dict[str, list[str]] = {
        "B23001": sorted({f"B23001_{c}" for band in B23001_BANDS.values() for c in band}),
        "B03002": [f"B03002_{c}" for c in ("001", "003", "004", "006", "007", "012")],
        "B19001": [f"B19001_{c}" for c in ["001", *INCOME_BRACKETS]],
        "B19083": ["B19083_001"],
        "B09019": ["B09019_011", "B09019_013"],
        "B11001": ["B11001_001"],
        "B25003": ["B25003_003"],
        "B25071": ["B25071_001"],
    }
    return cols


def read_shells(path) -> dict[str, str]:
    """unique id -> label from ACS20245YR_Table_Shells.txt (pipe-delimited)."""
    df = pd.read_csv(path, sep="|", dtype=str, usecols=["Unique ID", "Label"], encoding="utf-8", encoding_errors="replace")
    return dict(zip(df["Unique ID"].str.strip(), df["Label"].str.strip(), strict=True))


def assert_labels(shells: dict[str, str]) -> None:
    bad = [f"{uid}: expected '{exp}', shells say '{shells.get(uid)}'" for uid, exp in EXPECTED_LABELS.items() if not str(shells.get(uid, "")).startswith(exp)]
    if bad:
        raise RuntimeError("ACS table layout changed; the pipeline's column map needs review:\n  " + "\n  ".join(bad))


def _file_col(uid: str) -> str:
    table, seq = uid.split("_")
    return f"{table}_E{seq}"


def read_table(path, uids: list[str], prefix: str = TRACT_PREFIX) -> pd.DataFrame:
    """Rows of one summary level, indexed by GEO_ID, numeric columns named by unique id."""
    file_cols = {_file_col(u): u for u in uids}
    df = pd.read_csv(path, sep="|", dtype=str, usecols=["GEO_ID", *file_cols], na_values=NA_VALUES, keep_default_na=True, low_memory=False)
    df = df[df["GEO_ID"].str.startswith(prefix)].set_index("GEO_ID")
    df = df.rename(columns=file_cols)
    for c in uids:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def derive(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The registry fields from the raw table columns (pure; unit-tested)."""
    b23 = tables["B23001"]
    total = sum(b23[f"B23001_{t}"] for t, _, _ in B23001_BANDS.values())
    emp = sum(b23[f"B23001_{e}"] for _, e, _ in B23001_BANDS.values())
    unemp = sum(b23[f"B23001_{u}"] for _, _, u in B23001_BANDS.values())
    out = pd.DataFrame(index=b23.index)
    out["pop_16_29"] = total
    with np.errstate(divide="ignore", invalid="ignore"):
        out["emp_rate_16_29"] = (emp / (emp + unemp)).where((emp + unemp) > 0)

    b03 = tables["B03002"]
    pop = b03["B03002_001"]
    out = out.join(pd.DataFrame({"pop_total": pop}), how="outer")
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = lambda col: (100.0 * b03[col] / pop).where(pop > 0)  # noqa: E731
        out["pct_white"] = pct("B03002_003")
        out["pct_black"] = pct("B03002_004")
        out["pct_hisp"] = pct("B03002_012")
        out["pct_asian"] = pct("B03002_006") + pct("B03002_007")
    out["pct_other"] = (100.0 - out[["pct_white", "pct_black", "pct_hisp", "pct_asian"]].sum(axis=1, min_count=4)).clip(lower=0)

    hh = tables["B11001"]["B11001_001"]
    out = out.join(pd.DataFrame({"households": hh}), how="outer")
    ss = tables["B09019"]["B09019_011"] + tables["B09019"]["B09019_013"]
    with np.errstate(divide="ignore", invalid="ignore"):
        out["ss_couples_per_1k"] = (1000.0 * ss / hh).where(hh > 0)

    b19 = tables["B19001"]
    brackets = b19[[f"B19001_{c}" for c in INCOME_BRACKETS]]
    tot = b19["B19001_001"]
    with np.errstate(divide="ignore", invalid="ignore"):
        p = brackets.div(tot, axis=0)
        ent = -(p * np.log(p.where(p > 0))).sum(axis=1, min_count=1) / np.log(len(INCOME_BRACKETS))
    out["income_entropy"] = ent.where(tot > 0)
    out["gini"] = tables["B19083"]["B19083_001"]
    out["rent_share_income"] = tables["B25071"]["B25071_001"]
    out["renter_households"] = tables["B25003"]["B25003_003"]
    return out


def county_population(settings: Settings, sources: dict[str, Source]) -> pd.DataFrame:
    """County GEOID (5 chars) -> total population from B03002 (used by the HRSA loader)."""
    src = sources["acs_summary"]
    path = settings.raw(src.id) / "acsdt5y2024-b03002.dat"
    df = read_table(path, ["B03002_001"], prefix=COUNTY_PREFIX)
    return pd.DataFrame({"GEOID": [g[len(COUNTY_PREFIX) :] for g in df.index], "county_pop": df["B03002_001"].to_numpy()})


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    shells_src = sources["acs_table_shells"]
    assert_labels(read_shells(settings.raw(shells_src.id) / shells_src.files[0]))
    tables = {}
    for table, uids in needed_columns().items():
        fname = f"acsdt5y2024-{table.lower()}.dat"
        if fname not in source.files:
            raise FileNotFoundError(f"acs_summary: {fname} is not listed in sources.yaml files")
        tables[table] = read_table(settings.raw(source.id) / fname, uids)
        print(f"prep   acs {table}: {len(tables[table])} tract rows")
    derived = derive(tables)
    derived.index.name = "GEOIDFQ"
    derived = derived.reset_index()
    tracts = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOIDFQ", "GEOID"]).to_crs(4326)
    merged = tracts.merge(derived, on="GEOIDFQ", how="inner")
    print(f"prep   acs_summary: {len(merged)} tracts with geometry ({len(derived) - len(merged)} ACS rows without a cartographic polygon, {len(tracts) - len(merged)} polygons without data)")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
