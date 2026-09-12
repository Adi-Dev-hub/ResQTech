import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import os
import time

# ==========================================================
# RESQTECH - PUNE EMERGENCY INFRASTRUCTURE
# OpenStreetMap + Overpass API
# ==========================================================

OUTPUT_DIR = "ResQTech_Pune_Data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Multiple Overpass servers
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
]

# ==========================================================
# QUERY
# ==========================================================

query = """
[out:json][timeout:180];

area
  ["name"="Pune"]
  ["boundary"="administrative"]
  ->.searchArea;

(
  nwr["amenity"="hospital"](area.searchArea);
  nwr["amenity"="fire_station"](area.searchArea);
  nwr["amenity"="police"](area.searchArea);

  nwr["emergency"="ambulance_station"](area.searchArea);

  nwr["amenity"="rescue_station"](area.searchArea);

  nwr["emergency"="water_rescue"](area.searchArea);

  nwr["emergency"="water_rescue_station"](area.searchArea);

  nwr["emergency:social_facility"="shelter"](area.searchArea);

  nwr["social_facility"="shelter"](area.searchArea);
);

out center tags;
"""

# ==========================================================
# DOWNLOAD FROM OVERPASS
# ==========================================================

headers = {
    "User-Agent": "ResQTech-Emergency-GIS/1.0"
}

data = None

for server in OVERPASS_SERVERS:

    print("\nTrying Overpass server:")
    print(server)

    try:

        response = requests.get(
            server,
            params={"data": query},
            headers=headers,
            timeout=240
        )

        print("HTTP Status:", response.status_code)

        response.raise_for_status()

        data = response.json()

        print("SUCCESS!")
        break

    except Exception as e:

        print("Server failed:")
        print(e)

        time.sleep(2)


# ==========================================================
# CHECK DOWNLOAD
# ==========================================================

if data is None:

    print("\nERROR:")
    print("All Overpass servers failed.")

    print("\nTry again after a few minutes.")
    exit()


elements = data.get("elements", [])

print("\nTotal OSM objects downloaded:", len(elements))


# ==========================================================
# CONVERT TO DATAFRAME
# ==========================================================

features = []

for element in elements:

    tags = element.get("tags", {})

    # --------------------------
    # Node
    # --------------------------

    if element["type"] == "node":

        lat = element.get("lat")
        lon = element.get("lon")

    # --------------------------
    # Way / Relation
    # --------------------------

    elif "center" in element:

        lat = element["center"]["lat"]
        lon = element["center"]["lon"]

    else:
        continue

    features.append({

        "osm_id":
            element["id"],

        "osm_type":
            element["type"],

        "name":
            tags.get("name"),

        "amenity":
            tags.get("amenity"),

        "emergency":
            tags.get("emergency"),

        "social_facility":
            tags.get("social_facility"),

        "emergency_social_facility":
            tags.get("emergency:social_facility"),

        "phone":
            tags.get("phone"),

        "website":
            tags.get("website"),

        "operator":
            tags.get("operator"),

        "lat":
            lat,

        "lon":
            lon
    })


# ==========================================================
# CREATE GEODATAFRAME
# ==========================================================

df = pd.DataFrame(features)

if df.empty:

    print("No data found.")
    exit()


geometry = [
    Point(lon, lat)
    for lon, lat
    in zip(df["lon"], df["lat"])
]

gdf = gpd.GeoDataFrame(
    df,
    geometry=geometry,
    crs="EPSG:4326"
)


# ==========================================================
# CLASSIFY INFRASTRUCTURE
# ==========================================================

def classify(row):

    amenity = row["amenity"]
    emergency = row["emergency"]

    social = row["social_facility"]

    emergency_social = \
        row["emergency_social_facility"]

    if amenity == "hospital":
        return "Hospital"

    elif amenity == "fire_station":
        return "Fire Station"

    elif amenity == "police":
        return "Police Station"

    elif emergency == "ambulance_station":
        return "Ambulance Station"

    elif amenity == "rescue_station":
        return "Rescue Station"

    elif emergency in [
        "water_rescue",
        "water_rescue_station"
    ]:
        return "Water Rescue"

    elif social == "shelter":
        return "Emergency Shelter"

    elif emergency_social == "shelter":
        return "Emergency Shelter"

    return "Other"


gdf["facility_type"] = gdf.apply(
    classify,
    axis=1
)


# ==========================================================
# PRINT RESULTS
# ==========================================================

print("\n================================")
print("RESQTECH PUNE INFRASTRUCTURE")
print("================================")

print(
    gdf["facility_type"]
    .value_counts()
)


# ==========================================================
# SAVE GEOPACKAGE
# ==========================================================

gpkg = os.path.join(
    OUTPUT_DIR,
    "ResQTech_Pune_Emergency.gpkg"
)

# Main layer
gdf.to_file(
    gpkg,
    layer="all_emergency_infrastructure",
    driver="GPKG"
)


# ==========================================================
# SAVE EACH FACILITY TYPE
# ==========================================================

for facility in gdf["facility_type"].unique():

    if facility == "Other":
        continue

    layer = gdf[
        gdf["facility_type"] == facility
    ].copy()

    layer_name = (
        facility
        .lower()
        .replace(" ", "_")
    )

    layer.to_file(
        gpkg,
        layer=layer_name,
        driver="GPKG"
    )

    print(
        f"{facility}: {len(layer)}"
    )


# ==========================================================
# SAVE CSV
# ==========================================================

csv_file = os.path.join(
    OUTPUT_DIR,
    "Pune_Emergency_Infrastructure.csv"
)

gdf.drop(
    columns="geometry"
).to_csv(
    csv_file,
    index=False
)


print("\n================================")
print("DOWNLOAD COMPLETE")
print("================================")

print("\nGeoPackage:")
print(gpkg)

print("\nCSV:")
print(csv_file)