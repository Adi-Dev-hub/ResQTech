import requests
import geopandas as gpd
from shapely.geometry import LineString
import os


# ============================================================
# OPENSTREETMAP RAILWAY NETWORK DOWNLOADER
# Pune, Maharashtra
# ============================================================


print("=" * 50)
print("OPENSTREETMAP RAILWAY NETWORK")
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

# Output file
GEOJSON_FILE = os.path.join(
    OUTPUT_DIR,
    "PuneRailways.geojson"
)


# ------------------------------------------------------------
# CREATE OUTPUT DIRECTORY
# ------------------------------------------------------------

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


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
# railway=rail       -> main railway lines
# railway=light_rail -> light rail
# railway=subway     -> subway
# railway=tram       -> tram
#
# We are collecting railway ways with their geometry.
#
# ------------------------------------------------------------

query = f"""
[out:json][timeout:180];

(
    way["railway"="rail"]({BBOX});
    way["railway"="light_rail"]({BBOX});
    way["railway"="subway"]({BBOX});
    way["railway"="tram"]({BBOX});
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


print("OSM railway data received.")
print("Converting railway features...")
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

railway_records = []


for element in osm_data.get("elements", []):

    # Only process ways
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

    # Need at least 2 points for a LineString
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

    railway_records.append(
        {
            "osm_id": element.get("id"),

            "railway": tags.get(
                "railway",
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

            "operator": tags.get(
                "operator",
                ""
            ),

            "usage": tags.get(
                "usage",
                ""
            ),

            "service": tags.get(
                "service",
                ""
            ),

            "electrified": tags.get(
                "electrified",
                ""
            ),

            "geometry": line
        }
    )


# ------------------------------------------------------------
# CHECK RESULT
# ------------------------------------------------------------

if not railway_records:

    print("ERROR: No railway features were found.")
    raise SystemExit


print(
    f"Railway features converted: "
    f"{len(railway_records)}"
)

print()


# ------------------------------------------------------------
# CREATE GEODATAFRAME
# ------------------------------------------------------------

railways = gpd.GeoDataFrame(
    railway_records,
    geometry="geometry",
    crs="EPSG:4326"
)


# ------------------------------------------------------------
# SAVE GEOJSON
# ------------------------------------------------------------

print("Saving GeoJSON...")

try:

    railways.to_file(
        GEOJSON_FILE,
        driver="GeoJSON"
    )

    print(
        "GeoJSON saved successfully:"
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
# FINAL INFORMATION
# ------------------------------------------------------------

print()
print("=" * 50)
print("RAILWAY NETWORK DOWNLOAD COMPLETE")
print("=" * 50)
print()

print(
    f"Total railway features: "
    f"{len(railways)}"
)

print(
    f"Coordinate system: "
    f"{railways.crs}"
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
    "OpenStreetMap railway data downloaded successfully."
)

print("=" * 50)