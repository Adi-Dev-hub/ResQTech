import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from osgeo import gdal, ogr, osr


# ============================================================
# GDAL SETTINGS
# ============================================================

gdal.UseExceptions()


# ============================================================
# CHECK ARGUMENTS
# ============================================================

if len(sys.argv) < 5:
    print(
        "Usage:\n"
        "python interpolation.py "
        "<rainfall_shapefile> "
        "<pune_boundary_shapefile> "
        "<no_data_value> "
        "<smoothened>"
    )
    sys.exit(1)


rainfall_path = Path(sys.argv[1]).resolve()
boundary_path = Path(sys.argv[2]).resolve()

no_data_value = float(sys.argv[3])

smoothened = (
    sys.argv[4].strip().lower() == "true"
)


# ============================================================
# PRINT START INFORMATION
# ============================================================

print()
print("==========================================")
print("PUNE DISTRICT RAINFALL INTERPOLATION")
print("==========================================")

print(f"Rainfall stations : {rainfall_path}")
print(f"Pune boundary     : {boundary_path}")
print(f"NoData value      : {no_data_value}")
print(f"Smoothened        : {smoothened}")
print()


# ============================================================
# CHECK FILES
# ============================================================

if not rainfall_path.exists():
    raise FileNotFoundError(
        f"Rainfall shapefile not found:\n{rainfall_path}"
    )

if not boundary_path.exists():
    raise FileNotFoundError(
        f"Pune boundary shapefile not found:\n{boundary_path}"
    )


# ============================================================
# OPEN SHAPEFILES
# ============================================================

driver = ogr.GetDriverByName("ESRI Shapefile")


rainfall_ds = driver.Open(
    str(rainfall_path),
    0
)

if rainfall_ds is None:
    raise RuntimeError(
        f"Could not open rainfall shapefile:\n{rainfall_path}"
    )


rainfall_layer = rainfall_ds.GetLayer()


boundary_ds = driver.Open(
    str(boundary_path),
    0
)

if boundary_ds is None:
    raise RuntimeError(
        f"Could not open Pune boundary:\n{boundary_path}"
    )


boundary_layer = boundary_ds.GetLayer()


# ============================================================
# FIND RAINFALL FIELD
# ============================================================

layer_defn = rainfall_layer.GetLayerDefn()

field_names = []

for i in range(layer_defn.GetFieldCount()):
    field_names.append(
        layer_defn.GetFieldDefn(i).GetName()
    )


print("Rainfall fields:")
print(field_names)


rainfall_field = None

for field in field_names:

    if field.lower() == "rainfall":

        rainfall_field = field
        break


if rainfall_field is None:
    raise RuntimeError(
        "Could not find a 'rainfall' field "
        "in the rainfall shapefile."
    )


print(
    f"Using rainfall field: {rainfall_field}"
)


# ============================================================
# GET CRS
# ============================================================

rainfall_srs = rainfall_layer.GetSpatialRef()
boundary_srs = boundary_layer.GetSpatialRef()


if rainfall_srs is None:
    raise RuntimeError(
        "Rainfall shapefile has no CRS."
    )


if boundary_srs is None:
    raise RuntimeError(
        "Pune boundary shapefile has no CRS."
    )


# ============================================================
# READ RAINFALL STATIONS
# ============================================================

station_points = []
station_values = []


rainfall_layer.ResetReading()


for feature in rainfall_layer:

    value = feature.GetField(
        rainfall_field
    )

    if value is None:
        continue

    try:
        rainfall_value = float(value)
    except (TypeError, ValueError):
        continue

    geometry = feature.GetGeometryRef()

    if geometry is None:
        continue

    geometry = geometry.Clone()

    geometry_type = geometry.GetGeometryType()

    if geometry_type in (
        ogr.wkbPoint,
        ogr.wkbPoint25D
    ):

        x = geometry.GetX()
        y = geometry.GetY()

    else:

        centroid = geometry.Centroid()

        x = centroid.GetX()
        y = centroid.GetY()

    station_points.append(
        (x, y)
    )

    station_values.append(
        rainfall_value
    )


print()
print(
    f"Number of rainfall stations: "
    f"{len(station_points)}"
)


if len(station_points) < 2:

    raise RuntimeError(
        "At least two rainfall stations "
        "are required."
    )


print(
    f"Rainfall range: "
    f"{min(station_values):.2f} "
    f"to "
    f"{max(station_values):.2f} mm"
)


# ============================================================
# REPROJECT STATIONS TO PUNE BOUNDARY CRS
# ============================================================

if not rainfall_srs.IsSame(boundary_srs):

    print()
    print("CRS mismatch detected.")
    print(
        "Reprojecting rainfall stations "
        "to Pune boundary CRS..."
    )

    transform = osr.CoordinateTransformation(
        rainfall_srs,
        boundary_srs
    )

    transformed_points = []

    for x, y in station_points:

        point = ogr.Geometry(
            ogr.wkbPoint
        )

        point.AddPoint(x, y)

        point.Transform(transform)

        transformed_points.append(
            (
                point.GetX(),
                point.GetY()
            )
        )

    station_points = transformed_points

    print(
        "Rainfall stations reprojected successfully."
    )

else:

    print()
    print(
        "Rainfall stations and boundary "
        "already use the same CRS."
    )


# ============================================================
# PUNE BOUNDARY EXTENT
# ============================================================

xmin, xmax, ymin, ymax = (
    boundary_layer.GetExtent()
)


print()
print("Pune district extent:")

print(f"X minimum : {xmin}")
print(f"X maximum : {xmax}")
print(f"Y minimum : {ymin}")
print(f"Y maximum : {ymax}")


# ============================================================
# RASTER RESOLUTION
# ============================================================
#
# 1000 map units = approximately 1 km
# because the Pune boundary CRS is projected.
#
# ============================================================

resolution = 1000.0


width = int(
    np.ceil(
        (xmax - xmin) / resolution
    )
)


height = int(
    np.ceil(
        (ymax - ymin) / resolution
    )
)


print()
print("Interpolation raster:")
print(f"Width      : {width}")
print(f"Height     : {height}")
print(
    f"Resolution : {resolution} map units"
)


# ============================================================
# CREATE MEMORY DATASOURCE
# ============================================================

memory_driver = ogr.GetDriverByName("Memory")

memory_ds = memory_driver.CreateDataSource(
    "rainfall_memory"
)

if memory_ds is None:
    raise RuntimeError(
        "Could not create memory datasource."
    )


# ============================================================
# CREATE STATION LAYER
# ============================================================

station_layer = memory_ds.CreateLayer(
    "rainfall_stations",
    srs=boundary_srs,
    geom_type=ogr.wkbPoint
)

if station_layer is None:
    raise RuntimeError(
        "Could not create station layer."
    )


# ============================================================
# CREATE RAINFALL FIELD
# ============================================================

field_defn = ogr.FieldDefn(
    rainfall_field,
    ogr.OFTReal
)

station_layer.CreateField(
    field_defn
)


# ============================================================
# WRITE STATIONS
# ============================================================

for (
    (x, y),
    rainfall_value
) in zip(
    station_points,
    station_values
):

    point = ogr.Geometry(
        ogr.wkbPoint
    )

    point.AddPoint(
        x,
        y
    )

    feature = ogr.Feature(
        station_layer.GetLayerDefn()
    )

    feature.SetField(
        rainfall_field,
        rainfall_value
    )

    feature.SetGeometry(
        point
    )

    station_layer.CreateFeature(
        feature
    )

    feature = None
    point = None


print()
print(
    "Station layer prepared successfully."
)


# ============================================================
# IDW ALGORITHM
# ============================================================

if smoothened:

    algorithm = (
        "invdist:"
        "power=2:"
        "smoothing=1.0:"
        "radius1=0:"
        "radius2=0:"
        "angle=0:"
        "max_points=0:"
        "min_points=1:"
        f"nodata={no_data_value}"
    )

else:

    algorithm = (
        "invdist:"
        "power=2:"
        "smoothing=0:"
        "radius1=0:"
        "radius2=0:"
        "angle=0:"
        "max_points=0:"
        "min_points=1:"
        f"nodata={no_data_value}"
    )


# ============================================================
# RUN INTERPOLATION
# ============================================================

print()
print("Running IDW interpolation...")
print(
    f"Algorithm: {algorithm}"
)


# IMPORTANT:
# gdal.Grid receives the GDAL datasource,
# not the OGR layer.

interpolation_ds = gdal.Grid(
    "",
    memory_ds,
    format="MEM",
    outputBounds=[
        xmin,
        ymin,
        xmax,
        ymax
    ],
    width=width,
    height=height,
    outputType=gdal.GDT_Float32,
    zfield=rainfall_field,
    algorithm=algorithm
)


if interpolation_ds is None:
    raise RuntimeError(
        "GDAL interpolation failed."
    )


# ============================================================
# READ INTERPOLATED RASTER
# ============================================================

rainfall_grid = (
    interpolation_ds
    .ReadAsArray()
    .astype(np.float32)
)


print(
    "Interpolation completed."
)


# ============================================================
# CREATE RASTER GEOTRANSFORM
# ============================================================

x_resolution = (
    xmax - xmin
) / width


y_resolution = (
    ymax - ymin
) / height


geotransform = [
    xmin,
    x_resolution,
    0,
    ymax,
    0,
    -y_resolution
]


# ============================================================
# CREATE PUNE MASK
# ============================================================

print()
print(
    "Creating Pune district mask..."
)


mask_driver = gdal.GetDriverByName(
    "MEM"
)


mask_ds = mask_driver.Create(
    "",
    width,
    height,
    1,
    gdal.GDT_Byte
)


mask_ds.SetGeoTransform(
    geotransform
)


mask_ds.SetProjection(
    boundary_srs.ExportToWkt()
)


mask_band = (
    mask_ds.GetRasterBand(1)
)


mask_band.Fill(0)


# ============================================================
# RASTERIZE BOUNDARY
# ============================================================

gdal.RasterizeLayer(
    mask_ds,
    [1],
    boundary_layer,
    burn_values=[1]
)


pune_mask = (
    mask_band.ReadAsArray()
)


print(
    "Pune district mask created."
)


# ============================================================
# CREATE CLIPPED RAINFALL
# ============================================================

rainfall_clipped = (
    rainfall_grid.copy()
)


# Outside Pune = NoData

rainfall_clipped[
    pune_mask == 0
] = np.float32(
    no_data_value
)


# Invalid values = NoData

rainfall_clipped[
    ~np.isfinite(
        rainfall_clipped
    )
] = np.float32(
    no_data_value
)


# ============================================================
# STATISTICS
# ============================================================

valid_mask = (
    rainfall_clipped != no_data_value
)


valid_values = rainfall_clipped[
    valid_mask
]


if valid_values.size == 0:

    raise RuntimeError(
        "No valid rainfall cells found."
    )


min_rainfall = float(
    np.min(valid_values)
)

max_rainfall = float(
    np.max(valid_values)
)

mean_rainfall = float(
    np.mean(valid_values)
)


print()
print("Rainfall statistics:")
print(
    f"Minimum : {min_rainfall:.2f} mm"
)

print(
    f"Maximum : {max_rainfall:.2f} mm"
)

print(
    f"Mean    : {mean_rainfall:.2f} mm"
)


# ============================================================
# OUTPUT FILE
# ============================================================

output_path = (
    Path("D:/SIH/ADITYA_PROJECT/WORKING_PROJECT/Work/shapetiff")
    / "pune_rainfall_interpolated.tif"
)


# ============================================================
# DELETE OLD OUTPUT IF IT EXISTS
# ============================================================

if output_path.exists():

    print()
    print(
        "Existing output raster found."
    )

    print(
        "Trying to replace it..."
    )

    try:

        output_path.unlink()

    except PermissionError:

        raise PermissionError(
            "\nThe output TIFF is currently "
            "open or locked.\n\n"
            "Close 'pune_rainfall_interpolated.tif' "
            "in QGIS or any other program and "
            "run the script again."
        )


# ============================================================
# SAVE FINAL TIFF
# ============================================================

print()
print(
    "Saving final rainfall raster..."
)


output_driver = gdal.GetDriverByName(
    "GTiff"
)


output_ds = output_driver.Create(
    str(output_path),
    width,
    height,
    1,
    gdal.GDT_Float32,
    options=[
        "COMPRESS=LZW",
        "TILED=YES"
    ]
)


if output_ds is None:

    raise RuntimeError(
        "Could not create output GeoTIFF."
    )


output_ds.SetGeoTransform(
    geotransform
)


output_ds.SetProjection(
    boundary_srs.ExportToWkt()
)


output_band = (
    output_ds.GetRasterBand(1)
)


output_band.WriteArray(
    rainfall_clipped
)


output_band.SetNoDataValue(
    no_data_value
)


output_band.FlushCache()

output_ds.FlushCache()


# ============================================================
# CLOSE OUTPUT BEFORE PREVIEW
# ============================================================

output_ds = None


# ============================================================
# CREATE PREVIEW
# ============================================================

print()
print(
    "Creating rainfall interpolation preview..."
)


# ------------------------------------------------------------
# MASK ARRAYS FOR DISPLAY
# ------------------------------------------------------------

original_display = np.ma.masked_where(
    pune_mask == 0,
    np.ones_like(pune_mask, dtype=float)
)


unclipped_display = np.ma.masked_where(
    rainfall_grid == no_data_value,
    rainfall_grid
)


clipped_display = np.ma.masked_where(
    rainfall_clipped == no_data_value,
    rainfall_clipped
)


# ============================================================
# CREATE 3-PHASE PREVIEW
# ============================================================

fig, axes = plt.subplots(
    1,
    3,
    figsize=(20, 7)
)


# ============================================================
# PHASE 1
# ORIGINAL PUNE BOUNDARY
# ============================================================

axes[0].imshow(
    original_display,
    extent=[
        xmin,
        xmax,
        ymin,
        ymax
    ],
    origin="upper",
    cmap="gray",
    interpolation="nearest"
)


# Plot Pune boundary outline

boundary_layer.ResetReading()


for feature in boundary_layer:

    geometry = (
        feature.GetGeometryRef()
    )

    if geometry is None:
        continue

    geometry_type = (
        geometry.GetGeometryType()
    )


    def plot_geometry(
        geom,
        axis
    ):

        geom_type = (
            geom.GetGeometryType()
        )

        if geom_type in (
            ogr.wkbPolygon,
            ogr.wkbPolygon25D
        ):

            ring = geom.GetGeometryRef(0)

            points = ring.GetPoints()

            if len(points) > 1:

                xs = [
                    p[0]
                    for p in points
                ]

                ys = [
                    p[1]
                    for p in points
                ]

                axis.plot(
                    xs,
                    ys,
                    linewidth=2
                )


        elif geom_type in (
            ogr.wkbMultiPolygon,
            ogr.wkbMultiPolygon25D
        ):

            for i in range(
                geom.GetGeometryCount()
            ):

                plot_geometry(
                    geom.GetGeometryRef(i),
                    axis
                )


    plot_geometry(
        geometry,
        axes[0]
    )


axes[0].set_title(
    "Phase 1: Original Pune District Boundary"
)

axes[0].set_xlabel(
    "X"
)

axes[0].set_ylabel(
    "Y"
)


# ============================================================
# PHASE 2
# ORIGINAL INTERPOLATION
# ============================================================

im2 = axes[1].imshow(
    unclipped_display,
    extent=[
        xmin,
        xmax,
        ymin,
        ymax
    ],
    origin="upper",
    cmap="viridis",
    interpolation="nearest",
    vmin=min_rainfall,
    vmax=max_rainfall
)


axes[1].set_title(
    "Phase 2: Rainfall Interpolation"
)

axes[1].set_xlabel(
    "X"
)

axes[1].set_ylabel(
    "Y"
)


fig.colorbar(
    im2,
    ax=axes[1],
    label="Rainfall (mm)"
)


# ============================================================
# PHASE 3
# FINAL CLIPPED PUNE RAINFALL
# ============================================================

im3 = axes[2].imshow(
    clipped_display,
    extent=[
        xmin,
        xmax,
        ymin,
        ymax
    ],
    origin="upper",
    cmap="viridis",
    interpolation="nearest",
    vmin=min_rainfall,
    vmax=max_rainfall
)


axes[2].set_title(
    "Phase 3: Rainfall Clipped to Pune District"
)

axes[2].set_xlabel(
    "X"
)

axes[2].set_ylabel(
    "Y"
)


fig.colorbar(
    im3,
    ax=axes[2],
    label="Rainfall (mm)"
)


# ============================================================
# PREVIEW LAYOUT
# ============================================================

fig.suptitle(
    "Pune District Rainfall Interpolation",
    fontsize=16
)


plt.tight_layout()


# ============================================================
# SAVE PREVIEW IMAGE
# ============================================================

preview_path = (
    Path("D:/SIH/ADITYA_PROJECT/WORKING_PROJECT/Work/shapetiff")
    / "pune_rainfall_interpolation_preview.png"
)


plt.savefig(
    str(preview_path),
    dpi=150,
    bbox_inches="tight"
)


print()
print(
    "Preview saved to:"
)

print(
    preview_path
)


# ============================================================
# SHOW PREVIEW
# ============================================================

print()
print(
    "Opening rainfall interpolation preview..."
)


plt.show()


# ============================================================
# CLOSE DATASETS
# ============================================================

interpolation_ds = None
mask_ds = None
memory_ds = None
rainfall_ds = None
boundary_ds = None


# ============================================================
# SUCCESS
# ============================================================

print()
print("========================================")
print("SUCCESS")
print("========================================")

print()
print(
    "Final rainfall raster:"
)

print(
    output_path
)

print()
print(
    "Preview image:"
)

print(
    preview_path
)

print()
print(
    "The final raster covers the complete "
    "Pune district boundary."
)

print(
    "Areas outside Pune are NoData."
)

print()
print("========================================")