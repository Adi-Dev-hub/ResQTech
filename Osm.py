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

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Risk Map File", "", "GeoTIFF Files (*.tif *.tiff)")
        if file_path:
            self.ui.lineEdit.setText(file_path)
            self.risk_map_path = file_path

    def run_analysis(self):
        if not self.risk_map_path:
            print("Please select a file first!")
            return

        print(f"Processing file: {self.risk_map_path}")
        png_path = "combined_risk_output.png"

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

        cmap = ListedColormap(['yellow', 'orange', 'red', 'gray'])
        plt.imsave(png_path, risk_data, cmap=cmap)

        center_lat = (min_y + max_y) / 2
        center_lon = (min_x + max_x) / 2
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

        image_bounds = [[min_y, min_x], [max_y, max_x]]
        folium.raster_layers.ImageOverlay(
            name="Flood Risk Map",
            image=png_path,
            bounds=image_bounds,
            opacity=0.6,
            interactive=True,
            cross_origin=False,
            zindex=1
        ).add_to(m)

        api = overpy.Overpass()

        queries = {
            "hospital": 'node["amenity"="hospital"]({},{},{},{});out;',
            "school": 'node["amenity"="school"]({},{},{},{});out;',
            "fire_station": 'node["emergency"="fire_station"]({},{},{},{});out;',
            "police": 'node["amenity"="police"]({},{},{},{});out;',
        }

        infrastructure_info = {
            "hospital": {"color": {"1": "green", "2": "orange", "3": "red"}, "icon": "plus-square"},
            "school": {"color": "blue", "icon": "graduation-cap"},
            "fire_station": {"color": "darkred", "icon": "fire-extinguisher"},
            "police": {"color": "cadetblue", "icon": "shield"},
        }

        # Feature Groups
        fg_hosp_low = folium.FeatureGroup(name="Low Risk Hospitals")
        fg_hosp_med = folium.FeatureGroup(name="Moderate Risk Hospitals")
        fg_hosp_high = folium.FeatureGroup(name="High Risk Hospitals")
        fg_schools = folium.FeatureGroup(name="Schools")
        fg_fire = folium.FeatureGroup(name="Fire Stations")
        fg_police = folium.FeatureGroup(name="Police Stations")

        inv_affine = ~affine_transform

        for infra_type, query in queries.items():
            try:
                result = api.query(query.format(min_y, min_x, max_y, max_x))
            except Exception as e:
                print(f"Error querying {infra_type}: {e}")
                continue

            for node in result.nodes:
                lat, lon = float(node.lat), float(node.lon)
                col, row = inv_affine * (lon, lat)
                col, row = int(round(col)), int(round(row))

                if row < 0 or row >= risk_data.shape[0] or col < 0 or col >= risk_data.shape[1]:
                    continue

                name = node.tags.get("name", infra_type.capitalize())

                if infra_type == "hospital":
                    risk_value = risk_data[row, col]
                    if risk_value == 4:
                        continue
                    icon_color = infrastructure_info["hospital"]["color"].get(str(risk_value), "gray")
                    icon_name = infrastructure_info["hospital"]["icon"]
                    fg = fg_hosp_low if risk_value == 1 else fg_hosp_med if risk_value == 2 else fg_hosp_high
                else:
                    icon_color = infrastructure_info[infra_type]["color"]
                    icon_name = infrastructure_info[infra_type]["icon"]
                    fg = fg_schools if infra_type == "school" else fg_fire if infra_type == "fire_station" else fg_police

                fg.add_child(folium.Marker(
                    location=[lat, lon],
                    popup=f"{name} ({infra_type.replace('_', ' ').title()})",
                    icon=folium.Icon(color=icon_color, icon=icon_name, prefix="fa")
                ))

        m.add_child(fg_hosp_low)
        m.add_child(fg_hosp_med)
        m.add_child(fg_hosp_high)
        m.add_child(fg_schools)
        m.add_child(fg_fire)
        m.add_child(fg_police)
        folium.LayerControl().add_to(m)

        @self.app.route("/")
        def index():
            return render_template_string(m.get_root().render())

        def run_server():
            self.app.run(debug=False, use_reloader=False)

        threading.Thread(target=run_server, daemon=True).start()
        webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FloodRiskApp()
    window.show()
    sys.exit(app.exec())
