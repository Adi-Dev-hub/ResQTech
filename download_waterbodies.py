import os
import requests
import geopandas as gpd
from shapely.geometry import Polygon, LineString


# ============================================================
# CONFIGURATION
# ============================================================

MIN_LAT = 18.40
MIN_LON = 73.70
MAX_LAT = 18.65
MAX_LON = 74.00

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "data")
)

OUTPUT_FILE = os.path.join(
    DATA_DIR,
    "PuneWaterBodies.geojson"
)


# ============================================================
# OVERPASS SERVERS
# ============================================================

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


# ============================================================
# CREATE DATA DIRECTORY
# ============================================================

os.makedirs(DATA_DIR, exist_ok=True)


# ============================================================
# LIGHTER OVERPASS QUERY
# ============================================================

query = f"""
[out:json][timeout:120];

(
    way["natural"="water"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
    way["landuse"="reservoir"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
);

out geom;
"""


# ============================================================
# REQUEST HEADERS
# ============================================================

headers = {
    "User-Agent": "FloodRiskGIS/1.0",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded"
}


# ============================================================
# DOWNLOAD
# ============================================================

data = None

print("=" * 55)
print("OSM WATER BODY DOWNLOADER")
print("=" * 55)

for server in OVERPASS_SERVERS:

    print("\nTrying Overpass server:")
    print(server)

    try:

        response = requests.post(
            server,
            data={"data": query},
            headers=headers,
            timeout=150
        )

        print(
            "Overpass HTTP Status:",
            response.status_code
        )

        response.raise_for_status()

        data = response.json()

        print("\nOSM water body data downloaded successfully!")

        break

    except Exception as e:

        print("\nOverpass connection error:")
        print(e)

        print("Trying another Overpass server...")


# ============================================================
# CHECK DOWNLOAD
# ============================================================

if data is None:

    print("\n" + "=" * 55)
    print("ERROR: Could not download OSM water bodies.")
    print("=" * 55)

    raise SystemExit(1)


elements = data.get("elements", [])

print(
    "\nTotal OSM elements:",
    len(elements)
)


# ============================================================
# CONVERT OSM WAYS
# ============================================================

features = []

seen_ids = set()

for element in elements:

    if element.get("type") != "way":
        continue

    osm_id = element.get("id")

    if osm_id in seen_ids:
        continue

    seen_ids.add(osm_id)

    geometry_data = element.get(
        "geometry",
        []
    )

    if len(geometry_data) < 2:
        continue

    coordinates = []

    for point in geometry_data:

        lon = point.get("lon")
        lat = point.get("lat")

        if lon is not None and lat is not None:

            coordinates.append(
                (lon, lat)
            )

    if len(coordinates) < 2:
        continue

    tags = element.get(
        "tags",
        {}
    )

    geometry = None

    # --------------------------------------------------------
    # Closed way = Polygon
    # --------------------------------------------------------

    if (
        len(coordinates) >= 4
        and coordinates[0] == coordinates[-1]
    ):

        try:

            polygon = Polygon(
                coordinates
            )

            if not polygon.is_valid:

                polygon = polygon.buffer(0)

            if not polygon.is_empty:

                geometry = polygon

        except Exception:

            geometry = None

    # --------------------------------------------------------
    # Open way = LineString
    # --------------------------------------------------------

    else:

        try:

            geometry = LineString(
                coordinates
            )

        except Exception:

            geometry = None

    if geometry is None:
        continue

    features.append({

        "osm_id": osm_id,

        "name": tags.get(
            "name",
            ""
        ),

        "water": tags.get(
            "water",
            ""
        ),

        "natural": tags.get(
            "natural",
            ""
        ),

        "landuse": tags.get(
            "landuse",
            ""
        ),

        "operator": tags.get(
            "operator",
            ""
        ),

        "geometry": geometry
    })


# ============================================================
# RESULT
# ============================================================

print("\n" + "=" * 55)
print("WATER BODY CONVERSION")
print("=" * 55)

print(
    "Water body features:",
    len(features)
)


if len(features) == 0:

    print(
        "\nWARNING: No water bodies were found."
    )

    raise SystemExit(1)


# ============================================================
# CREATE GEODATAFRAME
# ============================================================

gdf = gpd.GeoDataFrame(
    features,
    geometry="geometry",
    crs="EPSG:4326"
)


# ============================================================
# SAVE GEOJSON
# ============================================================

print("\nSaving water body data...")

gdf.to_file(
    OUTPUT_FILE,
    driver="GeoJSON"
)


# ============================================================
# VERIFY
# ============================================================

print("\n" + "=" * 55)
print("WATER BODY DOWNLOAD COMPLETE")
print("=" * 55)

print(
    "Total water bodies:",
    len(gdf)
)

print(
    "CRS:",
    gdf.crs
)

print(
    "\nOutput file:"
)

print(
    OUTPUT_FILE
)


print("\nSample water bodies:")

for _, row in gdf.head(10).iterrows():

    name = row.get(
        "name",
        ""
    )

    water = row.get(
        "water",
        ""
    )

    natural = row.get(
        "natural",
        ""
    )

    if not name:
        name = "Unnamed"

    print(
        f"Name: {name} | "
        f"Water: {water or '-'} | "
        f"Natural: {natural or '-'}"
    )


print("\nDONE!")