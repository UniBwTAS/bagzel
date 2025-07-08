# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _rosbag_to_metadata_impl(ctx):
    rosbag = ctx.file.rosbag
    rosbag_path = rosbag.path
    rosbag_name = ctx.attr.rosbag_name

    # Declare output file path (in a named subdirectory)
    output_file = ctx.actions.declare_file(rosbag_name + "/metadata.json")

    # Use ctx.actions.run with argument list
    ctx.actions.run(
        inputs = [rosbag],
        outputs = [output_file],
        executable = ctx.executable.rosbag_tool,
        arguments = [
            rosbag_path,
            rosbag_name,
            output_file.path,
        ],
        progress_message = "[Generating] Metadata in directory: '{}'".format(rosbag_name),
    )

    return [DefaultInfo(files = depset([output_file]))]

rosbag_to_metadata = rule(
    implementation = _rosbag_to_metadata_impl,
    attrs = {
        "rosbag": attr.label(mandatory = True, allow_single_file = True),
        "rosbag_name": attr.string(mandatory = True),
        "rosbag_tool": attr.label(mandatory = True, executable = True, cfg = "exec"),
    },
)
