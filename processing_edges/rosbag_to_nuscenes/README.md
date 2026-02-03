<!--
SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

# Rosbag2 to NuScenes converter
This repository provides a tool to convert ROS2 bag files into the NuScenes dataset format. It is designed to facilitate the integration of ROS2 data with the NuScenes dataset.
Currently, it supports the conversion from image_raw and UDP-based point cloud data.
Also, it splits each bag into 20 sec. junks. They need to be merged afterward.

## Usage
0. Before you start, you need ROS2 bags. If you have ros1-bags, you can use the `rosbag2` tool to convert them to ros2-bags.
With the rosbags package, its straightforward:
```bash
rosbags-convert rosbag.bag --dst output_dir    
```
1. Clone the repository
2. Navigate to the project directory:
   ```bash
   cd rosbag2_to_nuscenes
   ```
3. Install the required dependencies:
   ```bash
    pip install -r requirements.txt
    ```
4. Update param/param.yaml to your needs. The param file is a list of topics which will be extracted. Further, all sensors have a TOKEN. This simplifies the merging step afterwards.
The Token must be Unique, and we simply start counting alphanumerically from 0 (each token has a length of 32 characters).
5. Run the conversion script:
   ```bash
    python rosbag2nuscenes.py \
        --input_bag_dir /media/lube/31a5a13b-3acd-42fa-bdb7-72f81ec9b255/tas/01_2023-01-16_11-08-49_tas/2023-01-16-11-08-50 \
        --output_dir  tas_nuscenes
    ```

##Merging
After the conversion, you will have multiple folders with 20 sec. junks. To merge them into one NuScenes dataset, you can use the `merge_scenes.py` script:
```bash
python merge_scenes.py \
    --base_path tas_nuscenes \
    --output_dir merged_nuscenes
```
This merges all the 20 sec. junks into one NuScenes dataset format.
This also means, all Tokens (except the sensor tokens) will be changed.
The files will not be copied, but a hard link will be created.


## ToDos:
- Add support for more sensor types (e.g., IMU, GPS, Ouster, pure Pointclouds etc.)
