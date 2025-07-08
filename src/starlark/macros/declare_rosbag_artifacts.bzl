# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

load("//src:starlark/rules/ros/extractors/rosbag_to_images.bzl", "rosbag_to_images")
load("//src:starlark/rules/core/images_to_sequences.bzl", "images_to_sequences")
load("//src:starlark/rules/core/merge_annotations.bzl", "merge_annotations")
load("//src:starlark/rules/ros/extractors/rosbag_to_metadata.bzl", "rosbag_to_metadata")
load("//src:starlark/rules/ros/extractors/rosbag_to_oxts.bzl", "rosbag_to_oxts")
load("//src:starlark/rules/python/oxts_to_maps.bzl", "oxts_to_maps")
load("//src:starlark/rules/ros/tools/transform_trajectory.bzl", "transform_trajectory")
load("//src:starlark/rules/python/visualize_trajectory.bzl", "visualize_trajectory")
load("//src:starlark/rules/ros/extractors/rosbag_to_transforms.bzl", "rosbag_to_transforms")
load("//src:starlark/rules/ros/extractors/rosbag_to_tf_trajectory.bzl", "rosbag_to_tf_trajectory")
load("//data:valid_rosbags.bzl", "VALID_ROSBAGS")

_ROSBAG_TOOLS = {
    "metadata": "//src/cpp/ros/extractors:rosbag_to_metadata",
    "oxts": "//src/cpp/ros/extractors:rosbag_to_oxts",
    "images": "//src/cpp/ros/extractors:rosbag_to_images",
    "transforms": "//src/cpp/ros/extractors:rosbag_to_transforms",
    "trajectory": "//src/cpp/ros/tools:transform_trajectory",
    "tf_traj": "//src/cpp/ros/extractors:rosbag_to_tf_trajectory",
    "sequence": "//src/cpp/tools:images_to_sequence",
    "vis_seq_traj_py": "//src/python/tools:vis_seq_traj",
    "vis_seq_traj_cpp": "//src/cpp/ros/tools:project_trajectory_to_image",
    "maps": "//src/python/tools:multi_gps_to_map",
    "merge_annos": "//src/cpp/tools:merge_annotations",
}

def _generate_target_names(rosbag_name):
    return {
        "metadata": "metadata_%s" % rosbag_name,
        "oxts": "oxts_%s" % rosbag_name,
        "images": "images_%s" % rosbag_name,
        "sequences": "sequences_%s" % rosbag_name,
        "transforms": "transforms_%s" % rosbag_name,
        "transformed_traj": "transformed_trajectory_%s" % rosbag_name,
        "trajectory": "trajectory_%s" % rosbag_name,
        "sequence_preview": "sequence_traj_preview_%s" % rosbag_name,
        "camera_info": "camera_info_%s" % rosbag_name,
        "dynamic_transforms": "dynamic_transforms_%s" % rosbag_name,
        "static_transforms": "static_transforms_%s" % rosbag_name,
    }

def _is_valid_rosbag(path):
    return path in VALID_ROSBAGS

def declare_rosbag_artifacts(name, topics, rosbag_dir):
    rosbag_paths = native.glob(["%s/**/*.bag" % rosbag_dir])
    unique_rosbags = {}
    duplicates = []

    for path in rosbag_paths:
        rosbag_name = path.split("/")[-1].replace(".bag", "")
        if rosbag_name in unique_rosbags:
            duplicates.append((path, unique_rosbags[rosbag_name]))
        else:
            unique_rosbags[rosbag_name] = path

    valid_metadata, invalid_metadata = [], []
    outputs = {
        "oxts": [], "metadata": [], "metadata_all": [],
        "images": [], "sequences": [], "transforms": [],
        "transformed": [], "trajectory": [], "preview": []
    }

    print("------------- ROSBAG BATCH -------------")
    print("Subset: %s | Valid: %d | Duplicates: %d" % (
        name, len(unique_rosbags), len(duplicates)))
    print("----------------------------------------")

    for rosbag_name, rosbag_path in unique_rosbags.items():
        targets = _generate_target_names(rosbag_name)

        if not _is_valid_rosbag(rosbag_path):
            rosbag_to_metadata(
                name = targets["metadata"],
                rosbag = rosbag_path,
                rosbag_name = rosbag_name,
                rosbag_tool = _ROSBAG_TOOLS["metadata"],
            )
            invalid_metadata.append(":" + targets["metadata"])
            continue

        # Valid bag: define full pipeline
        rosbag_to_oxts(name = targets["oxts"], rosbag = rosbag_path,
                       rosbag_name = rosbag_name, rosbag_tool = _ROSBAG_TOOLS["oxts"])
        outputs["oxts"].append(":" + targets["oxts"])

        rosbag_to_metadata(name = targets["metadata"], rosbag = rosbag_path,
                           rosbag_name = rosbag_name, rosbag_tool = _ROSBAG_TOOLS["metadata"])
        valid_metadata.append(":" + targets["metadata"])

        rosbag_to_transforms(name = targets["transforms"], rosbag = rosbag_path,
                             rosbag_name = rosbag_name, rosbag_tool = _ROSBAG_TOOLS["transforms"])
        outputs["transforms"].append(":" + targets["transforms"])

        rosbag_to_images(name = targets["images"], rosbag = rosbag_path,
                         rosbag_name = rosbag_name, rosbag_tool = _ROSBAG_TOOLS["images"],
                         topics = topics)
        outputs["images"].append(":" + targets["images"])

        transform_trajectory(name = targets["transformed_traj"],
                             trajectory_csv = ":" + targets["oxts"],
                             transform_json = [":" + targets["transforms"]],
                             transform_tool = _ROSBAG_TOOLS["trajectory"],
                             rosbag_name = rosbag_name)
        outputs["transformed"].append(":" + targets["transformed_traj"])

        rosbag_to_tf_trajectory(name = targets["trajectory"], bag = rosbag_path,
                                rosbag_name = rosbag_name,
                                trajectories = [
                                    "sensor/camera/surround/front:utm_fix",
                                    "vehicle/rear_axis:utm_fix",
                                    "sensor/ins/oxts:utm_fix",
                                ],
                                extract_tool = _ROSBAG_TOOLS["tf_traj"])
        outputs["trajectory"].append(":" + targets["trajectory"])

        native.filegroup(
            name = targets["trajectory"] + "_rear_axis",
            srcs = [":" + targets["trajectory"]],
            output_group = "vehicle_rear_axis_in_utm_fix.csv",
        )
        native.filegroup(
            name = targets["trajectory"] + "_camera",
            srcs = [":" + targets["trajectory"]],
            output_group = "sensor_camera_surround_front_in_utm_fix.csv",
        )


        images_to_sequences(name = targets["sequences"],
                            input_dir = ":" + targets["images"],
                            oxts_file = ":" + targets["trajectory"] + "_rear_axis",
                            sequence_tool = _ROSBAG_TOOLS["sequence"],
                            rosbag_name = rosbag_name)
        outputs["sequences"].append(":" + targets["sequences"])

        native.filegroup(
            name = targets["camera_info"],
            srcs = [":" + targets["transforms"]],
            output_group = "camera",
        )

        visualize_trajectory(
            name = targets["sequence_preview"],
            rosbag_name = rosbag_name,
            sequences_json = ":" + targets["sequences"],
            rear_csv = ":" + targets["trajectory"] + "_rear_axis",
            camera_csv = ":" + targets["trajectory"] + "_camera", # Assuming this CSV contains camera poses
            camera_info = ":" + targets["camera_info"],  # Make sure this is declared earlier
            vis_tool_py = _ROSBAG_TOOLS["vis_seq_traj_py"],
            vis_tool_cpp = _ROSBAG_TOOLS["vis_seq_traj_cpp"],
            image_dir = ":" + targets["images"],
        )
        outputs["preview"].append(":" + targets["sequence_preview"])

    all_metadata = valid_metadata + invalid_metadata

    _filegroups = {
        "sequences": outputs["sequences"],
        "sequences_trajectory_previews": outputs["preview"],
        "metadata": valid_metadata,
        "metadata_all": all_metadata,
        "transforms": outputs["transforms"],
        "trajectories": outputs["trajectory"],
        "oxts": outputs["oxts"],
        "images": outputs["images"],
    }

    for suffix, srcs in _filegroups.items():
        native.filegroup(name = "%s_%s" % (name, suffix), srcs = srcs)

    oxts_to_maps(
        name = name + "_maps",
        name_prefix = name,
        input_files = [":" + name + "_oxts"],
        tool = _ROSBAG_TOOLS["maps"],
    )

    merge_annotations(
        name = name + "_merge_annotations",
        name_prefix = name,
        inputs = outputs["sequences"],
        metadata = valid_metadata,
        merge_tool = _ROSBAG_TOOLS["merge_annos"],  # You can change this if it's not the correct tool
        val_split_percent = 20,  # Adjust as needed or expose as param
        seed = 42,               # Adjust as needed or expose as param
    )

    native.filegroup(
        name = name + "_all",
        srcs = outputs["sequences"] + all_metadata + outputs["oxts"]
              + outputs["images"] + [":" + name + "_maps"]
              + outputs["transforms"] + outputs["transformed"]
              + outputs["trajectory"] + outputs["preview"],
    )
