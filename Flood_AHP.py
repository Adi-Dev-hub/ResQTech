import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.features import geometry_mask

import matplotlib

# Use a non-interactive backend so the preview can be saved
# without requiring Matplotlib to render the entire raster
matplotlib.use("Agg")

import matplotlib.pyplot as plt

import geopandas as gpd


# ============================================================
# FLOOD RISK USING AHP
#
# Factors:
#   1. DEM
#   2. Slope
#   3. LULC
#   4. Rainfall
#   5. Population Density
#
# OUTPUT:
#   Continuous flood-risk percentage
#
# Example:
#   17.88 = 17.88% risk
#   50.00 = 50.00% risk
#   84.52 = 84.52% risk
#
# NO 1-5 CLASSIFICATION
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
# LULC RISK VALUES
#
# IMPORTANT:
# These values MUST match your LULC raster classes.
#
# Current mapping:
#
# 20  = Forest
# 30  = Shrubland / grassland
# 40  = Cropland
# 50  = Built-up
# 60  = Bare / sparse vegetation
# 80  = Water
# 90  = Wetland
# 111,112,114,116,122,124,126 = other classes
#
# These are example risk scores.
# Higher value = higher flood risk.
# ============================================================

LULC_RISK = {

    # Forest
    20: 0.20,

    # Shrub / grassland
    30: 0.35,

    # Cropland
    40: 0.60,

    # Built-up
    50: 0.90,

    # Bare / sparse land
    60: 0.70,

    # Water
    80: 1.00,

    # Wetland
    90: 0.85,

    # Additional classes
    111: 0.90,
    112: 0.80,
    114: 0.70,
    116: 0.70,
    122: 0.60,
    124: 0.50,
    126: 0.40
}


# ============================================================
# READ RASTER
# ============================================================

def read_raster(path):

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Raster not found:\n{path}"
        )

    print(f"    Opening: {path}")

    with rasterio.open(path) as src:

        data = src.read(1).astype(np.float32)

        profile = src.profile.copy()

        transform = src.transform

        crs = src.crs

        nodata = src.nodata

        bounds = src.bounds

        width = src.width
        height = src.height

    # Convert NoData to NaN
    if nodata is not None:

        data[data == nodata] = np.nan

    # Also remove infinite values
    data[~np.isfinite(data)] = np.nan

    return (
        data,
        profile,
        transform,
        crs,
        bounds,
        width,
        height
    )


# ============================================================
# ALIGN RASTER TO DEM
#
# IMPORTANT:
# We use actual geospatial reprojection/resampling instead
# of simply resizing the NumPy array.
# ============================================================

def align_to_reference(
    source_file,
    reference_profile,
    reference_transform,
    reference_crs,
    reference_shape
):

    with rasterio.open(source_file) as src:

        source_data = src.read(1).astype(np.float32)

        source_nodata = src.nodata

        if source_nodata is None:
            source_nodata = -9999.0

        source_data[
            source_data == source_nodata
        ] = np.nan

        source_data[
            ~np.isfinite(source_data)
        ] = np.nan

        destination = np.full(
            reference_shape,
            np.nan,
            dtype=np.float32
        )

        reproject(
            source=source_data,
            destination=destination,

            src_transform=src.transform,
            src_crs=src.crs,

            dst_transform=reference_transform,
            dst_crs=reference_crs,

            src_nodata=np.nan,
            dst_nodata=np.nan,

            resampling=Resampling.bilinear
        )

    return destination


# ============================================================
# ALIGN LULC
#
# LULC is categorical data.
#
# Therefore use nearest-neighbour resampling.
# ============================================================

def align_lulc(
    source_file,
    reference_transform,
    reference_crs,
    reference_shape
):

    with rasterio.open(source_file) as src:

        source_data = src.read(1).astype(np.float32)

        source_nodata = src.nodata

        if source_nodata is None:
            source_nodata = -9999.0

        source_data[
            source_data == source_nodata
        ] = np.nan

        destination = np.full(
            reference_shape,
            np.nan,
            dtype=np.float32
        )

        reproject(
            source=source_data,
            destination=destination,

            src_transform=src.transform,
            src_crs=src.crs,

            dst_transform=reference_transform,
            dst_crs=reference_crs,

            src_nodata=np.nan,
            dst_nodata=np.nan,

            resampling=Resampling.nearest
        )

    return destination


# ============================================================
# MIN-MAX NORMALIZATION
#
# Higher value = higher risk
#
# Result:
#   0 = lowest risk
#   1 = highest risk
# ============================================================

def minmax_normalize(data):

    result = np.full(
        data.shape,
        np.nan,
        dtype=np.float32
    )

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
# Lower value = higher risk
#
# Used for:
#   DEM
#   Slope
# ============================================================

def inverse_normalize(data):

    result = np.full(
        data.shape,
        np.nan,
        dtype=np.float32
    )

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
# LULC RISK
# ============================================================

def classify_lulc(lulc):

    risk = np.full(
        lulc.shape,
        np.nan,
        dtype=np.float32
    )

    unique_classes = np.unique(
        lulc[np.isfinite(lulc)]
    )

    unmapped = []

    for value in unique_classes:

        class_value = int(round(float(value)))

        if class_value in LULC_RISK:

            risk[
                lulc == class_value
            ] = LULC_RISK[class_value]

        else:

            unmapped.append(
                class_value
            )

    if unmapped:

        print()
        print(
            "WARNING:"
        )

        print(
            "Some LULC classes have no "
            "flood-risk mapping."
        )

        print(
            "Unmapped classes:"
        )

        for value in unmapped:

            print(
                f"    {value}"
            )

    return risk


# ============================================================
# FACTOR RISK FUNCTIONS
# ============================================================

def dem_risk(dem):

    return inverse_normalize(dem)


def slope_risk(slope):

    return inverse_normalize(slope)


def rainfall_risk(rainfall):

    return minmax_normalize(rainfall)


def population_risk(population):

    return minmax_normalize(population)


# ============================================================
# CALCULATE AHP FLOOD RISK
# ============================================================

def calculate_flood_risk(
    dem,
    slope,
    lulc,
    rainfall,
    population
):

    print()
    print(
        "Calculating normalized risk layers..."
    )

    # --------------------------------------------------------
    # NORMALIZE EACH FACTOR
    # --------------------------------------------------------

    dem_score = dem_risk(dem)

    slope_score = slope_risk(slope)

    lulc_score = classify_lulc(lulc)

    rainfall_score = rainfall_risk(
        rainfall
    )

    population_score = population_risk(
        population
    )

    # --------------------------------------------------------
    # PRINT VALID CELLS
    # --------------------------------------------------------

    print()
    print(
        "Valid normalized cells:"
    )

    print(
        "DEM        :",
        np.count_nonzero(
            np.isfinite(dem_score)
        )
    )

    print(
        "Slope      :",
        np.count_nonzero(
            np.isfinite(slope_score)
        )
    )

    print(
        "LULC       :",
        np.count_nonzero(
            np.isfinite(lulc_score)
        )
    )

    print(
        "Rainfall   :",
        np.count_nonzero(
            np.isfinite(rainfall_score)
        )
    )

    print(
        "Population :",
        np.count_nonzero(
            np.isfinite(population_score)
        )
    )

    # --------------------------------------------------------
    # COMMON VALID AREA
    # --------------------------------------------------------

    common_valid = (

        np.isfinite(dem_score)

        &

        np.isfinite(slope_score)

        &

        np.isfinite(lulc_score)

        &

        np.isfinite(rainfall_score)

        &

        np.isfinite(population_score)
    )

    print()
    print(
        "Common valid cells:",
        np.count_nonzero(
            common_valid
        )
    )

    # --------------------------------------------------------
    # WEIGHTED AHP OVERLAY
    # --------------------------------------------------------

    flood_risk = np.full(
        dem.shape,
        np.nan,
        dtype=np.float32
    )

    flood_risk[common_valid] = (

        WEIGHTS["dem"] *
        dem_score[common_valid]

        +

        WEIGHTS["slope"] *
        slope_score[common_valid]

        +

        WEIGHTS["lulc"] *
        lulc_score[common_valid]

        +

        WEIGHTS["rainfall"] *
        rainfall_score[common_valid]

        +

        WEIGHTS["population"] *
        population_score[common_valid]
    )

    return flood_risk


# ============================================================
# CREATE PUNE MASK
# ============================================================

def create_pune_mask(
    boundary_file,
    reference_shape,
    reference_transform,
    reference_crs
):

    print()
    print(
        "Creating Pune district mask..."
    )

    boundary = gpd.read_file(
        boundary_file
    )

    if boundary.empty:

        raise RuntimeError(
            "Pune boundary shapefile is empty."
        )

    print(
        "Boundary CRS:",
        boundary.crs
    )

    if boundary.crs is None:

        raise RuntimeError(
            "Pune boundary has no CRS."
        )

    # Reproject boundary to DEM CRS
    if boundary.crs != reference_crs:

        print(
            "Reprojecting Pune boundary "
            "to DEM CRS..."
        )

        boundary = boundary.to_crs(
            reference_crs
        )

    geometries = [
        geom
        for geom in boundary.geometry
        if geom is not None
        and not geom.is_empty
    ]

    if not geometries:

        raise RuntimeError(
            "No valid geometries found "
            "in Pune boundary."
        )

    mask = geometry_mask(
        geometries,

        out_shape=reference_shape,

        transform=reference_transform,

        invert=True
    )

    print(
        "Pune mask valid cells:",
        np.count_nonzero(mask)
    )

    return mask, boundary


# ============================================================
# CREATE LOW-MEMORY PREVIEW
#
# The DEM is 6623 x 5399.
#
# Rendering this directly requires a large amount of RAM.
#
# We therefore downsample ONLY the preview.
#
# The actual TIFF remains full resolution.
# ============================================================

def downsample_preview(
    data,
    max_dimension=1200
):

    height, width = data.shape

    scale = min(
        1.0,
        max_dimension /
        max(height, width)
    )

    if scale >= 1.0:

        return data

    new_height = max(
        1,
        int(height * scale)
    )

    new_width = max(
        1,
        int(width * scale)
    )

    # Use block averaging where possible.
    # This avoids creating huge RGBA arrays.

    row_edges = np.linspace(
        0,
        height,
        new_height + 1,
        dtype=int
    )

    col_edges = np.linspace(
        0,
        width,
        new_width + 1,
        dtype=int
    )

    output = np.full(
        (new_height, new_width),
        np.nan,
        dtype=np.float32
    )

    for r in range(new_height):

        r1 = row_edges[r]
        r2 = row_edges[r + 1]

        if r2 <= r1:
            continue

        row = data[r1:r2]

        for c in range(new_width):

            c1 = col_edges[c]
            c2 = col_edges[c + 1]

            if c2 <= c1:
                continue

            block = row[:, c1:c2]

            valid = block[
                np.isfinite(block)
            ]

            if valid.size:

                output[r, c] = np.mean(
                    valid
                )

    return output


# ============================================================
# CREATE 3-STAGE PREVIEW
# ============================================================

def create_preview(
    dem,
    flood_risk_before_mask,
    flood_risk_final,
    pune_mask,
    boundary,
    bounds,
    preview_path
):

    print()
    print(
        "======================================"
    )

    print(
        "CREATING FLOOD RISK PREVIEW"
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # LOW MEMORY PREVIEW
    # --------------------------------------------------------

    print(
        "Downsampling preview for display..."
    )

    dem_preview = downsample_preview(
        dem
    )

    risk_before_preview = (
        downsample_preview(
            flood_risk_before_mask
        )
    )

    risk_final_preview = (
        downsample_preview(
            flood_risk_final
        )
    )

    mask_preview = downsample_preview(
        pune_mask.astype(np.float32)
    )

    # --------------------------------------------------------
    # MASK OUTSIDE PUNE
    # --------------------------------------------------------

    dem_preview = np.where(
        mask_preview > 0.5,
        dem_preview,
        np.nan
    )

    risk_final_preview = np.where(
        mask_preview > 0.5,
        risk_final_preview,
        np.nan
    )

    # --------------------------------------------------------
    # EXTENT
    # --------------------------------------------------------

    xmin = bounds.left
    xmax = bounds.right
    ymin = bounds.bottom
    ymax = bounds.top

    # --------------------------------------------------------
    # CREATE FIGURE
    # --------------------------------------------------------

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(18, 6)
    )

    # ========================================================
    # STAGE 1
    # DEM
    # ========================================================

    im1 = axes[0].imshow(
        dem_preview,

        extent=[
            xmin,
            xmax,
            ymin,
            ymax
        ],

        origin="upper",

        cmap="terrain",

        interpolation="nearest"
    )

    axes[0].set_title(
        "Stage 1: Pune DEM"
    )

    axes[0].set_xlabel(
        "Longitude"
    )

    axes[0].set_ylabel(
        "Latitude"
    )

    fig.colorbar(
        im1,
        ax=axes[0],
        label="Elevation"
    )

    # ========================================================
    # STAGE 2
    # AHP RISK BEFORE PUNE MASK
    # ========================================================

    im2 = axes[1].imshow(
        risk_before_preview * 100,

        extent=[
            xmin,
            xmax,
            ymin,
            ymax
        ],

        origin="upper",

        cmap="RdYlGn_r",

        interpolation="nearest",

        vmin=0,

        vmax=100
    )

    axes[1].set_title(
        "Stage 2: AHP Flood Risk"
    )

    axes[1].set_xlabel(
        "Longitude"
    )

    axes[1].set_ylabel(
        "Latitude"
    )

    fig.colorbar(
        im2,
        ax=axes[1],
        label="Flood Risk (%)"
    )

    # ========================================================
    # STAGE 3
    # FINAL PUNE FLOOD RISK
    # ========================================================

    im3 = axes[2].imshow(
        risk_final_preview * 100,

        extent=[
            xmin,
            xmax,
            ymin,
            ymax
        ],

        origin="upper",

        cmap="RdYlGn_r",

        interpolation="nearest",

        vmin=0,

        vmax=100
    )

    # --------------------------------------------------------
    # PLOT PUNE BOUNDARY
    # --------------------------------------------------------

    boundary.boundary.plot(
        ax=axes[2],
        linewidth=1
    )

    axes[2].set_title(
        "Stage 3: Final Pune Flood Risk"
    )

    axes[2].set_xlabel(
        "Longitude"
    )

    axes[2].set_ylabel(
        "Latitude"
    )

    fig.colorbar(
        im3,
        ax=axes[2],
        label="Flood Risk (%)"
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    fig.suptitle(
        "Pune District AHP Flood Risk",
        fontsize=16
    )

    plt.tight_layout()

    # --------------------------------------------------------
    # SAVE PREVIEW
    # --------------------------------------------------------

    print(
        "Saving preview..."
    )

    plt.savefig(
        str(preview_path),
        dpi=120,
        bbox_inches="tight"
    )

    plt.close(
        fig
    )

    print()
    print(
        "Preview successfully saved:"
    )

    print(
        preview_path
    )


# ============================================================
# SAVE FLOOD RISK TIFF
#
# IMPORTANT:
#
# Risk is saved as percentage.
#
# Example:
#
# 17.88 means 17.88%
# 34.75 means 34.75%
# 84.52 means 84.52%
#
# NO CLASSIFICATION.
#
# tiled=False prevents:
# BLOCKXSIZE must be a multiple of 16
# ============================================================

def save_flood_risk(
    flood_risk,
    reference_profile,
    output_file
):

    print()
    print(
        "======================================"
    )

    print(
        "SAVING FLOOD RISK TIFF"
    )

    print(
        "======================================"
    )

    output_path = Path(
        output_file
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Convert 0-1 risk to 0-100 percentage
    # --------------------------------------------------------

    risk_percentage = (
        flood_risk * 100.0
    )

    risk_percentage = np.where(
        np.isfinite(risk_percentage),

        risk_percentage,

        -9999
    ).astype(
        np.float32
    )

    # --------------------------------------------------------
    # OUTPUT PROFILE
    # --------------------------------------------------------

    output_profile = reference_profile.copy()

    output_profile.update(

        driver="GTiff",

        dtype="float32",

        count=1,

        nodata=-9999,

        compress="lzw",

        tiled=False
    )

    # IMPORTANT:
    # Do NOT use:
    #
    # tiled=True
    #
    # blockxsize=
    #
    # blockysize=

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    with rasterio.open(
        output_path,
        "w",
        **output_profile
    ) as dst:

        dst.write(
            risk_percentage,
            1
        )

        dst.set_band_description(
            1,
            "Flood Risk Percentage"
        )

        dst.update_tags(
            1,

            DESCRIPTION=(
                "Continuous AHP Flood Risk "
                "Percentage"
            ),

            MIN_RISK_PERCENT=(
                "Minimum valid flood risk "
                "percentage"
            ),

            MAX_RISK_PERCENT=(
                "Maximum valid flood risk "
                "percentage"
            )
        )

    print()
    print(
        "Flood-risk TIFF saved:"
    )

    print(
        output_path
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # CHECK ARGUMENTS
    # --------------------------------------------------------

    if len(sys.argv) != 8:

        print(
            "\nUsage:\n"
            "python Flood_AHP.py "
            "<DEM> "
            "<SLOPE> "
            "<LULC> "
            "<RAINFALL> "
            "<POPULATION> "
            "<PUNE_BOUNDARY> "
            "<OUTPUT>\n"
        )

        print(
            "Example:\n"
        )

        print(
            'python "Work\\Flood_AHP.py" '
            '"Work\\shapetiff\\puneDem.tif" '
            '"Work\\shapetiff\\Slope_Tiff.tif" '
            '"Work\\shapetiff\\punelc.tif" '
            '"Work\\shapetiff\\pune_rainfall_interpolated.tif" '
            '"Work\\shapetiff\\Clipped_PopDensity.tif" '
            '"Work\\shapetiff\\Pune_shape_file.shp" '
            '"Work\\shapetiff\\pune_flood_risk.tif"'
        )

        sys.exit(1)

    # --------------------------------------------------------
    # INPUTS
    # --------------------------------------------------------

    dem_file = Path(
        sys.argv[1]
    )

    slope_file = Path(
        sys.argv[2]
    )

    lulc_file = Path(
        sys.argv[3]
    )

    rainfall_file = Path(
        sys.argv[4]
    )

    population_file = Path(
        sys.argv[5]
    )

    boundary_file = Path(
        sys.argv[6]
    )

    output_file = Path(
        sys.argv[7]
    )

    # --------------------------------------------------------
    # CHECK INPUT FILES
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        "CHECKING INPUT FILES"
    )

    print(
        "======================================"
    )

    input_files = [

        ("DEM", dem_file),

        ("Slope", slope_file),

        ("LULC", lulc_file),

        ("Rainfall", rainfall_file),

        ("Population", population_file),

        ("Pune Boundary", boundary_file)
    ]

    for name, path in input_files:

        if not path.exists():

            raise FileNotFoundError(
                f"{name} file not found:\n{path}"
            )

        print(
            f"OK: {path.resolve()}"
        )

    # --------------------------------------------------------
    # READ DEM
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        "Reading DEM..."
    )

    print(
        "    Opening:",
        dem_file
    )

    with rasterio.open(
        dem_file
    ) as src:

        dem = src.read(
            1
        ).astype(
            np.float32
        )

        dem_profile = src.profile.copy()

        dem_transform = src.transform

        dem_crs = src.crs

        dem_shape = (
            src.height,
            src.width
        )

        dem_bounds = src.bounds

        dem_nodata = src.nodata

    if dem_nodata is not None:

        dem[
            dem == dem_nodata
        ] = np.nan

    dem[
        ~np.isfinite(dem)
    ] = np.nan

    # --------------------------------------------------------
    # DEM INFORMATION
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        "DEM REFERENCE GRID"
    )

    print(
        "======================================"
    )

    print(
        "Width      :",
        dem_shape[1]
    )

    print(
        "Height     :",
        dem_shape[0]
    )

    print(
        "CRS        :",
        dem_crs
    )

    print(
        "Pixel size :",
        abs(dem_transform.a),
        abs(dem_transform.e)
    )

    print(
        "Extent     :",
        dem_bounds.left,
        dem_bounds.bottom,
        dem_bounds.right,
        dem_bounds.top
    )

    # --------------------------------------------------------
    # READ OTHER RASTERS
    # --------------------------------------------------------

    print()
    print(
        "Reading Slope..."
    )

    slope = align_to_reference(

        slope_file,

        dem_profile,

        dem_transform,

        dem_crs,

        dem_shape
    )

    print()
    print(
        "Reading LULC..."
    )

    lulc = align_lulc(

        lulc_file,

        dem_transform,

        dem_crs,

        dem_shape
    )

    print()
    print(
        "Reading Rainfall..."
    )

    rainfall = align_to_reference(

        rainfall_file,

        dem_profile,

        dem_transform,

        dem_crs,

        dem_shape
    )

    print()
    print(
        "Reading Population Density..."
    )

    population = align_to_reference(

        population_file,

        dem_profile,

        dem_transform,

        dem_crs,

        dem_shape
    )

    print()
    print(
        "======================================"
    )

    print(
        "All rasters aligned to DEM."
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    def print_stats(
        name,
        data
    ):

        valid = data[
            np.isfinite(data)
        ]

        if valid.size == 0:

            print(
                f"{name}: NO VALID DATA"
            )

            return

        print()
        print(
            f"{name} statistics:"
        )

        print(
            f"Minimum : {np.min(valid):.4f}"
        )

        print(
            f"Maximum : {np.max(valid):.4f}"
        )

        print(
            f"Mean    : {np.mean(valid):.4f}"
        )

    print_stats(
        "DEM",
        dem
    )

    print_stats(
        "Slope",
        slope
    )

    print_stats(
        "Rainfall",
        rainfall
    )

    print_stats(
        "Population Density",
        population
    )

    # --------------------------------------------------------
    # AHP
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        "RUNNING AHP WEIGHTED OVERLAY"
    )

    print(
        "======================================"
    )

    flood_risk = calculate_flood_risk(

        dem,

        slope,

        lulc,

        rainfall,

        population
    )

    # --------------------------------------------------------
    # CHECK
    # --------------------------------------------------------

    print()
    print(
        "Checking calculated flood risk..."
    )

    valid_risk = np.isfinite(
        flood_risk
    )

    if not np.any(valid_risk):

        raise RuntimeError(
            "\nNo valid flood-risk cells "
            "were calculated.\n\n"
            "This means at least one of the "
            "five input factors contains "
            "NoData over the entire common area."
        )

    # --------------------------------------------------------
    # CREATE PUNE MASK
    # --------------------------------------------------------

    pune_mask, boundary = create_pune_mask(

        boundary_file,

        dem_shape,

        dem_transform,

        dem_crs
    )

    # --------------------------------------------------------
    # SAVE COPY BEFORE MASK
    # --------------------------------------------------------

    flood_risk_before_mask = (
        flood_risk.copy()
    )

    # --------------------------------------------------------
    # APPLY PUNE BOUNDARY
    # --------------------------------------------------------

    print()
    print(
        "Applying Pune district boundary..."
    )

    flood_risk[
        ~pune_mask
    ] = np.nan

    valid_risk = np.isfinite(
        flood_risk
    )

    if not np.any(valid_risk):

        raise RuntimeError(
            "\nNo valid flood-risk cells "
            "exist inside the Pune boundary.\n\n"
            "Check:\n"
            "1. Pune boundary CRS\n"
            "2. DEM CRS\n"
            "3. Raster extents\n"
            "4. Pune_shape_file.shp"
        )

    # --------------------------------------------------------
    # RESULT STATISTICS
    # --------------------------------------------------------

    risk_values = flood_risk[
        valid_risk
    ]

    min_risk = float(
        np.min(risk_values)
    )

    max_risk = float(
        np.max(risk_values)
    )

    mean_risk = float(
        np.mean(risk_values)
    )

    print()
    print(
        "======================================"
    )

    print(
        "FLOOD RISK RESULT"
    )

    print(
        "======================================"
    )

    print(
        f"Minimum Risk : {min_risk * 100:.2f}%"
    )

    print(
        f"Maximum Risk : {max_risk * 100:.2f}%"
    )

    print(
        f"Mean Risk    : {mean_risk * 100:.2f}%"
    )

    print(
        f"Valid cells  : {np.count_nonzero(valid_risk)}"
    )

    # --------------------------------------------------------
    # PREVIEW FIRST
    # --------------------------------------------------------

    preview_path = (
        output_file.parent /
        "pune_flood_risk_preview.png"
    )

    create_preview(

        dem,

        flood_risk_before_mask,

        flood_risk,

        pune_mask,

        boundary,

        dem_bounds,

        preview_path
    )

    # --------------------------------------------------------
    # SAVE TIFF AFTER PREVIEW
    # --------------------------------------------------------

    save_flood_risk(

        flood_risk,

        dem_profile,

        output_file
    )

    # --------------------------------------------------------
    # FINAL INFORMATION
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        "AHP FLOOD RISK CALCULATION COMPLETE"
    )

    print(
        "======================================"
    )

    print()
    print(
        "AHP Weights:"
    )

    print(
        "DEM               :",
        WEIGHTS["dem"]
    )

    print(
        "Slope             :",
        WEIGHTS["slope"]
    )

    print(
        "LULC              :",
        WEIGHTS["lulc"]
    )

    print(
        "Rainfall          :",
        WEIGHTS["rainfall"]
    )

    print(
        "Population Density:",
        WEIGHTS["population"]
    )

    print()
    print(
        "Final flood-risk TIFF:"
    )

    print(
        output_file
    )

    print()
    print(
        "Preview:"
    )

    print(
        preview_path
    )

    print()
    print(
        "The TIFF contains CONTINUOUS "
        "flood-risk percentages."
    )

    print(
        "No 1-5 flood classification "
        "was performed."
    )

    print()
    print(
        "Example interpretation:"
    )

    print(
        "20.00 = 20% calculated AHP risk"
    )

    print(
        "50.00 = 50% calculated AHP risk"
    )

    print(
        "80.00 = 80% calculated AHP risk"
    )

    print()
    print(
        "======================================"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()