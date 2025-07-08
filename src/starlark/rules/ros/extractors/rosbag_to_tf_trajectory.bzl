# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _rosbag_to_tf_trajectory_impl(ctx):
    bag = ctx.file.bag
    tool = ctx.executable.extract_tool

    output_files = []
    output_dict = {}

    for pair in ctx.attr.trajectories:
        target_frame, reference_frame = pair.split(":")

        target = target_frame.replace("/", "_")
        reference = reference_frame.replace("/", "_")

        filename = "{}_in_{}.csv".format(target, reference)
        output_file = ctx.actions.declare_file("{}/trajectories/{}".format(ctx.attr.rosbag_name, filename))

        ctx.actions.run(
            inputs = [bag, tool],
            outputs = [output_file],
            executable = tool,
            arguments = [bag.path, output_file.path, target_frame, reference_frame],
            progress_message = "📍 Extracting TF trajectory of '{}' in '{}' using {}".format(
                target_frame, reference_frame, bag.path),
            mnemonic = "ExtractTFFrameTrajectory",
        )

        output_files.append(output_file)
        output_dict[filename] = depset([output_file])


    return [
        DefaultInfo(files = depset(output_files)),
        OutputGroupInfo(**output_dict)
    ]

rosbag_to_tf_trajectory = rule(
    implementation = _rosbag_to_tf_trajectory_impl,
    attrs = {
        "bag": attr.label(
            doc = "The input ROS bag file",
            allow_single_file = True,
            mandatory = True,
        ),
        "rosbag_name": attr.string(
            doc = "The name used in the output path",
            mandatory = True,
        ),
        "trajectories": attr.string_list(
            doc = "List of trajectories as 'target_frame:reference_frame'",
            mandatory = True,
        ),
        "extract_tool": attr.label(
            doc = "The C++ executable that extracts frame poses from the bag",
            executable = True,
            cfg = "exec",
            mandatory = True,
        ),
    },
    doc = "Extracts the trajectories of TF transforms over time from a ROS bag and writes CSVs for each pair.",
)
