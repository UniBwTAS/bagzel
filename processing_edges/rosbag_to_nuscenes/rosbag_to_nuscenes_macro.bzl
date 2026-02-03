# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

# rosbag_to_nuscenes_macro.bzl
load("@bagzel//starlark/core:slurmrule.bzl", "slurmrule")

def get_metadata_filename(bag_file):
    return get_directory(bag_file) + "/metadata.yaml"

def get_directory(bag_file):
    return bag_file[:bag_file.rfind("/")]

def single_rosbag_to_nuscenes(
        bag_file,
        output_dir,
        stem,
        tool = "@bagzel//processing_edges/rosbag_to_nuscenes:rosbag_to_nuscenes",
        param_file = "@bagzel//processing_edges/rosbag_to_nuscenes:nuscenes_param.json",
    ):
    src = [bag_file, param_file]

    # If a file ends with db3, we need the directory as input.
    # If a file ends with bag, we need the file as input.
    if bag_file.endswith(".db3"):
        src.append(get_metadata_filename(bag_file))
    elif bag_file.endswith(".bag"):
        pass
    else:
        fail("Unsupported file type: {}".format(bag_file))

    relative_output_dir = output_dir + "/" + stem
    target_name = stem + "_rosbag_to_nuscenes"

    src_path = "$(location {input})".format(input = bag_file)
    param_path = "$(location {param})".format(param = param_file)

    # NOTE: keeping your dst_path logic unchanged
    dst_path = "$(location {dst_dir}/{file_name})".format(dst_dir = output_dir, file_name = stem)

    slurmrule(
        name = target_name,
        srcs = src,
        out_dirs = [relative_output_dir],
        tool = tool,
        cmd = """
        ./$(location {tool}) \
          --input_bag {src} \
          --output_dir {dst} \
          --param_file {param}
        """.format(
            tool = tool,
            src = src_path,
            dst = dst_path,
            param = param_path,
        ),
    )

    return target_name
