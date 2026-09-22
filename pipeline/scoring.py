"""Score helpers shared by the ``hazards`` and ``score`` stages (SPEC §8.2, §8.3, §8.4, §20.4).

Conventions (SPEC §13.25):
- ``percentile_score`` is the plain midrank percentile of a raw value within a *domain* of hexes
  (inhabited hexes that have the value). It never encodes direction: a hazard score of 80 means
  "more hazard than 80% of the domain", a jobs score of 80 means "better job market than 80%".
  Direction lives in ``dimensions.yaml`` (``higher_is``) and the web client applies it.
- Missing raw values stay missing (nullable ``Int16`` with ``<NA>``), never 0 (invariant 3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def percentile_score(values: pd.Series, domain: pd.Series) -> pd.Series:
    """Midrank percentile (0-100) of every non-null value against ``values[domain]``.

    ``domain`` is a boolean Series aligned to ``values`` (e.g. ``inhabited & ok``). Values outside
    the domain (uninhabited hexes with data) are still scored against the domain's distribution,
    so the "show uninhabited" toggle has colours. Empty domain -> all null.
    """
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    has = v.notna().to_numpy()
    dom_mask = domain.to_numpy(dtype=bool) & has
    dom = np.sort(v.to_numpy()[dom_mask])
    out = pd.Series(pd.NA, index=values.index, dtype="Int16")
    if len(dom) == 0:
        return out
    vv = v.to_numpy()[has]
    # midrank: (number strictly below + number at-or-below) / 2, as a share of the domain
    left = np.searchsorted(dom, vv, side="left")
    right = np.searchsorted(dom, vv, side="right")
    score = np.clip(np.round(100.0 * (left + right) / (2.0 * len(dom))), 0, 100).astype("int16")
    out.iloc[np.flatnonzero(has)] = score
    return out


def minmax_score(values: pd.Series, group: pd.Series) -> pd.Series:
    """0-100 min-max normalisation within each ``group`` label, computed over the *distinct*
    raw values of the group (SPEC §8.3: "SHDI across all admin1 regions; WHR across countries",
    i.e. each region counts once however many hexes it covers). A group with a single distinct
    value scores 50 (documented on /methodology). Null value or null group -> null.
    """
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    out = pd.Series(pd.NA, index=values.index, dtype="Int16")
    frame = pd.DataFrame({"v": v, "g": group}).dropna(subset=["v", "g"])
    for _, sub in frame.groupby("g", sort=False):
        uniq = sub["v"].unique()
        lo, hi = float(uniq.min()), float(uniq.max())
        if hi == lo:
            score = np.full(len(sub), 50, dtype="int16")
        else:
            score = np.clip(np.round(100.0 * (sub["v"].to_numpy() - lo) / (hi - lo)), 0, 100).astype("int16")
        out.loc[sub.index] = score
    return out


def bivariate_class(exposure: pd.Series, wb: pd.Series, inhabited: pd.Series) -> pd.Series:
    """3x3 bivariate class 1-9 (SPEC §8.4): terciles of ``exposure`` and ``wb`` computed over
    inhabited hexes that have both values; ``class = 1 + exposure_tercile + 3 * wb_tercile``
    (tercile 0 = lowest). So 1 = low exposure / low wellbeing, 3 = high exposure / low wellbeing,
    7 = low exposure / high wellbeing, 9 = high / high. 0 when either value is missing.
    Uninhabited hexes are classed with the inhabited cut points.
    """
    e = pd.to_numeric(exposure, errors="coerce").astype("float64")
    w = pd.to_numeric(wb, errors="coerce").astype("float64")
    both = (e.notna() & w.notna()).to_numpy()
    dom = both & inhabited.to_numpy(dtype=bool)
    out = pd.Series(0, index=exposure.index, dtype="Int8")
    if dom.sum() == 0:
        return out

    def terciles(series: pd.Series) -> np.ndarray:
        cuts = np.nanpercentile(series.to_numpy()[dom], [100.0 / 3.0, 200.0 / 3.0])
        return np.searchsorted(cuts, series.to_numpy(), side="right")  # 0, 1 or 2

    cls = 1 + terciles(e) + 3 * terciles(w)
    out.iloc[np.flatnonzero(both)] = cls[both].astype("int8")
    return out
