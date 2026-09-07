import sys
import os
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6 import uic

class CarryingCapacityHandler(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. UI File path define karke load karein
        ui_path = os.path.join(os.path.dirname(__file__), 'ui', 'carrying_capacity.ui')
        
        if not os.path.exists(ui_path):
            print(f"[ERROR] UI File not found at: {ui_path}")
            return
            
        uic.loadUi(ui_path, self)
        print("[SUCCESS] Carrying Capacity UI Loaded Successfully.")

        # 2. Calculate Button Event Bind Karein
        if hasattr(self, 'btn_calculate_capacity'):
            self.btn_calculate_capacity.clicked.connect(self.calculate_capacity)
            print("[SUCCESS] Event signal connected to 'Calculate Safe Carrying Capacity' button.")

    def calculate_capacity(self):
        """
        SPHERE Standards-based Carrying Capacity Engine
        ----------------------------------------------
        - Space: 3.5 m² (Temp) / 12.0 m² (Perm) per person
        - Water: 15 L (Temp) / 70 L (Perm) per person per day
        - Toilets: 1 per 20 persons (Temp) / 1 per 5 persons (Perm)
        """
        try:
            # 1. Extract Values from Form Controls
            shelter_type = self.combo_shelter_type.currentText()
            land_ownership = self.combo_land_type.currentText()
            
            usable_area = self.spin_total_area.value()
            slope_angle = self.spin_slope.value()
            
            water_liters = self.spin_water_supply.value()
            toilet_count = self.spin_toilets.value()
            has_power = self.check_power_grid.isChecked()
            
            road_width = self.spin_road_width.value()
            hospital_dist = self.spin_hospital_dist.value()
            has_helipad = self.check_helipad.isChecked()

            # 2. Set Multipliers based on SPHERE Category
            if "Temporary" in shelter_type:
                sqm_per_person = 3.5
                water_per_person = 15.0
                people_per_toilet = 20
            else:  # Permanent Relocation
                sqm_per_person = 12.0
                water_per_person = 70.0
                people_per_toilet = 5

            # 3. Perform Capacity Calculations
            cap_space = int(usable_area / sqm_per_person) if sqm_per_person > 0 else 0
            cap_water = int(water_liters / water_per_person) if water_per_person > 0 else 0
            cap_sanitation = toilet_count * people_per_toilet

            # 4. Bottleneck Assessment (Limiting Factor)
            final_safe_capacity = min(cap_space, cap_water, cap_sanitation)

            limiting_factor = []
            if final_safe_capacity == cap_space:
                limiting_factor.append("Land Area Limit")
            if final_safe_capacity == cap_water:
                limiting_factor.append("Water Supply Deficit")
            if final_safe_capacity == cap_sanitation:
                limiting_factor.append("Sanitation / Toilet Shortage")

            bottleneck_str = " & ".join(limiting_factor) if limiting_factor else "None"

            # 5. Feasibility Checks
            slope_status = "SAFE (Suitable Terrain)" if slope_angle <= 15.0 else "WARNING (High Landslide/Erosion Risk)"
            access_status = "PASSED (Heavy Trucks / Relief Ops)" if road_width >= 6.0 else "RESTRICTED (Narrow Road Access)"

            # 6. Format and Render Output
            report_output = f"""
================================================================================
                 CARRYING CAPACITY ASSESSMENT REPORT
================================================================================
[+] Shelter Category   : {shelter_type}
[+] Land Ownership     : {land_ownership}
[+] Usable Site Area   : {usable_area:,.2f} sq. meters
[+] Terrain Slope      : {slope_angle:.1f}° ({slope_status})

------------------------ SPHERE RESOURCE BREAKDOWN -----------------------------
 [•] Space Capacity      : {cap_space:,} Persons (@ {sqm_per_person} m²/person)
 [•] Water Capacity      : {cap_water:,} Persons (@ {water_per_person} L/person/day)
 [•] Sanitation Capacity : {cap_sanitation:,} Persons (@ 1 Toilet / {people_per_toilet} persons)

------------------------ DECISION SUPPORT METRICS ------------------------------
 [!] RECOMMENDED MAXIMUM SAFE CAPACITY : {final_safe_capacity:,} PERSONS
 [!] Critical Limiting Factor          : {bottleneck_str}
 [!] Road Network Access Status        : {access_status} (Width: {road_width}m)
 [!] Nearest Hospital Distance         : {hospital_dist} Km
 [!] Power Infrastructure              : {"Grid Connected" if has_power else "Off-Grid (Generators Required)"}
 [!] Emergency Helipad Spot           : {"Available" if has_helipad else "Not Available"}
================================================================================
            """

            self.textBrowser_output.setText(report_output)

        except Exception as e:
            self.textBrowser_output.setText(f"[ERROR] Calculation failed: {str(e)}")

# Test standalone execution
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CarryingCapacityHandler()
    window.resize(600, 700)
    window.show()
    sys.exit(app.exec())