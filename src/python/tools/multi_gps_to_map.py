# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
import folium
from folium.plugins import HeatMap
from datetime import datetime
import os
from collections import defaultdict
import random

# CONFIGURATION
SAMPLE_RATE = 10            # Sample every 10th point when reading
MAX_POINTS_PER_YEAR = 20000 # Max points for heatmaps
SIMPLIFY_TRAJECTORY = 10    # Keep every 10th point for trajectories

def extract_year_from_csv(file_path):
    try:
        df = pd.read_csv(file_path, usecols=["timestamp_ns"])
        timestamp_ns = df["timestamp_ns"].iloc[0]
        return datetime.fromtimestamp(float(timestamp_ns) / 1e9).year
    except Exception as e:
        print(f"Error extracting year from {file_path}: {e}")
        return None

def load_coordinates_and_metadata(file_path, sample_rate=SAMPLE_RATE):
    try:
        df = pd.read_csv(file_path, usecols=["latitude", "longitude", "altitude", "timestamp_ns"])
        df = df.dropna(subset=["latitude", "longitude"])
        df = df.iloc[::sample_rate]  # Downsample points
        coords = df[["latitude", "longitude"]].values.tolist()
        polyline = coords

        if len(df) == 0:
            return [], [], {}

        timestamp_ns = df["timestamp_ns"].iloc[0]
        timestamp_iso = datetime.fromtimestamp(float(timestamp_ns) / 1e9).isoformat()

        metadata = {
            "latitude": df["latitude"].iloc[0],
            "longitude": df["longitude"].iloc[0],
            "altitude": df["altitude"].iloc[0] if "altitude" in df.columns else "N/A",
            "timestamp": timestamp_iso  # Use 'timestamp' for consistency with rest of code
        }

        return coords, polyline, metadata
    except Exception as e:
        print(f"Failed to load {file_path}: {e}")
        return [], [], {}

def create_heatmap(coords_by_year, output_file):
    print(f"Generating Heatmap: {output_file}")

    first_coords = next(iter(coords_by_year.values()))[0]
    m = folium.Map(location=first_coords, zoom_start=14)

    for year in sorted(coords_by_year.keys()):
        fg = folium.FeatureGroup(name=f"Heatmap {year}", show=(year == sorted(coords_by_year.keys())[0]))

        year_coords = coords_by_year[year]
        if len(year_coords) > MAX_POINTS_PER_YEAR:
            print(f"Downsampling heatmap points for year {year} from {len(year_coords)} to {MAX_POINTS_PER_YEAR}")
            year_coords = random.sample(year_coords, MAX_POINTS_PER_YEAR)

        HeatMap(year_coords, radius=6, blur=10, min_opacity=0.3).add_to(fg)
        m.add_child(fg)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(output_file)
    print(f"✅ Heatmap saved to {output_file}")

def create_trajectory_map(polylines_by_year, output_file):
    print(f"Generating Trajectory Map: {output_file}")

    first_coords = None
    for paths in polylines_by_year.values():
        if paths:
            first_coords = paths[0][0][0]  # first point of first path
            break

    if not first_coords:
        print("No trajectories found.")
        return

    m = folium.Map(location=first_coords, zoom_start=14)

    for year in sorted(polylines_by_year.keys()):
        traj_group = folium.FeatureGroup(name=f"Trajectories {year}", show=(year == sorted(polylines_by_year.keys())[0]))

        for path, filename, meta in polylines_by_year[year]:
            simplified_path = path[::SIMPLIFY_TRAJECTORY]

            popup_text = f"""
            <b>File:</b> {filename}<br>
            <b>Latitude:</b> {meta.get("latitude")}<br>
            <b>Longitude:</b> {meta.get("longitude")}<br>
            <b>Altitude:</b> {meta.get("altitude")}<br>
            <b>Timestamp:</b> {meta.get("timestamp")}
            """
            folium.PolyLine(
                simplified_path,
                color='blue',
                weight=2,
                opacity=0.4,
                popup=folium.Popup(popup_text, max_width=300)
            ).add_to(traj_group)

        m.add_child(traj_group)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(output_file)
    print(f"✅ Trajectory map saved to {output_file}")

def main(input_file_list, output_heatmap, output_trajectories):
    coords_by_year = defaultdict(list)
    polylines_by_year = defaultdict(list)

    # Read file paths
    with open(input_file_list, 'r') as f:
        csv_files = [line.strip() for line in f if line.strip()]

    print(f"Processing {len(csv_files)} CSV files...")

    for file in csv_files:
        year = extract_year_from_csv(file)
        if not year:
            continue

        coords, polyline, metadata = load_coordinates_and_metadata(file)
        if coords:
            coords_by_year[year].extend(coords)
        if polyline:
            polylines_by_year[year].append((polyline, os.path.basename(file), metadata))

    if not coords_by_year:
        print("No coordinate data found.")
        return

    create_heatmap(coords_by_year, output_heatmap)
    create_trajectory_map(polylines_by_year, output_trajectories)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate split heatmap and trajectory maps from ROS bag CSVs.")
    parser.add_argument("input_file_list", help="Path to a text file containing CSV file paths (one per line).")
    parser.add_argument("output_heatmap", help="Output HTML heatmap file.")
    parser.add_argument("output_trajectories", help="Output HTML trajectories file.")
    args = parser.parse_args()

    main(args.input_file_list, args.output_heatmap, args.output_trajectories)
