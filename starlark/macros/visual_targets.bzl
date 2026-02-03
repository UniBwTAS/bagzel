# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/ros/extractors/rosbag_to_images.bzl", "rosbag_to_images")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/core/images_to_sequences.bzl", "images_to_sequences")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/core/merge_worldmodel_annotations.bzl", "merge_worldmodel_annotations")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/ros/extractors/rosbag_to_metadata.bzl", "rosbag_to_metadata")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/ros/extractors/rosbag_to_oxts.bzl", "rosbag_to_oxts")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/python/oxts_to_maps.bzl", "oxts_to_maps")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/python/visualize_trajectory.bzl", "visualize_trajectory")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/ros/extractors/rosbag_to_transforms.bzl", "rosbag_to_transforms")
load("//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/ros/extractors/rosbag_to_tf_trajectory.bzl", "rosbag_to_tf_trajectory")
load("@bagzel_config//:config.bzl", "VALID_ROSBAGS")

# NOTE: If this file is used from external repos (e.g. @example_data_pad),
# prefer explicit repo labels like "@bagzel//..." for tools to avoid resolution surprises.
_ROSBAG_TOOLS = {
    "metadata": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/ros/extractors:rosbag_to_metadata",
    "oxts": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/ros/extractors:rosbag_to_oxts",
    "images": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/ros/extractors:rosbag_to_images",
    "transforms": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/ros/extractors:rosbag_to_transforms",
    "tf_traj": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/ros/extractors:rosbag_to_tf_trajectory",
    "sequence": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/tools:images_to_sequence",
    "vis_seq_traj_py": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/python/tools:vis_seq_traj",
    "vis_seq_traj_cpp": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/ros/tools:project_trajectory_to_image",
    "maps": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/python/tools:multi_gps_to_map",
    "merge_worldmodel_annos": "@bagzel//processing_edges/rosbag_to_vision_dataset/src/cpp/tools:merge_annotations",
}

def _generate_target_names(stem):
    # use a separator that will never appear in stems
    sep = "__"
    stages = {
        "metadata": "metadata",
        "oxts": "oxts",
        "images": "images",
        "sequences": "sequences",
        "transforms": "transforms",
        "trajectory": "trajectory",
        "sequence_preview": "sequence_traj_preview",
        "camera_info": "camera_info",
        "processed": "processed",
    }
    return {k: "{}{}{}".format(stem, sep, v) for (k, v) in stages.items()}


def _sanitize_target_piece(s):
    # Keep names Bazel-friendly and stable
    for ch in ["/", "\\", " ", "-", ".", ":", "@", "+", "(", ")", "[", "]", "{", "}", ","]:
        s = s.replace(ch, "_")
    return s

def _basename(p):
    return p.rsplit("/", 1)[-1]

# Build a lookup table once at load time
_VALID_BAG_BASENAMES = { _basename(p): True for p in VALID_ROSBAGS }


def _is_valid_rosbag(path, validate = True):
    if not validate:
        return True
    return _basename(path) in _VALID_BAG_BASENAMES

def _declare_single_rosbag_targets(
        *,
        name_prefix,
        rosbag_name,
        rosbag_path,
        topic_map,
        vehicle,
        validate = True,
        camera_topics = None):
    """
    Private helper: declares all targets for a single ROS1 bag.
    Returns a dict of labels (strings starting with ':').

    name_prefix: typically your "stem" from graph.bzl (unique per bag).
    rosbag_name: logical bag name (used in metadata fields / sequence naming).
    rosbag_path: path to the .bag file in the current package.
    """
    # targets = _generate_target_names(rosbag_name, name_prefix)
    stem = _sanitize_target_piece(name_prefix)   # e.g. 2024_12_05_..._0965...
    targets = _generate_target_names(stem)

    if camera_topics == None:
        camera_topics = [
            topic_map["CAM_FRONT"][vehicle],
            # optionally more cams...
        ]

    # Always extract metadata (even for invalid bags)
    rosbag_to_metadata(
        name = targets["metadata"],
        rosbag = rosbag_path,
        rosbag_name = rosbag_name,
        rosbag_tool = _ROSBAG_TOOLS["metadata"],
    )

    is_valid = _is_valid_rosbag(rosbag_path, validate)

    if not _is_valid_rosbag(rosbag_path, validate):
        # For invalid bags: only metadata target exists
        native.filegroup(
            name = targets["processed"],
            srcs = [":" + targets["metadata"]],
            visibility = ["//visibility:public"],
        )
        return {
            "valid": False,
            "processed": ":" + targets["processed"],
            "metadata": ":" + targets["metadata"],
            "oxts": None,
            "images": None,
            "sequences": None,
            "transforms": None,
            "trajectory": None,
            "preview": None,
        }

    # Valid bag: full pipeline
    rosbag_to_oxts(
        name = targets["oxts"],
        rosbag = rosbag_path,
        rosbag_name = rosbag_name,
        rosbag_tool = _ROSBAG_TOOLS["oxts"],
    )

    rosbag_to_transforms(
        name = targets["transforms"],
        rosbag = rosbag_path,
        rosbag_name = rosbag_name,
        rosbag_tool = _ROSBAG_TOOLS["transforms"],
        tf_topic = topic_map["TF"][vehicle],
        tf_static_topic = topic_map["TF_STATIC"][vehicle],
        camera_info_topic = topic_map["CAM_INFO"][vehicle],
    )

    rosbag_to_images(
        name = targets["images"],
        rosbag = rosbag_path,
        rosbag_name = rosbag_name,
        rosbag_tool = _ROSBAG_TOOLS["images"],
        topics = camera_topics,
    )

    rosbag_to_tf_trajectory(
        name = targets["trajectory"],
        bag = rosbag_path,
        rosbag_name = rosbag_name,
        trajectories = topic_map["TRAJECTORIES"][vehicle],
        extract_tool = _ROSBAG_TOOLS["tf_traj"],
    )

    native.filegroup(
        name = targets["trajectory"] + "_rear_axis",
        srcs = [":" + targets["trajectory"]],
        output_group = topic_map["OUTPUT_GROUPS"]["rear_axis"][vehicle],
    )
    native.filegroup(
        name = targets["trajectory"] + "_camera",
        srcs = [":" + targets["trajectory"]],
        output_group = topic_map["OUTPUT_GROUPS"]["camera"][vehicle],
    )

    images_to_sequences(
        name = targets["sequences"],
        input_dir = ":" + targets["images"],
        oxts_file = ":" + targets["trajectory"] + "_rear_axis",
        sequence_tool = _ROSBAG_TOOLS["sequence"],
        rosbag_name = rosbag_name,

    )

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
        camera_csv = ":" + targets["trajectory"] + "_camera",
        camera_info = ":" + targets["camera_info"],
        vis_tool_py = _ROSBAG_TOOLS["vis_seq_traj_py"],
        vis_tool_cpp = _ROSBAG_TOOLS["vis_seq_traj_cpp"],
        image_dir = ":" + targets["images"],
    )

    # One per-bag aggregate target (public)
    native.filegroup(
        name = targets["processed"],
        srcs = [
            ":" + targets["metadata"],
            ":" + targets["oxts"],
            ":" + targets["images"],
            ":" + targets["sequences"],
            ":" + targets["transforms"],
            ":" + targets["trajectory"],
            ":" + targets["sequence_preview"],
        ],
        visibility = ["//visibility:public"],
    )

    return {
        "valid": True,
        "processed": ":" + targets["processed"],
        "metadata": ":" + targets["metadata"],
        "oxts": ":" + targets["oxts"],
        "images": ":" + targets["images"],
        "sequences": ":" + targets["sequences"],
        "transforms": ":" + targets["transforms"],
        "trajectory": ":" + targets["trajectory"],
        "preview": ":" + targets["sequence_preview"],
    }

def declare_rosbag_per_target(
        *,
        name_prefix,
        rosbag_path,
        topic_map,
        vehicle,
        validate = True,
        rosbag_name = None,
        camera_topics = None):
    """
    PUBLIC API for graph.bzl:
      - declares per-rosbag targets
      - returns dict of labels, including a public `processed` filegroup

    name_prefix: unique stem from the caller (graph.bzl), e.g. "2024_..._0965..."
    rosbag_path: path to the ROS1 .bag file
    rosbag_name: optional; defaults to stem of file name
    """
    if rosbag_name == None:
        rosbag_name = rosbag_path.rsplit("/", 1)[-1].replace(".bag", "")
    
    print("Valid ROSBAG basenames dict: %s" % _VALID_BAG_BASENAMES)

    return _declare_single_rosbag_targets(
        name_prefix = name_prefix,
        rosbag_name = rosbag_name,
        rosbag_path = rosbag_path,
        topic_map = topic_map,
        vehicle = vehicle,
        validate = validate,
        camera_topics = camera_topics,
    )

def declare_rosbag_artifacts(name, topic_map, vehicle, rosbag_dir, validate = True, include_globs = None, exclude_globs = None, exclude_rosbag_names = None):
    if include_globs == None:
        include_globs = ["%s/**/*.bag" % rosbag_dir]
    if exclude_globs == None:
        exclude_globs = []
    if exclude_rosbag_names == None:
        exclude_rosbag_names = []
    

    rosbag_paths = native.glob(
        include = include_globs,
        exclude = exclude_globs,
        allow_empty = True,
    )
    
    # exclude_rosbag_names: list of names (without ".bag") to skip
    _excluded = {}
    for n in exclude_rosbag_names:
        _excluded[n] = True

    unique_rosbags = {}
    duplicates = []
    excluded_list = []

    for path in rosbag_paths:
        rosbag_name = path.rsplit("/", 1)[-1].replace(".bag", "")
        if rosbag_name in unique_rosbags:
            duplicates.append((path, unique_rosbags[rosbag_name]))
            continue
        if rosbag_name in _excluded:
            excluded_list.append((path, rosbag_name))
            continue
        unique_rosbags[rosbag_name] = path



    valid_metadata, invalid_metadata = [], []
    outputs = {
        "oxts": [], "metadata": [], "metadata_all": [],
        "images": [], "sequences": [], "transforms": [],
        "trajectory": [], "preview": []
    }

    valid_rosbags_count = 0
    for path in unique_rosbags.values():
        if _is_valid_rosbag(path, validate):
            valid_rosbags_count += 1

    total_rosbags = len(unique_rosbags)
    invalid_rosbags_count = total_rosbags - valid_rosbags_count

    print("------------- ROSBAG BATCH -------------")
    print("Subset: %s" % name)
    print("Total Rosbags: %d | Valid: %d | Invalid: %d | Duplicates: %d | Excluded: %d" % (
        total_rosbags, valid_rosbags_count, invalid_rosbags_count, len(duplicates), len(excluded_list)))
    print("----------------------------------------")

    for rosbag_name, rosbag_path in unique_rosbags.items():
        targets = _generate_target_names(rosbag_name, name)

        if not _is_valid_rosbag(rosbag_path, validate):
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
                             rosbag_name = rosbag_name, rosbag_tool = _ROSBAG_TOOLS["transforms"], tf_topic = topic_map["TF"][vehicle], tf_static_topic = topic_map["TF_STATIC"][vehicle], camera_info_topic = topic_map["CAM_INFO"][vehicle])
        outputs["transforms"].append(":" + targets["transforms"])

        rosbag_to_images(name = targets["images"], rosbag = rosbag_path,
                         rosbag_name = rosbag_name, rosbag_tool = _ROSBAG_TOOLS["images"],
                         topics = [
                                    topic_map["CAM_FRONT"][vehicle],
                                    # topic_map["CAM_LEFT"][vehicle],
                                    # topic_map["CAM_RIGHT"][vehicle],
                                    # topic_map["CAM_BACK"][vehicle],
                                    # topic_map["CAM_ROOF"][vehicle],
                                ],)
        outputs["images"].append(":" + targets["images"])
        rosbag_to_tf_trajectory(name = targets["trajectory"], bag = rosbag_path,
                                rosbag_name = rosbag_name,
                                trajectories = topic_map["TRAJECTORIES"][vehicle],
                                extract_tool = _ROSBAG_TOOLS["tf_traj"])
        outputs["trajectory"].append(":" + targets["trajectory"])

        native.filegroup(
            name = targets["trajectory"] + "_rear_axis",
            srcs = [":" + targets["trajectory"]],
            output_group = topic_map["OUTPUT_GROUPS"]["rear_axis"][vehicle],
        )

        native.filegroup(
            name = targets["trajectory"] + "_camera",
            srcs = [":" + targets["trajectory"]],
            output_group = topic_map["OUTPUT_GROUPS"]["camera"][vehicle],
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

    merge_worldmodel_annotations(
        name = name + "_wm_annos",
        name_prefix = name,
        inputs = outputs["sequences"],
        metadata = valid_metadata,
        merge_tool = _ROSBAG_TOOLS["merge_worldmodel_annos"], 
        val_split_percent = 20,
        seed = 42,           
    )
    
    merge_worldmodel_annotations(
        name = name + "_wm_annos_single_file",
        name_prefix = name,
        inputs = outputs["sequences"],
        metadata = valid_metadata,
        merge_tool = _ROSBAG_TOOLS["merge_worldmodel_annos"],      
        single = True,       
    )

    native.filegroup(
        name = name + "_all",
        srcs = outputs["sequences"] + outputs["oxts"]
              + outputs["images"] + [":" + name + "_maps"] + [":" + name + "_wm_annos"]
              + outputs["transforms"] + outputs["trajectory"] + outputs["preview"],
        visibility = ["//visibility:public"],
    )
