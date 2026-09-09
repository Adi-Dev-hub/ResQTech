from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
import subprocess
import sys
from pathlib import Path

from Interpolation_ui import Ui_Dialog


class InterpolationDialog(QDialog):

    def __init__(self):
        super().__init__()

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        # -----------------------------------------
        # Select rainfall shapefile
        # -----------------------------------------
        self.ui.toolButton.clicked.connect(
            lambda: self.load_file(
                self.ui.lineEdit,
                "Shapefiles (*.shp);;All Files (*)"
            )
        )

        # -----------------------------------------
        # Select extent raster
        # -----------------------------------------
        self.ui.toolButton_2.clicked.connect(
            lambda: self.load_file(
                self.ui.lineEdit_2,
                "Raster Files (*.tif *.tiff);;All Files (*)"
            )
        )

        # -----------------------------------------
        # Run interpolation
        # -----------------------------------------
        self.ui.pushButton.clicked.connect(self.run_script)

    # =================================================
    # FILE SELECTION
    # =================================================

    def load_file(self, line_edit, file_filter):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            "",
            file_filter
        )

        if file_path:
            line_edit.setText(file_path)

    # =================================================
    # RUN INTERPOLATION
    # =================================================

    def run_script(self):

        # -----------------------------------------
        # Default project files
        # -----------------------------------------

        project_root = Path(__file__).resolve().parents[1]

        rainfall_default = project_root / "data" / "DRMS_station.shp"
        dem_default = project_root / "data" / "puneDem.tif"

        # If fields are empty, use default files
        if not self.ui.lineEdit.text().strip():
            self.ui.lineEdit.setText(str(rainfall_default))

        if not self.ui.lineEdit_2.text().strip():
            self.ui.lineEdit_2.setText(str(dem_default))

        if not self.ui.lineEdit_3.text().strip():
            self.ui.lineEdit_3.setText("-1")

        # -----------------------------------------
        # Read parameters
        # -----------------------------------------

        rainfall_path = self.ui.lineEdit.text().strip()
        extent_raster_path = self.ui.lineEdit_2.text().strip()
        no_data_value = self.ui.lineEdit_3.text().strip()

        smoothened = self.ui.checkBox.isChecked()

        # -----------------------------------------
        # Check required files
        # -----------------------------------------

        if not rainfall_path:
            print("ERROR: Please select rainfall shapefile.")
            return

        if not extent_raster_path:
            print("ERROR: Please select extent raster.")
            return

        if not Path(rainfall_path).exists():
            print(f"ERROR: Rainfall shapefile not found:")
            print(rainfall_path)
            return

        if not Path(extent_raster_path).exists():
            print(f"ERROR: DEM raster not found:")
            print(extent_raster_path)
            return

        # -----------------------------------------
        # Print parameters
        # -----------------------------------------

        print("\n========================================")
        print("Running Rainfall Interpolation")
        print("========================================")

        print(f"Rainfall      : {rainfall_path}")
        print(f"Extent Raster : {extent_raster_path}")
        print(f"No Data Value : {no_data_value}")
        print(f"Smoothened    : {smoothened}")

        # -----------------------------------------
        # Locate interpolation.py
        # -----------------------------------------

        script_path = project_root / "Features" / "interpolation.py"

        print(f"\nInterpolation script:")
        print(script_path)

        if not script_path.exists():

            print("\nERROR: interpolation.py not found!")
            print(f"Expected location:")
            print(script_path)

            return

        # -----------------------------------------
        # Execute interpolation script
        # -----------------------------------------

        try:

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    rainfall_path,
                    extent_raster_path,
                    no_data_value,
                    str(smoothened)
                ],
                check=True
            )

            print("\n========================================")
            print("Interpolation completed successfully!")
            print("========================================")

        except subprocess.CalledProcessError as e:

            print("\n========================================")
            print("ERROR: Interpolation failed")
            print("========================================")

            print(f"Return code: {e.returncode}")

        except Exception as e:

            print("\n========================================")
            print("ERROR:")
            print(e)
            print("========================================")


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = InterpolationDialog()

    window.show()

    sys.exit(app.exec())