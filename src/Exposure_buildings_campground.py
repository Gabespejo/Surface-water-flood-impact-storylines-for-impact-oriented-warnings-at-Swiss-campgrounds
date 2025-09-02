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

def plot_intersections_with_grid(
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
    """

    # Load campground polygon
    camp_gdf = gpd.read_file(camp_polygon_path)
    selected_camp = camp_gdf[camp_gdf[polygon_column_name] == polygon_name]

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

    ax.set_title(f"Grid Intersection with Buffered Buildings\n{polygon_name}")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.legend()
    ax.set_aspect('equal')
    plt.grid(True)
    plt.show()

########################################################################################################

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