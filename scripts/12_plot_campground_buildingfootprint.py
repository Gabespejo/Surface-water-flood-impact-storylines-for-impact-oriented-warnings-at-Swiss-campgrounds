#!/usr/bin/env python3
"""
campground_building_exposure.py

One-stop script to:
- buffer buildings inside one campground polygon
- intersect LISFLOOD ASCII grid points
- compute max/mean depth per building
- classify (Low/Medium/High)
- export results (shp/csv/summary)
- save a "Figure 1"-style plot (camp boundary, original buildings, buffers, grid points, id labels)

Example (save plot to a FULL path):
python campground_building_exposure.py \
  --hazard "/storage/homefs/ge24z347/.../Morges_2m_75min_75.max" \
  --buildings "/rs_scratch/users/ge24z347/Data_forprocess/geo_hwr_footp_tlm2023.shp" \
  --campgrounds "/rs_scratch/users/ge24z347/Data_forprocess/addedpolygons_campingsite_391.geojson" \
  --camp-col "Campingplaetze_excel_finshed_Campingplatz" \
  --camp-name "TCS Camping Morges" \
  --buffer-m 2 \
  --outdir "/storage/homefs/ge24z347/LISFLOOD_FP_outputs/Morges_2m_scenarios" \
  --plot \
  --plot-transparent \
  --plot-path "/storage/homefs/ge24z347/Figures/Morges_clean_figure.png"
"""

from pathlib import Path
import re
import datetime
import argparse

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.pyplot as plt

try:
    import rtree
except ImportError as e:
    raise ImportError(
        "Missing dependency: rtree. Install it in your env (e.g., conda install rtree)."
    ) from e


# ----------------------------
# Core: exposure + classification
# ----------------------------
def generate_buffered_buildings_for_one_campground(
    hazard_path,
    buildings_path,
    geojson_file,
    polygon_column_name,
    polygon_name,
    buffer_meters=None,
    buffer_percent=100,
    output_folder="Outputs_Events",
):
    """
    Buffers only those buildings that fall inside a selected campground polygon,
    intersects with hazard grid points, and classifies based on depth values.

    Returns:
      final_gdf (GeoDataFrame),
      x_coords (list),
      y_coords (list),
      cell_index (list of int indices of intersected cells; may contain duplicates)
    """
    T_start = datetime.datetime.now()
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    # --- Load input data
    campgrounds_gdf = gpd.read_file(geojson_file)
    buildings_gdf = gpd.read_file(buildings_path)

    # Normalize selection (avoid trailing spaces issues)
    col_norm = campgrounds_gdf[polygon_column_name].astype(str).str.strip().str.lower()
    name_norm = str(polygon_name).strip().lower()
    selected_camp = campgrounds_gdf[col_norm == name_norm]

    if selected_camp.empty:
        available = sorted(campgrounds_gdf[polygon_column_name].astype(str).unique())
        raise ValueError(
            f"No campground found with name: '{polygon_name}'.\n"
            f"Column: {polygon_column_name}\n"
            f"Example available names: {available[:10]} ..."
        )

    camp_geom = selected_camp.iloc[0].geometry

    # --- Read ASCII header & raster values
    hazard_path = Path(hazard_path)
    with hazard_path.open("r") as f:
        ncols = int(f.readline().split()[1])
        nrows = int(f.readline().split()[1])
        xllcorner = float(f.readline().split()[1])
        yllcorner = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata_value = float(f.readline().split()[1])
        data_lines = f.readlines()

    dx = cellsize
    buffer_dist = buffer_meters if buffer_meters is not None else (buffer_percent / 100.0) * dx

    x_coords, y_coords, Z = [], [], []

    # NOTE: This matches your original approach (grid point at cell corner).
    # If you want *centers*, use:
    #   xllcorner + (col_idx + 0.5)*dx
    #   yllcorner + (nrows - 1 - row_idx + 0.5)*dx
    for row_idx, line in enumerate(data_lines):
        row_vals = [float(v) for v in re.split(r"\s+", line.strip()) if v]
        for col_idx, val in enumerate(row_vals):
            x_coords.append(xllcorner + col_idx * dx)
            y_coords.append(yllcorner + (nrows - 1 - row_idx) * dx)
            Z.append(val)

    Z = np.array(Z, dtype=float)
    Z[Z == nodata_value] = np.nan  # nodata -> nan

    # --- Build spatial index for grid points
    index = rtree.index.Index()
    for i, (xi, yi) in enumerate(zip(x_coords, y_coords)):
        index.insert(i, (xi, yi, xi, yi))  # bbox for a point

    # --- Filter buildings in campground
    buildings_in_camp = buildings_gdf[buildings_gdf.within(camp_geom)].copy()

    # --- Buffer buildings (sharp corners)
    buffered_geometries = []
    buffer_list = []
    cell_index = []

    for _, bldg in buildings_in_camp.iterrows():
        bldg_id = bldg["id_def"]
        buf = bldg.geometry.buffer(buffer_dist, resolution=1, cap_style=2, join_style=2)
        buffered_geometries.append(buf)

        for cell in list(index.intersection(buf.bounds)):
            pt = Point(x_coords[cell], y_coords[cell])
            if pt.intersects(buf):
                buffer_list.append(bldg_id)
                cell_index.append(cell)

    # overwrite geometry with buffers for output gdf
    buildings_in_camp["geometry"] = buffered_geometries
    buildings_in_camp = gpd.GeoDataFrame(buildings_in_camp, geometry="geometry", crs=buildings_gdf.crs)

    # --- Build depth table for all building-cell intersections
    if len(cell_index) == 0:
        buildings_in_camp["max_depth"] = 0.0
        buildings_in_camp["mean_depth"] = 0.0
        buildings_in_camp["class"] = "Low"
        buildings_in_camp["internally_flooded"] = False
        buildings_in_camp["area"] = buildings_in_camp.geometry.area.astype(int)
        final_gdf = buildings_in_camp

    else:
        depths = Z[np.array(cell_index, dtype=int)]
        df = pd.DataFrame({"depth": depths, "id_def": buffer_list})
        df = df.dropna(subset=["depth"])

        if df.empty:
            buildings_in_camp["max_depth"] = 0.0
            buildings_in_camp["mean_depth"] = 0.0
            buildings_in_camp["class"] = "Low"
            buildings_in_camp["internally_flooded"] = False
            buildings_in_camp["area"] = buildings_in_camp.geometry.area.astype(int)
            final_gdf = buildings_in_camp
        else:
            max_depth = df.groupby("id_def")["depth"].max().round(3).reset_index(name="max_depth")
            mean_depth = df.groupby("id_def")["depth"].mean().round(3).reset_index(name="mean_depth")
            categ_df = pd.merge(max_depth, mean_depth, on="id_def", how="outer")

            # --- Classification rules (unchanged)
            categ_df["class"] = "Low"
            categ_df.loc[(categ_df["mean_depth"] < 0.1) & (categ_df["max_depth"] >= 0.3), "class"] = "Medium"
            categ_df.loc[(categ_df["mean_depth"] >= 0.1) & (categ_df["max_depth"] < 0.3), "class"] = "Medium"
            categ_df.loc[(categ_df["mean_depth"] >= 0.1) & (categ_df["max_depth"] >= 0.3), "class"] = "High"
            categ_df["internally_flooded"] = categ_df["class"] == "High"

            final_gdf = buildings_in_camp.merge(categ_df, on="id_def", how="left")
            final_gdf["area"] = final_gdf.geometry.area.astype(int)
            final_gdf.fillna(
                {"class": "Low", "max_depth": 0.0, "mean_depth": 0.0, "internally_flooded": False},
                inplace=True,
            )

    # --- Export
    base_name = hazard_path.stem
    shp_out = output_folder / f"{base_name}_floodrisk.shp"
    csv_out = output_folder / f"{base_name}_floodrisk.csv"
    txt_out = output_folder / f"{base_name}_summary.txt"

    final_gdf.to_file(shp_out)
    final_gdf.drop(columns="geometry").to_csv(csv_out, index=False)

    with txt_out.open("w") as summary:
        summary.write(
            f"Summary of Exposure Analysis for: {base_name}\n\n"
            f"Campground: {polygon_name}\n"
            f"Building file: {buildings_path}\n"
            f"Hazard file: {hazard_path}\n\n"
            f"Number of buildings (inside camp): {len(final_gdf)}\n"
            f"Grid resolution: {dx} m\n"
            f"Buffer distance: {buffer_dist} m\n\n"
            f"Low: {(final_gdf['class'] == 'Low').sum()}\n"
            f"Medium: {(final_gdf['class'] == 'Medium').sum()}\n"
            f"High: {(final_gdf['class'] == 'High').sum()}\n"
        )

    print("Finished. Time required:", str(datetime.datetime.now() - T_start)[:-4])
    print("Saved:", shp_out)
    print("Saved:", csv_out)
    print("Saved:", txt_out)

    return final_gdf, x_coords, y_coords, cell_index


# ----------------------------
# Plot: "Figure 1"-style overview
# ----------------------------
def plot_intersections_with_grid_id(
    buffer_gdf,
    camp_polygon_path,
    polygon_column_name,
    polygon_name,
    buildings_path,
    x_coords,
    y_coords,
    cell_index,
    save_path,                # FULL path + filename
    transparent=True,
    label_offset=5,
):
    """
    Clean publication plot:
    - NO title
    - NO axis labels
    - NO ticks
    - NO grid
    - Transparent background
    - Legend only
    """

    camp_gdf = gpd.read_file(camp_polygon_path)
    camp_gdf["__cmp"] = camp_gdf[polygon_column_name].astype(str).str.strip().str.lower()
    polygon_name_clean = str(polygon_name).strip().lower()
    selected_camp = camp_gdf[camp_gdf["__cmp"] == polygon_name_clean]

    if selected_camp.empty:
        raise ValueError(f"Campground '{polygon_name}' not found.")

    camp_gdf.drop(columns="__cmp", inplace=True)

    buildings_gdf = gpd.read_file(buildings_path)
    buildings_in_camp = buildings_gdf[buildings_gdf.within(selected_camp.iloc[0].geometry)]

    points_x = [x_coords[i] for i in cell_index]
    points_y = [y_coords[i] for i in cell_index]

    fig, ax = plt.subplots(figsize=(10, 10))

    selected_camp.boundary.plot(ax=ax, color="black", linewidth=1, label="Campground")

    buildings_in_camp.plot(
        ax=ax,
        color="lightblue",
        edgecolor="blue",
        linewidth=0.7,
        label="Original Buildings",
    )

    buffer_gdf.boundary.plot(
        ax=ax,
        color="red",
        linewidth=1,
        label="Buffered Building",
    )

    ax.scatter(points_x, points_y, s=2, color="blue", alpha=0.4, label="Intersected Grid Points")

    if "id_def" in buildings_in_camp.columns:
        for _, row in buildings_in_camp.iterrows():
            centroid = row.geometry.centroid
            ax.text(
                centroid.x + label_offset,
                centroid.y + label_offset,
                str(int(row["id_def"])),
                fontsize=8,
                color="black",
                fontweight="bold",
            )

    # Clean style
    ax.set_title("")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_axis_off()
    ax.legend(frameon=False)
    ax.set_aspect("equal")

    plt.tight_layout()

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(
        save_path,
        dpi=300,
        transparent=transparent,
        bbox_inches="tight",
        pad_inches=0,
    )
    plt.close(fig)

    print(f"Saved clean figure to: {save_path}")


# ----------------------------
# CLI
# ----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Campground building exposure + Figure 1 plot")
    p.add_argument("--hazard", required=True, help="Path to LISFLOOD ASCII raster (.max/.asc).")
    p.add_argument("--buildings", required=True, help="Path to buildings shapefile/geo-package (must have id_def).")
    p.add_argument("--campgrounds", required=True, help="Path to campgrounds GeoJSON (or any vector).")
    p.add_argument("--camp-col", required=True, help="Column in campgrounds with campground names.")
    p.add_argument("--camp-name", required=True, help="Campground name to select (string match, spaces OK).")

    p.add_argument("--buffer-m", type=float, default=None, help="Buffer distance in meters (e.g., 2).")
    p.add_argument(
        "--buffer-percent",
        type=float,
        default=100.0,
        help="If --buffer-m not set, buffer = (buffer_percent/100)*cellsize (default 100).",
    )

    p.add_argument("--outdir", required=True, help="Output directory for shp/csv/summary outputs.")
    p.add_argument("--plot", action="store_true", help="If set, also save the Figure 1 plot PNG.")
    p.add_argument("--plot-transparent", action="store_true", help="Save plot with transparent background.")

    # NEW: full plot path
    p.add_argument("--plot-out", dest="plot_path", default=None,
               help="Full path including filename where plot will be saved.")

    # Backward compatible option (optional)
    p.add_argument(
        "--plot-name",
        default=None,
        help="(Optional) Filename for plot PNG if --plot-path is not set (default: <hazard_stem>_grid_intersection.png).",
    )

    return p.parse_args()


def main():
    a = parse_args()
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    final_gdf, x_coords, y_coords, cell_index = generate_buffered_buildings_for_one_campground(
        hazard_path=a.hazard,
        buildings_path=a.buildings,
        geojson_file=a.campgrounds,
        polygon_column_name=a.camp_col,
        polygon_name=a.camp_name,
        buffer_meters=a.buffer_m,
        buffer_percent=a.buffer_percent,
        output_folder=str(outdir),
    )

    if a.plot:
        # Priority 1: user provides full plot path
        if a.plot_path:
            plot_path = Path(a.plot_path)
            plot_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # fallback to outdir + plot-name / default
            hazard_stem = Path(a.hazard).stem
            plot_name = a.plot_name or f"{hazard_stem}_grid_intersection.png"
            plot_path = outdir / plot_name

        plot_intersections_with_grid_id(
            buffer_gdf=final_gdf,
            camp_polygon_path=a.campgrounds,
            polygon_column_name=a.camp_col,
            polygon_name=a.camp_name,
            buildings_path=a.buildings,
            x_coords=x_coords,
            y_coords=y_coords,
            cell_index=cell_index,
            save_path=str(plot_path),
            transparent=a.plot_transparent,
        )


if __name__ == "__main__":
    main()
