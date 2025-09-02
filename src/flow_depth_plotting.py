

########## PLOTTING ############################################ 

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def g_plots_from_wd_swissimage_files(dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge, swissimage_file, plot_title_prefix):
    """
    Generates plots of water depth data over a Swissimage background using a DEM grid.

    Parameters:
        dem_file (str): Path to the .dem file.
        wd_folder (str): Path to the folder containing .wd files.
        plot_output_folder (str): Path to save the plots.
        geo_ezgg_2km_ge (str): Path to the catchment shapefile.
        swissimage_file (str): Path to the Swissimage background (.tif).
        plot_title_prefix (str): Prefix for plot titles.
    """
    # Ensure the output directory exists
    os.makedirs(plot_output_folder, exist_ok=True)

    # Step 1: Read the DEM grid structure and mask
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Step 2: Read the Swissimage background in RGB
    with rasterio.open(swissimage_file) as src_swissimage:
        swissimage_data = src_swissimage.read([1, 2, 3])
        swissimage_bounds = src_swissimage.bounds

    # Step 3: Read the catchment shapefile
    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # Step 4: Iterate through all .wd files in the folder
    wd_files = sorted([os.path.join(wd_folder, f) for f in os.listdir(wd_folder) if f.endswith(".wd")])

    for i, wd_file in enumerate(wd_files):
        try:
            # Read water depth data
            with rasterio.open(wd_file) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            # Reproject water depth data to match DEM grid
            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            # Mask and categorize data
            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = ['#ffffcc', '#ffeda0', '#0047b3']
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            # Plot the data
            plt.figure(figsize=(12, 10))
            plt.imshow(
                np.moveaxis(swissimage_data, 0, -1),
                extent=(swissimage_bounds.left, swissimage_bounds.right, swissimage_bounds.bottom, swissimage_bounds.top),
                interpolation="none",
                zorder=0,
                alpha=0.9,
            )

            # Overlay transparent and masked data
            plt.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top), cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            plt.imshow(masked_data, cmap=cmap, norm=norm, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top), interpolation="none", zorder=2)

            # Overlay catchment boundaries
            catchments.boundary.plot(ax=plt.gca(), edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            # Customize plot
            plt.xlim(dem_bounds.left, dem_bounds.right)
            plt.ylim(dem_bounds.bottom, dem_bounds.top)

            # Colorbar
            cbar = plt.colorbar(label="Water Depth (m)", boundaries=categories, ticks=[0.10, 0.25, 0.50])
            cbar.set_ticklabels(["0.10m", "0.25m", "> 0.50 m"])

            # Title and labels
            time_minutes = i * 5
            plot_title = f"{plot_title_prefix} - {time_minutes} minutes"
            plt.title(plot_title)
            plt.xlabel("Longitude (m)")
            plt.ylabel("Latitude (m)")
            plt.legend(loc="upper right")

            # Save plot
            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(os.path.basename(wd_file))[0]}.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f"Plot saved: {plot_filename}")

        except Exception as e:
            print(f"Failed to process {wd_file}: {e}")

    print("All plots have been generated and saved.")


    ##############################################################

import os
import re
from PIL import Image

def create_gif_from_images(image_folder, output_gif, duration=500, start=0, end=12):
    """
    Creates a GIF from PNG images in a specified folder.

    Parameters:
        image_folder (str): Path to the folder containing PNG files.
        output_gif (str): Path to save the GIF file.
        duration (int): Duration between frames in milliseconds. Default is 500.
        start (int): Starting index of images to include in the GIF. Default is 0.
        end (int): Ending index of images to include in the GIF. Default is 12.
    """
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_gif), exist_ok=True)

    # Get all PNG files matching the expected naming pattern, e.g., xxx-0001.png
    image_files = sorted(
        [f for f in os.listdir(image_folder) if re.match(r".*-\d{4}\.png$", f)],
        key=lambda x: int(x.split('-')[-1].split('.')[0])
    )

    # Filter files from the specified range
    filtered_files = [f for f in image_files if start <= int(f.split('-')[-1].split('.')[0]) <= end]

    if len(filtered_files) == 0:
        print(f"No images found in the specified range ({start:04d} to {end:04d}).")
    else:
        print(f"Found {len(filtered_files)} images. Creating GIF...")

        # Load images
        images = [Image.open(os.path.join(image_folder, f)) for f in filtered_files]

        # Save as GIF
        images[0].save(
            output_gif,
            save_all=True,
            append_images=images[1:],
            duration=duration,
            loop=0  # Infinite loop
        )

        print(f" GIF created successfully: {output_gif}")


####################################################################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def generate_plot_for_max_file(
    dem_file, 
    max_file, 
    plot_output_folder, 
    geo_ezgg_2km_ge, 
    swissimage_file, 
    plot_title
):
    """
    Generates a plot of water depth from a `.max` file over a Swissimage background using a DEM grid.

    Parameters:
        dem_file (str): Path to the .dem file.
        max_file (str): Path to the .max file.
        plot_output_folder (str): Path to save the plot.
        geo_ezgg_2km_ge (str): Path to the catchment shapefile.
        swissimage_file (str): Path to the Swissimage background (.tif).
        plot_title (str): Title for the plot.
    """
    # Ensure the output directory exists
    os.makedirs(plot_output_folder, exist_ok=True)

    # Step 1: Read the DEM grid structure and mask
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Step 2: Read the Swissimage background in RGB
    with rasterio.open(swissimage_file) as src_swissimage:
        swissimage_data = src_swissimage.read([1, 2, 3])
        swissimage_bounds = src_swissimage.bounds

    # Step 3: Read the catchment shapefile
    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    try:
        # Read water depth data from .max file
        with rasterio.open(max_file) as src_max:
            max_data = src_max.read(1)
            max_transform = src_max.transform

        # Reproject water depth data to match DEM grid
        aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
        reproject(
            source=max_data,
            destination=aligned_data,
            src_transform=max_transform,
            src_crs="EPSG:2056",
            dst_transform=dem_transform,
            dst_crs="EPSG:2056",
            resampling=Resampling.nearest,
        )

        # Mask and categorize data
        masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
        transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

        categories = [0.10, 0.25, 0.50, 0.60]
        colors = ['#ffffcc', '#ffeda0', '#0047b3']
        cmap = ListedColormap(colors)
        norm = BoundaryNorm(categories, cmap.N, clip=True)

        # Plot the data
        plt.figure(figsize=(12, 10))
        plt.imshow(
            np.moveaxis(swissimage_data, 0, -1),
            extent=(swissimage_bounds.left, swissimage_bounds.right, swissimage_bounds.bottom, swissimage_bounds.top),
            interpolation="none",
            zorder=0,
            alpha=0.9,
        )

        # Overlay transparent and masked data
        plt.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top), cmap=ListedColormap(['none']), interpolation="none", zorder=1)
        plt.imshow(masked_data, cmap=cmap, norm=norm, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top), interpolation="none", zorder=2)

        # Overlay catchment boundaries
        catchments.boundary.plot(ax=plt.gca(), edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

        # Customize plot
        plt.xlim(dem_bounds.left, dem_bounds.right)
        plt.ylim(dem_bounds.bottom, dem_bounds.top)

        # Colorbar
        cbar = plt.colorbar(label="Water Depth (m)", boundaries=categories, ticks=[0.10, 0.25, 0.50])
        cbar.set_ticklabels(["0.10m", "0.25m", "> 0.50 m"])

        # Title and labels
        plt.title(plot_title)
        plt.xlabel("Longitude (m)")
        plt.ylabel("Latitude (m)")
        plt.legend(loc="upper right")

        # Save plot
        plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(os.path.basename(max_file))[0]}.png")
        plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"Plot saved: {plot_filename}")

    except Exception as e:
        print(f"Failed to process {max_file}: {e}")

    print("Plot for .max file has been generated and saved.")
#################################################################################################################################

from PIL import Image
from io import BytesIO
import numpy as np
import requests

def get_swisstopo_background_image(
    xmin, xmax, ymin, ymax,
    width=None, height=None,
    resolution_m=None,
    layer="ch.swisstopo.swisstlm3d-karte-grau",
    endpoint="https://wms.geo.admin.ch/",
    transparent=True,
    max_px=4096
):
    # compute pixel size if not given
    w_m = float(xmax - xmin); h_m = float(ymax - ymin)
    if width is None or height is None:
        if resolution_m is None:
            resolution_m = 2.0
        width  = int(np.ceil(w_m / resolution_m))
        height = int(np.ceil(h_m / resolution_m))

    # cap request size (WMS limit safety)
    scale = max(width/max_px, height/max_px, 1.0)
    width_req  = int(round(width/scale))
    height_req = int(round(height/scale))

    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0",
        "LAYERS": layer, "STYLES": "",
        "BBOX": f"{xmin},{ymin},{xmax},{ymax}",
        "CRS": "EPSG:2056",
        "WIDTH": width_req, "HEIGHT": height_req,
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE" if transparent else "FALSE",
        "MAP_RESOLUTION": "96", "DPI": "96",
    }
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "image/png,image/*,*/*;q=0.8"}

    r = requests.get(endpoint, params=params, headers=headers, timeout=30)
    if r.status_code != 200:
        print(" Failed to fetch WMS:", r.status_code, r.text[:200])
        return None

    img = Image.open(BytesIO(r.content)).convert("RGBA")
    if scale > 1.0:
        img = img.resize((width, height), resample=Image.BILINEAR)
    return img


################################################################################################################################
########################################## swisstopo background zoomed ##########################################################
import os
import math
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds
from matplotlib.colors import ListedColormap, BoundaryNorm
from PIL import Image
from io import BytesIO
import requests


# ---------- High-res tiled Swisstopo WMS fetcher (keeps your layer) ----------
def get_swisstopo_background_image_zoomed(
    xmin, xmax, ymin, ymax,
    *, width, height,
    layer="ch.swisstopo.swisstlm3d-karte-grau",  # << your requested layer
    endpoint="https://wms.geo.admin.ch/",
    transparent=True,
    max_px=4096,   # per-request cap
    timeout=30,
    dpi=192        # higher DPI for sharper labels (try 96 if you want default styling)
):
    """
    Fetch a WMS image for the bbox by tiling so no request exceeds max_px.
    Returns a RGBA PIL.Image of size (width, height) with no upscaling blur.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width/height must be > 0")

    w_m = float(xmax - xmin)
    h_m = float(ymax - ymin)
    px_w = w_m / float(width)
    px_h = h_m / float(height)

    tiles_x = max(1, math.ceil(width  / max_px))
    tiles_y = max(1, math.ceil(height / max_px))

    mosaic = Image.new("RGBA", (width, height))
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "image/png,image/*,*/*;q=0.8"}
    base_params = {
        "SERVICE": "WMS",
        "REQUEST": "GetMap",
        "VERSION": "1.3.0",
        "LAYERS": layer,
        "STYLES": "",
        "CRS": "EPSG:2056",
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE" if transparent else "FALSE",
        "MAP_RESOLUTION": str(dpi),
        "DPI": str(dpi),
    }

    for ty in range(tiles_y):
        y0_px = ty * max_px
        tile_h = min(max_px, height - y0_px)
        ymin_tile = ymin + y0_px * px_h
        ymax_tile = ymin + (y0_px + tile_h) * px_h

        for tx in range(tiles_x):
            x0_px = tx * max_px
            tile_w = min(max_px, width - x0_px)
            xmin_tile = xmin + x0_px * px_w
            xmax_tile = xmin + (x0_px + tile_w) * px_w

            params = dict(base_params)
            params.update({
                "BBOX": f"{xmin_tile},{ymin_tile},{xmax_tile},{ymax_tile}",
                "WIDTH": str(tile_w),
                "HEIGHT": str(tile_h),
            })

            r = requests.get(endpoint, params=params, headers=headers, timeout=timeout)
            if r.status_code != 200:
                print(f"❌ WMS tile failed [{tx},{ty}] {r.status_code}: {r.text[:200]}")
                tile_img = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
            else:
                tile_img = Image.open(BytesIO(r.content)).convert("RGBA")
                # Guard: some servers return off-by-one sizes
                if tile_img.size != (tile_w, tile_h):
                    tile_img = tile_img.resize((tile_w, tile_h), resample=Image.NEAREST)

            # PIL paste origin top-left; y increases up in map coords
            mosaic.paste(tile_img, (x0_px, height - (y0_px + tile_h)))

    return mosaic
##################################################################################################################################

import matplotlib.pyplot as plt
import rasterio
import numpy as np
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import cartopy.crs as ccrs
from PIL import Image
from io import BytesIO
import requests

def get_swisstopo_background_image(xmin, xmax, ymin, ymax, resolution_m=2, layer='ch.swisstopo.swisstlm3d-karte-grau'):
    width_px = int((xmax - xmin) / resolution_m)
    height_px = int((ymax - ymin) / resolution_m)
    bbox = f"{xmin},{ymin},{xmax},{ymax}"
    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetMap",
        "VERSION": "1.3.0",
        "LAYERS": layer,
        "BBOX": bbox,
        "CRS": "EPSG:2056",
        "WIDTH": width_px,
        "HEIGHT": height_px,
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE"
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/png,image/*,*/*;q=0.8"
    }
    response = requests.get("https://wms.geo.admin.ch/", params=params, headers=headers)
    if response.status_code == 200:
        return Image.open(BytesIO(response.content))
    else:
        print("❌ Failed to fetch WMS:", response.status_code)
        return None


################################################################################################################################

import cartopy.crs as ccrs
import matplotlib.pyplot as plt

def add_swisstopo_cartopy_wms_background(ax, extent, layer='ch.swisstopo.swisstlm3d-karte-grau', zorder=0):
    """
    Adds a swisstopo WMS background to the given Cartopy axis.

    Parameters:
        ax: A Cartopy GeoAxes instance.
        extent: [xmin, xmax, ymin, ymax] in EPSG:2056.
        layer: WMS layer name.
        zorder: Drawing order.
    """
    swiss_proj = ccrs.epsg(2056)
    ax.set_extent(extent, crs=swiss_proj)
    wms_url = 'https://wms.geo.admin.ch/?'
    ax.add_wms(wms_url, layers=[layer], zorder=zorder)


#####################################################################################################################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def g_plots_from_wd_swissTLMgray(dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge, 
                                 location_name, rain_intensity, plot_title_prefix, 
                                 color1="violet", color2="mediumvioletred", color3="darkmagenta"):
    os.makedirs(plot_output_folder, exist_ok=True)

    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # Get basemap using the original function
    basemap_img = get_swisstopo_background_image(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top)
    if basemap_img is None:
        print(" Background map not loaded.")
        return

    wd_files = sorted([os.path.join(wd_folder, f) for f in os.listdir(wd_folder) if f.endswith(".wd")])

    for i, wd_file in enumerate(wd_files):
        try:
            with rasterio.open(wd_file) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig, ax = plt.subplots(figsize=(12, 10))

            ax.imshow(basemap_img, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=0)

            ax.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, cmap=cmap, norm=norm,
                      extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=2)

            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            ax.set_xlim(dem_bounds.left, dem_bounds.right)
            ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

            cbar = plt.colorbar(ax.imshow(masked_data, cmap=cmap, norm=norm),
                                ax=ax, boundaries=categories, ticks=[0.10, 0.25, 0.50])
            cbar.set_label("Water Depth (m)", fontsize=16)
            cbar.ax.tick_params(labelsize=14)

            time_minutes = i * 5
            ax.set_title(f"{location_name} ({rain_intensity}) - {time_minutes} minutes", fontsize=18, fontweight="bold")
            ax.set_xlabel("Longitude (m)", fontsize=16)
            ax.set_ylabel("Latitude (m)", fontsize=16)
            ax.legend(loc="upper right", fontsize=14)

            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(os.path.basename(wd_file))[0]}.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f" Plot saved: {plot_filename}")

        except Exception as e:
            print(f" Failed to process {wd_file}: {e}")

    print(" All plots have been generated and saved.")


###########################################################################################################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd


def g_plots_from_wd_swissTLMgray_v2(dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge, 
                                 location_name, rain_intensity, plot_title_prefix, 
                                 color1="violet", color2="mediumvioletred", color3="darkmagenta"):
    """
    Generates plots of water depth data over a Swisstopo WMS basemap using a DEM grid.

    Parameters:
        dem_file (str): Path to the DEM file.
        wd_folder (str): Path to the folder containing .wd files.
        plot_output_folder (str): Path to save the plots.
        geo_ezgg_2km_ge (str): Path to the catchment shapefile.
        location_name (str): Name of the location to be used in the title (e.g., "Salavaux").
        rain_intensity (str): Rain intensity in mm/h to be used in the title (e.g., "25 mm/h").
        plot_title_prefix (str): Prefix for plot titles.
        color1 (str): First color (default: "violet").
        color2 (str): Second color (default: "mediumvioletred").
        color3 (str): Third color (default: "darkmagenta").
    """
    # Ensure the output directory exists
    os.makedirs(plot_output_folder, exist_ok=True)

    # Step 1: Read the DEM grid structure and mask
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Step 2: Read the catchment shapefile
    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # Step 3: Get Swisstopo WMS Map for Background using the helper function
    basemap_img = fetch_swisstopo_wms_background(dem_bounds)
    if basemap_img is None:
        return  # Stop execution if WMS fetch failed

    # Step 4: Iterate through all .wd files in the folder
    wd_files = sorted([os.path.join(wd_folder, f) for f in os.listdir(wd_folder) if f.endswith(".wd")])

    for i, wd_file in enumerate(wd_files):
        try:
            # Read water depth data
            with rasterio.open(wd_file) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            # Reproject water depth data to match DEM grid
            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            # Mask and categorize data
            masked_data = np.where((mask & (aligned_data >= 0.05)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.05), 1, np.nan)

            categories = [0.05, 0.10, 0.25, 2]  # Use np.inf for all values above 0.25
            colors = [color1, color2, color3]  # User-defined colors
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N)

            # Create figure
            fig, ax = plt.subplots(figsize=(12, 10))

            # Add Swisstopo WMS as background
            ax.imshow(basemap_img, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=0)

            # Overlay transparent and masked data
            ax.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, cmap=cmap, norm=norm,
                      extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=2)

            # Overlay catchment boundaries
            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            # Customize plot
            ax.set_xlim(dem_bounds.left, dem_bounds.right)
            ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

            # Colorbar
            cbar = plt.colorbar(ax.imshow(masked_data, cmap=cmap, norm=norm),
                    ax=ax, boundaries=categories, ticks=[0.05, 0.10, 0.25])

            # Increase the font size of the colorbar label
            cbar.set_label("Water Depth (m)", fontsize=16)

            # Increase font size of tick labels
            cbar.ax.tick_params(labelsize=14)  # Adjust tick labels separately

            # Dynamic Title
            time_minutes = i * 5
            ax.set_title(f"{location_name} ({rain_intensity}) - {time_minutes} minutes", fontsize=18, fontweight="bold")

            # Increase font size for axis labels
            ax.set_xlabel("Longitude (m)", fontsize=16)
            ax.set_ylabel("Latitude (m)", fontsize=16)

            # Increase font size of the legend
            ax.legend(loc="upper right", fontsize=14)

            # Save plot
            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(os.path.basename(wd_file))[0]}.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f"Plot saved: {plot_filename}")

        except Exception as e:
            print(f"Failed to process {wd_file}: {e}")

    print("All plots have been generated and saved.")

##########################################################################################################################
import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def g2_plots_from_wd_swissTLMgray(
    dem_file,
    wd_folder,
    plot_output_folder,
    geo_ezgg_2km_ge,
    location_name,
    rain_intensity,
    plot_title_prefix,
    color1="violet",
    color2="mediumvioletred",
    color3="darkmagenta",
    camp_polygon_path=None,
    zoom_to_camp=False
):
    """
    Generates plots of water depth data over a Swisstopo WMS basemap using a DEM grid.

    Parameters:
        dem_file (str): Path to the DEM file.
        wd_folder (str): Path to the folder containing .wd files.
        plot_output_folder (str): Path to save the plots.
        geo_ezgg_2km_ge (str): Path to the catchment shapefile.
        location_name (str): Name of the location to be used in the title (e.g., "Salavaux").
        rain_intensity (str): Rain intensity in mm/h to be used in the title (e.g., "25 mm/h").
        plot_title_prefix (str): Prefix for plot titles.
        color1, color2, color3 (str): Colors for water depth categories.
        camp_polygon_path (str): Path to campground polygon GeoJSON (optional).
        zoom_to_camp (bool): If True, zoom to the campground polygon.
    """

    os.makedirs(plot_output_folder, exist_ok=True)

    # Step 1: Read DEM
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Step 2: Read catchments
    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # Step 3: Read campground polygon (if given)
    camp_gdf = None
    if camp_polygon_path:
        try:
            camp_gdf = gpd.read_file(camp_polygon_path).to_crs("EPSG:2056")
        except Exception as e:
            print(f" Failed to read campground polygon: {e}")

    # Step 4: Fetch Swisstopo background
    basemap_img = fetch_swisstopo_wms_background(dem_bounds)
    if basemap_img is None:
        return

    # Step 5: Loop through .wd files
    wd_files = sorted([os.path.join(wd_folder, f) for f in os.listdir(wd_folder) if f.endswith(".wd")])

    for i, wd_file in enumerate(wd_files):
        try:
            with rasterio.open(wd_file) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            # Categorize water depth
            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig, ax = plt.subplots(figsize=(12, 10))

            # Add background map
            ax.imshow(basemap_img, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=0)

            # Add water depth overlays
            ax.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, cmap=cmap, norm=norm,
                      extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=2)

            # Plot catchment
            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            # Plot campground outline if available
            if camp_gdf is not None:
                camp_gdf.boundary.plot(ax=ax, edgecolor='red', linewidth=1.2, zorder=4, label="Campground")
                if zoom_to_camp:
                    bounds = camp_gdf.total_bounds
                    ax.set_xlim(bounds[0] - 10, bounds[2] + 10)
                    ax.set_ylim(bounds[1] - 10, bounds[3] + 10)
                else:
                    ax.set_xlim(dem_bounds.left, dem_bounds.right)
                    ax.set_ylim(dem_bounds.bottom, dem_bounds.top)
            else:
                ax.set_xlim(dem_bounds.left, dem_bounds.right)
                ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

            # Colorbar
            cbar = plt.colorbar(ax.imshow(masked_data, cmap=cmap, norm=norm),
                                ax=ax, boundaries=categories, ticks=[0.10, 0.25, 0.50])
            cbar.set_label("Water Depth (m)", fontsize=16)
            cbar.ax.tick_params(labelsize=14)

            # Title and labels
            time_minutes = i * 5
            ax.set_title(f"{plot_title_prefix} - {location_name} ({rain_intensity}) - {time_minutes} min",
                         fontsize=18, fontweight="bold")
            ax.set_xlabel("Longitude (m)", fontsize=16)
            ax.set_ylabel("Latitude (m)", fontsize=16)
            ax.legend(loc="upper right", fontsize=14)

            # Save plot
            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(os.path.basename(wd_file))[0]}.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f" Plot saved: {plot_filename}")

        except Exception as e:
            print(f"Failed to process {wd_file}: {e}")

    print(" All plots have been generated and saved.")

#######################################################################################################################
############################################################################################################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def g_plot_maxwd_swissTLM(
    dem_file, 
    max_file, 
    plot_output_folder, 
    geo_ezgg_2km_ge, 
    location_name, 
    rain_intensity, 
    color1="violet", color2="mediumvioletred", color3="darkmagenta"
):
    os.makedirs(plot_output_folder, exist_ok=True)

    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    basemap_img = get_swisstopo_background_image(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top)
    if basemap_img is None:
        print("Failed to fetch Swisstopo WMS basemap.")
        return

    try:
        with rasterio.open(max_file) as src_max:
            max_data = src_max.read(1)
            max_transform = src_max.transform

        aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
        reproject(
            source=max_data,
            destination=aligned_data,
            src_transform=max_transform,
            src_crs="EPSG:2056",
            dst_transform=dem_transform,
            dst_crs="EPSG:2056",
            resampling=Resampling.nearest,
        )

        masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
        transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

        categories = [0.10, 0.25, 0.50, 0.60]
        colors = [color1, color2, color3]
        cmap = ListedColormap(colors)
        norm = BoundaryNorm(categories, cmap.N, clip=True)

        fig, ax = plt.subplots(figsize=(12, 10))

        ax.imshow(basemap_img, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                  interpolation="none", zorder=0)
        ax.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                  cmap=ListedColormap(['none']), interpolation="none", zorder=1)
        ax.imshow(masked_data, cmap=cmap, norm=norm,
                  extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                  interpolation="none", zorder=2)

        catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

        ax.set_xlim(dem_bounds.left, dem_bounds.right)
        ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

        cbar = plt.colorbar(ax.imshow(masked_data, cmap=cmap, norm=norm),
                            ax=ax, boundaries=categories, ticks=[0.10, 0.25, 0.50])
        cbar.set_label("Water Depth (m)", fontsize=16)
        cbar.ax.tick_params(labelsize=14)

        ax.set_title(f"{location_name} ({rain_intensity}) - Max Water Depth", fontsize=18, fontweight="bold")
        ax.set_xlabel("Longitude (m)", fontsize=16)
        ax.set_ylabel("Latitude (m)", fontsize=16)
        ax.legend(loc="upper right", fontsize=14)

        plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(os.path.basename(max_file))[0]}.png")
        plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"\u2705 Plot saved: {plot_filename}")

    except Exception as e:
        print(f"\u274c Failed to process {max_file}: {e}")

    print("\u2705 Plot for .max file has been generated and saved.")

#########################################################################################################
###############################modified to add catchment or not #########################################
########################################################################################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm

def g_plot_maxwd_swissTLM_nocatchment(
    dem_file, 
    max_file, 
    plot_output_folder, 
    location_name, 
    rain_intensity, 
    color1="violet", color2="mediumvioletred", color3="darkmagenta",
    use_catchments=False, 
    geo_ezgg_2km_ge=None
):
    os.makedirs(plot_output_folder, exist_ok=True)

    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Optional catchments
    catchments = None
    if use_catchments and geo_ezgg_2km_ge:
        import geopandas as gpd
        catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    basemap_img = get_swisstopo_background_image(
        dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top
    )
    if basemap_img is None:
        print("Failed to fetch Swisstopo WMS basemap.")
        return

    try:
        with rasterio.open(max_file) as src_max:
            max_data = src_max.read(1)
            max_transform = src_max.transform

        aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
        reproject(
            source=max_data,
            destination=aligned_data,
            src_transform=max_transform,
            src_crs="EPSG:2056",
            dst_transform=dem_transform,
            dst_crs="EPSG:2056",
            resampling=Resampling.nearest,
        )

        # keep only >= 0.10 m for plotting; below is transparent
        masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
        has_depth = np.isfinite(masked_data).any()

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.imshow(
            basemap_img,
            extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
            interpolation="none", zorder=0
        )
        ax.set_xlim(dem_bounds.left, dem_bounds.right)
        ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

        if has_depth:
            # 3 classes: 0.10–0.30, 0.30–0.50, >0.50
            # choose a finite vmax for the top edge (>= 0.5001 to define the last bin)
            data_max = float(np.nanmax(masked_data))
            vmax = max(0.5001, data_max)
            boundaries = [0.10, 0.30, 0.50, vmax]

            from matplotlib.colors import ListedColormap, BoundaryNorm
            cmap = ListedColormap([color1, color2, color3])
            norm = BoundaryNorm(boundaries, cmap.N, clip=True)

            im = ax.imshow(
                masked_data, cmap=cmap, norm=norm,
                extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                interpolation="none", zorder=2
            )

            # Optional catchments
            if catchments is not None:
                catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            # Colorbar: ticks at 0.10, 0.30, 0.50; arrow on top if values exceed 0.50
            cbar = plt.colorbar(
                im, ax=ax, boundaries=boundaries, ticks=[0.10, 0.30, 0.50],
                fraction=0.035, pad=0.02, extend="max"
            )
            cbar.set_label("Water Depth (m)", fontsize=16)
            cbar.ax.tick_params(labelsize=14)
        else:
            # No pixels >= 0.10 m → show note and skip colorbar
            ax.text(
                0.5, 0.02,
                "No water depth ≥ 0.10 m in this scenario",
                ha="center", va="bottom", transform=ax.transAxes, fontsize=12,
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none")
            )
            if catchments is not None:
                catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

        ax.set_title(f"{location_name} ({rain_intensity}) - Max Water Depth", fontsize=18, fontweight="bold")
        ax.set_xlabel("Longitude (m)", fontsize=16)
        ax.set_ylabel("Latitude (m)", fontsize=16)

        if catchments is not None:
            ax.legend(loc="upper right", fontsize=14)

        plot_filename = os.path.join(
            plot_output_folder, f"{os.path.splitext(os.path.basename(max_file))[0]}.png"
        )
        plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
        plt.close()

        print(f" Plot saved: {plot_filename}")

    except Exception as e:
        print(f" Failed to process {max_file}: {e}")

############################################################################################################
###########################################################################################################
####################### the same as above but zoomed #####################################################
import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds
from matplotlib.colors import ListedColormap, BoundaryNorm

def g_plot_maxwd_swissTLM_nocatchment_zoomed(
    dem_file,
    max_file,
    plot_output_folder,
    location_name,
    rain_intensity,
    # Orange palette (0.10–0.30, 0.30–0.50, ≥0.50)
    color1="#fee8c8",
    color2="#fdbb84",
    color3="#e34a33",
    use_catchments=False,
    geo_ezgg_2km_ge=None,
    extent=None,                # (xmin, xmax, ymin, ymax) in m (or km if 'auto')
    extent_units="auto",        # "auto" | "m" | "km"
    target_pixel_size=None,     # overlay render grid (m/px); None = DEM native
    # Background controls (kept to your requested layer)
    bg_layer="ch.swisstopo.swisstlm3d-karte-grau",
    bg_pixel_size=1.0,          # WMS background pixel size (m/px). 0.5–2.0 is a good range.
    bg_max_px=4096,
    bg_dpi=192                  # try 96 for more default carto styling
):
    """
    Plots max water depth on high-res Swisstopo 'swisstlm3d-karte-grau'.
    - Exact framing to `extent` with 1:1 metric aspect (no distortion).
    - Tiled WMS (no server downscale) for a crisp background.
    - Orange depth classes: 0.10–0.30, 0.30–0.50, ≥0.50 m.
    """
    os.makedirs(plot_output_folder, exist_ok=True)

    def _extent_to_meters(ext, units):
        if ext is None:
            return None
        xmin, xmax, ymin, ymax = ext
        if units == "m":
            return xmin, xmax, ymin, ymax
        if units == "km":
            return xmin*1000.0, xmax*1000.0, ymin*1000.0, ymax*1000.0
        # auto: if values are ~thousands, treat as km
        sample = max(abs(x) for x in (xmin, xmax, ymin, ymax))
        return (xmin*1000.0, xmax*1000.0, ymin*1000.0, ymax*1000.0) if sample < 10000 else (xmin, xmax, ymin, ymax)

    # Keep the original requested extent for framing the plot & basemap
    plot_extent = _extent_to_meters(extent, extent_units) if extent is not None else None

    # --- Open DEM and decide plotting window ---
    with rasterio.open(dem_file) as src_dem:
        dem_crs = src_dem.crs
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999

        if plot_extent is not None:
            xmin, xmax, ymin, ymax = plot_extent
            dsb = src_dem.bounds
            xmin_r = max(xmin, dsb.left);  xmax_r = min(xmax, dsb.right)
            ymin_r = max(ymin, dsb.bottom); ymax_r = min(ymax, dsb.top)

            win = from_bounds(xmin_r, ymin_r, xmax_r, ymax_r, transform=src_dem.transform)
            dem_data = src_dem.read(1, window=win)
            dem_transform = src_dem.window_transform(win)
            dem_bounds = rasterio.coords.BoundingBox(xmin_r, ymin_r, xmax_r, ymax_r)
        else:
            dem_data = src_dem.read(1)
            dem_transform = src_dem.transform
            b = src_dem.bounds
            dem_bounds = rasterio.coords.BoundingBox(b.left, b.bottom, b.right, b.top)
            plot_extent = (b.left, b.right, b.bottom, b.top)

        # Optional render resampling (for overlay crispness)
        if target_pixel_size is not None and plot_extent is not None:
            from rasterio.transform import from_origin
            px = float(target_pixel_size)
            xmin, xmax, ymin, ymax = plot_extent
            width  = int(np.ceil((xmax - xmin) / px))
            height = int(np.ceil((ymax - ymin) / px))
            dem_resampled = np.full((height, width), dem_nodata_value, dtype=dem_data.dtype)
            dst_transform = from_origin(xmin, ymax, px, px)
            reproject(
                source=dem_data,
                destination=dem_resampled,
                src_transform=dem_transform,
                src_crs=dem_crs,
                dst_transform=dst_transform,
                dst_crs=dem_crs,
                resampling=Resampling.bilinear
            )
            dem_data = dem_resampled
            dem_transform = dst_transform
            dem_bounds = rasterio.coords.BoundingBox(xmin, ymin, xmax, ymax)

        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # --- Optional catchments ---
    catchments = None
    if use_catchments and geo_ezgg_2km_ge:
        import geopandas as gpd
        catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # --- Basemap for the EXACT plot extent (independent resolution) ---
    xmin, xmax, ymin, ymax = plot_extent
    px_bg = float(bg_pixel_size) if bg_pixel_size is not None else abs(dem_transform.a)
    bg_width  = int(np.ceil((xmax - xmin) / px_bg))
    bg_height = int(np.ceil((ymax - ymin) / px_bg))

    basemap_img = get_swisstopo_background_image_zoomed(
        xmin, xmax, ymin, ymax,
        width=bg_width, height=bg_height,
        layer=bg_layer,        # stays as swisstlm3d-karte-grau
        max_px=bg_max_px,
        dpi=bg_dpi
    )
    if basemap_img is None:
        print("Failed to fetch Swisstopo WMS basemap.")
        return

    # --- Align max depth to the render grid ---
    try:
        with rasterio.open(max_file) as src_max:
            max_data = src_max.read(1)
            max_transform = src_max.transform
            max_crs = src_max.crs

        aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
        reproject(
            source=max_data,
            destination=aligned_data,
            src_transform=max_transform,
            src_crs=max_crs if max_crs is not None else "EPSG:2056",
            dst_transform=dem_transform,
            dst_crs=dem_crs if dem_crs is not None else "EPSG:2056",
            resampling=Resampling.nearest,
        )

        masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
        has_depth = np.isfinite(masked_data).any()

        # --------- FIGURE: enforce 1:1 aspect in meters (no distortion) ---------
        xspan = xmax - xmin
        yspan = ymax - ymin
        base_width = 12.0
        fig, ax = plt.subplots(figsize=(base_width, base_width * (yspan / xspan)))

        # basemap (choose 'nearest' for razor sharp, 'bilinear' to soften labels slightly)
        ax.imshow(basemap_img, extent=plot_extent, interpolation="nearest", zorder=0)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")

        if has_depth:
            data_max = float(np.nanmax(masked_data))
            vmax = max(0.5001, data_max)
            boundaries = [0.10, 0.30, 0.50, vmax]
            cmap = ListedColormap([color1, color2, color3])
            norm = BoundaryNorm(boundaries, cmap.N, clip=True)

            im = ax.imshow(
                masked_data, cmap=cmap, norm=norm,
                extent=plot_extent,
                interpolation="none", zorder=2
            )

            if catchments is not None:
                catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7,
                                         zorder=3, label="Catchment Boundary")

            cbar = plt.colorbar(
                im, ax=ax, boundaries=boundaries, ticks=[0.10, 0.30, 0.50],
                fraction=0.035, pad=0.02, extend="max"
            )
            cbar.set_label("Water Depth (m)", fontsize=16)
            cbar.ax.tick_params(labelsize=14)
        else:
            ax.text(
                0.5, 0.02, "No water depth ≥ 0.10 m in this sector",
                ha="center", va="bottom", transform=ax.transAxes, fontsize=12,
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none")
            )
            if catchments is not None:
                catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7,
                                         zorder=3, label="Catchment Boundary")

        ax.set_title(f"{location_name} ({rain_intensity}) - Max Water Depth",
                     fontsize=18, fontweight="bold")
        ax.set_xlabel("Easting (m)", fontsize=16)
        ax.set_ylabel("Northing (m)", fontsize=16)
        if catchments is not None:
            ax.legend(loc="upper right", fontsize=14)

        plot_filename = os.path.join(
            plot_output_folder,
            f"{os.path.splitext(os.path.basename(max_file))[0]}{'_zoom' if extent else ''}.png"
        )
        plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"Plot saved: {plot_filename}")

    except Exception as e:
        print(f"Failed to process {max_file}: {e}")



###############################################################################################
#################### 4 classes for the water depth ############################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm

def g_plot_maxwd_swissTLM_nocatchment_4bins(
    dem_file,
    max_file,
    plot_output_folder,
    location_name,
    rain_intensity,
    # palette defaults (feel free to change)
    color_010_030="violet",
    color_030_050="mediumvioletred",
    color_050_100="darkmagenta",
    color_gt_100="black",
    use_catchments=False,
    geo_ezgg_2km_ge=None
):
    """
    Same idea as g_plot_maxwd_swissTLM_nocatchment, but with FOUR discrete classes:
      0.10–0.30, 0.30–0.50, 0.50–1.00, and >1.00 m.
    Values <= 0.10 m are hidden (transparent).
    """
    os.makedirs(plot_output_folder, exist_ok=True)

    # --- read DEM (for grid, extent, nodata mask) ---
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        dem_mask = dem_data != dem_nodata_value

    # --- optional catchments ---
    catchments = None
    if use_catchments and geo_ezgg_2km_ge:
        import geopandas as gpd
        catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # --- background (assumes you already have this helper) ---
    basemap_img = get_swisstopo_background_image(
        dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top
    )
    if basemap_img is None:
        print("Failed to fetch Swisstopo WMS basemap.")
        return

    try:
        # --- read & align MAX raster to DEM grid ---
        with rasterio.open(max_file) as src_max:
            max_data = src_max.read(1)
            max_transform = src_max.transform

        aligned = np.full(dem_shape, np.nan, dtype=np.float32)
        reproject(
            source=max_data,
            destination=aligned,
            src_transform=max_transform,
            src_crs="EPSG:2056",
            dst_transform=dem_transform,
            dst_crs="EPSG:2056",
            resampling=Resampling.nearest,
        )

        # hide <= 0.10 m and outside-DEM
        arr = np.where(dem_mask & (aligned > 0.10), aligned, np.nan)

        # --- 4-class scheme ---
        # boundaries: [0.10, 0.30, 0.50, 1.00, +inf]
        boundaries = [0.10, 0.30, 0.50, 1.00, np.inf]
        colors = [color_010_030, color_030_050, color_050_100, color_gt_100]
        labels = ["0.10–0.30 m", "0.30–0.50 m", "0.50–1.00 m", ">1.00 m"]

        cmap = ListedColormap(colors)
        norm = BoundaryNorm(boundaries, cmap.N, clip=False)

        # --- plot ---
        fig, ax = plt.subplots(figsize=(12, 10))
        ax.imshow(
            basemap_img,
            extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
            interpolation="none",
            zorder=0,
        )

        im = ax.imshow(
            arr,
            cmap=cmap,
            norm=norm,
            extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
            interpolation="none",
            zorder=2,
        )

        # optional catchments
        if catchments is not None:
            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment boundary")

        ax.set_xlim(dem_bounds.left, dem_bounds.right)
        ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

        # colorbar: put a tick in the middle of each class band (last tick a bit above 1.0)
        tick_pos = [0.20, 0.40, 0.75, 1.25]
        cbar = plt.colorbar(im, ax=ax, fraction=0.035, pad=0.02, ticks=tick_pos)
        cbar.ax.set_yticklabels(labels)
        cbar.set_label("Water depth (m)", fontsize=14)
        cbar.ax.tick_params(labelsize=12)

        ax.set_title(f"{location_name} ({rain_intensity}) — Max water depth", fontsize=16, fontweight="bold")
        ax.set_xlabel("Longitude (m)", fontsize=12)
        ax.set_ylabel("Latitude (m)", fontsize=12)

        if catchments is not None:
            ax.legend(loc="upper right", fontsize=10)

        out_png = os.path.join(
            plot_output_folder, f"{os.path.splitext(os.path.basename(max_file))[0]}.png"
        )
        plt.savefig(out_png, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"  Plot saved: {out_png}")

    except Exception as e:
        print(f"  Failed to process {max_file}: {e}")


############################################################################################
############ COMPARING SOLVERS JUST FOR ONE SCENARIO#######################################
###########################################################################################
######### crs first make sure that it is right for Switzerland ###########################
########################################################################################
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
import os

def compare_solver_extent_map(
    dem_file,
    solver_a_file,
    solver_b_file,
    output_folder,
    label_a="Solver A",
    label_b="Solver B",
    location="Location",
    rain="Rain X mm/h",
    threshold=0.10
):
    """
    Creates a categorical flood extent difference map comparing two solvers (A and B).
    """

    os.makedirs(output_folder, exist_ok=True)

    # Load DEM
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_transform = src_dem.transform
        dem_shape = dem_data.shape
        dem_bounds = src_dem.bounds
        dem_nodata = src_dem.nodata
        mask = dem_data != dem_nodata
        extent = (dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top)

    # Helper to align .max files
    def align_max(file):
        with rasterio.open(file) as src:
            data = src.read(1)
            src_transform = src.transform

        aligned = np.full(dem_shape, np.nan, dtype=np.float32)
        reproject(
            source=data,
            destination=aligned,
            src_transform=src_transform,
            src_crs="EPSG:2056",
            dst_transform=dem_transform,
            dst_crs="EPSG:2056",
            resampling=Resampling.nearest
        )

        return np.where(mask, aligned, np.nan)

    # Read and threshold both solvers
    a_aligned = align_max(solver_a_file)
    b_aligned = align_max(solver_b_file)

    flood_a = (a_aligned >= threshold)
    flood_b = (b_aligned >= threshold)

    # 0 = dry in both → white
    # 1 = flooded in both → green
    # 2 = overpredicted by A → blue
    # 3 = overpredicted by B → red
    comparison = np.full(dem_shape, np.nan)
    comparison[~mask] = np.nan
    comparison[(~flood_a) & (~flood_b)] = 0  # white
    comparison[(flood_a) & (flood_b)] = 1    # green
    comparison[(flood_a) & (~flood_b)] = 2   # blue
    comparison[(~flood_a) & (flood_b)] = 3   # red

    # Colors: white, green, blue, red
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(["white", "green", "blue", "red"])
    labels = ["Dry in both", "Flood in both", f"Only {label_a}", f"Only {label_b}"]

    # Plot
    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(comparison, cmap=cmap, extent=extent, interpolation="none")
    ax.set_title(f"{location} – {rain}\nFlood Extent Comparison\n{label_a} vs {label_b}", fontsize=14)
    ax.axis("off")

    # Custom legend
    import matplotlib.patches as mpatches
    patches = [mpatches.Patch(color=cmap(i), label=labels[i]) for i in range(4)]
    ax.legend(handles=patches, loc="lower right", fontsize=10)

    # Save
    safe_rain = re.sub(r"\D", "", rain) + "mmhr"
    out_path = os.path.join(output_folder, f"{location}_{label_a}_vs_{label_b}_{safe_rain}.png")
    plt.savefig(out_path, dpi=800, bbox_inches="tight")
    plt.close()
    print(f"Comparison plot saved to: {out_path}")



#####################################################################################################
#########################COMPARE SCENARIOS DIFFERENCE ###########################################
####################################################################################################

import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import BoundaryNorm
from matplotlib.cm import get_cmap
from PIL import Image
from io import BytesIO
import requests

def compare_solver_absolute_difference(dem_file, solver_a_file, solver_b_file, output_path, location, rain_label):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def reproject_to_dem(src_path, target_shape, target_transform):
        with rasterio.open(src_path) as src:
            data = src.read(1)
            aligned = np.full(target_shape, np.nan, dtype=np.float32)
            reproject(
                source=data,
                destination=aligned,
                src_transform=src.transform,
                src_crs="EPSG:2056",
                dst_transform=target_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )
            return aligned

    with rasterio.open(dem_file) as dem:
        mask = dem.read(1) != dem.nodata
        transform = dem.transform
        bounds = dem.bounds
        shape = dem.shape
        extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)

    # Fetch Swisstopo basemap
    basemap_img = get_swisstopo_background_image(bounds.left, bounds.right, bounds.bottom, bounds.top)
    if basemap_img is None:
        print(" Could not fetch Swisstopo basemap.")
        return

    a_data = reproject_to_dem(solver_a_file, shape, transform)
    b_data = reproject_to_dem(solver_b_file, shape, transform)

    # Compute absolute difference
    valid = mask & ~np.isnan(a_data) & ~np.isnan(b_data) & ((a_data >= 0.10) | (b_data >= 0.10))
    abs_diff = np.full(shape, np.nan, dtype=np.float32)
    abs_diff[valid] = np.abs(b_data[valid] - a_data[valid])
    abs_diff[abs_diff < 0.01] = np.nan  # remove very small differences

    # Define bin edges
    bins = [0.01, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    max_val = np.nanmax(abs_diff)
    if max_val > 0.30:
        bins.append(max_val + 0.01)  # Add extra bin

    # Set colormap and norm
    cmap = get_cmap("plasma", len(bins))  # color per bin
    norm = BoundaryNorm(bins, cmap.N, extend='max')

    fig, ax = plt.subplots(figsize=(10, 9))
    ax.imshow(basemap_img, extent=extent, interpolation="none", zorder=0)
    im = ax.imshow(abs_diff, cmap=cmap, norm=norm, extent=extent, interpolation="none", zorder=1)

    ax.set_title(f"{location} – {rain_label}\nAbsolute Water Depth Difference (|B − A|)", fontsize=14)
    ax.axis("off")

    # Custom colorbar ticks
    cbar = fig.colorbar(im, ax=ax, orientation="vertical", shrink=0.7, extend='max')
    cbar.set_label("Absolute Difference (meters)", fontsize=12)

    tick_positions = bins[:-1]
    tick_labels = [f"{b:.2f}" for b in tick_positions]
    tick_labels[-1] = f">{bins[-2]:.2f}"  # upper label as ">0.30" etc.

    cbar.set_ticks(tick_positions)
    cbar.set_ticklabels(tick_labels)

    plt.savefig(output_path, dpi=800, bbox_inches="tight")
    plt.close()
    print(f" Saved absolute difference map: {output_path}")

#######################################################################################################

from matplotlib.colors import BoundaryNorm
from matplotlib.cm import get_cmap
import os
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from flow_depth_plotting import get_swisstopo_background_image  

def compare_manning_difference_noabsolute(dem_file, solver_a_file, solver_b_file, output_path, location, rain_label):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def reproject_to_dem(src_path, target_shape, target_transform):
        with rasterio.open(src_path) as src:
            data = src.read(1)
            aligned = np.full(target_shape, np.nan, dtype=np.float32)
            reproject(
                source=data,
                destination=aligned,
                src_transform=src.transform,
                src_crs="EPSG:2056",
                dst_transform=target_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )
            return aligned

    # Load DEM and prepare extent
    with rasterio.open(dem_file) as dem:
        mask = dem.read(1) != dem.nodata
        transform = dem.transform
        bounds = dem.bounds
        shape = dem.shape
        extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)

    # Swisstopo background
    basemap_img = get_swisstopo_background_image(bounds.left, bounds.right, bounds.bottom, bounds.top)
    if basemap_img is None:
        print(" Could not fetch Swisstopo basemap.")
        return

    # Read aligned solver rasters
    a_data = reproject_to_dem(solver_a_file, shape, transform)
    b_data = reproject_to_dem(solver_b_file, shape, transform)

    # Signed difference (B - A)
    valid = mask & ~np.isnan(a_data) & ~np.isnan(b_data) & (
        (a_data >= 0.10) | (b_data >= 0.10)
    )
    signed_diff = np.full(shape, np.nan, dtype=np.float32)
    signed_diff[valid] = b_data[valid] - a_data[valid]
    signed_diff[np.abs(signed_diff) < 0.01] = np.nan  # ignore < 1 cm

    # Define bins every 5 cm from -0.5 to 0.5, with extremes beyond
    step = 0.05
    max_bin = 0.3
    bounds_bins = np.round(np.arange(-max_bin, max_bin + step, step), 2).tolist()
    bounds_bins.insert(0, -max_bin - 0.01)  # less than -max_bin
    bounds_bins.append(max_bin + 0.01)      # greater than max_bin

    # Colormap: RdBu_r with white at zero
    cmap = get_cmap("RdBu_r", len(bounds_bins) - 1)
    cmap.set_bad(color=(0, 0, 0, 0))  # transparent for NaNs
    norm = BoundaryNorm(bounds_bins, cmap.N)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.imshow(basemap_img, extent=extent, interpolation="none", zorder=0)
    im = ax.imshow(signed_diff, cmap=cmap, norm=norm, extent=extent,
                   interpolation="none", zorder=1)

    ax.set_title(f"{location} – {rain_label}\nWater Depth Difference (B − A)", fontsize=14)
    ax.axis("off")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, orientation="vertical", shrink=0.7, extend='both')
    cbar.set_label("Water Depth Difference (meters)", fontsize=12)
    cbar.set_ticks(bounds_bins)
    cbar.set_ticklabels([f"{b:.2f}" for b in bounds_bins])

    plt.savefig(output_path, dpi=800, bbox_inches="tight")
    plt.close()
    print(f" Saved signed difference map: {output_path}")

####################################################################################################
#####################FOR LIESTAL ###################################################################
####################FORECAST ######################################################################
###################################################################################################

from datetime import datetime, timedelta
import os
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def g_plots_selected_wd_liestal(dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge, 
                                      plot_title_prefix,
                                      initial_datetime_str, lead_times_hours,
                                      color1="violet", color2="mediumvioletred", color3="darkmagenta"):
    """
    Plots specific .wd files for the Liestal case using Swisstopo background.
    Each plot gets a title like "Liestal – 2024-06-25T15:00:00 + X hour lead time".
    """

    # Specific .wd filenames and assumed order matching the lead times
    selected_filenames = [
        "Liestal_2m_1_1-0012.wd",
        "Liestal_2m_1_1-0024.wd",
        "Liestal_2m_1_1-0036.wd",
        "Liestal_2m_1_1-0048.wd",
        "Liestal_2m_1_1-0060.wd"
    ]

    # Parse base datetime
    base_time = datetime.strptime(initial_datetime_str, "%Y-%m-%dT%H:%M:%S")

    # Ensure output directory exists
    os.makedirs(plot_output_folder, exist_ok=True)

    # Load DEM
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Load catchments
    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    # Get background map
    basemap_img = fetch_swisstopo_wms_background(dem_bounds)
    if basemap_img is None:
        print("Failed to fetch basemap.")
        return

    # Plot selected files
    for filename, lead_hours in zip(selected_filenames, lead_times_hours):
        wd_file_path = os.path.join(wd_folder, filename)
        if not os.path.isfile(wd_file_path):
            print(f"File not found: {filename}")
            continue

        try:
            with rasterio.open(wd_file_path) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig, ax = plt.subplots(figsize=(12, 10))

            ax.imshow(basemap_img, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=0)
            ax.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, cmap=cmap, norm=norm,
                      extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=2)

            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            ax.set_xlim(dem_bounds.left, dem_bounds.right)
            ax.set_ylim(dem_bounds.bottom, dem_bounds.top)

            cbar = plt.colorbar(ax.imshow(masked_data, cmap=cmap, norm=norm),
                                ax=ax, boundaries=categories, ticks=[0.10, 0.25, 0.50])
            cbar.set_label("Water Depth (m)", fontsize=16)
            cbar.ax.tick_params(labelsize=14)

            # Format title
            title = f"{plot_title_prefix} – {initial_datetime_str} + {lead_hours} hour lead time"
            ax.set_title(title, fontsize=18, fontweight="bold")

            ax.set_xlabel("Longitude (m)", fontsize=16)
            ax.set_ylabel("Latitude (m)", fontsize=16)
            ax.legend(loc="upper right", fontsize=14)

            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(filename)[0]}.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f"Plot saved: {plot_filename}")

        except Exception as e:
            print(f"Failed to process {filename}: {e}")

    print("Selected plots have been generated and saved.")

#####################################################################################################

#######################################################################################

from datetime import datetime
import os
import re
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

def g_plots_selected_wd_liestal_dinamic(dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge, 
                                        plot_title_prefix,
                                        initial_datetime_str, lead_times_hours,
                                        color1="violet", color2="mediumvioletred", color3="darkmagenta",
                                        xlim=None, ylim=None):
    """
    Dynamically plots water depth files for the Liestal case using Swisstopo background.
    Automatically infers ensemble member number from folder name.

    Parameters:
        dem_file (str): Path to DEM file.
        wd_folder (str): Path to folder with .wd files.
        plot_output_folder (str): Folder to save output plots.
        geo_ezgg_2km_ge (str): Catchment file in EPSG:2056.
        plot_title_prefix (str): Title prefix for plots (e.g., "Liestal").
        initial_datetime_str (str): Start time in "YYYY-MM-DDTHH:MM:SS".
        lead_times_hours (list[int]): Lead times for each plot (e.g., [1,2,3,4,5]).
        color1, color2, color3 (str): Color definitions.
        xlim, ylim (tuple): Optional zoom limits (EPSG:2056).
    """

    #  Extract ensemble number from folder name (e.g., Liestal_2m_2_fv1-gpu → 2)
    folder_name = os.path.basename(os.path.normpath(wd_folder))
    match = re.search(r"Liestal_2m_(\d+)_", folder_name)
    if not match:
        raise ValueError(f"Could not extract ensemble number from folder name: {folder_name}")
    ensemble_number = match.group(1)

    #  Build filenames dynamically
    time_steps = ["0012", "0024", "0036", "0048", "0060","0072","0084","0096","0108","0120"]
    selected_filenames = [f"Liestal_2m_{ensemble_number}_{ensemble_number}-{t}.wd" for t in time_steps]

    #  Parse base datetime
    base_time = datetime.strptime(initial_datetime_str, "%Y-%m-%dT%H:%M:%S")

    os.makedirs(plot_output_folder, exist_ok=True)

    #  Load DEM and metadata
    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        mask = dem_data != dem_nodata_value

    # Load catchment boundaries
    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")

    #  Fetch high-res background map
    basemap_img = fetch_swisstopo_wms_background(dem_bounds, pixel_size=1)   
    if basemap_img is None:
        print("Failed to fetch basemap.")
        return

    #  Plot each .wd file
    for filename, lead_hours in zip(selected_filenames, lead_times_hours):
        wd_file_path = os.path.join(wd_folder, filename)
        if not os.path.isfile(wd_file_path):
            print(f"File not found: {filename}")
            continue

        try:
            with rasterio.open(wd_file_path) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig, ax = plt.subplots(figsize=(12, 10))

            ax.imshow(basemap_img, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=0)
            ax.imshow(transparent_data, extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, cmap=cmap, norm=norm,
                      extent=(dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top),
                      interpolation="none", zorder=2)

            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3, label="Catchment Boundary")

            #  Zoom
            ax.set_xlim(xlim if xlim else (dem_bounds.left, dem_bounds.right))
            ax.set_ylim(ylim if ylim else (dem_bounds.bottom, dem_bounds.top))

            #  Colorbar
            cbar = plt.colorbar(ax.imshow(masked_data, cmap=cmap, norm=norm),
                                ax=ax, boundaries=categories, ticks=[0.10, 0.25, 0.50])
            cbar.set_label("Water Depth (m)", fontsize=16)
            cbar.ax.tick_params(labelsize=14)

            #  Title and labels
            title = f"{plot_title_prefix} – {initial_datetime_str} + {lead_hours} hour lead time"
            ax.set_title(title, fontsize=18, fontweight="bold")
            ax.set_xlabel("Longitude (m)", fontsize=16)
            ax.set_ylabel("Latitude (m)", fontsize=16)
            ax.legend(loc="upper right", fontsize=14)

            #  Save figure
            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(filename)[0]}.png")
            plt.savefig(plot_filename, dpi=1000, bbox_inches="tight")
            plt.close()

            print(f"Plot saved: {plot_filename}")

        except Exception as e:
            print(f"Failed to process {filename}: {e}")

    print(" All selected plots have been generated and saved.")

##############################################################################################################################

from datetime import datetime
import os
import re
import numpy as np
import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.plot import plotting_extent
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd
import cartopy.crs as ccrs


def g_plots_selected_wd_liestal_dinamic_no_cbar(dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge, 
                                                 plot_title_prefix,
                                                 initial_datetime_str, lead_times_hours,
                                                 color1="violet", color2="mediumvioletred", color3="darkmagenta",
                                                 xlim=None, ylim=None):
    """
    Plots water depth maps without colorbar for animation/video use.
    """
    import requests
    from PIL import Image
    from io import BytesIO
    import matplotlib.pyplot as plt
    import rasterio
    import numpy as np
    from rasterio.warp import reproject, Resampling
    from matplotlib.colors import ListedColormap, BoundaryNorm
    import geopandas as gpd
    import cartopy.crs as ccrs
    import os, re
    from datetime import datetime

    def get_swisstopo_background_image(xmin, xmax, ymin, ymax, resolution_m=2, layer='ch.swisstopo.swisstlm3d-karte-grau'):
        width_px = int((xmax - xmin) / resolution_m)
        height_px = int((ymax - ymin) / resolution_m)
        bbox = f"{xmin},{ymin},{xmax},{ymax}"
        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": layer,
            "BBOX": bbox,
            "CRS": "EPSG:2056",
            "WIDTH": width_px,
            "HEIGHT": height_px,
            "FORMAT": "image/png",
            "TRANSPARENT": "TRUE"
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/png,image/*,*/*;q=0.8"
        }
        response = requests.get("https://wms.geo.admin.ch/", params=params, headers=headers)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
        else:
            print(" Failed to fetch WMS:", response.status_code)
            return None

    folder_name = os.path.basename(os.path.normpath(wd_folder))
    match = re.search(r"Liestal_2m_(\d+)", folder_name)
    if not match:
        raise ValueError(f"Could not extract ensemble number from folder name: {folder_name}")
    ensemble_number = match.group(1)

    time_steps = [f"{h*12:04d}" for h in lead_times_hours]
    selected_filenames = [f"Liestal_2m_{ensemble_number}_{ensemble_number}-{t}.wd" for t in time_steps]
    base_time = datetime.strptime(initial_datetime_str, "%Y-%m-%dT%H:%M:%S")
    os.makedirs(plot_output_folder, exist_ok=True)

    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        extent = (dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top)
        mask = dem_data != dem_nodata_value

    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")
    xlim = xlim if xlim else (extent[0], extent[1])
    ylim = ylim if ylim else (extent[2], extent[3])
    zoom_extent = (xlim[0], xlim[1], ylim[0], ylim[1])

    for filename, lead_hours in zip(selected_filenames, lead_times_hours):
        wd_file_path = os.path.join(wd_folder, filename)
        if not os.path.isfile(wd_file_path):
            print(f"File not found: {filename}")
            continue

        try:
            with rasterio.open(wd_file_path) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig = plt.figure(figsize=(12, 10))
            crs_2056 = ccrs.epsg(2056)
            ax = fig.add_subplot(1, 1, 1, projection=crs_2056)
            ax.set_extent(zoom_extent, crs=crs_2056)

            bg_img = get_swisstopo_background_image(*zoom_extent, resolution_m=2)
            if bg_img is not None:
                ax.imshow(bg_img, extent=zoom_extent, transform=crs_2056, zorder=0)
            else:
                print(" Background image not loaded.")

            ax.imshow(transparent_data, extent=extent, transform=crs_2056,
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, extent=extent, transform=crs_2056,
                      cmap=cmap, norm=norm, interpolation="none", zorder=2)

            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3)

            title = f"{plot_title_prefix} – {initial_datetime_str} + {lead_hours} hour lead time"
            ax.set_title(title, fontsize=18, fontweight="bold")
            ax.set_xlabel("Easting (m)", fontsize=16)
            ax.set_ylabel("Northing (m)", fontsize=16)

            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(filename)[0]}_nocbar.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f" Plot saved: {plot_filename}")

        except Exception as e:
            print(f" Failed to process {filename}: {e}")

    print(" All video-ready plots (without colorbar) have been generated and saved.")

######################################################################################################

def g_plots_selected_wd_liestal_dinamic_no_cbar(
    dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge,
    plot_title_prefix, initial_datetime_str, lead_times_hours,
    color1="violet", color2="mediumvioletred", color3="darkmagenta",
    xlim=None, ylim=None
):
    """
    Plots deterministic water depth maps from observation/single scenario (no ensemble index) without colorbar.
    Example filename: Liestal_2m_0000.wd, Liestal_2m_0012.wd, etc.
    """
    import requests
    from PIL import Image
    from io import BytesIO
    import matplotlib.pyplot as plt
    import rasterio
    import numpy as np
    from rasterio.warp import reproject, Resampling
    from matplotlib.colors import ListedColormap, BoundaryNorm
    import geopandas as gpd
    import cartopy.crs as ccrs
    import os
    from datetime import datetime

    def get_swisstopo_background_image(xmin, xmax, ymin, ymax, resolution_m=2, layer='ch.swisstopo.swisstlm3d-karte-grau'):
        width_px = int((xmax - xmin) / resolution_m)
        height_px = int((ymax - ymin) / resolution_m)
        bbox = f"{xmin},{ymin},{xmax},{ymax}"
        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": layer,
            "BBOX": bbox,
            "CRS": "EPSG:2056",
            "WIDTH": width_px,
            "HEIGHT": height_px,
            "FORMAT": "image/png",
            "TRANSPARENT": "TRUE"
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/png,image/*,*/*;q=0.8"
        }
        response = requests.get("https://wms.geo.admin.ch/", params=params, headers=headers)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
        else:
            print(" Failed to fetch WMS:", response.status_code)
            return None

    time_steps = [f"{h*12:04d}" for h in lead_times_hours]
    selected_filenames = [f"Liestal_2m-{t}.wd" for t in time_steps]
    base_time = datetime.strptime(initial_datetime_str, "%Y-%m-%dT%H:%M:%S")
    os.makedirs(plot_output_folder, exist_ok=True)

    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        extent = (dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top)
        mask = dem_data != dem_nodata_value

    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")
    xlim = xlim if xlim else (extent[0], extent[1])
    ylim = ylim if ylim else (extent[2], extent[3])
    zoom_extent = (xlim[0], xlim[1], ylim[0], ylim[1])

    for filename, lead_hours in zip(selected_filenames, lead_times_hours):
        wd_file_path = os.path.join(wd_folder, filename)
        if not os.path.isfile(wd_file_path):
            print(f"File not found: {filename}")
            continue

        try:
            with rasterio.open(wd_file_path) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig = plt.figure(figsize=(12, 10))
            crs_2056 = ccrs.epsg(2056)
            ax = fig.add_subplot(1, 1, 1, projection=crs_2056)
            ax.set_extent(zoom_extent, crs=crs_2056)

            bg_img = get_swisstopo_background_image(*zoom_extent, resolution_m=2)
            if bg_img is not None:
                ax.imshow(bg_img, extent=zoom_extent, transform=crs_2056, zorder=0)
            else:
                print(" Background image not loaded.")

            ax.imshow(transparent_data, extent=extent, transform=crs_2056,
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, extent=extent, transform=crs_2056,
                      cmap=cmap, norm=norm, interpolation="none", zorder=2)

            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3)

            title = f"{plot_title_prefix} – {initial_datetime_str} + {lead_hours} hour lead time"
            ax.set_title(title, fontsize=18, fontweight="bold")
            ax.set_xlabel("Easting (m)", fontsize=16)
            ax.set_ylabel("Northing (m)", fontsize=16)

            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(filename)[0]}_nocbar.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f"✔ Plot saved: {plot_filename}")

        except Exception as e:
            print(f" Failed to process {filename}: {e}")

    print(" All deterministic plots (no colorbar) have been generated and saved.")

############################################################################################

def plot_Liestal_Combiprecip_perhour(
    dem_file, wd_folder, plot_output_folder, geo_ezgg_2km_ge,
    plot_title_prefix, initial_datetime_str, lead_times_hours,
    color1="violet", color2="mediumvioletred", color3="darkmagenta",
    xlim=None, ylim=None
):
    """
    Plots deterministic water depth maps from observation/single scenario (no ensemble index) without colorbar.
    Example filename: Liestal_2m-0000.wd, Liestal_2m-0001.wd, etc.
    """
    import requests
    from PIL import Image
    from io import BytesIO
    import matplotlib.pyplot as plt
    import rasterio
    import numpy as np
    from rasterio.warp import reproject, Resampling
    from matplotlib.colors import ListedColormap, BoundaryNorm
    import geopandas as gpd
    import cartopy.crs as ccrs
    import os
    from datetime import datetime, timedelta

    def get_swisstopo_background_image(xmin, xmax, ymin, ymax, resolution_m=2, layer='ch.swisstopo.swisstlm3d-karte-grau'):
        width_px = int((xmax - xmin) / resolution_m)
        height_px = int((ymax - ymin) / resolution_m)
        bbox = f"{xmin},{ymin},{xmax},{ymax}"
        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": layer,
            "BBOX": bbox,
            "CRS": "EPSG:2056",
            "WIDTH": width_px,
            "HEIGHT": height_px,
            "FORMAT": "image/png",
            "TRANSPARENT": "TRUE"
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/png,image/*,*/*;q=0.8"
        }
        response = requests.get("https://wms.geo.admin.ch/", params=params, headers=headers)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
        else:
            print(" Failed to fetch WMS:", response.status_code)
            return None

    time_steps = [f"{h:04d}" for h in lead_times_hours]
    selected_filenames = [f"Liestal_2m-{t}.wd" for t in time_steps]
    base_time = datetime.strptime(initial_datetime_str, "%Y-%m-%dT%H:%M:%S")
    os.makedirs(plot_output_folder, exist_ok=True)

    with rasterio.open(dem_file) as src_dem:
        dem_data = src_dem.read(1)
        dem_nodata_value = src_dem.nodata if src_dem.nodata is not None else -9999
        dem_transform = src_dem.transform
        dem_bounds = src_dem.bounds
        dem_shape = dem_data.shape
        extent = (dem_bounds.left, dem_bounds.right, dem_bounds.bottom, dem_bounds.top)
        mask = dem_data != dem_nodata_value

    catchments = gpd.read_file(geo_ezgg_2km_ge).to_crs("EPSG:2056")
    xlim = xlim if xlim else (extent[0], extent[1])
    ylim = ylim if ylim else (extent[2], extent[3])
    zoom_extent = (xlim[0], xlim[1], ylim[0], ylim[1])

    for filename, lead_hours in zip(selected_filenames, lead_times_hours):
        wd_file_path = os.path.join(wd_folder, filename)
        if not os.path.isfile(wd_file_path):
            print(f"File not found: {filename}")
            continue

        try:
            with rasterio.open(wd_file_path) as src_wd:
                wd_data = src_wd.read(1)
                wd_transform = src_wd.transform

            aligned_data = np.full(dem_shape, np.nan, dtype=np.float32)
            reproject(
                source=wd_data,
                destination=aligned_data,
                src_transform=wd_transform,
                src_crs="EPSG:2056",
                dst_transform=dem_transform,
                dst_crs="EPSG:2056",
                resampling=Resampling.nearest,
            )

            masked_data = np.where((mask & (aligned_data >= 0.10)), aligned_data, np.nan)
            transparent_data = np.where((aligned_data >= 0) & (aligned_data < 0.10), 1, np.nan)

            categories = [0.10, 0.25, 0.50, 0.60]
            colors = [color1, color2, color3]
            cmap = ListedColormap(colors)
            norm = BoundaryNorm(categories, cmap.N, clip=True)

            fig = plt.figure(figsize=(12, 10))
            crs_2056 = ccrs.epsg(2056)
            ax = fig.add_subplot(1, 1, 1, projection=crs_2056)
            ax.set_extent(zoom_extent, crs=crs_2056)

            bg_img = get_swisstopo_background_image(*zoom_extent, resolution_m=2)
            if bg_img is not None:
                ax.imshow(bg_img, extent=zoom_extent, transform=crs_2056, zorder=0)
            else:
                print(" Background image not loaded.")

            ax.imshow(transparent_data, extent=extent, transform=crs_2056,
                      cmap=ListedColormap(['none']), interpolation="none", zorder=1)
            ax.imshow(masked_data, extent=extent, transform=crs_2056,
                      cmap=cmap, norm=norm, interpolation="none", zorder=2)

            catchments.boundary.plot(ax=ax, edgecolor="black", linewidth=0.7, zorder=3)

            # ⏰ Actual forecast time title
            forecast_time = base_time + timedelta(hours=lead_hours)
            title = f"{plot_title_prefix} – {forecast_time.strftime('%Y-%m-%dT%H:%M:%S')}"
            ax.set_title(title, fontsize=18, fontweight="bold")
            ax.set_xlabel("Easting (m)", fontsize=16)
            ax.set_ylabel("Northing (m)", fontsize=16)

            plot_filename = os.path.join(plot_output_folder, f"{os.path.splitext(filename)[0]}_nocbar.png")
            plt.savefig(plot_filename, dpi=300, bbox_inches="tight")
            plt.close()

            print(f"✔ Plot saved: {plot_filename}")

        except Exception as e:
            print(f" Failed to process {filename}: {e}")

    print("✅ All deterministic plots (no colorbar) have been generated and saved.")