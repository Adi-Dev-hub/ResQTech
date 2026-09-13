import sys
import os
import threading
import webbrowser
import time
import html

import requests
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from osgeo import gdal
from affine import Affine

import folium
from folium.plugins import Fullscreen

from flask import Flask, Response

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog
)

from Osm_ui import Ui_Dialog


# ============================================================
# PATH SETTINGS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

ROADS_FILE = os.path.join(
    DATA_DIR,
    "PuneRoads.geojson"
)

RAILWAYS_FILE = os.path.join(
    DATA_DIR,
    "PuneRailways.geojson"
)


# ============================================================
# OSM / OVERPASS SETTINGS
# ============================================================

# Same Pune area used for the downloaded
# OSM road and railway datasets.

MIN_LAT = 18.40
MIN_LON = 73.70
MAX_LAT = 18.65
MAX_LON = 74.00


# Primary + backup Overpass servers

OVERPASS_URLS = [

    "https://overpass.private.coffee/api/interpreter",

    "https://overpass-api.de/api/interpreter"

]


# Proper headers help avoid HTTP 406 errors.

HEADERS = {

    "User-Agent":
        "FloodRiskGIS/1.0 "
        "(OpenStreetMap flood-risk visualization project)",

    "Accept":
        "application/json",

    "Content-Type":
        "application/x-www-form-urlencoded"

}


# ============================================================
# FLOOD RISK CLASSIFICATION
# ============================================================

# The AHP raster contains continuous values.
#
# Example:
#
# 18.17 = 18.17%
# 58.72 = 58.72%
# 96.20 = 96.20%
#
# We convert those continuous values into four
# visualization classes.

LOW_LIMIT = 25.0
MODERATE_LIMIT = 50.0
HIGH_LIMIT = 75.0


# ============================================================
# MAIN APPLICATION
# ============================================================

class FloodRiskApp(QDialog):

    def __init__(self):

        super().__init__()

        self.ui = Ui_Dialog()

        self.ui.setupUi(self)

        # ----------------------------------------------------
        # Connect buttons
        # ----------------------------------------------------

        self.ui.toolButton.clicked.connect(
            self.browse_file
        )

        self.ui.pushButton.clicked.connect(
            self.run_analysis
        )

        # ----------------------------------------------------
        # Variables
        # ----------------------------------------------------

        self.risk_map_path = ""

        self.app = Flask(__name__)

        self.map_html = ""

        self.server_started = False

        # ----------------------------------------------------
        # Flask route
        # ----------------------------------------------------

        @self.app.route("/")
        def index():

            if self.map_html:

                return Response(
                    self.map_html,
                    mimetype="text/html"
                )

            return Response(
                "<h2>Flood Risk Map is not ready yet.</h2>",
                mimetype="text/html"
            )


    # ========================================================
    # FILE BROWSER
    # ========================================================

    def browse_file(self):

        file_path, _ = QFileDialog.getOpenFileName(

            self,

            "Select Flood Risk Map",

            "",

            "GeoTIFF Files (*.tif *.tiff)"

        )

        if file_path:

            self.ui.lineEdit.setText(
                file_path
            )

            self.risk_map_path = file_path

            print()
            print("Selected risk map:")
            print(file_path)


    # ========================================================
    # CONVERT RASTER VALUE TO FLOOD RISK
    # ========================================================

    def classify_risk(self, value):

        # ----------------------------------------------------
        # NoData
        # ----------------------------------------------------

        if value is None:

            return {
                "class": "Unknown",
                "percentage": None,
                "color": "gray"
            }


        try:

            value = float(value)

        except:

            return {
                "class": "Unknown",
                "percentage": None,
                "color": "gray"
            }


        # ----------------------------------------------------
        # NoData value from raster
        # ----------------------------------------------------

        if (
            not np.isfinite(value)
            or value <= -9990
        ):

            return {
                "class": "Unknown",
                "percentage": None,
                "color": "gray"
            }


        # ----------------------------------------------------
        # AHP values are already percentages
        #
        # Example:
        # 18.17 -> 18.17%
        # 58.72 -> 58.72%
        # 96.20 -> 96.20%
        # ----------------------------------------------------

        percentage = value


        # ----------------------------------------------------
        # Classification
        # ----------------------------------------------------

        if percentage < LOW_LIMIT:

            risk_class = "Low"

            color = "yellow"


        elif percentage < MODERATE_LIMIT:

            risk_class = "Moderate"

            color = "orange"


        elif percentage < HIGH_LIMIT:

            risk_class = "High"

            color = "red"


        else:

            risk_class = "Very High"

            color = "darkred"


        return {

            "class": risk_class,

            "percentage": percentage,

            "color": color

        }


    # ========================================================
    # GET RASTER VALUE AT LAT/LON
    # ========================================================

    def get_raster_value(
        self,
        risk_data,
        inverse_transform,
        lon,
        lat
    ):

        try:

            # ------------------------------------------------
            # Convert geographic coordinate to pixel
            # ------------------------------------------------

            col, row = inverse_transform * (
                lon,
                lat
            )


            # ------------------------------------------------
            # Use floor instead of round
            # to select the containing raster cell.
            # ------------------------------------------------

            col = int(
                np.floor(col)
            )

            row = int(
                np.floor(row)
            )


            # ------------------------------------------------
            # Check raster boundaries
            # ------------------------------------------------

            if (

                row < 0

                or row >= risk_data.shape[0]

                or col < 0

                or col >= risk_data.shape[1]

            ):

                return None


            value = risk_data[
                row,
                col
            ]


            # ------------------------------------------------
            # NoData
            # ------------------------------------------------

            if not np.isfinite(value):

                return None


            if value <= -9990:

                return None


            return float(value)


        except Exception:

            return None


    # ========================================================
    # DOWNLOAD OSM INFRASTRUCTURE
    # ========================================================

    def download_infrastructure(self):

        print()
        print("==========================================")
        print("DOWNLOADING OSM INFRASTRUCTURE")
        print("==========================================")


        # ----------------------------------------------------
        # Combined Overpass query
        #
        # nwr = nodes + ways + relations
        #
        # out center tags gives coordinates for
        # ways/relations and tags for all objects.
        # ----------------------------------------------------

        query = f"""

[out:json][timeout:180];

(

    nwr["amenity"="hospital"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["amenity"="police"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["amenity"="school"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["amenity"="fire_station"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["amenity"="shelter"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["amenity"="clinic"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["amenity"="pharmacy"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["highway"="bus_stop"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

    nwr["railway"="station"]
    ({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON});

);

out center tags;

"""


        # ----------------------------------------------------
        # Try servers
        # ----------------------------------------------------

        for overpass_url in OVERPASS_URLS:

            print()
            print("Trying Overpass server:")
            print(overpass_url)

            try:

                response = requests.post(

                    overpass_url,

                    data={
                        "data": query
                    },

                    headers=HEADERS,

                    timeout=180

                )


                print(
                    "Overpass HTTP Status:",
                    response.status_code
                )


                # ------------------------------------------------
                # Successful response
                # ------------------------------------------------

                if response.status_code == 200:

                    data = response.json()


                    print()
                    print(
                        "OSM infrastructure downloaded successfully!"
                    )


                    print(
                        "Total OSM elements:",
                        len(
                            data.get(
                                "elements",
                                []
                            )
                        )
                    )


                    return data


                # ------------------------------------------------
                # Server error
                # ------------------------------------------------

                print(
                    "Server returned:",
                    response.status_code
                )


                print(
                    "Trying another Overpass server..."
                )


            except requests.exceptions.RequestException as e:

                print()
                print(
                    "Overpass connection error:"
                )

                print(e)

                print(
                    "Trying another Overpass server..."
                )


        # ----------------------------------------------------
        # All servers failed
        # ----------------------------------------------------

        print()
        print(
            "ERROR: All Overpass servers failed."
        )


        return None


    # ========================================================
    # GET LOCATION OF OSM ELEMENT
    # ========================================================

    def get_element_location(
        self,
        element
    ):

        # ----------------------------------------------------
        # Node
        # ----------------------------------------------------

        if element.get("type") == "node":

            lat = element.get("lat")

            lon = element.get("lon")


            if (

                lat is not None

                and lon is not None

            ):

                return (
                    float(lat),
                    float(lon)
                )


        # ----------------------------------------------------
        # Way / Relation
        # ----------------------------------------------------

        center = element.get(
            "center"
        )


        if center:

            lat = center.get(
                "lat"
            )

            lon = center.get(
                "lon"
            )


            if (

                lat is not None

                and lon is not None

            ):

                return (
                    float(lat),
                    float(lon)
                )


        return None


    # ========================================================
    # IDENTIFY INFRASTRUCTURE TYPE
    # ========================================================

    def get_infrastructure_type(
        self,
        tags
    ):

        amenity = tags.get(
            "amenity"
        )


        if amenity == "hospital":

            return "Hospital"


        if amenity == "police":

            return "Police Station"


        if amenity == "school":

            return "School"


        if amenity == "fire_station":

            return "Fire Station"


        if amenity == "shelter":

            return "Emergency Shelter"


        if amenity == "clinic":

            return "Clinic"


        if amenity == "pharmacy":

            return "Pharmacy"


        if tags.get(
            "highway"
        ) == "bus_stop":

            return "Bus Stop"


        if tags.get(
            "railway"
        ) == "station":

            return "Railway Station"


        return "Infrastructure"


    # ========================================================
    # CREATE POPUP
    # ========================================================

    def create_popup_html(

        self,

        name,

        infrastructure_type,

        tags,

        risk_info,

        lat,

        lon

    ):

        # ----------------------------------------------------
        # Safely escape OSM text before putting it into HTML
        # ----------------------------------------------------

        safe_name = html.escape(
            str(name)
        )


        safe_type = html.escape(
            str(infrastructure_type)
        )


        # ----------------------------------------------------
        # Flood risk
        # ----------------------------------------------------

        if risk_info["percentage"] is None:

            flood_risk_text = (
                "Unknown"
            )

            percentage_text = (
                "Not available"
            )

        else:

            flood_risk_text = (
                risk_info["class"]
            )

            percentage_text = (
                f"{risk_info['percentage']:.2f}%"
            )


        # ----------------------------------------------------
        # Popup HTML
        # ----------------------------------------------------

        popup_html = f"""

        <div style="
            font-family: Arial, sans-serif;
            width: 280px;
            line-height: 1.5;
        ">

            <h3 style="
                margin-top: 0;
                margin-bottom: 10px;
            ">
                {safe_name}
            </h3>


            <b>Type:</b>
            {safe_type}
            <br><br>


            <b>Flood Risk:</b>
            {flood_risk_text}
            <br>


            <b>AHP Score:</b>
            {percentage_text}
            <br><br>

        """


        # ----------------------------------------------------
        # Additional OSM information
        # ----------------------------------------------------

        additional_fields = [

            (
                "Operator",
                tags.get("operator")
            ),

            (
                "Phone",
                tags.get("phone")
            ),

            (
                "Website",
                tags.get("website")
            ),

            (
                "Street",
                tags.get("addr:street")
            ),

            (
                "City",
                tags.get("addr:city")
            ),

            (
                "Opening Hours",
                tags.get("opening_hours")
            )

        ]


        for label, value in additional_fields:

            if value:

                safe_value = html.escape(
                    str(value)
                )

                popup_html += f"""

                <b>{label}:</b>
                {safe_value}
                <br>

                """


        # ----------------------------------------------------
        # Coordinates
        # ----------------------------------------------------

        popup_html += f"""

            <br>

            <b>Latitude:</b>
            {lat:.6f}
            <br>

            <b>Longitude:</b>
            {lon:.6f}

        </div>

        """


        return popup_html


    # ========================================================
    # CREATE FEATURE GROUPS
    # ========================================================

    def create_feature_groups(self):

        return {

            "Hospital":
                folium.FeatureGroup(
                    name="🏥 Hospitals",
                    show=True
                ),

            "Police Station":
                folium.FeatureGroup(
                    name="🚓 Police Stations",
                    show=False
                ),

            "School":
                folium.FeatureGroup(
                    name="🏫 Schools",
                    show=False
                ),

            "Fire Station":
                folium.FeatureGroup(
                    name="🚒 Fire Stations",
                    show=False
                ),

            "Emergency Shelter":
                folium.FeatureGroup(
                    name="🏠 Emergency Shelters",
                    show=False
                ),

            "Clinic":
                folium.FeatureGroup(
                    name="⚕️ Clinics",
                    show=False
                ),

            "Pharmacy":
                folium.FeatureGroup(
                    name="💊 Pharmacies",
                    show=False
                ),

            "Bus Stop":
                folium.FeatureGroup(
                    name="🚌 Bus Stops",
                    show=False
                ),

            "Railway Station":
                folium.FeatureGroup(
                    name="🚉 Railway Stations",
                    show=False
                )

        }


    # ========================================================
    # ADD INFRASTRUCTURE
    # ========================================================

    def add_infrastructure(

        self,

        m,

        infrastructure_data,

        risk_data,

        inverse_transform

    ):

        print()
        print("==========================================")
        print("ADDING INFRASTRUCTURE TO MAP")
        print("==========================================")


        groups = (
            self.create_feature_groups()
        )


        # ----------------------------------------------------
        # Counters
        # ----------------------------------------------------

        counts = {

            "Hospital": 0,

            "Police Station": 0,

            "School": 0,

            "Fire Station": 0,

            "Emergency Shelter": 0,

            "Clinic": 0,

            "Pharmacy": 0,

            "Bus Stop": 0,

            "Railway Station": 0

        }


        # ----------------------------------------------------
        # Risk counters
        # ----------------------------------------------------

        risk_counts = {

            "Low": 0,

            "Moderate": 0,

            "High": 0,

            "Very High": 0,

            "Unknown": 0

        }


        # ----------------------------------------------------
        # Process OSM elements
        # ----------------------------------------------------

        for element in infrastructure_data.get(
            "elements",
            []
        ):

            tags = element.get(
                "tags",
                {}
            )


            location = (
                self.get_element_location(
                    element
                )
            )


            if location is None:

                continue


            lat, lon = location


            # ------------------------------------------------
            # Infrastructure type
            # ------------------------------------------------

            infrastructure_type = (

                self.get_infrastructure_type(
                    tags
                )

            )


            if infrastructure_type not in groups:

                continue


            # ------------------------------------------------
            # Get actual continuous AHP score
            # ------------------------------------------------

            raster_value = (

                self.get_raster_value(

                    risk_data,

                    inverse_transform,

                    lon,

                    lat

                )

            )


            # ------------------------------------------------
            # Convert score to risk class
            # ------------------------------------------------

            risk_info = (

                self.classify_risk(
                    raster_value
                )

            )


            risk_counts[
                risk_info["class"]
            ] += 1


            # ------------------------------------------------
            # Name
            # ------------------------------------------------

            name = tags.get(
                "name",
                infrastructure_type
            )


            # ------------------------------------------------
            # Popup
            # ------------------------------------------------

            popup_html = (

                self.create_popup_html(

                    name,

                    infrastructure_type,

                    tags,

                    risk_info,

                    lat,

                    lon

                )

            )


            popup = folium.Popup(

                popup_html,

                max_width=380

            )


            # ------------------------------------------------
            # Tooltip
            # ------------------------------------------------

            tooltip = folium.Tooltip(

                f"{name} | "
                f"{infrastructure_type} | "
                f"Risk: {risk_info['class']}"

            )


            # ------------------------------------------------
            # Marker color
            #
            # Use flood-risk color for ALL infrastructure
            # so the map visually shows which facilities are
            # located in higher-risk areas.
            # ------------------------------------------------

            marker_color = (
                risk_info["color"]
            )


            # ------------------------------------------------
            # Circle marker
            # ------------------------------------------------

            marker = folium.CircleMarker(

                location=[
                    lat,
                    lon
                ],

                radius=7,

                color=marker_color,

                fill=True,

                fill_color=marker_color,

                fill_opacity=0.90,

                weight=2,

                popup=popup,

                tooltip=tooltip

            )


            marker.add_to(
                groups[
                    infrastructure_type
                ]
            )


            counts[
                infrastructure_type
            ] += 1


        # ----------------------------------------------------
        # Add groups to map
        # ----------------------------------------------------

        for group in groups.values():

            group.add_to(m)


        # ----------------------------------------------------
        # Print summary
        # ----------------------------------------------------

        print()
        print("==========================================")
        print("INFRASTRUCTURE SUMMARY")
        print("==========================================")


        print(
            "Hospitals:",
            counts["Hospital"]
        )


        print(
            "Police Stations:",
            counts["Police Station"]
        )


        print(
            "Schools:",
            counts["School"]
        )


        print(
            "Fire Stations:",
            counts["Fire Station"]
        )


        print(
            "Emergency Shelters:",
            counts["Emergency Shelter"]
        )


        print(
            "Clinics:",
            counts["Clinic"]
        )


        print(
            "Pharmacies:",
            counts["Pharmacy"]
        )


        print(
            "Bus Stops:",
            counts["Bus Stop"]
        )


        print(
            "Railway Stations:",
            counts["Railway Station"]
        )


        # ----------------------------------------------------
        # Risk summary
        # ----------------------------------------------------

        print()
        print("==========================================")
        print("INFRASTRUCTURE FLOOD-RISK SUMMARY")
        print("==========================================")


        print(
            "Low:",
            risk_counts["Low"]
        )


        print(
            "Moderate:",
            risk_counts["Moderate"]
        )


        print(
            "High:",
            risk_counts["High"]
        )


        print(
            "Very High:",
            risk_counts["Very High"]
        )


        print(
            "Unknown:",
            risk_counts["Unknown"]
        )


    # ========================================================
    # RUN ANALYSIS
    # ========================================================

    def run_analysis(self):

        print()
        print("==========================================")
        print("STARTING FLOOD + OSM ANALYSIS")
        print("==========================================")


        # ====================================================
        # CHECK FLOOD FILE
        # ====================================================

        if not self.risk_map_path:

            print()
            print(
                "ERROR:"
            )

            print(
                "Please select a flood risk GeoTIFF first!"
            )

            return


        # ====================================================
        # OPEN FLOOD RASTER
        # ====================================================

        print()
        print(
            "Opening flood risk raster..."
        )


        dataset = gdal.Open(
            self.risk_map_path
        )


        if dataset is None:

            print()
            print(
                "ERROR: Cannot open raster:"
            )

            print(
                self.risk_map_path
            )

            return


        # ====================================================
        # READ RASTER AS FLOAT
        # ====================================================

        # IMPORTANT:
        #
        # DO NOT use uint8 here.
        #
        # Your AHP raster contains values such as:
        #
        # 18.174047
        # 58.72
        # 96.19677
        #
        # Therefore we must keep float32 precision.

        band = dataset.GetRasterBand(1)


        risk_data = band.ReadAsArray().astype(
            np.float32
        )


        # ====================================================
        # GET NODATA VALUE
        # ====================================================

        nodata_value = (
            band.GetNoDataValue()
        )


        if nodata_value is not None:

            print(
                "Raster NoData value:",
                nodata_value
            )


        # ====================================================
        # RASTER INFORMATION
        # ====================================================

        transform = (
            dataset.GetGeoTransform()
        )


        projection = (
            dataset.GetProjection()
        )


        print()
        print(
            "Raster size:",
            risk_data.shape
        )


        print()
        print(
            "Raster CRS:",
            projection
        )


        # ====================================================
        # AFFINE TRANSFORM
        # ====================================================

        affine_transform = (
            Affine.from_gdal(
                *transform
            )
        )


        inverse_transform = (
            ~affine_transform
        )


        # ====================================================
        # RASTER EXTENT
        # ====================================================

        min_x = transform[0]

        pixel_width = transform[1]

        max_y = transform[3]

        pixel_height = transform[5]


        rows, cols = (
            risk_data.shape
        )


        max_x = (
            min_x
            +
            cols * pixel_width
        )


        min_y = (
            max_y
            +
            rows * pixel_height
        )


        center_lat = (
            min_y + max_y
        ) / 2


        center_lon = (
            min_x + max_x
        ) / 2


        print()
        print(
            "Map center:",
            center_lat,
            center_lon
        )


        print()
        print(
            "Map extent:",
            min_y,
            min_x,
            max_y,
            max_x
        )


        # ====================================================
        # RASTER STATISTICS
        # ====================================================

        valid_mask = (

            np.isfinite(risk_data)

            &

            (risk_data > -9990)

        )


        if np.any(valid_mask):

            valid_values = (
                risk_data[
                    valid_mask
                ]
            )


            print()
            print(
                "Flood risk raster statistics:"
            )


            print(
                "Minimum:",
                float(
                    np.min(
                        valid_values
                    )
                )
            )


            print(
                "Maximum:",
                float(
                    np.max(
                        valid_values
                    )
                )
            )


            print(
                "Mean:",
                float(
                    np.mean(
                        valid_values
                    )
                )
            )


        dataset = None


        # ====================================================
        # CREATE FLOOD IMAGE
        # ====================================================

        print()
        print(
            "Creating flood risk image..."
        )


        png_path = os.path.join(

            BASE_DIR,

            "combined_risk_output.png"

        )


        # ----------------------------------------------------
        # Make a classified image.
        #
        # 0 = NoData
        # 1 = Low
        # 2 = Moderate
        # 3 = High
        # 4 = Very High
        # ----------------------------------------------------

        classified_risk = np.zeros(
            risk_data.shape,
            dtype=np.uint8
        )


        classified_risk[
            (
                valid_mask
                &
                (risk_data < LOW_LIMIT)
            )
        ] = 1


        classified_risk[
            (
                valid_mask
                &
                (risk_data >= LOW_LIMIT)
                &
                (risk_data < MODERATE_LIMIT)
            )
        ] = 2


        classified_risk[
            (
                valid_mask
                &
                (risk_data >= MODERATE_LIMIT)
                &
                (risk_data < HIGH_LIMIT)
            )
        ] = 3


        classified_risk[
            (
                valid_mask
                &
                (risk_data >= HIGH_LIMIT)
            )
        ] = 4


        # ----------------------------------------------------
        # Correct four-class color map
        # ----------------------------------------------------

        cmap = ListedColormap(

            [
                "white",
                "yellow",
                "orange",
                "red",
                "darkred"
            ]

        )


        plt.imsave(

            png_path,

            classified_risk,

            cmap=cmap,

            vmin=0,

            vmax=4

        )


        # ====================================================
        # CREATE FOLIUM MAP
        # ====================================================

        m = folium.Map(

            location=[
                center_lat,
                center_lon
            ],

            zoom_start=10,

            control_scale=True

        )


        # ====================================================
        # FULL SCREEN
        # ====================================================

        Fullscreen(

            position="topright",

            title="Full Screen",

            title_cancel="Exit Full Screen",

            force_separate_button=True

        ).add_to(m)


        # ====================================================
        # FLOOD RISK LAYER
        # ====================================================

        flood_layer = folium.FeatureGroup(

            name="🌊 Flood Risk Map",

            show=True

        )


        image_bounds = [

            [
                min_y,
                min_x
            ],

            [
                max_y,
                max_x
            ]

        ]


        folium.raster_layers.ImageOverlay(

            image=png_path,

            bounds=image_bounds,

            opacity=0.60,

            interactive=True,

            cross_origin=False,

            zindex=1

        ).add_to(
            flood_layer
        )


        flood_layer.add_to(m)


        # ====================================================
        # FLOOD LEGEND
        # ====================================================

        legend_html = """

        <div style="
            position: fixed;
            bottom: 30px;
            left: 30px;
            width: 190px;
            z-index: 9999;
            background-color: white;
            border: 2px solid grey;
            border-radius: 8px;
            padding: 12px;
            font-size: 13px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        ">

        <b style="font-size:16px;">
            Flood Risk
        </b>

        <br><br>


        <span style="
            display:inline-block;
            width:18px;
            height:18px;
            background:yellow;
            margin-right:6px;
            border:1px solid #777;
        "></span>

        Low (&lt;25%)
        <br><br>


        <span style="
            display:inline-block;
            width:18px;
            height:18px;
            background:orange;
            margin-right:6px;
            border:1px solid #777;
        "></span>

        Moderate (25–50%)
        <br><br>


        <span style="
            display:inline-block;
            width:18px;
            height:18px;
            background:red;
            margin-right:6px;
            border:1px solid #777;
        "></span>

        High (50–75%)
        <br><br>


        <span style="
            display:inline-block;
            width:18px;
            height:18px;
            background:darkred;
            margin-right:6px;
            border:1px solid #777;
        "></span>

        Very High (&ge;75%)

        </div>

        """


        m.get_root().html.add_child(

            folium.Element(
                legend_html
            )

        )


        # ====================================================
        # LOAD OSM ROADS
        # ====================================================

        print()
        print("==========================================")
        print(
            "LOADING OSM ROAD NETWORK"
        )
        print("==========================================")


        if os.path.exists(
            ROADS_FILE
        ):

            try:

                roads = gpd.read_file(
                    ROADS_FILE
                )


                print(
                    "Road features:",
                    len(roads)
                )


                roads_layer = (
                    folium.FeatureGroup(

                        name="🚗 OSM Road Network",

                        show=False

                    )
                )


                # ------------------------------------------------
                # Only use fields that actually exist
                # ------------------------------------------------

                possible_fields = [

                    "highway",
                    "name",
                    "ref",
                    "surface",
                    "lanes",
                    "maxspeed"

                ]


                road_fields = [

                    field

                    for field in possible_fields

                    if field in roads.columns

                ]


                road_aliases = {

                    "highway":
                        "Road Type",

                    "name":
                        "Name",

                    "ref":
                        "Reference",

                    "surface":
                        "Surface",

                    "lanes":
                        "Lanes",

                    "maxspeed":
                        "Max Speed"

                }


                aliases = [

                    road_aliases[
                        field
                    ]

                    for field in road_fields

                ]


                tooltip = None


                if road_fields:

                    tooltip = folium.GeoJsonTooltip(

                        fields=road_fields,

                        aliases=aliases,

                        localize=True,

                        sticky=False

                    )


                folium.GeoJson(

                    roads,

                    style_function=lambda feature: {

                        "color": "blue",

                        "weight": 2,

                        "opacity": 0.7

                    },

                    tooltip=tooltip

                ).add_to(
                    roads_layer
                )


                roads_layer.add_to(m)


            except Exception as e:

                print()
                print(
                    "ERROR loading roads:"
                )

                print(e)


        else:

            print()
            print(
                "Road GeoJSON not found:"
            )

            print(
                ROADS_FILE
            )


        # ====================================================
        # LOAD OSM RAILWAYS
        # ====================================================

        print()
        print("==========================================")
        print(
            "LOADING OSM RAILWAY NETWORK"
        )
        print("==========================================")


        if os.path.exists(
            RAILWAYS_FILE
        ):

            try:

                railways = gpd.read_file(
                    RAILWAYS_FILE
                )


                print(
                    "Railway features:",
                    len(railways)
                )


                railway_layer = (
                    folium.FeatureGroup(

                        name="🚆 OSM Railway Network",

                        show=False

                    )
                )


                possible_fields = [

                    "railway",
                    "name",
                    "ref",
                    "operator",
                    "usage",
                    "electrified"

                ]


                railway_fields = [

                    field

                    for field in possible_fields

                    if field in railways.columns

                ]


                railway_aliases = {

                    "railway":
                        "Railway Type",

                    "name":
                        "Name",

                    "ref":
                        "Reference",

                    "operator":
                        "Operator",

                    "usage":
                        "Usage",

                    "electrified":
                        "Electrified"

                }


                aliases = [

                    railway_aliases[
                        field
                    ]

                    for field in railway_fields

                ]


                tooltip = None


                if railway_fields:

                    tooltip = folium.GeoJsonTooltip(

                        fields=railway_fields,

                        aliases=aliases,

                        localize=True,

                        sticky=False

                    )


                folium.GeoJson(

                    railways,

                    style_function=lambda feature: {

                        "color": "darkred",

                        "weight": 3,

                        "opacity": 0.8

                    },

                    tooltip=tooltip

                ).add_to(
                    railway_layer
                )


                railway_layer.add_to(m)


            except Exception as e:

                print()
                print(
                    "ERROR loading railways:"
                )

                print(e)


        else:

            print()
            print(
                "Railway GeoJSON not found:"
            )

            print(
                RAILWAYS_FILE
            )


        # ====================================================
        # DOWNLOAD INFRASTRUCTURE
        # ====================================================

        infrastructure_data = (

            self.download_infrastructure()

        )


        # ====================================================
        # ADD INFRASTRUCTURE
        # ====================================================

        if infrastructure_data is not None:

            self.add_infrastructure(

                m,

                infrastructure_data,

                risk_data,

                inverse_transform

            )

        else:

            print()
            print(
                "Infrastructure was not added "
                "because Overpass download failed."
            )


        # ====================================================
        # LAYER CONTROL
        # ====================================================

        folium.LayerControl(

            collapsed=False

        ).add_to(m)


        # ====================================================
        # SAVE HTML
        # ====================================================

        html_path = os.path.join(

            BASE_DIR,

            "Flood_OSM_Map.html"

        )


        m.save(
            html_path
        )


        print()
        print(
            "Map saved to:"
        )

        print(
            html_path
        )


        # ====================================================
        # READ HTML FOR FLASK
        # ====================================================

        with open(

            html_path,

            "r",

            encoding="utf-8"

        ) as f:

            self.map_html = f.read()


        # ====================================================
        # START FLASK
        # ====================================================

        if not self.server_started:

            self.server_started = True


            def run_server():

                self.app.run(

                    host="127.0.0.1",

                    port=5000,

                    debug=False,

                    use_reloader=False

                )


            server_thread = threading.Thread(

                target=run_server,

                daemon=True

            )


            server_thread.start()


            time.sleep(2)


            webbrowser.open(
                "http://127.0.0.1:5000/"
            )


        print()
        print("==========================================")
        print(
            "MAP READY!"
        )
        print("==========================================")


        print()
        print(
            "Open in browser:"
        )


        print(
            "http://127.0.0.1:5000/"
        )


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )


    window = FloodRiskApp()


    window.show()


    sys.exit(
        app.exec()
    )