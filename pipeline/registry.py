"""Load and validate ``sources.yaml`` and ``dimensions.yaml`` (SPEC §6.2, §20.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import RES_TAGS

VERIFY = "VERIFY"
ACCESS_MODES = ("direct", "manual", "dataverse", "fixture")
GROUPS = ("hazard", "wellbeing", "life", "reference")
KINDS = ("score", "signed", "composition")
JOINERS = ("polygon_centroid", "iso_lookup", "area_weighted_overlay", "point_density")


@dataclass
class Source:
    id: str
    name: str
    group: str
    access: str
    url: str | None
    format: str
    license: str
    files: list[str]
    attribution: str = ""
    license_note: str = ""
    vintage: str = VERIFY
    processing: str = ""
    recipe: str = ""
    crs: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def unverified(self) -> bool:
        """True when the license or (for direct sources) the URL is still VERIFY (invariant 4)."""
        if self.license.strip().upper().startswith(VERIFY):
            return True
        return self.access == "direct" and (not self.url or self.url.strip().upper() == VERIFY)

    def to_manifest(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "group": self.group,
            "access": self.access,
            "url": self.url,
            "format": self.format,
            "license": self.license,
            "license_note": self.license_note,
            "vintage": self.vintage,
            "attribution": self.attribution,
            "processing": self.processing,
            "files": self.files,
        }
        d.update(self.extra)
        return d


SCALES = ("percentile", "minmax")
COMPOSITION_KEYS = ("w", "b", "h", "a", "o")  # §6.1: {id}_w/b/h/a/o shares


@dataclass
class JoinSpec:
    source: str
    joiner: str
    res: str  # admin1 | county | tract | national | none
    field: str
    domain: str = "global"  # global | oecd | us ; scoring domain (§20.4)
    id_field: str | None = None
    weight_field: str | None = None
    per_capita: bool = False
    # composition dims only: component key (w/b/h/a/o) -> source column carrying that share
    fields: dict[str, str] | None = None
    # short source label carried on the hex (e.g. wb_source = "shdi" | "whr"); defaults to the source id
    label: str | None = None

    def to_manifest(self) -> dict[str, Any]:
        d = {"source": self.source, "joiner": self.joiner, "res": self.res, "field": self.field, "domain": self.domain, "label": self.label or self.source}
        if self.weight_field:
            d["weight_field"] = self.weight_field
        if self.fields:
            d["fields"] = dict(self.fields)
        return d


@dataclass
class Dimension:
    id: str
    name: str
    group: str
    kind: str
    higher_is: str = "better"
    coverage: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    joiners: list[JoinSpec] = field(default_factory=list)
    note: str = ""
    scale: str = "percentile"  # percentile (§8.2, §20.4) | minmax within source (§8.3, wellbeing)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "group": self.group,
            "kind": self.kind,
            "higher_is": self.higher_is,
            "coverage": self.coverage,
            "sources": self.sources,
            "scale": self.scale,
            "joiners": [j.to_manifest() for j in self.joiners],
            "note": self.note,
        }


def _load_yaml(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list at top level")
    return data


KNOWN_SOURCE_KEYS = {
    "id", "name", "group", "access", "url", "format", "license", "files", "attribution",
    "license_note", "vintage", "processing", "recipe", "crs",
}


def load_sources(path: Path) -> dict[str, Source]:
    out: dict[str, Source] = {}
    for raw in _load_yaml(path):
        sid = raw.get("id")
        if not sid:
            raise ValueError(f"{path}: source without id: {raw}")
        if sid in out:
            raise ValueError(f"{path}: duplicate source id {sid}")
        access = raw.get("access", "direct")
        if access not in ACCESS_MODES:
            raise ValueError(f"{sid}: access must be one of {ACCESS_MODES}")
        group = raw.get("group", "reference")
        if group not in GROUPS:
            raise ValueError(f"{sid}: group must be one of {GROUPS}")
        files = raw.get("files") or []
        if isinstance(files, str):
            files = [files]
        extra = {k: v for k, v in raw.items() if k not in KNOWN_SOURCE_KEYS}
        out[sid] = Source(
            id=sid,
            name=raw.get("name", sid),
            group=group,
            access=access,
            url=raw.get("url"),
            format=raw.get("format", "unknown"),
            license=str(raw.get("license", VERIFY)),
            files=list(files),
            attribution=raw.get("attribution", ""),
            license_note=raw.get("license_note", "") or "",
            vintage=str(raw.get("vintage", VERIFY)),
            processing=raw.get("processing", "") or "",
            recipe=raw.get("recipe", "") or "",
            crs=raw.get("crs"),
            extra=extra,
        )
    return out


def load_dimensions(path: Path, sources: dict[str, Source] | None = None) -> dict[str, Dimension]:
    out: dict[str, Dimension] = {}
    for raw in _load_yaml(path):
        did = raw.get("id")
        if not did:
            raise ValueError(f"{path}: dimension without id: {raw}")
        if did in out:
            raise ValueError(f"{path}: duplicate dimension id {did}")
        kind = raw.get("kind", "score")
        if kind not in KINDS:
            raise ValueError(f"{did}: kind must be one of {KINDS}")
        group = raw.get("group", "life")
        if group not in GROUPS:
            raise ValueError(f"{did}: group must be one of {GROUPS}")
        scale = raw.get("scale", "percentile")
        if scale not in SCALES:
            raise ValueError(f"{did}: scale must be one of {SCALES}")
        joiners: list[JoinSpec] = []
        for j in raw.get("joiners") or []:
            if j.get("joiner") not in JOINERS:
                raise ValueError(f"{did}: joiner must be one of {JOINERS}: {j}")
            if j.get("res") not in RES_TAGS:
                raise ValueError(f"{did}: res must be one of {RES_TAGS}: {j}")
            if sources is not None and j.get("source") not in sources:
                raise ValueError(f"{did}: joiner references unknown source {j.get('source')}")
            fields = j.get("fields")
            if kind == "composition":
                # every composition joiner must map all five §6.1 component keys to source columns
                if not isinstance(fields, dict) or set(fields) != set(COMPOSITION_KEYS):
                    raise ValueError(f"{did}: composition joiners need `fields` with keys {COMPOSITION_KEYS}: {j}")
            elif fields:
                raise ValueError(f"{did}: `fields` is only valid for composition dimensions: {j}")
            joiners.append(
                JoinSpec(
                    source=j["source"],
                    joiner=j["joiner"],
                    res=j["res"],
                    field=j.get("field", fields["w"] if fields else "value"),
                    domain=j.get("domain", "global"),
                    id_field=j.get("id_field"),
                    weight_field=j.get("weight_field"),
                    per_capita=bool(j.get("per_capita", False)),
                    fields=dict(fields) if fields else None,
                    label=j.get("label"),
                )
            )
        out[did] = Dimension(
            id=did,
            name=raw.get("name", did),
            group=group,
            kind=kind,
            higher_is=raw.get("higher_is", "better"),
            coverage=list(raw.get("coverage") or []),
            sources=list(raw.get("sources") or []),
            joiners=joiners,
            note=raw.get("note", "") or "",
            scale=scale,
        )
    return out


REFERENCE_SOURCE_IDS = ("natural_earth_land", "geoboundaries_adm0", "geoboundaries_adm1", "ghsl_pop")


def used_source_ids(sources: dict[str, Source], dims: dict[str, Dimension]) -> set[str]:
    """Every source id a stage actually reads: the reference layers, every dimension's sources
    (hazards included) and the geometry / also_needs sources behind them. Registry entries that
    nothing uses (the fixture world's deliberate `unverified_example`) are not counted."""
    used = set(REFERENCE_SOURCE_IDS)
    for d in dims.values():
        used.update(d.sources)
        used.update(j.source for j in d.joiners)
    for sid in list(used):
        src = sources.get(sid)
        if src is None:
            continue
        for key in ("geometry",):
            if src.extra.get(key):
                used.add(src.extra[key])
        used.update(src.extra.get("also_needs", []) or [])
    return used
