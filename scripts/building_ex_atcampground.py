#!/usr/bin/env -S mamba run -n env_py311 python
# -*- coding: utf-8 -*-

"""
Campground flood exposure (multi-scenario, multi-camp) – CLI
Outputs ONLY:
  • CSV summary (per campground / scenario / optional asset class)
  • Heatmap PNGs (optional)

Example:
  ./camp_exposure_cli.py \
    --hazard '/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build/*_2m_v*/**/*.max' \
    --scenario-regex '_(\\d+)\\.max$' \
    --buildings '/rs_scratch/users/ge24z347/Data_forprocess/geo_hwr_footp_tlm2023.shp' \
    --campgrounds '/rs_scratch/users/ge24z347/Data_forprocess/addedpolygons_campingsite_391.geojson' \
    --polygon-column 'Campingplaetze_excel_finshed_Campingplatz' \
    --camp 'TCS Camping Salavaux plage ' \
    --buffer-m 2 \
    --summary-out '/storage/homefs/ge24z347/buildings_exposed_atcampgrounds/summary.csv' \
    --plot-heatmaps \
    --plots-outdir '/storage/homefs/ge24z347/buildings_exposed_atcampgrounds/plots'
"""

import os
import re
import glob
import math
import argparse
import datetime
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point
from matplotlib.colors import ListedColormap, BoundaryNorm

# ---------- I/O helpers ----------

def read_ascii_max(hazard_path: str):
    """Read LISFLOOD .max ASCII (ESRI ASCII-like)."""
    with open(hazard_path, "r") as f:
        ncols = int(f.readline().split()[1])
        nrows = int(f.readline().split()[1])
        xll = float(f.readline().split()[1])
        yll = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata = float(f.readline().split()[1])
        data = np.fromstring(" ".join(ln.strip() for ln in f.readlines()), sep=" ")
    if data.size != ncols * nrows:
        raise ValueError(f"[{hazard_path}] grid has {data.size} values but expected {ncols*nrows}")
    Z = data.reshape((nrows, ncols))
    return ncols, nrows, xll, yll, cellsize, nodata, Z

def extract_scenario_id(path: str, regex: str):
    m = re.search(regex, os.path.basename(path))
    if not m:
        return None
    # Support patterns with one or more capturing groups; use the first non-None
    for g in m.groups():
        if g is not None:
            return int(g)
    return None

# ---------- core computation ----------

def iterate_candidate_indices(bbox, ncols, nrows, xll, yll, dx):
    """Map a geometry bbox to candidate row/col index ranges."""
    minx, miny, maxx, maxy = bbox
    c_min = int(math.floor((minx - xll) / dx))
    c_max = int(math.floor((maxx - xll) / dx))
    c_min = max(0, min(c_min, ncols - 1))
    c_max = max(0, min(c_max, ncols - 1))
    r_min = int(math.floor(nrows - 1 - (maxy - yll) / dx))
    r_max = int(math.floor(nrows - 1 - (miny - yll) / dx))
    r_min = max(0, min(r_min, nrows - 1))
    r_max = max(0, min(r_max, nrows - 1))
    return r_min, r_max, c_min, c_max

def classify_depths(df, mean_thr=0.1, max_thr=0.3):
    """Low/Medium/High rules (your thresholds)."""
    df = df.copy()
    df["class"] = "Low"
    df.loc[(df["mean_depth"] < mean_thr) & (df["max_depth"] >= max_thr), "class"] = "Medium"
    df.loc[(df["mean_depth"] >= mean_thr) & (df["max_depth"] < max_thr), "class"] = "Medium"
    df.loc[(df["mean_depth"] >= mean_thr) & (df["max_depth"] >= max_thr), "class"] = "High"
    df["internally_flooded"] = df["class"].eq("High")
    return df

def process_one_hazard(
    hazard_path,
    camps_sel,
    polygon_column,
    bldg_gdf,
    id_column,
    asset_class_column,
    buffer_m,
    scenario_regex,
):
    """Process a single hazard raster against all selected campgrounds."""
    ncols, nrows, xll, yll, dx, nodata, Z = read_ascii_max(hazard_path)
    scenario = extract_scenario_id(hazard_path, scenario_regex)
    if scenario is None:
        raise ValueError(f"Could not extract scenario id from: {hazard_path}")

    out = []
    for _, camp in camps_sel.iterrows():
        camp_name = str(camp[polygon_column])
        camp_geom = camp.geometry

        # Buildings strictly inside the camp polygon (buffer(0) to fix potential ring validity)
        b_in = bldg_gdf[bldg_gdf.geometry.within(camp_geom.buffer(0))].copy()
        if b_in.empty:
            continue

        # Buffer buildings (square caps to match your original choice)
        b_in["buffer_geom"] = b_in.geometry.buffer(buffer_m, resolution=1, cap_style=2, join_style=2)

        rows = []
        for _, b in b_in.iterrows():
            bid = b.get(id_column, b.name)
            buf = b["buffer_geom"]
            r_min, r_max, c_min, c_max = iterate_candidate_indices(buf.bounds, ncols, nrows, xll, yll, dx)

            depths = []
            for r in range(r_min, r_max + 1):
                y = yll + (nrows - 1 - r) * dx
                for c in range(c_min, c_max + 1):
                    x = xll + c * dx
                    if buf.contains(Point(x, y)):
                        d = Z[r, c]
                        if d != nodata:
                            depths.append(d)

            if depths:
                rows.append((bid, float(np.max(depths)), float(np.mean(depths))))
            else:
                rows.append((bid, 0.0, 0.0))

        tmp = pd.DataFrame(rows, columns=[id_column, "max_depth", "mean_depth"])
        tmp = classify_depths(tmp, mean_thr=0.1, max_thr=0.3)

        keep_cols = [id_column, "geometry"]
        if asset_class_column and asset_class_column in b_in.columns:
            keep_cols.append(asset_class_column)

        g = b_in[keep_cols].merge(tmp, on=id_column, how="left")
        g["area"] = g.geometry.area.astype(int)
        g["scenario"] = scenario
        g["campground"] = camp_name
        out.append(g)

    return out

def summarize_results(results_gdf, id_column, asset_class_column=None):
    group_cols = ["campground", "scenario"]
    if asset_class_column and asset_class_column in results_gdf.columns:
        group_cols.append(asset_class_column)

    summary = (
        results_gdf
        .groupby(group_cols, dropna=False)
        .agg(
            total_assets=(id_column, "count"),
            affected_high=("internally_flooded", "sum"),
            pct_affected_high=("internally_flooded", lambda s: 100.0 * s.sum() / max(len(s), 1)),
            mean_max_depth=("max_depth", "mean"),
            mean_mean_depth=("mean_depth", "mean"),
        )
        .reset_index()
        .sort_values(group_cols)
    )
    return summary

# ---------- plotting (optional) ----------

def plot_heatmaps(summary_df, outdir, asset_class_column=None):
    """Original continuous %High heatmaps (per camp, optionally per asset class)."""
    os.makedirs(outdir, exist_ok=True)
    for camp, dfc in summary_df.groupby("campground"):
        if asset_class_column and asset_class_column in dfc.columns and dfc[asset_class_column].notna().any():
            pivot = dfc.pivot_table(index=asset_class_column, columns="scenario",
                                    values="pct_affected_high", aggfunc="mean")
            title = f"{camp} – % High by class"
            outpng = os.path.join(outdir, f"{camp}_byclass_heatmap.png")
        else:
            pivot = dfc.pivot_table(index="campground", columns="scenario",
                                    values="pct_affected_high", aggfunc="mean")
            title = f"{camp} – % High"
            outpng = os.path.join(outdir, f"{camp}_heatmap.png")

        # sort scenarios numerically
        try:
            sorted_cols = sorted(pivot.columns, key=lambda x: int(x))
            pivot = pivot.reindex(sorted_cols, axis=1)
        except Exception:
            pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        _simple_heatmap(pivot, outpng, title=title)

def _simple_heatmap(pivot_df, outpng, title=""):
    arr = pivot_df.values.astype(float)
    fig, ax = plt.subplots(figsize=(max(6, arr.shape[1] * 0.8), 2.2 + 0.6 * max(0, arr.shape[0]-1)))
    im = ax.imshow(arr, aspect="auto")
    ax.set_title(title)
    ax.set_yticks(range(pivot_df.shape[0]))
    ax.set_yticklabels(list(pivot_df.index))
    ax.set_xticks(range(pivot_df.shape[1]))
    ax.set_xticklabels(list(pivot_df.columns), rotation=45, ha="right")
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, f"{arr[i, j]:.0f}%", va="center", ha="center")
    plt.colorbar(im, ax=ax, label="% affected (High)")
    plt.tight_layout()
    fig.savefig(outpng, dpi=200)
    plt.close(fig)

def plot_categorical_heatmaps(results_gdf, outdir, id_column):
    """
    New categorical heatmaps:
      • One heatmap per campground
      • Rows = building IDs, columns = scenarios
      • Cell colors = Low / Medium / High using fixed palette
      • If multiple model versions exist for the same scenario, we take the worst class (High > Medium > Low).
    """
    os.makedirs(outdir, exist_ok=True)

    # Map classes to integers for a categorical colormap
    class_to_int = {"Low": 0, "Medium": 1, "High": 2}

    # Your requested colors: Low (beige), Medium (orange), High (dark red)
    cmap = ListedColormap(["#f5d7a4", "#f28c1b", "#8e0d12"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)

    for camp, dfc in results_gdf.groupby("campground"):
        # Build a tidy table with numeric class codes
        tidy = (
            dfc[[id_column, "scenario", "class"]]
            .assign(cls_num=lambda d: d["class"].map(class_to_int).fillna(0).astype(int))
        )

        # Aggregate duplicates (same building + same scenario across multiple versions)
        # Rule: keep the WORST (max) class -> High > Medium > Low
        tidy_agg = (
            tidy.groupby([id_column, "scenario"], as_index=False)["cls_num"].max()
        )

        # Pivot to buildings × scenarios
        pivot = tidy_agg.pivot(index=id_column, columns="scenario", values="cls_num")

        # sort scenarios numerically if possible
        try:
            pivot = pivot.reindex(sorted(pivot.columns, key=int), axis=1)
        except Exception:
            pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        arr = pivot.values
        if arr.size == 0:
            continue

        # figure size scales with content
        fig, ax = plt.subplots(
            figsize=(max(7, arr.shape[1] * 0.8), max(4, 0.35 * max(5, arr.shape[0])))
        )
        im = ax.imshow(arr, aspect="auto", cmap=cmap, norm=norm)

        ax.set_title(f"Building Exposure by Rainfall Scenario – {camp}")
        ax.set_yticks(range(pivot.shape[0]))
        ax.set_yticklabels([str(i) for i in pivot.index])
        ax.set_xticks(range(pivot.shape[1]))
        ax.set_xticklabels([str(c) for c in pivot.columns], rotation=45, ha="right")

        # categorical colorbar with labels
        cbar = plt.colorbar(im, ax=ax, ticks=[0, 1, 2])
        cbar.ax.set_yticklabels(["Low", "Medium", "High"])

        outpng = os.path.join(outdir, f"{camp}_categorical_heatmap.png")
        plt.tight_layout()
        fig.savefig(outpng, dpi=200)
        plt.close(fig)

# ---------- CLI ----------

def main():
    p = argparse.ArgumentParser(description="Campground flood exposure (CSV + heatmaps only)")
    p.add_argument("--hazard", required=True,
                   help="Glob for .max files (supports ** recursion, e.g., '/path/*_2m_v*/**/*.max').")
    p.add_argument("--scenario-regex", default=r"_(\d+)\.max$",
                   help="Regex to extract scenario id from filename (default matches '..._10.max').")
    p.add_argument("--buildings", required=True, help="Buildings footprints (GeoPackage/Shapefile).")
    p.add_argument("--campgrounds", required=True, help="Campgrounds polygons (GeoJSON/GPKG/etc.).")
    p.add_argument("--polygon-column", required=True, help="Column in camp layer with the campground name.")
    p.add_argument("--camp", action="append", required=True,
                   help="Campground name to include (repeat flag for multiple).")
    p.add_argument("--id-column", default="id_def", help="Building id column (default: id_def).")
    p.add_argument("--asset-class-column", default=None,
                   help="Optional column in buildings for class (e.g., 'mobile'/'non_mobile').")
    p.add_argument("--buffer-m", type=float, default=2.0, help="Buffer (meters) around each building (default: 2).")
    p.add_argument("--summary-out", required=True, help="CSV for per-camp (and class) summaries.")
    p.add_argument("--plot-heatmaps", action="store_true", help="If set, export heatmaps per campground.")
    p.add_argument("--plots-outdir", default=None, help="Folder to save heatmaps (required if --plot-heatmaps).")
    p.add_argument("--plot-out",dest="plot_out",default=None,help="Full path including filename where plot will be saved.")
    args = p.parse_args()

    start = datetime.datetime.now()

    # Hazards (enable **)
    hazard_paths = sorted(glob.glob(args.hazard, recursive=True))
    if not hazard_paths:
        raise SystemExit(f"No hazard files found for pattern: {args.hazard}")

    # Load static layers
    bldg_gdf = gpd.read_file(args.buildings)
    camps_gdf = gpd.read_file(args.campgrounds)

    # CRS checks
    if bldg_gdf.crs is None or not bldg_gdf.crs.is_projected:
        raise SystemExit("Buildings layer must be in a projected CRS (meters).")
    if camps_gdf.crs != bldg_gdf.crs:
        camps_gdf = camps_gdf.to_crs(bldg_gdf.crs)

    # Filter camps
    if args.polygon_column not in camps_gdf.columns:
        raise SystemExit(f"Campgrounds file lacks column: {args.polygon_column}")
    camps_sel = camps_gdf[camps_gdf[args.polygon_column].isin(args.camp)].copy()
    if camps_sel.empty:
        raise SystemExit("No campgrounds matched the provided --camp names.")

    # Process hazards
    all_gdfs = []
    for hp in hazard_paths:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Processing hazard: {hp}")
        gdfs = process_one_hazard(
            hp, camps_sel, args.polygon_column, bldg_gdf, args.id_column,
            args.asset_class_column, args.buffer_m, args.scenario_regex
        )
        all_gdfs.extend(gdfs)

    if not all_gdfs:
        raise SystemExit("No results were produced. Check your inputs.")

    results_gdf = gpd.GeoDataFrame(pd.concat(all_gdfs, ignore_index=True), geometry="geometry", crs=bldg_gdf.crs)

    # CSV summary
    summary_df = summarize_results(results_gdf, args.id_column, args.asset_class_column)
    os.makedirs(os.path.dirname(args.summary_out), exist_ok=True)
    summary_df.to_csv(args.summary_out, index=False)
    print(f"Saved summary: {args.summary_out}")

    # Optional heatmaps
    if args.plot_heatmaps:
        if not args.plots_outdir:
            raise SystemExit("--plots-outdir is required when --plot-heatmaps is set.")
        # Only categorical (Low/Medium/High) heatmap
        plot_categorical_heatmaps(results_gdf, args.plots_outdir, args.id_column)
        print(f"Saved categorical heatmaps to: {args.plots_outdir}")

    elapsed = datetime.datetime.now() - start
    print(f"Done in {str(elapsed)[:-4]}.")

if __name__ == "__main__":
    main()