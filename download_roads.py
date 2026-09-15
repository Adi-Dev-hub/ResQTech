import requests
import geopandas as gpd
from shapely.geometry import LineString
import os


# ============================================================
# OPENSTREETMAP ROAD NETWORK DOWNLOADER
# Pune, Maharashtra
# ============================================================


print("=" * 50)
print("OPENSTREETMAP ROAD NETWORK")
print("=" * 50)
print()

# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------

AREA_NAME = "Pune"

# Overpass API
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Pune approximate bounding box
# south, west, north, east
BBOX = "18.40,73.70,18.65,74.00"

# Output directory
OUTPUT_DIR = "../data"

# Output files
GEOJSON_FILE = os.path.join(
    OUTPUT_DIR,
    "PuneRoads.geojson"
)

SHAPEFILE_FOLDER = os.path.join(
    OUTPUT_DIR,
    "PuneRoads_Shapefile"
)


# ------------------------------------------------------------
# CREATE OUTPUT DIRECTORY
# ------------------------------------------------------------

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ------------------------------------------------------------
# INFORMATION
# ------------------------------------------------------------

print(f"Area: {AREA_NAME}")
print("Source: OpenStreetMap")
print("API: Overpass")
print()
print("Bounding box:")
print(BBOX)
print()


# ------------------------------------------------------------
# OVERPASS QUERY
# ------------------------------------------------------------
#
# highway=* contains roads and paths in OpenStreetMap.
#
# out geom;
# tells Overpass to return the actual coordinates
# of each road.
#
# ------------------------------------------------------------

query = f"""
[out:json][timeout:180];

(
    way["highway"]({BBOX});
);

out geom;
"""


# ------------------------------------------------------------
# SEND REQUEST
# ------------------------------------------------------------

print("Sending request to Overpass...")
print("Please wait...")
print()

try:

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=240,
        headers={
            "User-Agent": "PuneFloodGIS/1.0"
        }
    )

except requests.exceptions.Timeout:

    print()
    print("ERROR: Overpass request timed out.")
    print("Please try again later.")
    raise SystemExit

except requests.exceptions.RequestException as e:

    print()
    print("ERROR: Could not connect to Overpass.")
    print(e)
    raise SystemExit


# ------------------------------------------------------------
# CHECK HTTP RESPONSE
# ------------------------------------------------------------

print(f"HTTP status: {response.status_code}")
print()


if response.status_code != 200:

    print("ERROR: Overpass did not return valid data.")
    print()
    print(response.text[:1000])
    raise SystemExit


print("OSM data received.")
print("Converting road features...")
print()


# ------------------------------------------------------------
# READ JSON
# ------------------------------------------------------------

try:

    osm_data = response.json()

except Exception as e:

    print("ERROR: Could not read OSM JSON data.")
    print(e)
    raise SystemExit


# ------------------------------------------------------------
# CONVERT OSM WAYS TO GEOMETRIES
# ------------------------------------------------------------

road_records = []


for element in osm_data.get("elements", []):

    # We only want OSM ways
    if element.get("type") != "way":
        continue

    # Get geometry
    geometry = element.get("geometry")

    if not geometry:
        continue

    # Create coordinate list
    coordinates = []

    for point in geometry:

        latitude = point.get("lat")
        longitude = point.get("lon")

        if latitude is None or longitude is None:
            continue

        coordinates.append(
            (longitude, latitude)
        )

    # A LineString needs at least two points
    if len(coordinates) < 2:
        continue

    try:

        line = LineString(coordinates)

    except Exception:
        continue


    # --------------------------------------------------------
    # OSM TAGS
    # --------------------------------------------------------

    tags = element.get("tags", {})

    road_records.append(
        {
            "osm_id": element.get("id"),

            "highway": tags.get(
                "highway",
                ""
            ),

            "name": tags.get(
                "name",
                ""
            ),

            "ref": tags.get(
                "ref",
                ""
            ),

            "surface": tags.get(
                "surface",
                ""
            ),

            "lanes": tags.get(
                "lanes",
                ""
            ),

            "maxspeed": tags.get(
                "maxspeed",
                ""
            ),

            "oneway": tags.get(
                "oneway",
                ""
            ),

            "geometry": line
        }
    )


# ------------------------------------------------------------
# CHECK RESULT
# ------------------------------------------------------------

if not road_records:

    print("ERROR: No road features were found.")
    raise SystemExit


print(
    f"Road features converted: {len(road_records)}"
)
print()


# ------------------------------------------------------------
# CREATE GEODATAFRAME
# ------------------------------------------------------------

roads = gpd.GeoDataFrame(
    road_records,
    geometry="geometry",
    crs="EPSG:4326"
)


# ------------------------------------------------------------
# SAVE GEOJSON
# ------------------------------------------------------------

print("Saving GeoJSON...")

try:

    roads.to_file(
        GEOJSON_FILE,
        driver="GeoJSON"
    )

    print(
        f"GeoJSON saved successfully:"
    )

    print(
        os.path.abspath(GEOJSON_FILE)
    )

except Exception as e:

    print()
    print("ERROR: Could not save GeoJSON.")
    print(e)
    raise SystemExit


# ------------------------------------------------------------
# SAVE SHAPEFILE
# ------------------------------------------------------------

print()
print("Saving Shapefile...")

try:

    # Make sure folder exists
    os.makedirs(
        SHAPEFILE_FOLDER,
        exist_ok=True
    )

    roads.to_file(
        SHAPEFILE_FOLDER,
        driver="ESRI Shapefile"
    )

    print(
        "Shapefile saved successfully:"
    )

    print(
        os.path.abspath(SHAPEFILE_FOLDER)
    )

except PermissionError:

    print(
        "WARNING: Windows permission denied "
        "while saving Shapefile."
    )

    print(
        "This does NOT affect the GeoJSON file."
    )

except Exception as e:

    print(
        "WARNING: Shapefile could not be saved."
    )

    print(
        "Reason:",
        e
    )

    print(
        "The GeoJSON file is still available."
    )


# ------------------------------------------------------------
# FINAL INFORMATION
# ------------------------------------------------------------

print()
print("=" * 50)
print("ROAD NETWORK DOWNLOAD COMPLETE")
print("=" * 50)
print()

print(
    f"Total road features: {len(roads)}"
)

print(
    f"Coordinate system: {roads.crs}"
)

print()
print(
    "Main output file:"
)

print(
    os.path.abspath(GEOJSON_FILE)
)

print()
print(
    "OpenStreetMap road data downloaded successfully."
)

print("=" * 50)