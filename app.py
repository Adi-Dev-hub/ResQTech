import os
import sys
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtCore import QDir, QFile, QIODevice, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# ==============================================================================
# MODERN COMPACT LIGHT THEME
# ==============================================================================
MODERN_LIGHT_THEME = """
QMainWindow {
    background-color: #F1F5F9;
}

QWidget {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 12px;
    color: #1E293B;
}

#HeaderBanner {
    background-color: #0F172A;
    border-bottom: 2px solid #2563EB;
}

#HeaderTitle {
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 600;
}

#HeaderSubtitle {
    color: #94A3B8;
    font-size: 11px;
    font-weight: 400;
}

QMenuBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 1px 4px;
}

QMenuBar::item {
    background-color: transparent;
    padding: 4px 10px;
    border-radius: 4px;
    color: #334155;
    font-weight: 500;
}

QMenuBar::item:selected {
    background-color: #F1F5F9;
    color: #0F172A;
}

QToolBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    spacing: 4px;
    padding: 3px;
}

#LeftNavPanel {
    background-color: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}

#NavHeader {
    font-size: 10px;
    font-weight: 700;
    color: #64748B;
    padding: 8px 12px 4px 12px;
    letter-spacing: 0.5px;
}

QPushButton.NavButton {
    background-color: transparent;
    color: #475569;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
}

QPushButton.NavButton:hover {
    background-color: #F8FAFC;
    color: #0F172A;
}

QPushButton.NavButton:checked {
    background-color: #EFF6FF;
    color: #1D4ED8;
    border-left: 3px solid #2563EB;
    font-weight: 700;
}

#RightPanelScroll {
    background-color: #F1F5F9;
    border: none;
}

#RightPanelHeader {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 8px 12px;
}

#RightPanelHeaderTitle {
    color: #0F172A;
    font-size: 12px;
    font-weight: 700;
}

QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 12px;
    font-weight: 700;
    color: #1E3A8A;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    background-color: #FFFFFF;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    color: #0F172A;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1.5px solid #2563EB;
}

QPushButton {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 700;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #1D4ED8;
}

#MapCanvasArea {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
}

#LayerControlPanel {
    background-color: #FFFFFF;
    border-top: 1px solid #CBD5E1;
    padding: 6px;
}
"""


# ==============================================================================
# QGIS-STYLE MULTI-LAYER MAP CANVAS WITH MATPLOTLIB & GEOPANDAS
# ==============================================================================
class GISMapCanvasWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MapCanvasArea")

        # Layer Management Storage
        self.layers = {}  # {layer_id: {"gdf": GeoDataFrame, "visible": bool, "style": dict, "name": str}}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Embedded Matplotlib Figure
        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        # Layer Control Box (QGIS Layers Panel)
        self.layer_panel = QFrame()
        self.layer_panel.setObjectName("LayerControlPanel")
        self.layer_layout = QHBoxLayout(self.layer_panel)
        self.layer_layout.setContentsMargins(5, 2, 5, 2)
        
        lbl_layers = QLabel("QGIS Layers:")
        lbl_layers.setStyleSheet("font-weight: bold; color: #0F172A;")
        self.layer_layout.addWidget(lbl_layers)
        self.layer_layout.addStretch()

        layout.addWidget(self.layer_panel)

        self.ax.set_title("ResQTech Spatial Visualization Area", fontsize=11)
        self.ax.set_axis_off()

    def update_canvas_layer(self, layer_name: str):
        if not self.layers:
            self.ax.clear()
            self.ax.text(
                0.5,
                0.5,
                f"Active Layer: {layer_name}\n(Select & Load GeoJSON to Plot Data)",
                horizontalalignment="center",
                verticalalignment="center",
                fontsize=12,
                color="#64748B",
                transform=self.ax.transAxes,
            )
            self.ax.set_axis_off()
            self.canvas.draw()

    def add_or_update_layer(self, file_path: str):
        """Adds a layer to the layer registry and renders all active layers together."""
        try:
            gdf = gpd.read_file(file_path)
            file_title = os.path.basename(file_path)
            file_lower = file_title.lower()

            # Determine symbology type
            if "hospital" in file_lower:
                layer_id = "hospitals"
                display_name = "Hospitals (+)"
                style = {"color": "#E63946", "marker": "P", "size": 90}
            elif "police" in file_lower:
                layer_id = "police"
                display_name = "Police Stations (*)"
                style = {"color": "#1D3557", "marker": "*", "size": 90}
            else:
                layer_id = file_lower
                display_name = file_title
                style = {"color": "#2563EB", "marker": "o", "size": 50}

            # Register/Update Layer Data
            self.layers[layer_id] = {
                "gdf": gdf,
                "visible": True,
                "style": style,
                "name": display_name,
            }

            self._rebuild_layer_ui()
            self.redraw_all_layers()

            print(f"SUCCESS: Added/Updated layer '{display_name}' in QGIS engine!")
        except Exception as e:
            print(f"Error loading layer: {e}")

    def toggle_layer_visibility(self, layer_id: str, is_visible: bool):
        """Toggles a specific layer On/Off and redraws the canvas."""
        if layer_id in self.layers:
            self.layers[layer_id]["visible"] = is_visible
            self.redraw_all_layers()

    def _rebuild_layer_ui(self):
        """Rebuilds the bottom QGIS-style layer toggle checkboxes."""
        # Clear existing toggles
        for i in reversed(range(self.layer_layout.count())):
            item = self.layer_layout.itemAt(i)
            widget = item.widget()
            if widget and isinstance(widget, QCheckBox):
                widget.setParent(None)

        # Add checkboxes for registered layers
        for layer_id, layer_info in self.layers.items():
            chk = QCheckBox(layer_info["name"])
            chk.setChecked(layer_info["visible"])
            chk.setStyleSheet("font-weight: 600; margin-right: 10px;")
            chk.toggled.connect(
                lambda checked, lid=layer_id: self.toggle_layer_visibility(lid, checked)
            )
            self.layer_layout.addWidget(chk)

    def redraw_all_layers(self):
        """Clears canvas and renders all visible layers simultaneously."""
        self.ax.clear()
        visible_count = 0

        for layer_id, layer_info in self.layers.items():
            if layer_info["visible"]:
                visible_count += 1
                gdf = layer_info["gdf"]
                style = layer_info["style"]
                gdf.plot(
                    ax=self.ax,
                    color=style["color"],
                    edgecolor="#0F172A",
                    marker=style["marker"],
                    markersize=style["size"],
                    alpha=0.85,
                    label=layer_info["name"],
                )

        if visible_count > 0:
            self.ax.set_title(
                f"Multi-Layer View ({visible_count} active layer(s))",
                fontsize=11,
                fontweight="bold",
            )
            self.ax.legend(loc="upper right", frameon=True)
        else:
            self.ax.set_title("All layers turned off", fontsize=11)

        self.ax.set_axis_off()
        self.canvas.draw()


# ==============================================================================
# MAIN APPLICATION WINDOW
# ==============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Disaster Risk & Relocation Decision Support System")
        self.resize(1400, 880)

        self.loader = QUiLoader()

        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._build_main_layout()
        self._connect_osm_form_signals()

    def _create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("New Project")
        file_menu.addAction("Open Project")
        file_menu.addAction("Save Project")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        hazard_menu = menubar.addMenu("Hazard Analysis")
        hazard_menu.addAction("Flood", lambda: self.switch_page(0))
        hazard_menu.addAction("Landslide", lambda: self.switch_page(1))
        hazard_menu.addAction("Cyclone", lambda: self.switch_page(2))
        hazard_menu.addAction("Tsunami", lambda: self.switch_page(3))
        hazard_menu.addAction("Cloudburst", lambda: self.switch_page(4))
        hazard_menu.addAction("Forest Fire", lambda: self.switch_page(5))
        hazard_menu.addSeparator()
        hazard_menu.addAction("Multi-Hazard Analysis", lambda: self.switch_page(6))

        reloc_menu = menubar.addMenu("Relocation & Safety")
        reloc_menu.addAction("Relocation Assessment", lambda: self.switch_page(7))
        reloc_menu.addAction("Population Exposure", lambda: self.switch_page(8))
        reloc_menu.addAction("Carrying Capacity", lambda: self.switch_page(9))
        reloc_menu.addAction("Red Zone Delineation", lambda: self.switch_page(10))
        reloc_menu.addAction("OSM / Infrastructure", lambda: self.switch_page(11))

    def _create_tool_bar(self):
        toolbar = QToolBar("GIS Quick Tools")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        actions = [
            "Add Layer",
            "Open Raster",
            "Open Vector",
            "Symbology",
            "Refresh",
            "Zoom In",
            "Zoom Out",
            "Full Extent",
        ]
        for name in actions:
            action = QAction(name, self)
            toolbar.addAction(action)

    def _create_status_bar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Status: Ready | Active CRS: EPSG:4326 - WGS 84")

    def load_ui_file(self, file_name: str) -> QWidget:
        """Loads a .ui file directly from the ui/ folder."""
        ui_dir = os.path.join(os.path.dirname(__file__), "ui")
        ui_path = os.path.join(ui_dir, file_name)

        file = QFile(ui_path)
        if not file.exists():
            print(f"Error: Could not find UI file: {ui_path}")
            fallback_widget = QWidget()
            lbl = QLabel(f"Missing UI File:\n{file_name}", fallback_widget)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return fallback_widget

        file.open(QIODevice.ReadOnly)
        loaded_widget = self.loader.load(file, self)
        file.close()
        return loaded_widget

    def _build_main_layout(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        root_layout = QVBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Header Banner
        banner = QWidget()
        banner.setObjectName("HeaderBanner")
        banner.setMaximumHeight(32)
        banner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(12, 0, 12, 0)

        t1 = QLabel("DRRDSS — Disaster Risk & Relocation Decision Support System")
        t1.setObjectName("HeaderTitle")
        t2 = QLabel("NDRF | MHA")
        t2.setObjectName("HeaderSubtitle")

        banner_layout.addWidget(t1)
        banner_layout.addStretch()
        banner_layout.addWidget(t2)
        root_layout.addWidget(banner)

        # Splitter Layout
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. Left Sidebar Navigation
        left_panel = QWidget()
        left_panel.setObjectName("LeftNavPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        nav_lbl = QLabel("DISASTER & CAPACITY MODULES")
        nav_lbl.setObjectName("NavHeader")
        left_layout.addWidget(nav_lbl)

        self.nav_buttons = []
        disasters = [
            ("Flood", 0),
            ("Landslide", 1),
            ("Cyclone", 2),
            ("Tsunami", 3),
            ("Cloudburst", 4),
            ("Forest Fire", 5),
            ("Multi-Hazard Analysis", 6),
            ("Relocation Assessment", 7),
            ("Population Exposure", 8),
            ("Carrying Capacity", 9),
            ("Red Zone Delineation", 10),
            ("OSM Vector Infrastructure", 11),
        ]

        for name, idx in disasters:
            btn = QPushButton(f"  {name}")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "NavButton")
            btn.clicked.connect(lambda _, x=idx: self.switch_page(x))
            left_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # 2. Central GIS Map Area
        self.map_canvas = GISMapCanvasWidget()
        splitter.addWidget(self.map_canvas)

        # 3. Right Container with Scroll Area
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        r_header = QWidget()
        r_header.setObjectName("RightPanelHeader")
        r_header_layout = QHBoxLayout(r_header)
        r_header_layout.setContentsMargins(12, 6, 12, 6)
        r_title = QLabel("HAZARD INPUT & ANALYSIS")
        r_title.setObjectName("RightPanelHeaderTitle")
        r_header_layout.addWidget(r_title)
        right_layout.addWidget(r_header)

        # Stacked Widget Loading .ui Files
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.load_ui_file("flood_form.ui"))  # Index 0
        self.stacked_widget.addWidget(self.load_ui_file("landslide_form.ui"))  # Index 1
        self.stacked_widget.addWidget(self.load_ui_file("cyclone_form.ui"))  # Index 2
        self.stacked_widget.addWidget(self.load_ui_file("tsunami_form.ui"))  # Index 3
        self.stacked_widget.addWidget(self.load_ui_file("cloudburst_form.ui"))  # Index 4
        self.stacked_widget.addWidget(self.load_ui_file("forest_fire_form.ui"))  # Index 5
        self.stacked_widget.addWidget(self.load_ui_file("multi_hazard_form.ui"))  # Index 6
        self.stacked_widget.addWidget(self.load_ui_file("relocation_form.ui"))  # Index 7
        self.stacked_widget.addWidget(self.load_ui_file("population_form.ui"))  # Index 8
        self.stacked_widget.addWidget(self.load_ui_file("population_carrying_capacity_form.ui"))  # Index 9
        self.stacked_widget.addWidget(self.load_ui_file("red_zone_form.ui"))  # Index 10
        self.stacked_widget.addWidget(self.load_ui_file("osm_loader_form.ui"))  # Index 11

        # Scroll Wrapper
        right_scroll = QScrollArea()
        right_scroll.setObjectName("RightPanelScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setWidget(self.stacked_widget)

        right_layout.addWidget(right_scroll)
        splitter.addWidget(right_container)

        splitter.setSizes([220, 760, 420])
        root_layout.addWidget(splitter, 1)

        self.switch_page(0)

    def _connect_osm_form_signals(self):
        """Connects input UI elements in osm_loader_form.ui to output rendering on the canvas."""
        osm_form_widget = self.stacked_widget.widget(11)
        if not osm_form_widget:
            return

        btn_browse = osm_form_widget.findChild(
            QPushButton, "btnBrowseVectorLayer"
        ) or osm_form_widget.findChild(QPushButton, "btnBrowseVector")
        btn_render = osm_form_widget.findChild(
            QPushButton, "btnRenderVector"
        ) or osm_form_widget.findChild(QPushButton, "btnLoadMap")
        txt_path = osm_form_widget.findChild(
            QLineEdit, "txtVectorPathInput"
        ) or osm_form_widget.findChild(QLineEdit, "txtVectorPath")

        if btn_browse:

            def browse_vector_file():
                file_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select GeoJSON Dataset",
                    os.path.dirname(__file__),
                    "Vector Files (*.geojson *.json *.shp *.gpkg)",
                )
                if file_path and txt_path:
                    txt_path.setText(file_path)

            btn_browse.clicked.connect(browse_vector_file)

        if btn_render:

            def render_vector_layer():
                if txt_path and txt_path.text():
                    path = txt_path.text()
                    self.map_canvas.add_or_update_layer(path)
                else:
                    self.statusbar.showMessage(
                        "Please select a GeoJSON file first using Browse!"
                    )

            btn_render.clicked.connect(render_vector_layer)

    def switch_page(self, index: int):
        self.stacked_widget.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        disaster_names = [
            "Flood",
            "Landslide",
            "Cyclone",
            "Tsunami",
            "Cloudburst",
            "Forest Fire",
            "Multi-Hazard",
            "Relocation",
            "Population Exposure",
            "Carrying Capacity",
            "Red Zone Delineation",
            "OSM Vector Infrastructure",
        ]
        active_name = disaster_names[index]
        self.map_canvas.update_canvas_layer(active_name)
        self.statusbar.showMessage(
            f"Status: Active Module -> {active_name} Analysis"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(MODERN_LIGHT_THEME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())