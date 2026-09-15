import sys
import os
import json
import webbrowser
import threading
import requests

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from osgeo import gdal

import numpy as np
import geopandas as gpd

import folium
from folium.features import DivIcon

from affine import Affine

from flask import Flask, render_template_string


# ============================================================
# BASE DIRECTORIES
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..")
)

DATA_DIR = os.path.join(
    PROJECT_DIR,
    "data"
)


# ============================================================
# DATA FILES
# ============================================================

ROADS_FILE = os.path.join(
    DATA_DIR,
    "PuneRoads.geojson"
)

RAILWAYS_FILE = os.path.join(
    DATA_DIR,
    "PuneRailways.geojson"
)

WATER_FILE = os.path.join(
    DATA_DIR,
    "PuneWaterBodies.geojson"
)


# ============================================================
# OVERPASS SERVERS
# ============================================================

OVERPASS_SERVERS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


# ============================================================
# INFRASTRUCTURE BOUNDING BOX
# ============================================================

# Same Pune area used for roads and railways

MIN_LAT = 18.40
MIN_LON = 73.70
MAX_LAT = 18.65
MAX_LON = 74.00


# ============================================================
# FLASK APP
# ============================================================

flask_app = Flask(__name__)


# ============================================================
# MAIN GUI CLASS
# ============================================================

class FloodRiskApp(QDialog):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Flood Risk + OSM GIS")

        self.risk_map_path = ""

        self.map_html = ""

        self.server_started = False

        # ----------------------------------------------------
        # Simple UI
        # ----------------------------------------------------

        from PySide6.QtWidgets import (
            QVBoxLayout,
            QPushButton,
            QLineEdit
        )

        layout = QVBoxLayout()

        self.file_edit = QLineEdit()

        self.file_edit.setPlaceholderText(
            "Select flood risk GeoTIFF..."
        )

        browse_button = QPushButton(
            "Browse Risk Map"
        )

        run_button = QPushButton(
            "Run Flood + OSM Analysis"
        )

        browse_button.clicked.connect(
            self.browse_file
        )

        run_button.clicked.connect(
            self.run_analysis
        )

        layout.addWidget(self.file_edit)
        layout.addWidget(browse_button)
        layout.addWidget(run_button)

        self.setLayout(layout)

    # ========================================================
    # BROWSE RASTER
    # ========================================================

    def browse_file(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Risk Map File",
            "",
            "GeoTIFF Files (*.tif *.tiff)"
        )

        if file_path:

            self.file_edit.setText(
                file_path
            )

            self.risk_map_path = file_path

            print("\nSelected risk map:")
            print(file_path)

    # ========================================================
    # FLOOD RISK CLASSIFICATION
    # ========================================================

    @staticmethod
    def classify_risk(value):

        if value is None:
            return "Unknown"

        if value == -9999:
            return "Unknown"

        if not np.isfinite(value):
            return "Unknown"

        value = float(value)

        if value < 25:
            return "Low"

        elif value < 50:
            return "Moderate"

        elif value < 75:
            return "High"

        else:
            return "Very High"

    # ========================================================
    # RISK COLOR
    # ========================================================

    @staticmethod
    def risk_color(risk):

        colors = {
            "Low": "#FFFF00",
            "Moderate": "#F5A623",
            "High": "#EF3825",
            "Very High": "#8B0000",
            "Unknown": "#808080"
        }

        return colors.get(
            risk,
            "#808080"
        )

    # ========================================================
    # GET RASTER VALUE
    # ========================================================

    @staticmethod
    def get_raster_value(
        risk_data,
        inverse_transform,
        lon,
        lat
    ):

        try:

            col, row = inverse_transform * (
                lon,
                lat
            )

            col = int(round(col))
            row = int(round(row))

            if (
                row < 0
                or row >= risk_data.shape[0]
                or col < 0
                or col >= risk_data.shape[1]
            ):

                return None

            value = risk_data[row, col]

            if value == -9999:
                return None

            if not np.isfinite(value):
                return None

            return float(value)

        except Exception:

            return None

    # ========================================================
    # LOAD GEOJSON FILE
    # ========================================================

    @staticmethod
    def load_geojson(
        filename,
        layer_name
    ):

        print("\n" + "=" * 42)
        print("LOADING", layer_name)
        print("=" * 42)

        if not os.path.exists(filename):

            print("File not found:")
            print(filename)

            return None

        try:

            gdf = gpd.read_file(
                filename
            )

            print(
                layer_name,
                "features:",
                len(gdf)
            )

            print(
                "CRS:",
                gdf.crs
            )

            return gdf

        except Exception as e:

            print(
                "Error loading",
                layer_name,
                ":",
                e
            )

            return None

    # ========================================================
    # DOWNLOAD INFRASTRUCTURE
    # ========================================================

    def download_infrastructure(
        self
    ):

        print("\n" + "=" * 42)
        print("DOWNLOADING OSM INFRASTRUCTURE")
        print("=" * 42)

        query = f"""
        [out:json][timeout:180];

        (
            nwr["amenity"="hospital"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["amenity"="police"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["amenity"="school"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["amenity"="fire_station"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["amenity"="shelter"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["amenity"="clinic"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["amenity"="pharmacy"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["highway"="bus_stop"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
            nwr["railway"="station"]({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});
        );

        out center;
        """

        headers = {
            "User-Agent":
                "FloodRiskGIS/1.0 (OSM infrastructure)",
            "Accept":
                "application/json",
            "Content-Type":
                "application/x-www-form-urlencoded"
        }

        for server in OVERPASS_SERVERS:

            print("\nTrying Overpass server:")
            print(server)

            try:

                response = requests.post(
                    server,
                    data={"data": query},
                    headers=headers,
                    timeout=180
                )

                print(
                    "Overpass HTTP Status:",
                    response.status_code
                )

                response.raise_for_status()

                data = response.json()

                print(
                    "\nOSM infrastructure downloaded successfully!"
                )

                print(
                    "Total OSM elements:",
                    len(data.get("elements", []))
                )

                return data.get(
                    "elements",
                    []
                )

            except Exception as e:

                print(
                    "\nOverpass connection error:"
                )

                print(e)

                print(
                    "Trying another Overpass server..."
                )

        print(
            "\nERROR: All Overpass servers failed."
        )

        return []

    # ========================================================
    # GET OSM ELEMENT LOCATION
    # ========================================================

    @staticmethod
    def get_element_location(
        element
    ):

        element_type = element.get(
            "type"
        )

        # Node
        if element_type == "node":

            lat = element.get("lat")
            lon = element.get("lon")

            if lat is not None and lon is not None:

                return float(lat), float(lon)

        # Way / Relation
        center = element.get(
            "center"
        )

        if center:

            lat = center.get("lat")
            lon = center.get("lon")

            if lat is not None and lon is not None:

                return float(lat), float(lon)

        return None, None

    # ========================================================
    # ADD INFRASTRUCTURE
    # ========================================================

    def add_infrastructure(
        self,
        map_object,
        elements,
        risk_data,
        inverse_transform
    ):

        print("\n" + "=" * 42)
        print("ADDING INFRASTRUCTURE TO MAP")
        print("=" * 42)

        categories = {

            "hospital": {
                "title": "Hospitals",
                "icon": "🏥"
            },

            "police": {
                "title": "Police Stations",
                "icon": "👮"
            },

            "school": {
                "title": "Schools",
                "icon": "🏫"
            },

            "fire_station": {
                "title": "Fire Stations",
                "icon": "🚒"
            },

            "shelter": {
                "title": "Emergency Shelters",
                "icon": "🏠"
            },

            "clinic": {
                "title": "Clinics",
                "icon": "⚕️"
            },

            "pharmacy": {
                "title": "Pharmacies",
                "icon": "💊"
            },

            "bus_stop": {
                "title": "Bus Stops",
                "icon": "🚌"
            },

            "station": {
                "title": "Railway Stations",
                "icon": "🚉"
            }
        }

        groups = {}

        counts = {}

        for key, info in categories.items():

            groups[key] = folium.FeatureGroup(
                name=info["icon"] + " " + info["title"]
            )

            counts[key] = 0

        # ----------------------------------------------------
        # Process every OSM element
        # ----------------------------------------------------

        for element in elements:

            tags = element.get(
                "tags",
                {}
            )

            amenity = tags.get(
                "amenity"
            )

            highway = tags.get(
                "highway"
            )

            railway = tags.get(
                "railway"
            )

            # Determine category
            category = None

            if amenity == "hospital":
                category = "hospital"

            elif amenity == "police":
                category = "police"

            elif amenity == "school":
                category = "school"

            elif amenity == "fire_station":
                category = "fire_station"

            elif amenity == "shelter":
                category = "shelter"

            elif amenity == "clinic":
                category = "clinic"

            elif amenity == "pharmacy":
                category = "pharmacy"

            elif highway == "bus_stop":
                category = "bus_stop"

            elif railway == "station":
                category = "station"

            if category is None:
                continue

            lat, lon = self.get_element_location(
                element
            )

            if lat is None or lon is None:
                continue

            # ------------------------------------------------
            # Raster risk
            # ------------------------------------------------

            risk_value = self.get_raster_value(
                risk_data,
                inverse_transform,
                lon,
                lat
            )

            risk = self.classify_risk(
                risk_value
            )

            if risk_value is not None:

                score = f"{risk_value:.2f}%"

            else:

                score = "Unavailable"

            # ------------------------------------------------
            # Basic OSM information
            # ------------------------------------------------

            name = tags.get(
                "name",
                "Unnamed " + categories[category]["title"]
            )

            phone = tags.get(
                "phone",
                tags.get(
                    "contact:phone",
                    ""
                )
            )

            website = tags.get(
                "website",
                tags.get(
                    "contact:website",
                    ""
                )
            )

            street = tags.get(
                "addr:street",
                ""
            )

            city = tags.get(
                "addr:city",
                ""
            )

            opening_hours = tags.get(
                "opening_hours",
                ""
            )

            # ------------------------------------------------
            # Popup
            # ------------------------------------------------

            popup_html = f"""
            <div style="
                width:320px;
                font-family:Arial;
                font-size:13px;
            ">

                <h3 style="
                    margin-bottom:12px;
                ">
                    {name}
                </h3>

                <b>Type:</b>
                {categories[category]["title"]}

                <br><br>

                <b>Flood Risk:</b>
                <span style="
                    color:{self.risk_color(risk)};
                    font-weight:bold;
                ">
                    {risk}
                </span>

                <br>

                <b>AHP Score:</b>
                {score}

                <br><br>
            """

            if phone:

                popup_html += f"""
                <b>Phone:</b>
                {phone}
                <br>
                """

            if website:

                popup_html += f"""
                <b>Website:</b>
                {website}
                <br>
                """

            if street:

                popup_html += f"""
                <b>Street:</b>
                {street}
                <br>
                """

            if city:

                popup_html += f"""
                <b>City:</b>
                {city}
                <br>
                """

            if opening_hours:

                popup_html += f"""
                <b>Opening Hours:</b>
                {opening_hours}
                <br>
                """

            popup_html += f"""

                <br>

                <b>Latitude:</b>
                {lat:.6f}

                <br>

                <b>Longitude:</b>
                {lon:.6f}

            </div>
            """

            popup = folium.Popup(
                popup_html,
                max_width=380
            )

            # ------------------------------------------------
            # Marker
            # ------------------------------------------------

            marker = folium.CircleMarker(

                location=[
                    lat,
                    lon
                ],

                radius=8,

                color=self.risk_color(
                    risk
                ),

                fill=True,

                fill_color=self.risk_color(
                    risk
                ),

                fill_opacity=0.9,

                weight=2,

                tooltip=(
                    f"{name} | "
                    f"{categories[category]['title']} | "
                    f"Risk: {risk}"
                ),

                popup=popup
            )

            marker.add_to(
                groups[category]
            )

            counts[category] += 1

        # ----------------------------------------------------
        # Add groups to map
        # ----------------------------------------------------

        for category in categories:

            groups[category].add_to(
                map_object
            )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print("\n" + "=" * 42)
        print("INFRASTRUCTURE SUMMARY")
        print("=" * 42)

        for category, info in categories.items():

            print(
                f"{info['title']}:",
                counts[category]
            )

    # ========================================================
    # ADD WATER BODIES
    # ========================================================

    def add_water_bodies(
        self,
        map_object,
        water_gdf,
        risk_data,
        inverse_transform
    ):

        print("\n" + "=" * 42)
        print("ADDING OSM WATER BODIES")
        print("=" * 42)

        water_group = folium.FeatureGroup(
            name="🌊 OSM Water Bodies"
        )

        if water_gdf is None:

            print(
                "Water body file not available."
            )

            water_group.add_to(
                map_object
            )

            return

        if len(water_gdf) == 0:

            print(
                "No water bodies found."
            )

            water_group.add_to(
                map_object
            )

            return

        count = 0

        for _, row in water_gdf.iterrows():

            geometry = row.geometry

            if geometry is None:
                continue

            if geometry.is_empty:
                continue

            # ------------------------------------------------
            # Determine representative point
            # ------------------------------------------------

            try:

                point = geometry.representative_point()

                lon = float(point.x)
                lat = float(point.y)

            except Exception:

                continue

            # ------------------------------------------------
            # Risk lookup
            # ------------------------------------------------

            risk_value = self.get_raster_value(
                risk_data,
                inverse_transform,
                lon,
                lat
            )

            risk = self.classify_risk(
                risk_value
            )

            if risk_value is not None:

                score = f"{risk_value:.2f}%"

            else:

                score = "Unavailable"

            # ------------------------------------------------
            # Water body information
            # ------------------------------------------------

            name = row.get(
                "name",
                ""
            )

            if not name or str(name) == "nan":

                name = "Unnamed Water Body"

            water_type = row.get(
                "water",
                ""
            )

            natural_type = row.get(
                "natural",
                ""
            )

            landuse = row.get(
                "landuse",
                ""
            )

            man_made = row.get(
                "man_made",
                ""
            )

            operator = row.get(
                "operator",
                ""
            )

            # ------------------------------------------------
            # Determine display type
            # ------------------------------------------------

            display_type = "Water Body"

            if water_type:

                display_type = str(
                    water_type
                ).replace(
                    "_",
                    " "
                ).title()

            elif natural_type:

                display_type = str(
                    natural_type
                ).replace(
                    "_",
                    " "
                ).title()

            elif landuse:

                display_type = str(
                    landuse
                ).replace(
                    "_",
                    " "
                ).title()

            # ------------------------------------------------
            # Popup
            # ------------------------------------------------

            popup_html = f"""
            <div style="
                width:330px;
                font-family:Arial;
                font-size:13px;
            ">

                <h3 style="
                    margin-bottom:12px;
                ">
                    🌊 {name}
                </h3>

                <b>Type:</b>
                {display_type}

                <br><br>

                <b>Flood Risk:</b>
                <span style="
                    color:{self.risk_color(risk)};
                    font-weight:bold;
                ">
                    {risk}
                </span>

                <br>

                <b>AHP Score:</b>
                {score}

                <br><br>
            """

            if operator:

                popup_html += f"""
                <b>Operator:</b>
                {operator}
                <br>
                """

            if man_made:

                popup_html += f"""
                <b>Man Made:</b>
                {man_made}
                <br>
                """

            popup_html += f"""

                <br>

                <b>Latitude:</b>
                {lat:.6f}

                <br>

                <b>Longitude:</b>
                {lon:.6f}

            </div>
            """

            popup = folium.Popup(
                popup_html,
                max_width=390
            )

            tooltip_text = (
                f"🌊 {name} | "
                f"{display_type} | "
                f"Risk: {risk}"
            )

            # ------------------------------------------------
            # Water body polygon
            # ------------------------------------------------

            folium.GeoJson(
                geometry.__geo_interface__,
                style_function=lambda feature: {
                    "color": "#0066CC",
                    "weight": 2,
                    "fillColor": "#00BFFF",
                    "fillOpacity": 0.45
                },
                highlight_function=lambda feature: {
                    "weight": 4,
                    "fillOpacity": 0.65
                },
                tooltip=tooltip_text,
                popup=popup
            ).add_to(
                water_group
            )

            count += 1

        water_group.add_to(
            map_object
        )

        print(
            "Water bodies displayed:",
            count
        )

    # ========================================================
    # MAIN ANALYSIS
    # ========================================================

    def run_analysis(self):

        if not self.risk_map_path:

            print(
                "\nPlease select a flood risk file first."
            )

            return

        print("\n" + "=" * 42)
        print("STARTING FLOOD + OSM ANALYSIS")
        print("=" * 42)

        # ====================================================
        # OPEN RASTER
        # ====================================================

        print("\nOpening flood risk raster...")

        dataset = gdal.Open(
            self.risk_map_path
        )

        if dataset is None:

            print(
                "Cannot open risk map:"
            )

            print(
                self.risk_map_path
            )

            return

        band = dataset.GetRasterBand(
            1
        )

        risk_data = band.ReadAsArray().astype(
            np.float32
        )

        transform = dataset.GetGeoTransform()

        projection = dataset.GetProjection()

        affine_transform = Affine.from_gdal(
            *transform
        )

        inverse_transform = (
            ~affine_transform
        )

        rows, cols = risk_data.shape

        min_x = transform[0]
        pixel_width = transform[1]

        max_y = transform[3]
        pixel_height = transform[5]

        max_x = (
            min_x
            + cols * pixel_width
        )

        min_y = (
            max_y
            + rows * pixel_height
        )

        print(
            "Raster size:",
            risk_data.shape
        )

        print(
            "Raster CRS:",
            projection
        )

        print(
            "Map center:",
            (min_y + max_y) / 2,
            (min_x + max_x) / 2
        )

        print(
            "Map extent:",
            min_y,
            min_x,
            max_y,
            max_x
        )

        dataset = None

        # ====================================================
        # CREATE FLOOD IMAGE
        # ====================================================

        print(
            "\nCreating flood risk image..."
        )

        png_path = os.path.join(
            PROJECT_DIR,
            "combined_risk_output.png"
        )

        # ----------------------------------------------------
        # Convert percentage raster to display categories
        # ----------------------------------------------------

        display_data = np.zeros_like(
            risk_data,
            dtype=np.uint8
        )

        valid = (
            risk_data != -9999
        ) & np.isfinite(
            risk_data
        )

        display_data[
            valid & (risk_data < 25)
        ] = 1

        display_data[
            valid
            & (risk_data >= 25)
            & (risk_data < 50)
        ] = 2

        display_data[
            valid
            & (risk_data >= 50)
            & (risk_data < 75)
        ] = 3

        display_data[
            valid
            & (risk_data >= 75)
        ] = 4

        from matplotlib.colors import ListedColormap

        import matplotlib.pyplot as plt

        cmap = ListedColormap([
            "white",
            "#FFFF00",
            "#F5A623",
            "#EF3825",
            "#8B0000"
        ])

        plt.imsave(
            png_path,
            display_data,
            cmap=cmap,
            vmin=0,
            vmax=4
        )

        # ====================================================
        # CREATE MAP
        # ====================================================

        center_lat = (
            min_y + max_y
        ) / 2

        center_lon = (
            min_x + max_x
        ) / 2

        map_object = folium.Map(

            location=[
                center_lat,
                center_lon
            ],

            zoom_start=10,

            control_scale=True
        )

        # ====================================================
        # FLOOD RISK OVERLAY
        # ====================================================

        image_bounds = [
            [min_y, min_x],
            [max_y, max_x]
        ]

        folium.raster_layers.ImageOverlay(

            name="🌊 Flood Risk Map",

            image=png_path,

            bounds=image_bounds,

            opacity=0.55,

            interactive=True,

            cross_origin=False,

            zindex=1

        ).add_to(
            map_object
        )

        # ====================================================
        # ROAD NETWORK
        # ====================================================

        roads = self.load_geojson(
            ROADS_FILE,
            "OSM ROAD NETWORK"
        )

        if roads is not None:

            road_group = folium.FeatureGroup(
                name="🚗 OSM Road Network"
            )

            folium.GeoJson(

                roads.to_json(),

                style_function=lambda feature: {
                    "color": "#0066FF",
                    "weight": 2,
                    "opacity": 0.8
                },

                tooltip=folium.GeoJsonTooltip(
                    fields=[
                        "highway",
                        "name",
                        "ref",
                        "surface",
                        "lanes",
                        "maxspeed"
                    ],
                    aliases=[
                        "Road Type",
                        "Name",
                        "Reference",
                        "Surface",
                        "Lanes",
                        "Max Speed"
                    ],
                    localize=True,
                    sticky=False
                )

            ).add_to(
                road_group
            )

            road_group.add_to(
                map_object
            )

        # ====================================================
        # RAILWAY NETWORK
        # ====================================================

        railways = self.load_geojson(
            RAILWAYS_FILE,
            "OSM RAILWAY NETWORK"
        )

        if railways is not None:

            railway_group = folium.FeatureGroup(
                name="🚆 OSM Railway Network"
            )

            folium.GeoJson(

                railways.to_json(),

                style_function=lambda feature: {
                    "color": "#8B0000",
                    "weight": 4,
                    "opacity": 0.9
                },

                tooltip=folium.GeoJsonTooltip(
                    fields=[
                        "railway",
                        "name",
                        "ref",
                        "operator",
                        "usage",
                        "electrified"
                    ],
                    aliases=[
                        "Railway Type",
                        "Name",
                        "Reference",
                        "Operator",
                        "Usage",
                        "Electrified"
                    ],
                    localize=True,
                    sticky=False
                )

            ).add_to(
                railway_group
            )

            railway_group.add_to(
                map_object
            )

        # ====================================================
        # WATER BODIES
        # ====================================================

        water_bodies = self.load_geojson(
            WATER_FILE,
            "OSM WATER BODIES"
        )

        self.add_water_bodies(
            map_object,
            water_bodies,
            risk_data,
            inverse_transform
        )

        # ====================================================
        # INFRASTRUCTURE
        # ====================================================

        infrastructure = (
            self.download_infrastructure()
        )

        self.add_infrastructure(
            map_object,
            infrastructure,
            risk_data,
            inverse_transform
        )

        # ====================================================
        # FLOOD RISK LEGEND
        # ====================================================

        legend_html = """

        <div style="
            position: fixed;
            bottom: 40px;
            left: 40px;
            z-index: 9999;
            background-color: white;
            border: 2px solid grey;
            border-radius: 8px;
            padding: 15px;
            font-size: 14px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
        ">

        <h3 style="margin-top:0;">
            Flood Risk
        </h3>

        <div>
            <span style="
                display:inline-block;
                width:22px;
                height:22px;
                background:#FFFF00;
                margin-right:10px;
            "></span>
            Low (&lt;25%)
        </div>

        <br>

        <div>
            <span style="
                display:inline-block;
                width:22px;
                height:22px;
                background:#F5A623;
                margin-right:10px;
            "></span>
            Moderate (25–50%)
        </div>

        <br>

        <div>
            <span style="
                display:inline-block;
                width:22px;
                height:22px;
                background:#EF3825;
                margin-right:10px;
            "></span>
            High (50–75%)
        </div>

        <br>

        <div>
            <span style="
                display:inline-block;
                width:22px;
                height:22px;
                background:#8B0000;
                margin-right:10px;
            "></span>
            Very High (≥75%)
        </div>

        </div>

        """

        map_object.get_root().html.add_child(
            folium.Element(
                legend_html
            )
        )

        # ====================================================
        # LAYER CONTROL
        # ====================================================

        folium.LayerControl(
            collapsed=False
        ).add_to(
            map_object
        )

        # ====================================================
        # SAVE MAP
        # ====================================================

        output_map = os.path.join(
            PROJECT_DIR,
            "Flood_OSM_Map.html"
        )

        map_object.save(
            output_map
        )

        print("\n" + "=" * 42)

        print(
            "Map saved to:"
        )

        print(
            output_map
        )

        print("=" * 42)

        self.map_html = map_object.get_root().render()

        # ====================================================
        # START FLASK
        # ====================================================

        if not self.server_started:

            self.server_started = True

            def run_server():

                flask_app.run(
                    host="127.0.0.1",
                    port=5000,
                    debug=False,
                    use_reloader=False
                )

            threading.Thread(
                target=run_server,
                daemon=True
            ).start()

        print("\n" + "=" * 42)

        print("MAP READY!")

        print("=" * 42)

        print(
            "\nOpen in browser:"
        )

        print(
            "http://127.0.0.1:5000/"
        )

        webbrowser.open(
            "http://127.0.0.1:5000/"
        )


# ============================================================
# FLASK ROUTE
# ============================================================

@flask_app.route("/")
def index():

    # Find the active dialog
    for widget in QApplication.topLevelWidgets():

        if isinstance(
            widget,
            FloodRiskApp
        ):

            if widget.map_html:

                return render_template_string(
                    widget.map_html
                )

    return """
    <h2>
        Map is not ready.
    </h2>

    <p>
        Run the analysis from the GUI.
    </p>
    """


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    qt_app = QApplication(
        sys.argv
    )

    window = FloodRiskApp()

    window.resize(
        500,
        180
    )

    window.show()

    sys.exit(
        qt_app.exec()
    )