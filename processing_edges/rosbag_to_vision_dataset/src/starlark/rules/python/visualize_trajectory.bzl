# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
# SPDX-License-Identifier: Apache-2.0

def _visualize_trajectory_impl(ctx):
    sequences_json = ctx.file.sequences_json
    vis_tool_py = ctx.executable.vis_tool_py
    vis_tool_cpp = ctx.executable.vis_tool_cpp
    image_dir_files = ctx.attr.image_dir[DefaultInfo].files


    rear_csv = ctx.file.rear_csv
    camera_csv = ctx.file.camera_csv
    camera_info = ctx.file.camera_info

    rosbag_name = ctx.attr.rosbag_name
    # output_dir = ctx.actions.declare_directory("{}/sequences_trajectories".format(rosbag_name))

    output_py_dir = ctx.actions.declare_directory("{}/previews/traj3d".format(rosbag_name))
    output_cpp_dir = ctx.actions.declare_directory("{}/previews/proj_imgs".format(rosbag_name))

    all_inputs = depset([
        sequences_json,
        vis_tool_py,
        vis_tool_cpp,
        rear_csv,
        camera_csv,
        camera_info
    ], transitive = [image_dir_files])


    # --- 1. Run Python 3D visualization ---
    ctx.actions.run(
        inputs = all_inputs,
        outputs = [output_py_dir],
        executable = vis_tool_py,
        arguments = [
            sequences_json.path,
            output_py_dir.path,
        ],
        progress_message = "📈 Generating 3D matplotlib visualizations from: {}".format(sequences_json.path),
    )

    # --- 2. Run C++ projection visualization ---
    ctx.actions.run(
        inputs = all_inputs,
        outputs = [output_cpp_dir],
        executable = vis_tool_cpp,
        arguments = [
            sequences_json.path,
            rear_csv.path,
            camera_csv.path,
            camera_info.path,
            output_cpp_dir.path,
        ],
        progress_message = "📷 Projecting 3D trajectory into images from: {}".format(sequences_json.path),
    )

    return [DefaultInfo(files = depset([output_py_dir, output_cpp_dir]))]


visualize_trajectory = rule(
    implementation = _visualize_trajectory_impl,
    attrs = {
        "sequences_json": attr.label(
            allow_single_file = True,
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
        "vis_tool_py": attr.label(
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
        "vis_tool_cpp": attr.label(
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
        "image_dir": attr.label(
            allow_files = True,
            mandatory = True,
            providers = [DefaultInfo],
        ),
        "rosbag_name": attr.string(mandatory = True),
    },
)
