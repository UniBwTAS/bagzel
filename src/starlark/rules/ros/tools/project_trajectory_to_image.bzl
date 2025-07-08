# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _project_trajectory_impl(ctx):
    projection_tool = ctx.executable.projection_tool
    rear_csv = ctx.file.rear_csv
    camera_csv = ctx.file.camera_csv
    camera_info = ctx.file.camera_info
    image_file = ctx.file.input_image
    rosbag_name = ctx.attr.rosbag_name

    # Define the output image path
    output_image = ctx.actions.declare_file("{}/projected_trajectory.png".format(rosbag_name))

    ctx.actions.run(
        inputs = [projection_tool, rear_csv, camera_csv, camera_info, image_file],
        outputs = [output_image],
        executable = projection_tool,
        arguments = [
            rear_csv.path,
            camera_csv.path,
            camera_info.path,
            image_file.path,
            output_image.path,
        ],
        progress_message = "📷 Projecting trajectory onto image for bag: {}".format(rosbag_name),
    )

    return [DefaultInfo(files = depset([output_image]))]

project_trajectory_to_image = rule(
    implementation = _project_trajectory_impl,
    attrs = {
        "projection_tool": attr.label(
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
        "rear_csv": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "camera_csv": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "camera_info": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "input_image": attr.label(
            allow_single_file = True,
            mandatory = True,
        ),
        "rosbag_name": attr.string(
            mandatory = True,
        ),
    },
)
