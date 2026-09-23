"""Joiners (SPEC §20.3): attach a value from a source to each hex, with a resolution tag.

Every joiner takes a hexes DataFrame (``h3, lat, lng``; some need ``population``) and returns a
pandas Series aligned to the hexes index. Missing -> NaN / None, never 0 (invariant 3).
"""

from .area_weighted_overlay import area_weighted_overlay
from .iso_lookup import iso_lookup
from .point_density import point_density
from .point_mean import point_mean
from .point_radius import point_radius
from .polygon_centroid import polygon_centroid
from .raster_mean import raster_mean

JOINERS = {
    "polygon_centroid": polygon_centroid,
    "iso_lookup": iso_lookup,
    "area_weighted_overlay": area_weighted_overlay,
    "point_density": point_density,
    # hex-level layers (resolution tag `hex`): computed straight from a raster or a point set
    "raster_mean": raster_mean,
    "point_mean": point_mean,
    "point_radius": point_radius,
}

__all__ = ["JOINERS", "area_weighted_overlay", "iso_lookup", "point_density", "point_mean", "point_radius", "polygon_centroid", "raster_mean"]
