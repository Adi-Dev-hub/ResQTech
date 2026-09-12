import sys
import os
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import cKDTree


# ---------------------------------------------------------
# INPUTS
# ---------------------------------------------------------

input_raster = sys.argv[1]
osm_roads = sys.argv[2]
output_raster = sys.argv[3]


# ---------------------------------------------------------
# READ TIFF
# ---------------------------------------------------------

print("Reading TIFF...")

with rasterio.open(input_raster) as src:
    profile = src.profile.copy()
    transform = src.transform
    width = src.width
    height = src.height
    raster_crs = src.crs

print("Raster CRS:", raster_crs)
print("Raster size:", width, "x", height)


# ---------------------------------------------------------
# READ OSM ROADS
# ---------------------------------------------------------

print("Reading OSM roads...")

roads = gpd.read_file(osm_roads)

print("OSM CRS:", roads.crs)

if roads.empty:
    raise ValueError("No road features found in the OSM file.")


# ---------------------------------------------------------
# REPROJECT ROADS TO RASTER CRS
# ---------------------------------------------------------

if roads.crs != raster_crs:
    print("Reprojecting roads...")
    roads = roads.to_crs(raster_crs)


# ---------------------------------------------------------
# IMPORTANT:
# DISTANCE MUST BE IN METERS
# ---------------------------------------------------------

if raster_crs.is_geographic:
    raise ValueError(
        "Your TIFF uses latitude/longitude coordinates. "
        "Reproject the TIFF to a meter-based projected CRS before running this script."
    )


# ---------------------------------------------------------
# GET ROAD POINTS
# ---------------------------------------------------------

print("Preparing road geometries...")

road_geometries = roads.geometry.dropna()

# Extract coordinates from road vertices
road_points = []

for geom in road_geometries:

    if geom.geom_type == "LineString":

        road_points.extend(list(geom.coords))

    elif geom.geom_type == "MultiLineString":

        for line in geom.geoms:
            road_points.extend(list(line.coords))


road_points = np.array(road_points)

if len(road_points) == 0:
    raise ValueError("Could not extract road coordinates.")


print("Number of road points:", len(road_points))


# ---------------------------------------------------------
# CREATE KD-TREE
# ---------------------------------------------------------

print("Creating spatial index...")

tree = cKDTree(road_points)


# ---------------------------------------------------------
# CREATE PIXEL CENTER COORDINATES
# ---------------------------------------------------------

print("Calculating pixel coordinates...")

rows, cols = np.indices((height, width))

xs, ys = rasterio.transform.xy(
    transform,
    rows,
    cols,
    offset="center"
)

xs = np.asarray(xs)
ys = np.asarray(ys)

pixel_points = np.column_stack(
    (xs.ravel(), ys.ravel())
)


# ---------------------------------------------------------
# FIND NEAREST ROAD
# ---------------------------------------------------------

print("Calculating distance to nearest road...")

distances, indexes = tree.query(
    pixel_points,
    k=1
)

distance_array = distances.reshape(
    (height, width)
).astype("float32")


# ---------------------------------------------------------
# SAVE DISTANCE RASTER
# ---------------------------------------------------------

print("Saving output raster...")

profile.update(
    dtype="float32",
    count=1,
    nodata=-9999,
    compress="lzw"
)

with rasterio.open(output_raster, "w", **profile) as dst:

    dst.write(
        distance_array,
        1
    )


print()
print("DONE!")
print("Output:", output_raster)
print(
    "Minimum distance:",
    np.nanmin(distance_array),
    "meters"
)

print(
    "Maximum distance:",
    np.nanmax(distance_array),
    "meters"
)