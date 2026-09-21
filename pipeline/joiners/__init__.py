"""Joiners (SPEC §20.3): attach a value from a source to each hex, with a resolution tag.

Every joiner takes a hexes DataFrame (``h3, lat, lng``; some need ``population``) and returns a
pandas Series aligned to the hexes index. Missing -> NaN / None, never 0 (invariant 3).
"""

from .area_weighted_overlay import area_weighted_overlay
from .iso_lookup import iso_lookup
from .point_density import point_density
from .polygon_centroid import polygon_centroid

JOINERS = {
    "polygon_centroid": polygon_centroid,
    "iso_lookup": iso_lookup,
    "area_weighted_overlay": area_weighted_overlay,
    "point_density": point_density,
}

__all__ = ["JOINERS", "area_weighted_overlay", "iso_lookup", "point_density", "polygon_centroid"]
