<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

# Generated build targets


The `declare_rosbag_artifacts` macro automatically generates a set of Bazel build targets for processing ROS bag data. These targets represent different stages of the data extraction and transformation pipeline.

---

## Valid Rosbags

To ensure pipeline efficiency and correctness, a prefiltering mechanism is used to select only valid ROS bags—those containing the desired topics for extraction. 

These valid file paths must be manually listed in the `data/valid_rosbags.bzl` file. Automation of this filtering step is **currently under development**.

---

## Target Summary

The `<name>` placeholder corresponds to the value provided to the `name` attribute in the `declare_rosbag_artifacts` macro. In the minimal working example, this is defined as `name = "rosbags_sub1"`.

The `rosbag_dir` attribute specifies the directory containing the ROS bag files. For example, if the bags are located in `data/rosbags` and the `BUILD` file resides in the `data/` folder, then `rosbag_dir = "rosbags"` will recursively scan the specified directory and its subfolders.

The following targets are generated:

```bash
//data:<name>_all
//data:<name>_oxts          
//data:<name>_images
//data:<name>_maps
//data:<name>_metadata
//data:<name>_metadata_all
//data:<name>_sequences
//data:<name>_sequences_trajectory_previews
//data:<name>_transforms
//data:<name>_trajectories
//data:<name>_merge_annotations
```
---

## Target Descriptions
- `//data:<name>_all`

Aggregates all outputs from the processing pipeline: sequences, metadata (valid and all), GPS data, maps, image frames, transformations, trajectories, previews.

- `//data:<name>_oxts`

Contains CSV files with GPS data extracted from the ROS bag files.

- `//data:<name>_images`

Extracted image frames from the ROS bags using specific topics. Useful for training visual models or frame-based analysis.

- `//data:<name>_maps`

A collection of visual map files (e.g., GPS heatmaps and trajectories map) created from the extracted GPS data. Useful for spatial verification and trajectory visualization.

- `//data:<name>_metadata`

Metadata files describing the content of each ROS bag, such as topic summaries, durations, and message counts. Only includes metadata from valid ROS bags.

- `//data:<name>_metadata_all`

Includes metadata for all ROS bags, even those filtered out (invalid or duplicates). Useful for diagnostics or quality control.

- `//data:<name>_sequences`

Sequence folders constructed from the extracted images, formatted and ordered using the images_to_sequences rule. Ideal for feeding into model pipelines or structured datasets.

- `//data:<name>_sequences_trajectory_previews`

Visualizations of camera trajectories overlaid on image sequences.

- `//data:<name>_transforms`

Static and dynamic transform files extracted from the ROS bag data.

- `//data:<name>_trajectories`

TF-extracted trajectory data (e.g. in UTM coordinates) per defined topic (e.g., rear_axis, front camera, etc.).

- `//data:<name>_merge_annotations`

A merged annotation dataset produced from metadata and sequences, with validation split and seeding.

---