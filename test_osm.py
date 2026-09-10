import sys
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class OSMTestWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OSM / GeoJSON Tester Window")
        self.resize(900, 650)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.btn_load = QPushButton(
            "Click Here to Select & Test Your .geojson File"
        )
        self.btn_load.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 10px; background-color: #2563EB; color: white;"
        )
        self.btn_load.clicked.connect(self.load_vector_file)
        layout.addWidget(self.btn_load)

        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

    def load_vector_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GIS Vector File",
            "",
            "Vector Files (*.geojson *.shp *.gpkg)",
        )
        if file_path:
            try:
                self.ax.clear()
                print(f"Loading file: {file_path}")

                # Read geojson using GeoPandas
                gdf = gpd.read_file(file_path)

                # Plot on canvas
                gdf.plot(ax=self.ax, color="#2563EB", edgecolor="black")
                self.ax.set_title(
                    f"Successfully Rendered: {file_path.split('/')[-1]}",
                    fontsize=12,
                )
                self.ax.set_axis_off()
                self.canvas.draw()
                print("SUCCESS: Map rendered on screen!")
            except Exception as e:
                print(f"ERROR while rendering: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OSMTestWindow()
    window.show()
    sys.exit(app.exec())