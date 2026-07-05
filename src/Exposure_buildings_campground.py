import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import rtree
import os
import re
import datetime
from operator import itemgetter

def generate_buffered_buildings_for_one_campground(
    hazard_path, 
    buildings_path, 
    geojson_file, 
    polygon_column_name, 
    polygon_name, 
    buffer_meters=None, 
    buffer_percent=100,
    output_folder="Outputs_Events"
):
    """
    Buffers only those buildings that fall inside a selected campground polygon,
    intersects with hazard grid cell centers, and classifies based on depth values.

    Parameters:
    - hazard_path: path to ASCII raster (.asc) to extract grid resolution and depths
    - buildings_path: path to buildings file (must include 'id_def')
    - geojson_file: path to campgrounds GeoJSON
    - polygon_column_name: name of the column with campground names
    - polygon_name: exact name of the campground to select
    - buffer_meters: fixed buffer distance (in meters)
    - buffer_percent: fallback buffer as % of raster resolution if buffer_meters is None
    - output_folder: directory to save outputs

    Returns:
    - GeoDataFrame of classified buildings with 'id_def', depths, and flood class
    """

    T_start = datetime.datetime.now()

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Step 1: Load input data
    campgrounds_gdf = gpd.read_file(geojson_file)
    buildings_gdf = gpd.read_file(buildings_path)

    selected_camp = campgrounds_gdf[campgrounds_gdf[polygon_column_name] == polygon_name]
    if selected_camp.empty:
        raise ValueError(f"No campground found with name: {polygon_name}")
    camp_geom = selected_camp.iloc[0].geometry

    # Step 2: Read ASCII header and build grid
    with open(hazard_path, 'r') as f:
        ncols = int(f.readline().split()[1])
        nrows = int(f.readline().split()[1])
        xllcorner = float(f.readline().split()[1])
        yllcorner = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata_value = float(f.readline().split()[1])
        data_lines = f.readlines()

    dx = cellsize
    buffer_dist = buffer_meters if buffer_meters is not None else (buffer_percent / 100) * dx

    x_coords = []
    y_coords = []
    Z = []
    for row_idx, line in enumerate(data_lines):
        row_vals = [float(v) for v in re.split(r'\s+', line.strip()) if v]
        for col_idx, val in enumerate(row_vals):
            x_coords.append(xllcorner + col_idx * dx)
            y_coords.append(yllcorner + (nrows - 1 - row_idx) * dx)
            Z.append(val)

    # Step 3: Create spatial index of grid cell centers
    index = rtree.index.Index()
    for i, (xi, yi) in enumerate(zip(x_coords, y_coords)):
        index.insert(i, (xi, yi))

    # Step 4: Filter buildings and apply sharp-edge buffer
    buildings_in_camp = buildings_gdf[buildings_gdf.within(camp_geom)].copy()

    buffer_list = []
    cell_index = []
    buffered_geometries = []

    for _, bldg in buildings_in_camp.iterrows():
        bldg_id = bldg['id_def']
        # Create sharp-corner buffer using cap_style=2 and join_style=2
        buffer = bldg['geometry'].buffer(buffer_dist, resolution=1, cap_style=2, join_style=2)
        buffered_geometries.append(buffer)
        for cell in list(index.intersection(buffer.bounds)):
            pt = Point(x_coords[cell], y_coords[cell])
            if pt.intersects(buffer):
                buffer_list.append(bldg_id)
                cell_index.append(cell)

    buildings_in_camp["geometry"] = buffered_geometries
    buildings_in_camp = gpd.GeoDataFrame(buildings_in_camp, geometry="geometry", crs=buildings_gdf.crs)

    df = pd.DataFrame(list(zip(itemgetter(*cell_index)(Z), buffer_list)), columns=['depth', 'id_def'])

    max_depth = df.groupby('id_def')['depth'].max().round(3).reset_index(name='max_depth')
    mean_depth = df.groupby('id_def')['depth'].mean().round(3).reset_index(name='mean_depth')
    categ_df = pd.merge(max_depth, mean_depth)

    # Step 5: Classification based on thresholds
    categ_df['class'] = 'Low'
    categ_df.loc[(categ_df['mean_depth'] < 0.1) & (categ_df['max_depth'] >= 0.3), 'class'] = 'Medium'
    categ_df.loc[(categ_df['mean_depth'] >= 0.1) & (categ_df['max_depth'] < 0.3), 'class'] = 'Medium'
    categ_df.loc[(categ_df['mean_depth'] >= 0.1) & (categ_df['max_depth'] >= 0.3), 'class'] = 'High'
    categ_df['internally_flooded'] = categ_df['class'] == 'High'

    final_gdf = buildings_in_camp.merge(categ_df, on='id_def', how='left')
    final_gdf['area'] = final_gdf.geometry.area.astype(int)
    final_gdf.fillna({'class': 'Low', 'max_depth': 0.0, 'mean_depth': 0.0, 'internally_flooded': False}, inplace=True)

    # Step 6: Export results
    base_name = os.path.splitext(os.path.basename(hazard_path))[0]
    final_gdf.to_file(f"{output_folder}/{base_name}_floodrisk.shp")
    final_gdf.drop(columns='geometry').to_csv(f"{output_folder}/{base_name}_floodrisk.csv", index=False)

    with open(f"{output_folder}/{base_name}_summary.txt", 'w') as summary:
        summary.write(f'Summary of Exposure Analysis for: {base_name}\n\n'
                      f'Campground: {polygon_name}\n'
                      f'Building file: {buildings_path}\n\n'
                      f'Number of buildings: {len(buildings_in_camp)}\n'
                      f'Grid resolution: {dx}m\n'
                      f'Buffer distance: {buffer_dist}m\n\n'
                      f"Low: {(final_gdf['class'] == 'Low').sum()}\n"
                      f"Medium: {(final_gdf['class'] == 'Medium').sum()}\n"
                      f"High: {(final_gdf['class'] == 'High').sum()}\n")

    print('Finished. Time required:', str(datetime.datetime.now() - T_start)[:-4])
    return final_gdf, x_coords, y_coords, cell_index


#########################################################################################################

import matplotlib.pyplot as plt
import geopandas as gpd

def plot_intersections_with_grid_id(
    buffer_gdf, 
    camp_polygon_path, 
    polygon_column_name, 
    polygon_name, 
    buildings_path,
    x_coords, 
    y_coords, 
    cell_index
):
    """
    Visualizes:
    - Original buildings (blue)
    - Buffered buildings (red)
    - Intersected hazard grid points (tiny transparent blue)
    - Campground polygon (black)
    - Labels each building with its id_def in bold black text
    """

    # Load campground polygon
    camp_gdf = gpd.read_file(camp_polygon_path)

    # Normalize and search
    camp_gdf["__cmp"] = camp_gdf[polygon_column_name].str.strip().str.lower()
    polygon_name_clean = polygon_name.strip().lower()
    selected_camp = camp_gdf[camp_gdf["__cmp"] == polygon_name_clean]

    if selected_camp.empty:
        available = camp_gdf["__cmp"].unique()
        raise ValueError(
            f"❌ Campground name '{polygon_name}' not found.\n"
            f"🧩 Available names (normalized):\n{available}"
        )

    # Drop helper column
    camp_gdf.drop(columns="__cmp", inplace=True)

    # Load original building footprints
    buildings_gdf = gpd.read_file(buildings_path)
    buildings_in_camp = buildings_gdf[buildings_gdf.within(selected_camp.iloc[0].geometry)]

    # Extract intersected grid points
    points_x = [x_coords[i] for i in cell_index]
    points_y = [y_coords[i] for i in cell_index]

    # Plotting
    fig, ax = plt.subplots(figsize=(10, 10))
    selected_camp.boundary.plot(ax=ax, color='black', linewidth=1, label='Campground')
    buildings_in_camp.plot(ax=ax, color='lightblue', edgecolor='blue', linewidth=0.7, label='Original Buildings')
    buffer_gdf.boundary.plot(ax=ax, color='red', linewidth=1, label='Buffered Building')
    ax.scatter(points_x, points_y, s=2, color='blue', alpha=0.4, label='Intersected Grid Points')

    # ➕ Add bold black labels for each building's id_def
    if "id_def" in buildings_in_camp.columns:
        for _, row in buildings_in_camp.iterrows():
            centroid = row.geometry.centroid
            ax.text(
                centroid.x + 5, 
                centroid.y + 5, 
                str(int(row["id_def"])), 
                fontsize=8, 
                color="black", 
                fontweight="bold", 
                alpha=0.9
            )

    ax.set_title(f"Grid Intersection with Buffered Buildings\n{polygon_name.strip()}")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.legend()
    ax.set_aspect('equal')
    plt.grid(True)
    plt.tight_layout()
    plt.show()

########################################################################################################
##########################################################################################################################

#### Multiple Scenarios of the Flood Exposure  
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import rtree
import os
import re
import datetime
from operator import itemgetter

def process_multiple_hazard_files(
    hazard_paths,
    buildings_path,
    geojson_file,
    polygon_column_name,
    polygon_name,
    buffer_meters=None,
    buffer_percent=100,
    output_folder="Outputs_Events"
):
    all_results = []

    for hazard_path in hazard_paths:
        print(f"Processing: {hazard_path}")
        T_start = datetime.datetime.now()

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        campgrounds_gdf = gpd.read_file(geojson_file)
        buildings_gdf = gpd.read_file(buildings_path)

        selected_camp = campgrounds_gdf[campgrounds_gdf[polygon_column_name] == polygon_name]
        if selected_camp.empty:
            raise ValueError(f"No campground found with name: {polygon_name}")
        camp_geom = selected_camp.iloc[0].geometry

        with open(hazard_path, 'r') as f:
            ncols = int(f.readline().split()[1])
            nrows = int(f.readline().split()[1])
            xllcorner = float(f.readline().split()[1])
            yllcorner = float(f.readline().split()[1])
            cellsize = float(f.readline().split()[1])
            nodata_value = float(f.readline().split()[1])
            data_lines = f.readlines()

        dx = cellsize
        buffer_dist = buffer_meters if buffer_meters is not None else (buffer_percent / 100) * dx

        x_coords = []
        y_coords = []
        Z = []
        for row_idx, line in enumerate(data_lines):
            row_vals = [float(v) for v in re.split(r'\s+', line.strip()) if v]
            for col_idx, val in enumerate(row_vals):
                x_coords.append(xllcorner + col_idx * dx)
                y_coords.append(yllcorner + (nrows - 1 - row_idx) * dx)
                Z.append(val)

        index = rtree.index.Index()
        for i, (xi, yi) in enumerate(zip(x_coords, y_coords)):
            index.insert(i, (xi, yi))

        buildings_in_camp = buildings_gdf[buildings_gdf.within(camp_geom)].copy()

        buffer_list = []
        cell_index = []
        buffered_geometries = []

        for _, bldg in buildings_in_camp.iterrows():
            bldg_id = bldg['id_def']
            buffer = bldg['geometry'].buffer(buffer_dist, resolution=1, cap_style=2, join_style=2)
            buffered_geometries.append(buffer)
            for cell in list(index.intersection(buffer.bounds)):
                pt = Point(x_coords[cell], y_coords[cell])
                if pt.intersects(buffer):
                    buffer_list.append(bldg_id)
                    cell_index.append(cell)

        buildings_in_camp["geometry"] = buffered_geometries
        buildings_in_camp = gpd.GeoDataFrame(buildings_in_camp, geometry="geometry", crs=buildings_gdf.crs)

        df = pd.DataFrame(list(zip(itemgetter(*cell_index)(Z), buffer_list)), columns=['depth', 'id_def'])

        max_depth = df.groupby('id_def')['depth'].max().round(3).reset_index(name='max_depth')
        mean_depth = df.groupby('id_def')['depth'].mean().round(3).reset_index(name='mean_depth')
        categ_df = pd.merge(max_depth, mean_depth)

        categ_df['class'] = 'Low'
        categ_df.loc[(categ_df['mean_depth'] < 0.1) & (categ_df['max_depth'] >= 0.3), 'class'] = 'Medium'
        categ_df.loc[(categ_df['mean_depth'] >= 0.1) & (categ_df['max_depth'] < 0.3), 'class'] = 'Medium'
        categ_df.loc[(categ_df['mean_depth'] >= 0.1) & (categ_df['max_depth'] >= 0.3), 'class'] = 'High'
        categ_df['internally_flooded'] = categ_df['class'] == 'High'

        final_gdf = buildings_in_camp.merge(categ_df, on='id_def', how='left')
        final_gdf['area'] = final_gdf.geometry.area.astype(int)
        final_gdf.fillna({'class': 'Low', 'max_depth': 0.0, 'mean_depth': 0.0, 'internally_flooded': False}, inplace=True)

        scenario = int(re.findall(r'_(\d+)_1h', hazard_path)[0])
        final_gdf['scenario'] = scenario

        final_gdf = final_gdf[['id_def', 'objectid', 'geometry', 'max_depth', 'mean_depth', 'class', 'internally_flooded', 'area', 'scenario']]
        all_results.append(final_gdf)

        print(f"Finished {scenario}. Time: {str(datetime.datetime.now() - T_start)[:-4]}")

    return pd.concat(all_results, ignore_index=True)

################################################################################################################
###############################################################################################################
def export_building_level_exposure_csv(
    hazard_glob,
    buildings_path,
    campgrounds_path,
    polygon_column,
    camp_names,
    out_csv,
    id_column="id_def",
    buffer_m=2.0,
    mean_thr=0.1,
    max_thr=0.3,
):
    import os, glob, math
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    from shapely.geometry import Point

    def read_ascii_max(path):
        with open(path) as f:
            ncols = int(f.readline().split()[1])
            nrows = int(f.readline().split()[1])
            xll = float(f.readline().split()[1])
            yll = float(f.readline().split()[1])
            dx = float(f.readline().split()[1])
            nodata = float(f.readline().split()[1])
            data = np.fromstring(" ".join(ln.strip() for ln in f.readlines()), sep=" ")
        Z = data.reshape((nrows, ncols))
        return ncols, nrows, xll, yll, dx, nodata, Z

    def iterate_indices(bbox, ncols, nrows, xll, yll, dx):
        minx, miny, maxx, maxy = bbox
        c_min = max(0, min(int((minx - xll)//dx), ncols-1))
        c_max = max(0, min(int((maxx - xll)//dx), ncols-1))
        r_min = max(0, min(int(nrows-1-(maxy-yll)//dx), nrows-1))
        r_max = max(0, min(int(nrows-1-(miny-yll)//dx), nrows-1))
        return r_min, r_max, c_min, c_max

    def classify(df):
        df = df.copy()
        df["class"] = "Low"
        df.loc[(df["mean_depth"] < mean_thr) & (df["max_depth"] >= max_thr), "class"] = "Medium"
        df.loc[(df["mean_depth"] >= mean_thr) & (df["max_depth"] < max_thr), "class"] = "Medium"
        df.loc[(df["mean_depth"] >= mean_thr) & (df["max_depth"] >= max_thr), "class"] = "High"
        df["internally_flooded"] = df["class"].eq("High")
        return df

    if isinstance(camp_names, str):
        camp_names = [camp_names]

    hazards = sorted(glob.glob(hazard_glob, recursive=True))
    if not hazards:
        raise ValueError("No hazard files found.")

    bldg = gpd.read_file(buildings_path)
    camps = gpd.read_file(campgrounds_path)

    if camps.crs != bldg.crs:
        camps = camps.to_crs(bldg.crs)

    camps_sel = camps[camps[polygon_column].isin(camp_names)]
    if camps_sel.empty:
        raise ValueError("No campgrounds matched camp_names.")

    rows = []

    for hp in hazards:
        # scenario from filename: ..._75.max -> 75
        scenario = int(os.path.basename(hp).split("_")[-1].replace(".max", ""))
        ncols, nrows, xll, yll, dx, nodata, Z = read_ascii_max(hp)

        for _, camp in camps_sel.iterrows():
            camp_name = camp[polygon_column]
            b_in = bldg[bldg.geometry.within(camp.geometry)].copy()
            if b_in.empty:
                continue

            b_in["buffer"] = b_in.geometry.buffer(buffer_m)

            for _, b in b_in.iterrows():
                bid = b.get(id_column, b.name)
                buf = b["buffer"]

                r_min, r_max, c_min, c_max = iterate_indices(buf.bounds, ncols, nrows, xll, yll, dx)

                depths = []
                for r in range(r_min, r_max + 1):
                    y = yll + (nrows - 1 - r) * dx
                    for c in range(c_min, c_max + 1):
                        x = xll + c * dx
                        if buf.contains(Point(x, y)):
                            d = Z[r, c]
                            if d != nodata:
                                depths.append(d)

                rows.append({
                    "campground": str(camp_name),
                    "scenario": int(scenario),
                    id_column: bid,
                    "max_depth": float(np.max(depths)) if depths else 0.0,
                    "mean_depth": float(np.mean(depths)) if depths else 0.0,
                })

    df = pd.DataFrame(rows)
    df = classify(df)

    # keep exactly what you want
    df = df[["campground", "scenario", id_column, "max_depth", "mean_depth", "class", "internally_flooded"]]

    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


################################################################################################################
###############################################################################################################

def plot_first_change_threshold(
    df_nodisch,
    df_disch,
    camp_name,
    id_column="id_def",
    out_png=None,
    show=True,
    dpi=200,
):
    """
    For each building:
      - find the FIRST rainfall scenario where class(with discharge) != class(without)
      - plot that scenario as the "change threshold"
      - color shows direction:
          red  = higher exposure with discharge
          blue = lower exposure with discharge
          grey = no change across all scenarios

    Inputs must contain columns:
      campground, scenario, id_column, class
    """
    import os
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    class_to_int = {"Low": 0, "Medium": 1, "High": 2}

    # Filter to this campground
    a = df_nodisch[df_nodisch["campground"] == camp_name].copy()
    b = df_disch[df_disch["campground"] == camp_name].copy()
    if a.empty or b.empty:
        raise ValueError(f"No rows found for campground='{camp_name}' in one of the datasets.")

    # Convert class to numeric and aggregate duplicates (worst-case)
    a["num"] = a["class"].map(class_to_int).fillna(0).astype(int)
    b["num"] = b["class"].map(class_to_int).fillna(0).astype(int)
    a = a.groupby([id_column, "scenario"], as_index=False)["num"].max()
    b = b.groupby([id_column, "scenario"], as_index=False)["num"].max()

    # Pivot to building × scenario
    A = a.pivot(index=id_column, columns="scenario", values="num")
    B = b.pivot(index=id_column, columns="scenario", values="num")

    # Align (union of buildings and scenarios), fill missing as Low (0)
    idx = A.index.union(B.index)
    cols = A.columns.union(B.columns)
    A = A.reindex(index=idx, columns=cols).fillna(0)
    B = B.reindex(index=idx, columns=cols).fillna(0)

    # Sort scenarios numerically if possible
    try:
        cols_sorted = sorted(cols, key=int)
    except Exception:
        cols_sorted = sorted(cols)
    A = A.reindex(cols_sorted, axis=1)
    B = B.reindex(cols_sorted, axis=1)

    # Compute first change threshold
    thresholds = []
    for bid in A.index:
        diff = (B.loc[bid] - A.loc[bid]).astype(int)
        changed = diff[diff != 0]
        if len(changed) == 0:
            thresholds.append((bid, np.nan, 0))  # no change
        else:
            first_scn = changed.index[0]
            direction = int(np.sign(changed.iloc[0]))  # +1 higher exposure with discharge, -1 lower
            thresholds.append((bid, float(first_scn), direction))

    thr = pd.DataFrame(thresholds, columns=[id_column, "first_change_scenario", "direction"])

    # Sort: earliest change first; no-change last
    thr = thr.sort_values(["first_change_scenario", id_column], na_position="last").reset_index(drop=True)

    # Plot
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * max(6, len(thr)))))

    y = np.arange(len(thr))
    x = thr["first_change_scenario"].values

    colors = np.where(
        thr["direction"].values > 0, "#d7191c",    # red: higher exposure with discharge
        np.where(thr["direction"].values < 0, "#2c7bb6", "#bdbdbd")  # blue / grey
    )

    ax.scatter(x, y, c=colors, s=50)

    ax.set_yticks(y)
    ax.set_yticklabels(thr[id_column].astype(str))
    ax.set_xlabel("Rainfall scenario where discharge FIRST changes exposure class")
    ax.set_title(f"Threshold where discharge starts to matter – {camp_name}")

    if len(cols_sorted) <= 30:
        ax.set_xticks(cols_sorted)

    # annotate "no change"
    if len(cols_sorted) > 0:
        xmax = cols_sorted[-1]
        for i, val in enumerate(x):
            if np.isnan(val):
                ax.text(xmax, i, "no change", va="center", ha="left", fontsize=9, color="#666666")

    plt.tight_layout()

    # Save / show control
    if out_png:
        os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
        fig.savefig(out_png, dpi=dpi)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return thr
