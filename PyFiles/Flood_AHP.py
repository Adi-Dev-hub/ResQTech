import sys
import numpy as np
import rasterio

from rasterio.warp import reproject, Resampling


# ============================================================
# FLOOD RISK USING AHP
# Continuous Flood Risk Index: 0-100%
#
# Factors:
#   1. DEM
#   2. Slope
#   3. LULC
#   4. Rainfall
#   5. Population Density
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
# CHECK WEIGHTS
# ============================================================

if not np.isclose(sum(WEIGHTS.values()), 1.0):
    raise ValueError(
        f"AHP weights must sum to 1. Current sum = "
        f"{sum(WEIGHTS.values())}"
    )


# ============================================================
# READ REFERENCE DEM
# ============================================================

def read_reference_raster(path):

    with rasterio.open(path) as src:

        data = src.read(1).astype(np.float32)

        profile = src.profile.copy()

        transform = src.transform
        crs = src.crs

        width = src.width
        height = src.height

        nodata = src.nodata

    # Convert NoData to NaN
    if nodata is not None:
        data[data == nodata] = np.nan

    # Remove invalid values
    data[~np.isfinite(data)] = np.nan

    return (
        data,
        profile,
        transform,
        crs,
        width,
        height
    )


# ============================================================
# READ AND REPROJECT/ALIGN RASTER
# ============================================================

def read_and_align(
    path,
    reference_transform,
    reference_crs,
    reference_width,
    reference_height,
    resampling_method
):

    with rasterio.open(path) as src:

        source = src.read(1).astype(np.float32)

        source_nodata = src.nodata

        destination = np.full(
            (reference_height, reference_width),
            np.nan,
            dtype=np.float32
        )

        reproject(
            source=source,
            destination=destination,

            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=source_nodata,

            dst_transform=reference_transform,
            dst_crs=reference_crs,
            dst_nodata=np.nan,

            resampling=resampling_method
        )

    destination[~np.isfinite(destination)] = np.nan

    return destination


# ============================================================
# NORMALIZATION
#
# Higher value = higher flood risk
#
# Rainfall
# Population Density
# ============================================================

def normalize(data, valid_mask):

    result = np.full(
        data.shape,
        np.nan,
        dtype=np.float32
    )

    valid = (
        np.isfinite(data) &
        valid_mask
    )

    if not np.any(valid):
        return result

    minimum = np.nanmin(data[valid])
    maximum = np.nanmax(data[valid])

    if maximum == minimum:

        result[valid] = 0.5

    else:

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
# DEM
# Slope
# ============================================================

def inverse_normalize(data, valid_mask):

    result = np.full(
        data.shape,
        np.nan,
        dtype=np.float32
    )

    valid = (
        np.isfinite(data) &
        valid_mask
    )

    if not np.any(valid):
        return result

    minimum = np.nanmin(data[valid])
    maximum = np.nanmax(data[valid])

    if maximum == minimum:

        result[valid] = 0.5

    else:

        result[valid] = (
            (maximum - data[valid]) /
            (maximum - minimum)
        )

    return result


# ============================================================
# SHOW ACTUAL LULC CLASSES
# ============================================================

def get_lulc_classes(lulc):

    valid = np.isfinite(lulc)

    if not np.any(valid):
        return []

    values = np.unique(lulc[valid])

    return values


# ============================================================
# LULC RISK RECLASSIFICATION
#
# YOUR LULC RASTER:
#
# 20
# 30
# 40
# 50
# 60
# 80
# 90
# 112
# 114
# 116
# 122
# 124
# 126
#
# 255 = NoData
#
# IMPORTANT:
# The meanings of these classes must match the legend
# of the LULC dataset.
#
# DO NOT invent class meanings.
# ============================================================

def classify_lulc(lulc):

    risk = np.full(
        lulc.shape,
        np.nan,
        dtype=np.float32
    )

    # --------------------------------------------------------
    # PUT YOUR ACTUAL LULC -> FLOOD RISK VALUES HERE
    #
    # Format:
    #
    # risk[lulc == CLASS_CODE] = RISK_VALUE
    #
    # Risk value must be between 0 and 1.
    #
    # Example:
    #
    # risk[lulc == 20] = 0.80
    #
    # --------------------------------------------------------

    # ========================================================
    # TEMPORARY MAPPING
    #
    # These values are ONLY based on the assumption that
    # lower/higher classes correspond to different land
    # cover types.
    #
    # YOU SHOULD REPLACE THESE WITH THE ACTUAL LEGEND VALUES.
    # ========================================================

    LULC_RISK = {

        20: 0.20,
        30: 0.30,
        40: 0.40,
        50: 0.90,
        60: 0.70,
        80: 1.00,
        90: 0.80,

        112: 0.20,
        114: 0.30,
        116: 0.40,

        122: 0.60,
        124: 0.70,
        126: 0.90
    }

    # Apply mapping
    for class_code, risk_value in LULC_RISK.items():

        risk[lulc == class_code] = risk_value

    return risk


# ============================================================
# CHECK LULC RECLASSIFICATION
# ============================================================

def check_lulc_classification(lulc, lulc_score):

    actual_classes = get_lulc_classes(lulc)

    print("\nLULC classes found:")

    for value in actual_classes:

        count = np.count_nonzero(
            lulc == value
        )

        mapped = np.isfinite(
            lulc_score[lulc == value]
        )

        mapped_count = np.count_nonzero(mapped)

        print(
            f"  Class {value:g} : "
            f"{count} pixels | "
            f"Mapped: {mapped_count}"
        )

    unmapped = (
        np.isfinite(lulc) &
        ~np.isfinite(lulc_score)
    )

    if np.any(unmapped):

        print(
            "\nWARNING:"
        )

        print(
            "Some LULC classes have no flood-risk "
            "mapping."
        )

        print(
            "Unmapped classes:"
        )

        values = np.unique(
            lulc[unmapped]
        )

        for value in values:

            print(
                f"  {value:g}"
            )

        return False

    return True


# ============================================================
# CALCULATE FLOOD RISK
# ============================================================

def calculate_flood_risk(
    dem,
    slope,
    lulc,
    rainfall,
    population
):

    print(
        "\nCalculating common valid area..."
    )

    # --------------------------------------------------------
    # First make sure all five input layers are valid
    # --------------------------------------------------------

    common_valid = (
        np.isfinite(dem) &
        np.isfinite(slope) &
        np.isfinite(lulc) &
        np.isfinite(rainfall) &
        np.isfinite(population)
    )

    print(
        "Valid pixels available for AHP:",
        np.count_nonzero(common_valid)
    )

    if not np.any(common_valid):

        raise ValueError(
            "No common valid pixels exist between "
            "the input rasters."
        )

    # --------------------------------------------------------
    # NORMALIZE DEM
    # --------------------------------------------------------

    print("\nNormalizing DEM...")

    dem_score = inverse_normalize(
        dem,
        common_valid
    )

    # --------------------------------------------------------
    # NORMALIZE SLOPE
    # --------------------------------------------------------

    print("Normalizing Slope...")

    slope_score = inverse_normalize(
        slope,
        common_valid
    )

    # --------------------------------------------------------
    # LULC
    # --------------------------------------------------------

    print("Reclassifying LULC...")

    lulc_score = classify_lulc(
        lulc
    )

    # Check LULC
    lulc_ok = check_lulc_classification(
        lulc,
        lulc_score
    )

    if not lulc_ok:

        raise ValueError(
            "\nLULC classification is incomplete. "
            "The program stopped to prevent an incorrect "
            "flood-risk map."
        )

    # --------------------------------------------------------
    # NORMALIZE RAINFALL
    # --------------------------------------------------------

    print("Normalizing Rainfall...")

    rainfall_score = normalize(
        rainfall,
        common_valid
    )

    # --------------------------------------------------------
    # NORMALIZE POPULATION
    # --------------------------------------------------------

    print(
        "Normalizing Population Density..."
    )

    population_score = normalize(
        population,
        common_valid
    )

    # --------------------------------------------------------
    # FINAL VALID PIXELS
    # --------------------------------------------------------

    final_valid = (

        common_valid &

        np.isfinite(dem_score) &

        np.isfinite(slope_score) &

        np.isfinite(lulc_score) &

        np.isfinite(rainfall_score) &

        np.isfinite(population_score)
    )

    print(
        "\nFinal valid pixels for AHP:",
        np.count_nonzero(final_valid)
    )

    if not np.any(final_valid):

        raise ValueError(
            "No valid pixels remain after "
            "normalization and LULC classification."
        )

    # --------------------------------------------------------
    # AHP WEIGHTED OVERLAY
    # --------------------------------------------------------

    print(
        "\nRunning AHP weighted overlay..."
    )

    flood_risk = np.full(
        dem.shape,
        np.nan,
        dtype=np.float32
    )

    flood_risk[final_valid] = (

        WEIGHTS["dem"] *
        dem_score[final_valid]

        +

        WEIGHTS["slope"] *
        slope_score[final_valid]

        +

        WEIGHTS["lulc"] *
        lulc_score[final_valid]

        +

        WEIGHTS["rainfall"] *
        rainfall_score[final_valid]

        +

        WEIGHTS["population"] *
        population_score[final_valid]
    )

    return flood_risk


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # CHECK COMMAND-LINE ARGUMENTS
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
    # READ DEM
    # --------------------------------------------------------

    print("\nReading DEM...")

    (
        dem,
        profile,
        reference_transform,
        reference_crs,
        reference_width,
        reference_height
    ) = read_reference_raster(
        dem_file
    )

    print(
        f"DEM size: "
        f"{reference_width} x {reference_height}"
    )

    print(
        f"DEM CRS: {reference_crs}"
    )

    # --------------------------------------------------------
    # SLOPE
    #
    # Continuous raster:
    # Bilinear resampling
    # --------------------------------------------------------

    print(
        "\nReading and aligning Slope..."
    )

    slope = read_and_align(
        slope_file,
        reference_transform,
        reference_crs,
        reference_width,
        reference_height,
        Resampling.bilinear
    )

    # --------------------------------------------------------
    # LULC
    #
    # Categorical raster:
    # Nearest neighbour
    # --------------------------------------------------------

    print(
        "Reading and aligning LULC..."
    )

    lulc = read_and_align(
        lulc_file,
        reference_transform,
        reference_crs,
        reference_width,
        reference_height,
        Resampling.nearest
    )

    # --------------------------------------------------------
    # RAINFALL
    #
    # Continuous raster:
    # Bilinear
    # --------------------------------------------------------

    print(
        "Reading and aligning Rainfall..."
    )

    rainfall = read_and_align(
        rainfall_file,
        reference_transform,
        reference_crs,
        reference_width,
        reference_height,
        Resampling.bilinear
    )

    # --------------------------------------------------------
    # POPULATION
    #
    # Continuous raster:
    # Bilinear
    # --------------------------------------------------------

    print(
        "Reading and aligning Population Density..."
    )

    population = read_and_align(
        population_file,
        reference_transform,
        reference_crs,
        reference_width,
        reference_height,
        Resampling.bilinear
    )

    print(
        "\nAll rasters aligned to DEM."
    )

    # --------------------------------------------------------
    # INPUT STATISTICS
    # --------------------------------------------------------

    print("\nInput ranges:")

    if np.any(np.isfinite(dem)):

        print(
            f"DEM       : "
            f"{np.nanmin(dem):.3f} "
            f"to "
            f"{np.nanmax(dem):.3f}"
        )

    if np.any(np.isfinite(slope)):

        print(
            f"Slope     : "
            f"{np.nanmin(slope):.3f} "
            f"to "
            f"{np.nanmax(slope):.3f}"
        )

    if np.any(np.isfinite(rainfall)):

        print(
            f"Rainfall  : "
            f"{np.nanmin(rainfall):.3f} "
            f"to "
            f"{np.nanmax(rainfall):.3f}"
        )

    if np.any(np.isfinite(population)):

        print(
            f"Population: "
            f"{np.nanmin(population):.3f} "
            f"to "
            f"{np.nanmax(population):.3f}"
        )

    # --------------------------------------------------------
    # CALCULATE AHP
    # --------------------------------------------------------

    flood_risk = calculate_flood_risk(
        dem,
        slope,
        lulc,
        rainfall,
        population
    )

    # --------------------------------------------------------
    # CONVERT 0-1 TO 0-100%
    # --------------------------------------------------------

    flood_risk_percentage = (
        flood_risk * 100.0
    )

    # Make absolutely sure the output is 0-100
    valid = np.isfinite(
        flood_risk_percentage
    )

    flood_risk_percentage[valid] = np.clip(
        flood_risk_percentage[valid],
        0.0,
        100.0
    )

    # --------------------------------------------------------
    # OUTPUT PROFILE
    # --------------------------------------------------------

    output_profile = profile.copy()

    output_profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        width=reference_width,
        height=reference_height,
        transform=reference_transform,
        crs=reference_crs,
        nodata=-9999,
        compress="lzw"
    )

    # --------------------------------------------------------
    # CONVERT NaN TO NoData
    # --------------------------------------------------------

    output_data = np.where(
        np.isfinite(flood_risk_percentage),
        flood_risk_percentage,
        -9999
    ).astype(np.float32)

    # --------------------------------------------------------
    # SAVE OUTPUT
    # --------------------------------------------------------

    print(
        "\nSaving flood-risk raster..."
    )

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

    valid_output = np.isfinite(
        flood_risk_percentage
    )

    print(
        "\n========================================"
    )

    print(
        "AHP FLOOD RISK CALCULATION COMPLETE"
    )

    print(
        "========================================"
    )

    print("\nAHP Weights:")

    print(
        f"DEM                : {WEIGHTS['dem']}"
    )

    print(
        f"Slope              : {WEIGHTS['slope']}"
    )

    print(
        f"LULC               : {WEIGHTS['lulc']}"
    )

    print(
        f"Rainfall           : {WEIGHTS['rainfall']}"
    )

    print(
        f"Population Density : {WEIGHTS['population']}"
    )

    print(
        f"Total Weight       : "
        f"{sum(WEIGHTS.values())}"
    )

    if np.any(valid_output):

        minimum = np.nanmin(
            flood_risk_percentage
        )

        maximum = np.nanmax(
            flood_risk_percentage
        )

        mean = np.nanmean(
            flood_risk_percentage
        )

        print(
            "\nFlood Risk Index (%):"
        )

        print(
            f"Minimum Risk : {minimum:.2f}%"
        )

        print(
            f"Maximum Risk : {maximum:.2f}%"
        )

        print(
            f"Mean Risk    : {mean:.2f}%"
        )

        print(
            f"Valid Pixels : "
            f"{np.count_nonzero(valid_output)}"
        )

    else:

        print(
            "\nERROR: No valid output pixels."
        )

    print(
        "\nOutput:"
    )

    print(
        output_file
    )

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
