# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _transform_trajectory_impl(ctx):
    trajectory_csv = ctx.file.trajectory_csv
    transform_json_files = ctx.files.transform_json
    dynamic_transform_json = transform_json_files[0]
    static_transform_json = transform_json_files[1]
    transform_tool = ctx.executable.transform_tool
    rosbag_name = ctx.attr.rosbag_name

    output_file = ctx.actions.declare_file("{}/trajectories/transformed_trajectory.csv".format(rosbag_name))

    ctx.actions.run(
        inputs = [trajectory_csv, static_transform_json, dynamic_transform_json, transform_tool],
        outputs = [output_file],
        executable = transform_tool,
        arguments = [
            trajectory_csv.path,
            static_transform_json.path,
            dynamic_transform_json.path,
            output_file.path,
        ],
        progress_message = "🚗 Transforming trajectory: {}".format(trajectory_csv.path),
    )
 
    return [DefaultInfo(files = depset([output_file]))]


transform_trajectory = rule(
    implementation = _transform_trajectory_impl,
    attrs = {
        "trajectory_csv": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "transform_json": attr.label_list(
            # allow_single_file = True,
            mandatory = True,
        ),
        "rosbag_name": attr.string(mandatory = True),
        "transform_tool": attr.label(
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
    },
)
