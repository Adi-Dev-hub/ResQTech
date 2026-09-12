import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

input_file = "shapetiff/puneDem.tif"
output_file = "shapetiff/puneDem_meter.tif"

# UTM Zone 43N - suitable for Pune
target_crs = "EPSG:32643"

with rasterio.open(input_file) as src:

    transform, width, height = calculate_default_transform(
        src.crs,
        target_crs,
        src.width,
        src.height,
        *src.bounds
    )

    profile = src.profile.copy()

    profile.update(
        crs=target_crs,
        transform=transform,
        width=width,
        height=height
    )

    with rasterio.open(output_file, "w", **profile) as dst:

        for band in range(1, src.count + 1):

            reproject(
                source=rasterio.band(src, band),
                destination=rasterio.band(dst, band),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=target_crs,
                resampling=Resampling.bilinear
            )

print("Reprojection completed!")
print("Output:", output_file)
print("CRS:", target_crs)