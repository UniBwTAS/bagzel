<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

# Bagzel configuration parameters

This repo uses a Starlark config (`@bagzel_config//:config.bzl`) as the **single source of truth**. Pipeline macros load values from there (e.g. `TOPIC_MAP`, `VEHICLE`, `VALIDATE`).

## NuScenes parameters (exported via `nuscenes_param_dict()`)

- **`BAG_INFO`**: high-level metadata for the dataset run  
  - `VEHICLE`: platform identifier (e.g. `TOUAREG`)  
  - `DESCRIPTION`: human-readable description  
  - `ODOM_TOPIC`: ROS odometry topic used as ego-motion reference  
  - `TRACK`: NuScenes “log/track” identifier  

- **`SENSOR_META`** (exported as **`SENSOR_INFO`**): per-sensor metadata  
  - `FRAME`: TF frame ID  
  - `TOKEN`: stable unique sensor token  
  - `TOPIC`: ROS topic for that sensor’s data stream  

- **`EXTRACTION`**: controls temporal slicing and validation
  - **`min_bag_duration_sec`** (`float`):  
    Minimum required duration (in seconds) of a ROS bag for processing.  
    Bags shorter than this threshold are skipped entirely.
  - **`scene_length_sec`** (`float`):  
    Length (in seconds) of each exported NuScenes scene.  
    The bag is split into consecutive, non-overlapping scenes of this duration.

`nuscenes_param_dict()` returns:
- `BAG_INFO`
- `SENSOR_INFO` (= `SENSOR_META`)
- `EXTRACTION`

## ROS1 pipeline parameters / Visual Dataset Parameters

- **`VALIDATE`** (`bool`): enable/disable validation gating  
  - `True`: only bags listed in `VALID_ROSBAGS` are processed fully (others produce **metadata only**)  
  - `False`: process all discovered bags  

- **`VEHICLE`** (`string`): selects the vehicle key used inside `TOPIC_MAP` (e.g. `touareg`, `goose`)

- **`VALID_ROSBAGS`** (`list[str]`): allowlist of ROS1 `.bag` files (canonical/clean set)

- **`TOPIC_MAP`**: vehicle-specific ROS topics and derived outputs  
  - camera topics: `CAM_FRONT`, `CAM_LEFT`, `CAM_RIGHT`, `CAM_BACK`, `CAM_ROOF`  
  - calibration / TF: `CAM_INFO`, `TF`, `TF_STATIC`  
  - lidar: `LIDAR` (may be empty if unavailable)  
  - `TRAJECTORIES`: list of `"<frame_a>:<frame_b>"` pairs used to compute trajectories  
  - `OUTPUT_GROUPS`: named outputs extracted from trajectory artifacts (e.g. `rear_axis`, `camera` → CSV filenames)

## How the pipeline uses it (at a glance)

- `graph_macro(...)` loads `TOPIC_MAP`, `VEHICLE`, `VALIDATE` and passes them into per-bag target declaration.
- For ROS1 bags, validation uses `VALID_ROSBAGS` (when `VALIDATE=True`) to decide:  
  - **valid** → extract images, transforms, trajectories, sequences, previews, etc.  
  - **invalid** → extract metadata only (keeps the graph consistent and debuggable)

