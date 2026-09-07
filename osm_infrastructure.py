import requests
import geopandas as gpd
from shapely.geometry import Point
import time

# ============================================================
# 1. LOAD PROJECT STUDY AREA
# ============================================================

boundary = gpd.read_file("data/Pune_shape_file.shp")
boundary = boundary.to_crs("EPSG:4326")

west, south, east, north = boundary.total_bounds

print("Study Area:")
print("West :", west)
print("South:", south)
print("East :", east)
print("North:", north)


# ============================================================
# 2. OVERPASS API
# ============================================================

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# We divide the large area into smaller grid cells.
GRID_SIZE = 0.25


# ============================================================
# 3. FUNCTION TO QUERY ONE GRID CELL
# ============================================================

def get_osm_data(south, west, north, east):

    query = f"""
    [out:json][timeout:30];

    (
      nwr["amenity"="hospital"]({south},{west},{north},{east});
      nwr["amenity"="police"]({south},{west},{north},{east});
    );

    out center tags;
    """

    try:

        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={
                "User-Agent": "FloodRiskAssessment/1.0"
            },
            timeout=60
        )

        response.raise_for_status()

        return response.json()["elements"]

    except Exception as e:

        print("Request failed:", e)

        return []


# ============================================================
# 4. CREATE GRID
# ============================================================

all_elements = []

current_south = south

cell_number = 0

total_cells = 0

temp_south = south

while temp_south < north:

    temp_north = min(temp_south + GRID_SIZE, north)

    temp_west = west

    while temp_west < east:

        temp_east = min(temp_west + GRID_SIZE, east)

        total_cells += 1

        temp_west = temp_east

    temp_south = temp_north


print("\nTotal grid cells:", total_cells)
print("Starting OpenStreetMap download...")


# ============================================================
# 5. DOWNLOAD EACH GRID CELL
# ============================================================

current_south = south

while current_south < north:

    current_north = min(
        current_south + GRID_SIZE,
        north
    )

    current_west = west

    while current_west < east:

        current_east = min(
            current_west + GRID_SIZE,
            east
        )

        cell_number += 1

        print(
            f"\nProcessing cell {cell_number}/{total_cells}"
        )

        print(
            "Bounds:",
            current_south,
            current_west,
            current_north,
            current_east
        )

        elements = get_osm_data(
            current_south,
            current_west,
            current_north,
            current_east
        )

        print(
            "Objects received:",
            len(elements)
        )

        all_elements.extend(elements)

        current_west = current_east

        # Small delay to avoid sending requests too quickly
        time.sleep(1)

    current_south = current_north


# ============================================================
# 6. REMOVE DUPLICATES
# ============================================================

unique_elements = {}

for element in all_elements:

    key = (
        element["type"],
        element["id"]
    )

    unique_elements[key] = element


print("\nTotal unique OSM objects:", len(unique_elements))


# ============================================================
# 7. CONVERT OSM DATA TO GEODATAFRAME
# ============================================================

records = []

for element in unique_elements.values():

    # Node
    if element["type"] == "node":

        latitude = element.get("lat")
        longitude = element.get("lon")

    # Way / Relation
    else:

        center = element.get("center", {})

        latitude = center.get("lat")
        longitude = center.get("lon")

    if latitude is None or longitude is None:
        continue

    tags = element.get("tags", {})

    records.append({

        "osm_id": element["id"],

        "osm_type": element["type"],

        "amenity": tags.get(
            "amenity",
            ""
        ),

        "name": tags.get(
            "name",
            "Unnamed"
        ),

        "latitude": latitude,

        "longitude": longitude,

        "geometry": Point(
            longitude,
            latitude
        )
    })


gdf = gpd.GeoDataFrame(
    records,
    geometry="geometry",
    crs="EPSG:4326"
)


# ============================================================
# 8. SEPARATE HOSPITALS AND POLICE STATIONS
# ============================================================

hospitals = gdf[
    gdf["amenity"] == "hospital"
].copy()

police = gdf[
    gdf["amenity"] == "police"
].copy()


# ============================================================
# 9. CLIP TO EXACT PROJECT BOUNDARY
# ============================================================

print("\nClipping data to project boundary...")

hospitals = gpd.clip(
    hospitals,
    boundary
)

police = gpd.clip(
    police,
    boundary
)


# ============================================================
# 10. SAVE RESULTS
# ============================================================

hospitals.to_file(
    "data/osm_hospitals.geojson",
    driver="GeoJSON"
)

police.to_file(
    "data/osm_police_stations.geojson",
    driver="GeoJSON"
)


# ============================================================
# 11. FINAL RESULT
# ============================================================

print("\n===================================")
print("OSM DOWNLOAD COMPLETED")
print("===================================")

print(
    "Hospitals found       :",
    len(hospitals)
)

print(
    "Police stations found :",
    len(police)
)

print("\nFiles created:")

print(
    "data/osm_hospitals.geojson"
)

print(
    "data/osm_police_stations.geojson"
)

print("\nDone!")