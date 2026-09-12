import sys
import webbrowser
import threading

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from osgeo import gdal
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

import folium
import overpy
from affine import Affine

from flask import Flask, render_template_string

from Osm_ui import Ui_Dialog  # Your Qt Designer UI


class FloodRiskApp(QDialog):

    def __init__(self):
        super().__init__()

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        self.ui.toolButton.clicked.connect(self.browse_file)
        self.ui.pushButton.clicked.connect(self.run_analysis)

        self.risk_map_path = ""
        self.app = Flask(__name__)

    # ---------------------------------------------------------
    # SELECT FLOOD RISK RASTER
    # ---------------------------------------------------------

    def browse_file(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Risk Map File",
            "",
            "GeoTIFF Files (*.tif *.tiff)"
        )

        if file_path:
            self.ui.lineEdit.setText(file_path)
            self.risk_map_path = file_path

    # ---------------------------------------------------------
    # MAIN ANALYSIS
    # ---------------------------------------------------------

    def run_analysis(self):

        if not self.risk_map_path:
            print("Please select a file first!")
            return

        print(f"Processing file: {self.risk_map_path}")

        png_path = "combined_risk_output.png"

        # -----------------------------------------------------
        # OPEN FLOOD RISK RASTER
        # -----------------------------------------------------

        dataset = gdal.Open(self.risk_map_path)

        if dataset is None:
            print(f"Cannot open risk map: {self.risk_map_path}")
            return

        band = dataset.GetRasterBand(1)

        risk_data = band.ReadAsArray().astype(np.uint8)

        transform = dataset.GetGeoTransform()

        affine_transform = Affine.from_gdal(*transform)

        min_x, pixel_width, _, max_y, _, pixel_height = transform

        rows, cols = risk_data.shape

        max_x = min_x + cols * pixel_width
        min_y = max_y + rows * pixel_height

        dataset = None

        # -----------------------------------------------------
        # CREATE RISK IMAGE
        # -----------------------------------------------------

        cmap = ListedColormap([
            'yellow',
            'orange',
            'red',
            'gray'
        ])

        plt.imsave(
            png_path,
            risk_data,
            cmap=cmap
        )

        # -----------------------------------------------------
        # MAP CENTER
        # -----------------------------------------------------

        center_lat = (min_y + max_y) / 2
        center_lon = (min_x + max_x) / 2

        print("\nMap center:")
        print("Latitude :", center_lat)
        print("Longitude:", center_lon)

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12
        )

        # -----------------------------------------------------
        # FLOOD RISK IMAGE
        # -----------------------------------------------------

        image_bounds = [
            [min_y, min_x],
            [max_y, max_x]
        ]

        folium.raster_layers.ImageOverlay(
            name="Flood Risk Map",
            image=png_path,
            bounds=image_bounds,
            opacity=0.6,
            interactive=True,
            cross_origin=False,
            zindex=1
        ).add_to(m)

        # -----------------------------------------------------
        # CONNECT TO OPENSTREETMAP / OVERPASS
        # -----------------------------------------------------

        print("\nConnecting to OpenStreetMap Overpass...")

        api = overpy.Overpass()

        # -----------------------------------------------------
        # OSM QUERIES
        # -----------------------------------------------------

        queries = {

            "hospital":
                'node["amenity"="hospital"]({},{},{},{});out;',

            "school":
                'node["amenity"="school"]({},{},{},{});out;',

            "fire_station":
                'node["emergency"="fire_station"]({},{},{},{});out;',

            "police":
                'node["amenity"="police"]({},{},{},{});out;',
        }

        # -----------------------------------------------------
        # INFRASTRUCTURE STYLE
        # -----------------------------------------------------

        infrastructure_info = {

            "hospital": {
                "color": {
                    "1": "green",
                    "2": "orange",
                    "3": "red"
                },
                "icon": "plus-square"
            },

            "school": {
                "color": "blue",
                "icon": "graduation-cap"
            },

            "fire_station": {
                "color": "darkred",
                "icon": "fire-extinguisher"
            },

            "police": {
                "color": "cadetblue",
                "icon": "shield"
            }
        }

        # -----------------------------------------------------
        # FEATURE GROUPS
        # -----------------------------------------------------

        fg_hosp_low = folium.FeatureGroup(
            name="Low Risk Hospitals"
        )

        fg_hosp_med = folium.FeatureGroup(
            name="Moderate Risk Hospitals"
        )

        fg_hosp_high = folium.FeatureGroup(
            name="High Risk Hospitals"
        )

        fg_schools = folium.FeatureGroup(
            name="Schools"
        )

        fg_fire = folium.FeatureGroup(
            name="Fire Stations"
        )

        fg_police = folium.FeatureGroup(
            name="Police Stations"
        )

        # -----------------------------------------------------
        # NEW: ROAD FEATURE GROUP
        # -----------------------------------------------------

        fg_roads = folium.FeatureGroup(
            name="Major Roads"
        )

        # -----------------------------------------------------
        # NEW: RAILWAY FEATURE GROUP
        # -----------------------------------------------------

        fg_railways = folium.FeatureGroup(
            name="Railways"
        )

        # -----------------------------------------------------
        # INVERSE AFFINE TRANSFORM
        # -----------------------------------------------------

        inv_affine = ~affine_transform

        # =====================================================
        # HOSPITAL / SCHOOL / FIRE / POLICE
        # =====================================================

        for infra_type, query in queries.items():

            print(f"\nQuerying {infra_type}...")

            try:

                result = api.query(
                    query.format(
                        min_y,
                        min_x,
                        max_y,
                        max_x
                    )
                )

                print(
                    f"{infra_type}: "
                    f"{len(result.nodes)} locations found"
                )

            except Exception as e:

                print(
                    f"Error querying {infra_type}: {e}"
                )

                continue

            for node in result.nodes:

                lat = float(node.lat)
                lon = float(node.lon)

                col, row = inv_affine * (lon, lat)

                col = int(round(col))
                row = int(round(row))

                if (
                    row < 0
                    or row >= risk_data.shape[0]
                    or col < 0
                    or col >= risk_data.shape[1]
                ):
                    continue

                name = node.tags.get(
                    "name",
                    infra_type.capitalize()
                )

                # -------------------------------------------------
                # HOSPITAL RISK
                # -------------------------------------------------

                if infra_type == "hospital":

                    risk_value = risk_data[row, col]

                    if risk_value == 4:
                        continue

                    icon_color = (
                        infrastructure_info["hospital"]["color"]
                        .get(
                            str(risk_value),
                            "gray"
                        )
                    )

                    icon_name = (
                        infrastructure_info["hospital"]["icon"]
                    )

                    if risk_value == 1:

                        fg = fg_hosp_low

                    elif risk_value == 2:

                        fg = fg_hosp_med

                    else:

                        fg = fg_hosp_high

                # -------------------------------------------------
                # OTHER INFRASTRUCTURE
                # -------------------------------------------------

                else:

                    icon_color = (
                        infrastructure_info[infra_type]["color"]
                    )

                    icon_name = (
                        infrastructure_info[infra_type]["icon"]
                    )

                    if infra_type == "school":

                        fg = fg_schools

                    elif infra_type == "fire_station":

                        fg = fg_fire

                    else:

                        fg = fg_police

                # -------------------------------------------------
                # ADD MARKER
                # -------------------------------------------------

                fg.add_child(
                    folium.Marker(
                        location=[lat, lon],

                        popup=(
                            f"{name} "
                            f"({infra_type.replace('_', ' ').title()})"
                        ),

                        icon=folium.Icon(
                            color=icon_color,
                            icon=icon_name,
                            prefix="fa"
                        )
                    )
                )

        # =====================================================
        # NEW: MAJOR ROADS
        # =====================================================

        print("\nQuerying major roads...")

        road_query = f'''
        way["highway"~"motorway|trunk|primary|secondary|tertiary"]
        ({min_y},{min_x},{max_y},{max_x});
        out geom;
        '''

        try:

            road_result = api.query(
                road_query
            )

            print(
                "Major roads found:",
                len(road_result.ways)
            )

        except Exception as e:

            print(
                f"Error querying roads: {e}"
            )

            road_result = None

        # -----------------------------------------------------
        # DRAW ROADS
        # -----------------------------------------------------

        if road_result:

            for way in road_result.ways:

                try:

                    road_points = [
                        [
                            float(point.lat),
                            float(point.lon)
                        ]
                        for point in way.nodes
                    ]

                    if len(road_points) < 2:
                        continue

                    road_name = way.tags.get(
                        "name",
                        "Unnamed Road"
                    )

                    road_type = way.tags.get(
                        "highway",
                        "road"
                    )

                    popup_text = (
                        f"<b>{road_name}</b><br>"
                        f"Type: {road_type}"
                    )

                    folium.PolyLine(
                        locations=road_points,

                        weight=4,

                        opacity=0.8,

                        popup=popup_text,

                        tooltip=road_name
                    ).add_to(fg_roads)

                except Exception as e:

                    print(
                        "Error drawing road:",
                        e
                    )

        # =====================================================
        # NEW: RAILWAYS
        # =====================================================

        print("\nQuerying railways...")

        railway_query = f'''
        way["railway"~"rail|light_rail|tram"]
        ({min_y},{min_x},{max_y},{max_x});
        out geom;
        '''

        try:

            railway_result = api.query(
                railway_query
            )

            print(
                "Railway lines found:",
                len(railway_result.ways)
            )

        except Exception as e:

            print(
                f"Error querying railways: {e}"
            )

            railway_result = None

        # -----------------------------------------------------
        # DRAW RAILWAYS
        # -----------------------------------------------------

        if railway_result:

            for way in railway_result.ways:

                try:

                    railway_points = [
                        [
                            float(point.lat),
                            float(point.lon)
                        ]
                        for point in way.nodes
                    ]

                    if len(railway_points) < 2:
                        continue

                    railway_name = way.tags.get(
                        "name",
                        "Railway"
                    )

                    railway_type = way.tags.get(
                        "railway",
                        "railway"
                    )

                    popup_text = (
                        f"<b>{railway_name}</b><br>"
                        f"Type: {railway_type}"
                    )

                    folium.PolyLine(
                        locations=railway_points,

                        weight=4,

                        opacity=0.9,

                        dash_array="8, 6",

                        popup=popup_text,

                        tooltip=railway_name
                    ).add_to(fg_railways)

                except Exception as e:

                    print(
                        "Error drawing railway:",
                        e
                    )

        # =====================================================
        # ADD ALL FEATURE GROUPS TO MAP
        # =====================================================

        m.add_child(fg_hosp_low)

        m.add_child(fg_hosp_med)

        m.add_child(fg_hosp_high)

        m.add_child(fg_schools)

        m.add_child(fg_fire)

        m.add_child(fg_police)

        # NEW
        m.add_child(fg_roads)

        # NEW
        m.add_child(fg_railways)

        # -----------------------------------------------------
        # LAYER CONTROL
        # -----------------------------------------------------

        folium.LayerControl(
            collapsed=False
        ).add_to(m)

        # =====================================================
        # FLASK SERVER
        # =====================================================

        @self.app.route("/")
        def index():

            return render_template_string(
                m.get_root().render()
            )

        # -----------------------------------------------------
        # START SERVER
        # -----------------------------------------------------

        def run_server():

            self.app.run(
                debug=False,
                use_reloader=False
            )

        threading.Thread(
            target=run_server,
            daemon=True
        ).start()

        # -----------------------------------------------------
        # OPEN BROWSER
        # -----------------------------------------------------

        webbrowser.open(
            "http://127.0.0.1:5000/"
        )


# =============================================================
# PROGRAM START
# =============================================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = FloodRiskApp()

    window.show()

    sys.exit(app.exec())