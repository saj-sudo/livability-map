"""ILOSTAT youth unemployment (UNE_DEAP_SEX_AGE_RT_A) -> national table (SPEC §20.6 jobs,
global fallback).

The API CSV has ``ref_area (ISO3), source, indicator, sex, classif1, time, obs_value, ...``.
We keep both sexes (``SEX_T``), ages 15-24 (``AGE_YTHADULT_Y15-24``), the latest year up to the
current one, and store ``youth_employment_rate = 100 - unemployment rate`` so higher is better.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from ..config import Settings
from ..registry import Source
from .util import iso3_to_iso2

SEX = "SEX_T"
AGE = "AGE_YTHADULT_Y15-24"


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> pd.DataFrame:
    path = settings.raw(source.id) / source.files[0]
    df = pd.read_csv(path, usecols=lambda c: c in {"ref_area", "sex", "classif1", "time", "obs_value"}, low_memory=False)
    return prepare(df)


def prepare(df: pd.DataFrame, this_year: int | None = None) -> pd.DataFrame:
    """Pure part of the loader (unit-tested on a synthetic frame)."""
    this_year = this_year or dt.date.today().year
    df = df[(df["sex"] == SEX) & (df["classif1"] == AGE)].copy()
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df["obs_value"] = pd.to_numeric(df["obs_value"], errors="coerce")
    df = df.dropna(subset=["time", "obs_value"])
    df = df[df["time"] <= this_year]
    df = df.sort_values("time").drop_duplicates("ref_area", keep="last")
    out = pd.DataFrame(
        {
            "iso_a3": df["ref_area"].astype(str),
            "iso_a2": iso3_to_iso2(df["ref_area"].astype(str)),
            "youth_unemployment_rate": df["obs_value"].astype(float),
            "youth_employment_rate": (100.0 - df["obs_value"].astype(float)).clip(0, 100),
            "year": df["time"].astype(int),
        }
    ).dropna(subset=["iso_a2"])
    print(f"prep   ilostat_youth_unemp: {len(out)} countries, years {out['year'].min() if len(out) else '-'}..{out['year'].max() if len(out) else '-'}")
    return out.reset_index(drop=True)
