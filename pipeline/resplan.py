"""Resolution plan (SPEC §9.1, §13.32): which H3 resolutions are built, where, and at which zooms.

``pipeline/resolution_plan.yaml`` (``pipeline/fixtures/resolution_plan.yaml`` for the fixture
world) lists one entry per resolution, ascending:

- ``fill: land`` entries cover every land cell (a *complete* resolution, as res 4 and 5 always
  were);
- ``fill: children`` entries are the H3 children of every cell of ``parent`` that matches any
  ``where`` rule: ``countries`` (ISO2 codes; the parent centroid's country per geoBoundaries) or
  ``urban`` (``centre`` | ``cluster``; the parent polygon touches a GHS-SMOD polygon of that kind
  written by the ``urban`` stage).

Every entry also says which zoom range its tile layer serves and which PMTiles ``archive`` it
belongs to, so the tiler and the web app take their layer table from here (through the
manifest) rather than from a fixed table. Any res 4-10 is allowed: Session 11 adds res 9/10
inside urban centres by editing the yaml only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FILLS = ("land", "children")
URBAN_KINDS = ("centre", "cluster")
RULE_KEYS = ("countries", "urban")
RES_MIN, RES_MAX = 4, 10
_ARCHIVE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ResEntry:
    res: int
    fill: str  # land | children
    zooms: tuple[int, int]  # (minzoom, maxzoom) of this resolution's tile layer
    archive: str = "hexes"  # PMTiles archive name (hexes.pmtiles, hexes_fine.pmtiles, ...)
    parent: int | None = None  # for children fills: the resolution whose cells are refined
    where: dict = field(default_factory=dict)  # countries: [ISO2...] and/or urban: centre|cluster
    slim_below_zoom: int | None = None  # ship the slim attribute set below this zoom (hex4 at z2)

    @property
    def complete(self) -> bool:
        """True when every land cell exists at this resolution (a `land` fill)."""
        return self.fill == "land"

    def to_manifest(self) -> dict:
        return {
            "res": self.res,
            "fill": self.fill,
            "parent": self.parent,
            "where": dict(self.where),
            "zooms": list(self.zooms),
            "archive": self.archive,
            "slim_below_zoom": self.slim_below_zoom,
            "complete": self.complete,
        }


@dataclass(frozen=True)
class ResolutionPlan:
    entries: tuple[ResEntry, ...]

    def resolutions(self) -> list[int]:
        return [e.res for e in self.entries]

    def entry(self, res: int) -> ResEntry:
        for e in self.entries:
            if e.res == res:
                return e
        raise KeyError(f"res {res} is not in the resolution plan (the plan has {self.resolutions()})")

    def reference_res(self, res: int) -> int | None:
        """The finest complete resolution coarser than ``res``: the distribution a derived
        resolution's scores are ranked against (SPEC §13.32). None for a complete resolution."""
        if self.entry(res).complete:
            return None
        below = [e.res for e in self.entries if e.complete and e.res < res]
        return max(below) if below else None

    def next_finer(self, res: int) -> ResEntry | None:
        finer = [e for e in self.entries if e.res > res]
        return finer[0] if finer else None

    def archives(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for e in self.entries:
            out.setdefault(e.archive, []).append(e.res)
        return out

    def to_manifest(self) -> list[dict]:
        return [e.to_manifest() for e in self.entries]


def _entry(raw: dict, previous: list[ResEntry]) -> ResEntry:
    """One validated entry; every failure is a plain sentence naming the entry."""
    res = int(raw.get("res", -1))
    if not RES_MIN <= res <= RES_MAX:
        raise ValueError(f"resolution plan: res must be between {RES_MIN} and {RES_MAX}, got {res}")
    if previous and res <= previous[-1].res:
        raise ValueError(f"resolution plan: entries must be ascending (res {res} comes after res {previous[-1].res})")
    fill = raw.get("fill")
    if fill not in FILLS:
        raise ValueError(f"resolution plan res {res}: fill must be one of {FILLS}, got {fill!r}")
    if not previous and fill != "land":
        raise ValueError("resolution plan: the first entry must be a complete `land` fill")
    zooms = tuple(int(z) for z in (raw.get("zooms") or ()))
    if len(zooms) != 2 or zooms[0] > zooms[1]:
        raise ValueError(f"resolution plan res {res}: zooms must be [minzoom, maxzoom], got {list(zooms)}")
    if previous and zooms[0] <= previous[-1].zooms[1]:
        raise ValueError(f"resolution plan res {res}: zooms {list(zooms)} overlap res {previous[-1].res} zooms {list(previous[-1].zooms)}")
    archive = str(raw.get("archive", "hexes"))
    if not _ARCHIVE.match(archive):
        raise ValueError(f"resolution plan res {res}: archive name {archive!r} must be lowercase letters, digits and underscores")
    parent = raw.get("parent")
    where = dict(raw.get("where") or {})
    if fill == "children":
        if parent is None or int(parent) not in [p.res for p in previous]:
            raise ValueError(f"resolution plan res {res}: parent must name an earlier entry, got {parent!r}")
        parent = int(parent)
        if not where:
            raise ValueError(f"resolution plan res {res}: a children entry needs a `where` rule (countries and/or urban)")
    else:
        parent = None
    unknown = set(where) - set(RULE_KEYS)
    if unknown:
        raise ValueError(f"resolution plan res {res}: unknown where keys {sorted(unknown)} (allowed: {RULE_KEYS})")
    if "urban" in where and where["urban"] not in URBAN_KINDS:
        raise ValueError(f"resolution plan res {res}: urban must be one of {URBAN_KINDS}, got {where['urban']!r}")
    if "countries" in where:
        where["countries"] = [str(c).upper() for c in where["countries"] or []]
    slim = raw.get("slim_below_zoom")
    return ResEntry(
        res=res,
        fill=fill,
        zooms=(zooms[0], zooms[1]),
        archive=archive,
        parent=parent,
        where=where,
        slim_below_zoom=None if slim is None else int(slim),
    )


def load_plan(path: Path) -> ResolutionPlan:
    if not path.exists():
        raise FileNotFoundError(f"resolution plan {path} is missing")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: list[ResEntry] = []
    for item in raw.get("resolutions") or []:
        entries.append(_entry(item, entries))
    if not entries:
        raise ValueError(f"resolution plan {path} has no `resolutions` entries")
    return ResolutionPlan(tuple(entries))
