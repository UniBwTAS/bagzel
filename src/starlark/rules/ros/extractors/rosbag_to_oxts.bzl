# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _rosbag_to_oxts_impl(ctx):
    rosbag = ctx.file.rosbag
    rosbag_name = ctx.attr.rosbag_name
    oxts_ip = "195.0.0.20" # IP address of the OXFORD GPS device is hardcoded and set to touareg's oxford ip.

    # Output file in subfolder
    output_csv = ctx.actions.declare_file("{}/oxts/oxts_{}_{}.csv".format(rosbag_name, rosbag_name, oxts_ip))

    ctx.actions.run(
        inputs = [rosbag],
        outputs = [output_csv],
        executable = ctx.executable.rosbag_tool,
        arguments = [
            rosbag.path,
            output_csv.path,
            oxts_ip, 
        ],
        progress_message = "[Extracting GPS] {}".format(rosbag_name),
    )

    return [DefaultInfo(files = depset([output_csv]))]

rosbag_to_oxts = rule(
    implementation = _rosbag_to_oxts_impl,
    attrs = {
        "rosbag": attr.label(mandatory = True, allow_single_file = True),
        "rosbag_name": attr.string(mandatory = True),
        "rosbag_tool": attr.label(mandatory = True, executable = True, cfg = "exec"),
    },
)
