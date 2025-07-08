# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _filter_rosbag_impl(ctx):
    input_files = ctx.attr.rosbag_dir[DefaultInfo].files
    output_file = ctx.actions.declare_file("valid_rosbags.bzl")

    # Command arguments: <rosbag_dir> <output> <topic1> <topic2> ...
    arguments = [
        ctx.attr.rosbag_dir.label.package, 
        output_file.path,
    ] + ctx.attr.topics

    ctx.actions.run(
        inputs = input_files.to_list(),
        outputs = [output_file],
        executable = ctx.executable.filter_tool,
        arguments = arguments,
        progress_message = "Filtering rosbags and generating valid_rosbags.bzl",
    )

    return [DefaultInfo(files = depset([output_file]))]

filter_rosbag = rule(
    implementation = _filter_rosbag_impl,
    attrs = {
        "rosbag_dir": attr.label(
            allow_files = True,
            mandatory = True,
        ),
        "topics": attr.string_list(mandatory = True),
        "filter_tool": attr.label(
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
    },
)
