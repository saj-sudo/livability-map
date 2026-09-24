"""Score helpers shared by the ``hazards`` and ``score`` stages (SPEC §8.2, §8.3, §8.4, §20.4).

Conventions (SPEC §13.25):
- ``percentile_score`` is the plain midrank percentile of a raw value within a *domain* of hexes
  (inhabited hexes that have the value). It never encodes direction: a hazard score of 80 means
  "more hazard than 80% of the domain", a jobs score of 80 means "better job market than 80%".
  Direction lives in ``dimensions.yaml`` (``higher_is``) and the web client applies it.
- Missing raw values stay missing (nullable ``Int16`` with ``<NA>``), never 0 (invariant 3).
- A derived resolution (res 6, 7; SPEC §13.32) passes a ``reference``: the values of the finest
  complete resolution in the same domain, so a neighbourhood hex is ranked among res-5 hexes and
  keeps its colour meaning at every zoom. The same goes for the wellbeing min-max bounds and the
  bivariate tercile cuts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _num(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("float64")


def percentile_score(values: pd.Series, domain: pd.Series, reference: np.ndarray | None = None) -> pd.Series:
    """Midrank percentile (0-100) of every non-null value against ``values[domain]``.

    ``domain`` is a boolean Series aligned to ``values`` (e.g. ``inhabited & ok``). Values outside
    the domain (uninhabited hexes with data) are still scored against the domain's distribution,
    so the "show uninhabited" toggle has colours. ``reference``, when given, replaces
    ``values[domain]`` as the distribution ranked against (SPEC §13.32). Empty distribution ->
    all null.
    """
    v = _num(values)
    has = v.notna().to_numpy()
    if reference is not None:
        ref = np.asarray(reference, dtype="float64")
        dom = np.sort(ref[np.isfinite(ref)])
    else:
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


def minmax_score(values: pd.Series, group: pd.Series, reference: pd.DataFrame | None = None) -> pd.Series:
    """0-100 min-max normalisation within each ``group`` label, computed over the *distinct*
    raw values of the group (SPEC §8.3: "SHDI across all admin1 regions; WHR across countries",
    i.e. each region counts once however many hexes it covers). A group with a single distinct
    value scores 50 (documented on /methodology). Null value or null group -> null.

    ``reference`` (columns ``v``, ``g``): per-group bounds taken from that frame's distinct values
    instead (a derived resolution, SPEC §13.32); values beyond them clip to 0 / 100. Groups absent
    from the reference fall back to their own range.
    """
    v = _num(values)
    out = pd.Series(pd.NA, index=values.index, dtype="Int16")
    bounds: dict = {}
    if reference is not None:
        rf = pd.DataFrame({"v": _num(reference["v"]), "g": reference["g"]}).dropna(subset=["v", "g"])
        for g, sub in rf.groupby("g", sort=False):
            uniq = sub["v"].unique()
            bounds[g] = (float(uniq.min()), float(uniq.max()))
    frame = pd.DataFrame({"v": v, "g": group}).dropna(subset=["v", "g"])
    for g, sub in frame.groupby("g", sort=False):
        if g in bounds:
            lo, hi = bounds[g]
        else:
            uniq = sub["v"].unique()
            lo, hi = float(uniq.min()), float(uniq.max())
        if hi == lo:
            score = np.full(len(sub), 50, dtype="int16")
        else:
            score = np.clip(np.round(100.0 * (sub["v"].to_numpy() - lo) / (hi - lo)), 0, 100).astype("int16")
        out.loc[sub.index] = score
    return out


def bivariate_cuts(exposure: pd.Series, wb: pd.Series, inhabited: pd.Series) -> tuple[np.ndarray, np.ndarray] | None:
    """Tercile cut points of ``exposure`` and ``wb`` over inhabited hexes that have both values
    (SPEC §8.4); None when no hex qualifies. A derived resolution reuses its reference's cuts."""
    e, w = _num(exposure), _num(wb)
    dom = (e.notna() & w.notna()).to_numpy() & inhabited.to_numpy(dtype=bool)
    if dom.sum() == 0:
        return None
    q = [100.0 / 3.0, 200.0 / 3.0]
    return np.nanpercentile(e.to_numpy()[dom], q), np.nanpercentile(w.to_numpy()[dom], q)


def bivariate_class(exposure: pd.Series, wb: pd.Series, inhabited: pd.Series, cuts: tuple[np.ndarray, np.ndarray] | None = None) -> pd.Series:
    """3x3 bivariate class 1-9 (SPEC §8.4): terciles of ``exposure`` and ``wb`` computed over
    inhabited hexes that have both values; ``class = 1 + exposure_tercile + 3 * wb_tercile``
    (tercile 0 = lowest). So 1 = low exposure / low wellbeing, 3 = high exposure / low wellbeing,
    7 = low exposure / high wellbeing, 9 = high / high. 0 when either value is missing.
    Uninhabited hexes are classed with the inhabited cut points; ``cuts`` overrides them.
    """
    e, w = _num(exposure), _num(wb)
    both = (e.notna() & w.notna()).to_numpy()
    out = pd.Series(0, index=exposure.index, dtype="Int8")
    cuts = cuts if cuts is not None else bivariate_cuts(exposure, wb, inhabited)
    if cuts is None:
        return out
    e_cuts, w_cuts = cuts
    cls = 1 + np.searchsorted(e_cuts, e.to_numpy(), side="right") + 3 * np.searchsorted(w_cuts, w.to_numpy(), side="right")
    out.iloc[np.flatnonzero(both)] = cls[both].astype("int8")
    return out
