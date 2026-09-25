<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

# 🥯 Bagzel: A Bazel-Powered Rosbag Extraction Pipeline

**Bagzel** is an efficient and reproducible data extraction pipeline for ROS 1 and ROS 2 bag files, built on **Bazel**. It generates structured datasets from recorded robotic data—including image sequences, GPS logs, metadata, and map visualizations—and supports exporting data in the standardized nuScenes format.

---

## 🚀 Installation

### 🔧 Prerequisites

Make sure the following are installed on your system:

- **Bazel** ([installation guide](https://bazel.build/install))
- **git**
- **Git Large File Storage (LFS)** ([Git LFS installation guide](https://git-lfs.com))

To install Git LFS:
```bash
git lfs install
```

### 📥 Repository Setup

To obtain and prepare the source code:

```bash
git clone https://github.com/UniBwTAS/bagzel.git
cd bagzel
```
> The immutable example dataset is **not part of the repository**: the standalone Bazel module automatically downloads it from the [`v0.2.0` GitHub release](https://github.com/UniBwTAS/bagzel/releases/tag/v0.2.0) at first use (see the `example_data` `http_archive` in `MODULE.bazel`). You do not need `git lfs pull` or any other manual download for the example data.



## 🛠️ Build and Run: Minimal Working Example

This section shows the two main functionalities of Bagzel:
1. Building a **nuScenes dataset** from ROS 1 and ROS 2 bag files.
2. Building a **vision dataset** (with evaluation metrics) from ROS 1 bag files.


## Quick builds (fast / minimal)

These are the simplest “sanity check” builds that avoid the heavier cross-bag steps.

### 1) Fastest: build only NuScenes exports (ROS1 + ROS2)

The `example_data` repository is downloaded automatically from the immutable
[`v0.2.0` GitHub release](https://github.com/UniBwTAS/bagzel/releases/tag/v0.2.0)
archive — no manual download and no Git LFS involved.

```bash
bazel build @example_data//:data_pipeline_processed__nuscenes_data
```

### 2) ROS1-only visual pipeline outputs (still relatively quick)

```bash
bazel build @example_data//:data_pipeline_processed__visual_data
```


### 3) Per-bag quick build (one bag)

If you want to build just one bag’s outputs, build its per-bag `__everything` filegroup:

```bash
bazel build @example_data//:<stem>__everything
```

You can copy `<stem>` from `bazel query @example_data//:all`.

---

## Full build (everything)

This builds:

- NuScenes exports
- ROS1 processed outputs
- maps (`__maps`)
- merged annotations (`__wm_annos`, `__wm_annos_single_file`)

```bash
bazel build @example_data//:data_pipeline_processed__everything
```
> **Note:** This target builds all outputs and duplicates some generated data, which can significantly increase storage usage. It’s intended for development/testing and is not recommended for production workflows.

### 1. Build own dataset from ROS 1 and ROS 2 bags

The built-in example dataset is fetched automatically from the GitHub release archive; it needs no configuration. To process **your own** recordings, expose them to Bazel via an **external repository**. Bazel then manages all symlinks internally, so you do **not** need to create any symlinks inside the project directory.

You can configure where your bag data is located via the `path` attribute in `MODULE.bazel`. Relative paths are interpreted w.r.t. the workspace root; absolute paths are also supported.

Add the following to your `MODULE.bazel`:

```bzl
external_repository = use_extension(
    "@bagzel//src:starlark/rules/core/external_repository.bzl",
    "external_repository",
)

external_repository.local_repo(
    repo_name = "example_data",  # name of the external repository
    build_file = "@bagzel//src/starlark/macros/graph-build:BUILD.graph.bazel",
    empty_build_file = "@bagzel//src/starlark/macros/graph-build:BUILD.graph.empty.bazel",
    path = "data/own_example_data/",  # path to the data directory
)

use_repo(external_repository, "own_example_data")
```

### Adding your own config files

The config directory needs the following structure

```
.
├── BUILD.bazel
├── MODULE.bazel
└── config.bzl
```

Thereby the BUILD.bazel file can be completely empty. The MODULE.bazel file needs one line of code

```
module(name = "bagzel_config", version = "0.0.0")
```

In the config.bzl needs to have the following structure:

```
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
```

A short explaination what these config control can be found at [docs/config-bagzel.md](docs/config-bagzel.md).

List all generated targets:

```bash
bazel query @own_example_data//:all
```

---



## 📚 Documentations
- [docs/graph-macro.md](docs/graph-macro.md) – Overview of the generated Bazel targets and data structure.
- [docs/config-bagzel.md](docs/config-bagzel.md) – Overview of the configuation parameters of bagzel.
- [docs/bazel](docs/bazel/) – Documentations regarding Bazel usage, updating Python dependencies, and profiling.
- [docs/licensing-reuse.md](docs/licensing-reuse.md) – Documentations for managing the licensing of this github project reuse is used.


---

## 📄 Publications

Bagzel is described in an IEEE CASE 2026 conference paper and two open-access
preprints. For academic use, prefer the conference paper.

| Publication | Venue | Links |
| --- | --- | --- |
| **Modeling Robotics Dataset Construction as an Artifact-Based Build Process** | 2026 IEEE 22nd International Conference on Automation Science and Engineering (CASE), Shenyang, China, 17–21 August 2026 | [arXiv](https://arxiv.org/abs/2606.00162) · [prerecorded presentation](https://youtu.be/x6ia-x3_nf0?si=2PJfOVnFWp-ax1cW) |
| **Modeling Robotics Dataset Construction as an Artifact-Based Build Process** | arXiv preprint, arXiv:2606.00162 | [paper](https://doi.org/10.48550/arXiv.2606.00162) |
| **Bagzel: A Bazel Extension for Reproducible Dataset Builds from ROS 1 and ROS 2 Bags** | engrXiv preprint | [paper](https://doi.org/10.31224/6452) |

## 🎤 Conferences

Bagzel has been presented at the following venues:

* **IEEE CASE 2026** – *Modeling Robotics Dataset Construction as an Artifact-Based Build Process*
  [Prerecorded presentation](https://youtu.be/x6ia-x3_nf0?si=2PJfOVnFWp-ax1cW)

* **ROSCon DE & FR 2025** – *Processing ROSbags at Scale: Reproducible Data Workflows for Robotics*
  [Slides](https://roscon.ros.org/de/2025/img/slides/S2_4__Pohl__Processing_ROSbags_at_Scale_Reproducible_Data_Workflows_for_Robotics.pdf) · [Recording](https://vimeo.com/showcase/12079514?video=1156745897)

* **BazelCon 2025** – *Bazel Beyond Code: Scalable AI Data Pipelines for Autonomous Systems*
  [Slides / Recording](https://sched.co/2AFgF)


---

## 📖 How to cite

If you use Bagzel in academic work, please prefer the IEEE CASE 2026 conference
paper. The repository also includes [`CITATION.cff`](CITATION.cff) for GitHub's
citation tooling. The CASE entry will be extended with its DOI and page range
once its IEEE Xplore record is available.

```bibtex
@inproceedings{pohl2026modeling,
  author    = {Pohl, Leon and Beer, Lukas and Sebastian, George and Maehlisch, Mirko},
  title     = {Modeling Robotics Dataset Construction as an Artifact-Based Build Process},
  booktitle = {2026 IEEE 22nd International Conference on Automation Science and Engineering (CASE)},
  year      = {2026},
  month     = aug,
  address   = {Shenyang, China},
  publisher = {IEEE}
}

@misc{pohl2026moda,
  author        = {Pohl, Leon and Beer, Lukas and Sebastian, George and Maehlisch, Mirko},
  title         = {Modeling Robotics Dataset Construction as an Artifact-Based Build Process},
  year          = {2026},
  month         = may,
  archiveprefix = {arXiv},
  eprint        = {2606.00162},
  doi           = {10.48550/arXiv.2606.00162}
}

@misc{pohl2026bag,
  author       = {Pohl, Leon and Beer, Lukas and Sebastian, George and Maehlisch, Mirko},
  title        = {Bagzel: A Bazel Extension for Reproducible Dataset Builds from ROS 1 and ROS 2 Bags},
  year         = {2026},
  month        = feb,
  publisher    = {engrXiv},
  doi          = {10.31224/6452},
  howpublished = {engrXiv preprint}
}
```

---

## 🧾 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](./LICENSES/Apache-2.0.txt) file for details.
