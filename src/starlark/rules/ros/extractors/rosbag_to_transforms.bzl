# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _rosbag_to_transforms_impl(ctx):
    rosbag = ctx.file.rosbag
    rosbag_name = ctx.attr.rosbag_name

    # Output files
    dynamic_output = ctx.actions.declare_file("{}/transforms/dynamic_transforms.json".format(rosbag_name))
    static_output = ctx.actions.declare_file("{}/transforms/static_transforms.json".format(rosbag_name))
    camera_output = ctx.actions.declare_file("{}/camera/camera_info.json".format(rosbag_name))

    ctx.actions.run(
        inputs = [rosbag],
        outputs = [dynamic_output, static_output, camera_output],
        executable = ctx.executable.rosbag_tool,
        arguments = [
            rosbag.path,
            dynamic_output.path,
            static_output.path,
            camera_output.path,
        ],
        progress_message = "[Generating] Transforms + CameraInfo from rosbag: '{}'".format(rosbag_name),
        mnemonic = "ExtractTFAndCamera",
    )

    return [
        DefaultInfo(files = depset([dynamic_output, static_output, camera_output])),
        OutputGroupInfo(
            dynamic = depset([dynamic_output]),
            static = depset([static_output]),
            camera = depset([camera_output]),
        ),
    ]


rosbag_to_transforms = rule(
    implementation = _rosbag_to_transforms_impl,
    attrs = {
        "rosbag": attr.label(mandatory = True, allow_single_file = True),
        "rosbag_name": attr.string(mandatory = True),
        "rosbag_tool": attr.label(mandatory = True, executable = True, cfg = "exec"),
    },
)
