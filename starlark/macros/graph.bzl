# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

load("@bagzel//starlark/core:shellrule.bzl", "shellrule")
load("@bagzel//processing_edges/rosbag_to_nuscenes:rosbag_to_nuscenes_macro.bzl", "single_rosbag_to_nuscenes")
load("@bagzel//processing_edges/mwe_print_filenames:mwe_print_filenames.bzl", "print_nuscenes")
load("@bagzel//:starlark/macros/visual_targets.bzl", "declare_rosbag_per_target")
load("@bagzel//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/python/oxts_to_maps.bzl", "oxts_to_maps")
load("@bagzel//processing_edges/rosbag_to_vision_dataset/src:starlark/rules/core/merge_worldmodel_annotations.bzl", "merge_worldmodel_annotations")
load(
    "@bagzel_config//:config.bzl",
    "TOPIC_MAP",
    "VALIDATE",
    "VEHICLE",
)


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

def to_hex(n):
    hex_chars = "0123456789abcdef"
    result = ""
    started = False
    for i in range(16):  # 32 bits = 8 hex digits
        shift = (7 - i) * 4
        digit = (n >> shift) & 0xF
        if digit != 0 or started or i == 7:
            result += hex_chars[digit]
            started = True
    return result

def hash_string_64(s):
    hash_v = "{}".format(hash(s))
    hash_v = hash_v.replace("-", "0")  # Replace dashes with 0
    hash_v = hash_v.replace(" ", "_")  # Replace spaces with underscores
    return hash_v



def get_stem(bag_file):
    base_name = bag_file.split("/")[-1]
    stem = base_name.split(".")[0]  # Get the file name without extension
    stem = stem.replace("-", "_")  # Replace dashes with underscores
    stem = stem.replace(" ", "_")  # Replace spaces with underscores
    stem = stem + "_{}".format(hash_string_64(bag_file))

    return stem



#function which checks validity. You may exclude some bags which might be a copy
#this happens if it has "copy" in its name (+ its invalid for reading later
#or: this happens if we filtered it somehow ("filtered")
def isPathValid(filename):
    lower_filename = filename.lower()
    isValid = True

    isValid = isValid and not ("copy" in lower_filename)
    isValid = isValid and not ("filtered" in lower_filename)

    return isValid

def is_ros1_bag(p):
    return p.endswith(".bag")


def graph_macro(name, input_bag_files, output_dir = "output", per_bag_nuscenes_hooks = [],):
    all_everything = []     # global “everything”
    all_oxts = []           # for maps
    all_sequences = []      # for merged annos
    all_metadata = []       # for merged annos (valid-only if you want)
    all_visual_processed = [] # optional
    all_nuscenes_processed = [] # optional

    for bag_file in input_bag_files:
        if not isPathValid(bag_file):
            continue

        stem = get_stem(bag_file)

        # --- NuScenes (ROS1 + ROS2) ---
        nuscenes_target = single_rosbag_to_nuscenes(
            bag_file = bag_file,
            output_dir = output_dir,
            stem = stem,
            tool = "@bagzel//processing_edges/rosbag_to_nuscenes:rosbag_to_nuscenes",
        )
        all_nuscenes_processed.append(":" + nuscenes_target)
        all_everything.append(":" + nuscenes_target)

        ctx = {
            "name": name,
            "stem": stem,
            "bag_file": bag_file,
            "output_dir": output_dir,
            "nuscenes_target": ":" + nuscenes_target,  # label string
            "add_everything": all_everything,          # list to append to
        }
        for h in per_bag_nuscenes_hooks:
            all_everything.extend(h(ctx) or [])

        # # --- STEP 2: PRINT ALL FILES CREATED (per bag) ---
        # print_target = print_nuscenes(
        #     input_nuscenes_target = nuscenes_target,
        #     stem = stem,
        #     tool = "@bagzel//src/starlark/rules/core/mwe_print_filenames:mwe_print_filenames",
        # )
        # all_print_nuscenes.append(":" + print_target)
        # all_everything.append(":" + print_target)

        # --- ROS1-only pipeline ---
        if is_ros1_bag(bag_file):
            r = declare_rosbag_per_target(
                name_prefix = stem,
                rosbag_path = bag_file,
                topic_map = TOPIC_MAP,
                vehicle = VEHICLE,
                validate = VALIDATE,
            )

            all_visual_processed.append(r["processed"])
            all_everything.append(r["processed"])

            if r["valid"]:
                all_oxts.append(r["oxts"])
                all_sequences.append(r["sequences"])
                all_metadata.append(r["metadata"])

            # optional: per-bag "everything"
            native.filegroup(
                name = "{}__everything".format(stem),
                srcs = [":" + nuscenes_target, r["processed"]],
                visibility = ["//visibility:public"],
            )

    # ---------------- SUM TARGETS (cross-bag) ----------------

    # 1) maps from all oxts
    native.filegroup(
        name = name + "__oxts_all",
        srcs = all_oxts,
    )

    oxts_to_maps(
        name = name + "__maps",
        name_prefix = name,
        input_files = [":" + name + "__oxts_all"],
        tool = _ROSBAG_TOOLS["maps"],
    )
    all_everything.append(":" + name + "__maps")

    # 2) merged world model annotations
    merge_worldmodel_annotations(
        name = name + "__wm_annos",
        name_prefix = name,
        inputs = all_sequences,
        metadata = all_metadata,
        merge_tool = _ROSBAG_TOOLS["merge_worldmodel_annos"],
        val_split_percent = 20,
        seed = 42,
    )
    all_everything.append(":" + name + "__wm_annos")

    # optional single-file version
    merge_worldmodel_annotations(
        name = name + "__wm_annos_single_file",
        name_prefix = name,
        inputs = all_sequences,
        metadata = all_metadata,
        merge_tool = _ROSBAG_TOOLS["merge_worldmodel_annos"],
        single = True,
    )
    all_everything.append(":" + name + "__wm_annos_single_file")

    # ---------------- GLOBAL AGGREGATES ----------------

    native.filegroup(
        name = name + "__everything",
        srcs = all_everything,
        visibility = ["//visibility:public"],
    )

    native.filegroup(
        name = name + "__visual_data",
        srcs = all_visual_processed,
        visibility = ["//visibility:public"],
    )
    native.filegroup(
        name = name + "__nuscenes_data",
        srcs = all_nuscenes_processed,
        visibility = ["//visibility:public"],
    )


################### STEP 2: PRINT ALL FILES CREATED ###################

        #this is a dummy-target, which prints all files created by the previous step
        # this can be used as blueprint for further processing steps
        #the
        # print_target = print_nuscenes(
        #    input_nuscenes_target = nuscenes_target,
        #    stem = stem,
        #    tool = "@bagzel//src/starlark/rules/core/mwe_print_filenames:mwe_print_filenames"
        # )
        # all_targets.append(":{t}".format(t=print_target))
        # per_bag_target.append(":{t}".format(t=print_target))

        # native.filegroup(
        #     name = "{}_graph_everything".format(stem),
        #     srcs = per_bag_target,
        #     visibility = ["//visibility:public"],
        # )