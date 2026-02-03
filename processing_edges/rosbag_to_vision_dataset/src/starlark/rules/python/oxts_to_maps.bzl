# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _oxts_to_maps_impl(ctx):
    name_prefix = ctx.attr.name_prefix or ctx.label.name

    input_files = ctx.files.input_files

    # 🔥 Outputs go into a "maps/" subfolder under this rule's output directory
    output_trajectory_map = ctx.actions.declare_file("maps/{}_trajectory_map.html".format(name_prefix))
    output_heat_map = ctx.actions.declare_file("maps/{}_heat_map.html".format(name_prefix))
    input_list_file = ctx.actions.declare_file("maps/{}_csv_file_list.txt".format(name_prefix))

    ctx.actions.write(
        output = input_list_file,
        content = "\n".join([f.path for f in input_files]),
    )

    ctx.actions.run(
        inputs = input_files + [input_list_file],
        outputs = [output_trajectory_map, output_heat_map],
        arguments = [input_list_file.path, output_heat_map.path, output_trajectory_map.path],
        executable = ctx.executable.tool,
        progress_message = "[{}] Generating GPS heat & trajectory map".format(name_prefix),
    )

    return [DefaultInfo(files = depset([output_trajectory_map, output_heat_map]))]



oxts_to_maps = rule(
    implementation = _oxts_to_maps_impl,
    attrs = {
        "input_files": attr.label_list(allow_files = [".csv"], mandatory = True),
        "tool": attr.label(mandatory = True, executable = True, cfg = "exec"),
        "name_prefix": attr.string(),  # Optional override for clean naming
    },
)

