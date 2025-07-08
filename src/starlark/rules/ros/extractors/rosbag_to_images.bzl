# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _rosbag_to_images_impl(ctx):
    rosbag = ctx.file.rosbag
    rosbag_path = rosbag.path
    rosbag_name = ctx.attr.rosbag_name

    all_outputs = []

    for topic in ctx.attr.topics:
        topic_folder = topic.lstrip("/").replace("/", "_")
        topic_output_dir = "{}/images/{}".format(rosbag_name, topic_folder)
        output_dir = ctx.actions.declare_directory(topic_output_dir)

        ctx.actions.run(
            inputs = [rosbag],
            outputs = [output_dir],
            executable = ctx.executable.rosbag_tool,
            arguments = [
                rosbag.path,
                topic,
                output_dir.path,
            ],
            progress_message = "[Extracting] Rosbag: '{}', Topic: '{}'".format(rosbag_name, topic),
        )

        all_outputs.append(output_dir)

    return [DefaultInfo(files = depset(all_outputs))]

rosbag_to_images = rule(
    implementation = _rosbag_to_images_impl,
    attrs = {
        "rosbag": attr.label(mandatory = True, allow_single_file = True),
        "rosbag_name": attr.string(mandatory = True),
        "rosbag_tool": attr.label(mandatory = True, executable = True, cfg = "exec"),
        "topics": attr.string_list(mandatory = True),
    },
)
