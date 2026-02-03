# SPDX-FileCopyrightText: 2026 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

# ---------------- NuScenes param "model" ----------------
# Keep this in .bzl because you need analysis-time config AND want one source of truth.
BAG_INFO = {
    "VEHICLE": "TOUAREG",
    "DESCRIPTION": "Touareg of the Institute for Autonomous Driving",
    "ODOM_TOPIC": "/localization/egomotion/odom",
    "TRACK": "TOUAREG",
}

SENSOR_META = {
    "LIDAR_TOP": {
        "FRAME": "sensor/lidar/vls128_roof",
        "TOKEN": "a0000000000000000000000000000001",
        # LIDAR_TOP topic is not in TOPIC_MAP in your snippet, so store it here.
        "TOPIC": "/bus/vls128_roof/eth_scan/bus_to_host",
    },
    "CAM_FRONT": {
        "FRAME": "sensor/camera/surround/front",
        "TOKEN": "a0000000000000000000000000000002",
        "TOPIC": "/sensor/camera/surround/front/image_raw",
    },
    "CAM_LEFT": {
        "FRAME": "sensor/camera/surround/left",
        "TOKEN": "a0000000000000000000000000000003",
        "TOPIC": "/sensor/camera/surround/left/image_raw",
    },
    "CAM_BACK": {
        "FRAME": "sensor/camera/surround/back",
        "TOKEN": "a0000000000000000000000000000004",
        "TOPIC": "/sensor/camera/surround/back/image_raw",
    },
    "CAM_RIGHT": {
        "FRAME": "sensor/camera/surround/right",
        "TOKEN": "a0000000000000000000000000000005",
        "TOPIC": "/sensor/camera/surround/right/image_raw",
    },
}

EXTRACTION = {
    "min_bag_duration_sec": 0.25,
    "scene_length_sec": 0.25
  }



def nuscenes_param_dict():
    # Matches the YAML structure 1:1, just as a Starlark dict.
    return {
        "BAG_INFO": BAG_INFO,
        "SENSOR_INFO": SENSOR_META,
        "EXTRACTION": EXTRACTION,
    }


# ---------------- Bagzel ROS 1 Pipeline Configuration Parameters ----------------
VALIDATE = False
VEHICLE = "touareg"

VALID_ROSBAGS = [
    "rosbags/2024-06-26_15-08-50_tas/2024-06-26-15-08-51_short.bag",
    "rosbags/2025-04-28_itsc_albi_pemo_forest/2025-04-28-18-25-09_short.bag",
]

TOPIC_MAP = {
    "CAM_FRONT": {
        "touareg": "/sensor/camera/surround/front/image_raw",
        "goose":   "/sensor/camera/windshield/vis/image_rect_color",
    },
    "CAM_INFO": {
        "touareg": "/sensor/camera/surround/front/camera_info",
        "goose":   "/sensor/camera/windshield/vis/camera_info",
    },
    "CAM_LEFT": {
        "touareg": "/sensor/camera/surround/left/image_raw",
        "goose":   "/sensor/camera/surround/left/image_raw",
    },
    "CAM_RIGHT": {
        "touareg": "/sensor/camera/surround/right/image_raw",
        "goose":   "/sensor/camera/surround/right/image_raw",
    },
    "CAM_BACK": {
        "touareg": "/sensor/camera/surround/back/image_raw",
        "goose":   "/sensor/camera/surround/back/image_raw",
    },
    "CAM_ROOF": {
        "touareg": "/sensor/camera/roof/ir/image_raw",
        "goose":   "/sensor/camera/roof/ir/image_raw",
    },
    "LIDAR": {
        "touareg": "",
        "goose":   "/sensor/lidar/vls128_roof/velodyne_points",
    },
    "TF_STATIC": {
        "touareg": "/tf_static",
        "goose":   "/tf_static",
    },
    "TF": {
        "touareg": "/tf",
        "goose":   "/tf",
    },
    "TRAJECTORIES": {
        "touareg": [
            "sensor/camera/surround/front:utm",
            "vehicle/rear_axis:utm",
            "sensor/ins/oxts:utm",
        ],
        "goose": [
            "sensor/camera/windshield/vis:utm",
            "vehicle/rear_axis:utm",
            "sensor/ins/oxts:utm",
        ],
    },
    "OUTPUT_GROUPS": {
        "rear_axis": {
            "touareg": "vehicle_rear_axis_in_utm.csv",
            "goose": "vehicle_rear_axis_in_utm.csv",
        },
        "camera": {
            "touareg": "sensor_camera_surround_front_in_utm.csv",
            "goose": "sensor_camera_windshield_vis_in_utm.csv",
        },
    },
}
