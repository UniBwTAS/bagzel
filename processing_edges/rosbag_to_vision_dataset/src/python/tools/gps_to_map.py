# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
import folium
from datetime import datetime
from geopy.distance import geodesic
import argparse

def calculate_total_distance(coords):
    """Calculate total distance in meters between coordinates."""
    distance = 0.0
    for i in range(1, len(coords)):
        distance += geodesic(coords[i - 1], coords[i]).meters
    return distance

def main(input_file, output_file):
    # Load CSV
    df = pd.read_csv(input_file)

    # Convert timestamps
    df["time"] = df["timestamp"].apply(lambda x: datetime.fromtimestamp(float(x)))

    # Compute metadata
    start_time = df["time"].iloc[0]
    end_time = df["time"].iloc[-1]
    coords = list(zip(df["latitude"], df["longitude"]))
    distance_m = calculate_total_distance(coords)

    # Initialize map
    m = folium.Map(location=[df["latitude"].iloc[0], df["longitude"].iloc[0]], zoom_start=18)

    # Add small points
    for _, row in df.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=3,
            popup=f'Time: {row["time"]}\nAlt: {row["altitude"]:.2f}m',
            color='blue',
            fill=True,
        ).add_to(m)

    # Add start and end markers
    folium.Marker(
        location=[df["latitude"].iloc[0], df["longitude"].iloc[0]],
        popup=f'Start Time: {start_time}',
        icon=folium.Icon(color='green', icon='play')
    ).add_to(m)

    folium.Marker(
        location=[df["latitude"].iloc[-1], df["longitude"].iloc[-1]],
        popup=f'End Time: {end_time}',
        icon=folium.Icon(color='red', icon='stop')
    ).add_to(m)

    # Draw polyline
    folium.PolyLine(
        locations=coords,
        color="red",
        weight=2.5,
        opacity=1
    ).add_to(m)

    # Add metadata legend
    legend_html = f"""
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 300px; height: 120px; 
                z-index:9999; background-color:white; padding: 10px;
                border:2px solid grey; font-size:14px;">
        <b>Metadata</b><br>
        Start Time: {start_time}<br>
        End Time: {end_time}<br>
        Distance Traveled: {distance_m:.2f} meters
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save map
    m.save(output_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate trajectory map from ROS bag CSV.")
    parser.add_argument("input_file", help="Path to input CSV file.")
    parser.add_argument("output_file", help="Path to output HTML map file.")
    args = parser.parse_args()

    main(args.input_file, args.output_file)
