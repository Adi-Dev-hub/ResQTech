import sys
import webbrowser
import threading
import os

import geopandas as gpd
import folium

from flask import Flask, render_template_string


# =============================================================
# FLASK APPLICATION
# =============================================================

app = Flask(__name__)

CURRENT_MAP = None


# =============================================================
# CREATE PUNE MAP
# =============================================================

def create_pune_map(pune_boundary_path):

    print("\n==============================================")
    print("          PUNE DISTRICT MAP")
    print("==============================================")

    # ---------------------------------------------------------
    # CHECK SHAPEFILE
    # ---------------------------------------------------------

    if not os.path.exists(pune_boundary_path):

        print("\nERROR:")
        print("Pune boundary shapefile not found:")
        print(pune_boundary_path)

        return None

    # =========================================================
    # LOAD PUNE BOUNDARY
    # =========================================================

    print("\nLoading Pune boundary...")

    pune = gpd.read_file(
        pune_boundary_path
    )

    if pune.empty:

        print("\nERROR:")
        print("Pune boundary shapefile is empty.")

        return None

    print(
        "Pune boundary loaded successfully."
    )

    print(
        "Original CRS:",
        pune.crs
    )

    # =========================================================
    # CONVERT TO WGS84
    # =========================================================

    if pune.crs is not None:

        pune = pune.to_crs(
            epsg=4326
        )

    print(
        "Converted to EPSG:4326"
    )

    # =========================================================
    # GET FULL PUNE EXTENT
    # =========================================================

    bounds = pune.total_bounds

    min_lon = bounds[0]
    min_lat = bounds[1]

    max_lon = bounds[2]
    max_lat = bounds[3]

    print("\n==============================================")
    print("FULL PUNE DISTRICT EXTENT")
    print("==============================================")

    print(
        "Minimum Longitude:",
        min_lon
    )

    print(
        "Minimum Latitude :",
        min_lat
    )

    print(
        "Maximum Longitude:",
        max_lon
    )

    print(
        "Maximum Latitude :",
        max_lat
    )

    # =========================================================
    # MAP CENTER
    # =========================================================

    center_lat = (
        min_lat + max_lat
    ) / 2

    center_lon = (
        min_lon + max_lon
    ) / 2

    print("\nMap center:")

    print(
        "Latitude :",
        center_lat
    )

    print(
        "Longitude:",
        center_lon
    )

    # =========================================================
    # CREATE MAP
    # =========================================================

    m = folium.Map(

        location=[
            center_lat,
            center_lon
        ],

        zoom_start=10,

        tiles="OpenStreetMap"

    )

    # =========================================================
    # PUNE DISTRICT LAYER
    # =========================================================

    # ---------------------------------------------------------
    # THIS IS THE ONLY CHECKBOX
    # ---------------------------------------------------------

    pune_layer = folium.FeatureGroup(

        name="Pune District",

        overlay=True,

        show=True

    )

    # =========================================================
    # PUNE HIGHLIGHT
    # =========================================================

    folium.GeoJson(

        pune.to_json(),

        name="Pune District Boundary",

        style_function=lambda feature: {

            "fillColor": "#00FFFF",

            "color": "#0000FF",

            "weight": 3,

            "fillOpacity": 0.20

        },

        highlight_function=lambda feature: {

            "color": "#0000FF",

            "weight": 5,

            "fillOpacity": 0.35

        }

    ).add_to(
        pune_layer
    )

    # =========================================================
    # ADD PUNE LAYER TO MAP
    # =========================================================

    pune_layer.add_to(m)

    # =========================================================
    # ZOOM TO COMPLETE PUNE DISTRICT
    # =========================================================

    m.fit_bounds(

        [

            [
                min_lat,
                min_lon
            ],

            [
                max_lat,
                max_lon
            ]

        ]

    )

    # =========================================================
    # LAYER CONTROL
    # =========================================================

    folium.LayerControl(

        collapsed=False

    ).add_to(m)

    # =========================================================
    # RESULT
    # =========================================================

    print("\n==============================================")
    print("       PUNE MAP CREATED SUCCESSFULLY")
    print("==============================================")

    return m


# =============================================================
# FLASK ROUTE
# =============================================================

@app.route("/")
def index():

    global CURRENT_MAP

    if CURRENT_MAP is None:

        return """
        <h2>Pune map could not be created.</h2>
        """

    return render_template_string(

        CURRENT_MAP
        .get_root()
        .render()

    )


# =============================================================
# START FLASK SERVER
# =============================================================

def run_server():

    app.run(

        host="127.0.0.1",

        port=5000,

        debug=False,

        use_reloader=False

    )


# =============================================================
# MAIN PROGRAM
# =============================================================

if __name__ == "__main__":

    # ---------------------------------------------------------
    # REQUIRE ONLY ONE ARGUMENT
    #
    # Argument = Pune boundary shapefile
    # ---------------------------------------------------------

    if len(sys.argv) < 2:

        print("\nUsage:")

        print(
            'python Osm_pune.py '
            '"shapetiff\\Pune_Subdis_boundary.shp"'
        )

        sys.exit(1)

    # ---------------------------------------------------------
    # PUNE SHAPEFILE
    # ---------------------------------------------------------

    pune_boundary_path = sys.argv[1]

    print("\nPune boundary:")

    print(
        os.path.abspath(
            pune_boundary_path
        )
    )

    # ---------------------------------------------------------
    # CREATE MAP
    # ---------------------------------------------------------

    CURRENT_MAP = create_pune_map(

        pune_boundary_path

    )

    if CURRENT_MAP is None:

        print(
            "\nMap creation failed."
        )

        sys.exit(1)

    # ---------------------------------------------------------
    # START SERVER
    # ---------------------------------------------------------

    server_thread = threading.Thread(

        target=run_server,

        daemon=True

    )

    server_thread.start()

    # ---------------------------------------------------------
    # OPEN BROWSER
    # ---------------------------------------------------------

    print(
        "\nOpening browser..."
    )

    webbrowser.open(

        "http://127.0.0.1:5000/"

    )

    print("\n==============================================")
    print("       PUNE WEB MAP IS RUNNING")
    print("==============================================")

    print(
        "http://127.0.0.1:5000/"
    )

    print(
        "\nPress CTRL+C to stop."
    )

    # ---------------------------------------------------------
    # KEEP SERVER ALIVE
    # ---------------------------------------------------------

    try:

        while True:

            threading.Event().wait(1)

    except KeyboardInterrupt:

        print(
            "\nServer stopped."
        )
