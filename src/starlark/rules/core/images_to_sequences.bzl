# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _images_to_sequences_impl(ctx):
    input_files = ctx.attr.input_dir[DefaultInfo].files
    oxts_file = ctx.file.oxts_file  # <-- new input
    rosbag_name = ctx.attr.rosbag_name

    output_jsons = []

    for images_dir in input_files.to_list():
        topic_name = images_dir.path.split("/")[-1]

        sequences_output_dir = ctx.actions.declare_directory(
            "{}/sequences/{}".format(rosbag_name, topic_name)
        )
        output_json = ctx.actions.declare_file(
            "{}/sequences/sequences_{}.json".format(rosbag_name, topic_name)
        )

        ctx.actions.run(
            inputs = [images_dir, oxts_file],  # <-- include CSV
            outputs = [output_json, sequences_output_dir],
            executable = ctx.executable.sequence_tool,
            arguments = [
                images_dir.path,
                oxts_file.path,              # <-- pass to binary
                output_json.path,
            ],
            progress_message = "[Sequencing] Rosbag: '{}', Topic: '{}'".format(rosbag_name, topic_name),
        )

        output_jsons.append(output_json)

    return [DefaultInfo(files = depset(output_jsons))]

images_to_sequences = rule(
    implementation = _images_to_sequences_impl,
    attrs = {
        "input_dir": attr.label(
            providers = [DefaultInfo],
            mandatory = True,
        ),
        "sequence_tool": attr.label(
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
        "oxts_file": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "rosbag_name": attr.string(
            mandatory = True,
        ),
    },
)
