import sys
import numpy as np
import rasterio
from scipy.ndimage import zoom


# ============================================================
# FLOOD RISK USING AHP
# Continuous Flood Risk Index: 0-100%
#
# Factors:
# 1. DEM
# 2. Slope
# 3. LULC
# 4. Rainfall
# 5. Population Density
# ============================================================


# ============================================================
# AHP WEIGHTS
# ============================================================

WEIGHTS = {
    "dem": 0.200,
    "slope": 0.250,
    "lulc": 0.125,
    "rainfall": 0.350,
    "population": 0.075
}


# ============================================================
# READ RASTER
# ============================================================

def read_raster(path):

    with rasterio.open(path) as src:

        data = src.read(1).astype(float)
        profile = src.profile.copy()
        nodata = src.nodata

    # Convert NoData to NaN
    if nodata is not None:
        data[data == nodata] = np.nan

    return data, profile


# ============================================================
# RESAMPLE TO DEM GRID
# ============================================================

def resample_to_reference(data, reference_shape):

    if data.shape == reference_shape:
        return data

    zoom_y = reference_shape[0] / data.shape[0]
    zoom_x = reference_shape[1] / data.shape[1]

    return zoom(
        data,
        (zoom_y, zoom_x),
        order=1
    )


# ============================================================
# NORMALIZATION
#
# Higher value = higher flood risk
#
# Used for:
# Rainfall
# Population Density
# ============================================================

def normalize(data):

    result = np.full(data.shape, np.nan)

    valid = np.isfinite(data)

    if not np.any(valid):
        return result

    minimum = np.nanmin(data)
    maximum = np.nanmax(data)

    if maximum == minimum:

        result[valid] = 0.5

        return result

    result[valid] = (
        (data[valid] - minimum) /
        (maximum - minimum)
    )

    return result


# ============================================================
# INVERSE NORMALIZATION
#
# Lower value = higher flood risk
#
# Used for:
# DEM
# Slope
# ============================================================

def inverse_normalize(data):

    result = np.full(data.shape, np.nan)

    valid = np.isfinite(data)

    if not np.any(valid):
        return result

    minimum = np.nanmin(data)
    maximum = np.nanmax(data)

    if maximum == minimum:

        result[valid] = 0.5

        return result

    result[valid] = (
        (maximum - data[valid]) /
        (maximum - minimum)
    )

    return result


# ============================================================
# LULC RISK RECLASSIFICATION
#
# IMPORTANT:
# These class codes MUST match your LULC raster.
#
# Example:
# 1 = Water
# 2 = Forest
# 3 = Cropland
# 4 = Built-up
# 5 = Barren
# ============================================================

def classify_lulc(lulc):

    risk = np.full(lulc.shape, np.nan)

    # Water
    risk[lulc == 1] = 1.00

    # Forest
    risk[lulc == 2] = 0.20

    # Cropland
    risk[lulc == 3] = 0.60

    # Built-up
    risk[lulc == 4] = 0.90

    # Barren
    risk[lulc == 5] = 0.70

    return risk


# ============================================================
# AHP FLOOD RISK CALCULATION
# ============================================================

def calculate_flood_risk(
        dem,
        slope,
        lulc,
        rainfall,
        population):

    print("Calculating normalized risk layers...")

    # --------------------------------------------------------
    # Normalize each factor
    # --------------------------------------------------------

    dem_score = inverse_normalize(dem)

    slope_score = inverse_normalize(slope)

    lulc_score = classify_lulc(lulc)

    rainfall_score = normalize(rainfall)

    population_score = normalize(population)


    # --------------------------------------------------------
    # AHP WEIGHTED OVERLAY
    # --------------------------------------------------------

    flood_risk = (

        WEIGHTS["dem"] *
        dem_score

        +

        WEIGHTS["slope"] *
        slope_score

        +

        WEIGHTS["lulc"] *
        lulc_score

        +

        WEIGHTS["rainfall"] *
        rainfall_score

        +

        WEIGHTS["population"] *
        population_score

    )

    return flood_risk


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():

    # --------------------------------------------------------
    # CHECK INPUT ARGUMENTS
    # --------------------------------------------------------

    if len(sys.argv) != 7:

        print(
            "\nUsage:\n"
            "python Flood_AHP.py "
            "<DEM> "
            "<SLOPE> "
            "<LULC> "
            "<RAINFALL> "
            "<POPULATION> "
            "<OUTPUT>\n"
        )

        sys.exit(1)


    # --------------------------------------------------------
    # FILE PATHS
    # --------------------------------------------------------

    dem_file = sys.argv[1]

    slope_file = sys.argv[2]

    lulc_file = sys.argv[3]

    rainfall_file = sys.argv[4]

    population_file = sys.argv[5]

    output_file = sys.argv[6]


    # --------------------------------------------------------
    # READ INPUT RASTERS
    # --------------------------------------------------------

    print("\nReading DEM...")

    dem, profile = read_raster(
        dem_file
    )


    print("Reading Slope...")

    slope, _ = read_raster(
        slope_file
    )


    print("Reading LULC...")

    lulc, _ = read_raster(
        lulc_file
    )


    print("Reading Rainfall...")

    rainfall, _ = read_raster(
        rainfall_file
    )


    print("Reading Population Density...")

    population, _ = read_raster(
        population_file
    )


    # --------------------------------------------------------
    # USE DEM AS REFERENCE GRID
    # --------------------------------------------------------

    reference_shape = dem.shape


    print("\nChecking raster dimensions...")


    slope = resample_to_reference(
        slope,
        reference_shape
    )


    lulc = resample_to_reference(
        lulc,
        reference_shape
    )


    rainfall = resample_to_reference(
        rainfall,
        reference_shape
    )


    population = resample_to_reference(
        population,
        reference_shape
    )


    print("All rasters aligned to DEM.")


    # --------------------------------------------------------
    # CALCULATE AHP FLOOD RISK
    # --------------------------------------------------------

    print("\nRunning AHP weighted overlay...")


    flood_risk = calculate_flood_risk(
        dem,
        slope,
        lulc,
        rainfall,
        population
    )


    # ========================================================
    # CONVERT AHP SCORE TO PERCENTAGE
    # ========================================================

    flood_risk_percentage = (
        flood_risk * 100
    )


    # --------------------------------------------------------
    # SAVE FLOOD RISK PERCENTAGE RASTER
    # --------------------------------------------------------

    output_profile = profile.copy()


    output_profile.update(
        dtype="float32",
        count=1,
        nodata=-9999,
        compress="lzw"
    )


    output_data = np.where(
        np.isfinite(flood_risk_percentage),
        flood_risk_percentage,
        -9999
    ).astype(np.float32)


    with rasterio.open(
        output_file,
        "w",
        **output_profile
    ) as dst:

        dst.write(
            output_data,
            1
        )


    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    valid = np.isfinite(
        flood_risk_percentage
    )


    if np.any(valid):

        minimum = np.nanmin(
            flood_risk_percentage
        )

        maximum = np.nanmax(
            flood_risk_percentage
        )

        mean = np.nanmean(
            flood_risk_percentage
        )

    else:

        minimum = np.nan

        maximum = np.nan

        mean = np.nan


    # --------------------------------------------------------
    # FINAL OUTPUT
    # --------------------------------------------------------

    print("\n========================================")

    print(
        "AHP FLOOD RISK CALCULATION COMPLETE"
    )

    print("========================================")


    print("\nAHP Weights:")

    print(
        "DEM                 :",
        WEIGHTS["dem"]
    )

    print(
        "Slope               :",
        WEIGHTS["slope"]
    )

    print(
        "LULC                :",
        WEIGHTS["lulc"]
    )

    print(
        "Rainfall            :",
        WEIGHTS["rainfall"]
    )

    print(
        "Population Density  :",
        WEIGHTS["population"]
    )


    print("\nFlood Risk Index (%):")

    print(
        "Minimum Risk        :",
        minimum,
        "%"
    )

    print(
        "Maximum Risk        :",
        maximum,
        "%"
    )

    print(
        "Mean Risk           :",
        mean,
        "%"
    )


    print("\nOutput:")

    print(output_file)


    print(
        "\nThe output contains continuous "
        "AHP Flood Risk Index values from "
        "0 to 100%."
    )

    print(
        "No 1-5 classification was performed."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()