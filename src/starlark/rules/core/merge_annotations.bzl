# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _merge_annotations_impl(ctx):
    name_prefix = ctx.attr.name_prefix or ctx.label.name

    # Output files placed in 'annos/' subfolder and prefixed with name_prefix
    output_train_file = ctx.actions.declare_file("annos/{}_train.json".format(name_prefix))
    output_val_file = ctx.actions.declare_file("annos/{}_val.json".format(name_prefix))
    output_train_manifest = ctx.actions.declare_file("annos/{}_train_manifest.json".format(name_prefix))
    output_val_manifest = ctx.actions.declare_file("annos/{}_val_manifest.json".format(name_prefix))

    rosbag_jsons = ctx.files.inputs
    metadata_jsons = ctx.files.metadata

    if not rosbag_jsons:
        fail("No rosbag.json files provided")

    arguments = [f.path for f in rosbag_jsons] + \
                [f.path for f in metadata_jsons] + [
                    output_train_file.path,
                    output_val_file.path,
                    output_train_manifest.path,
                    output_val_manifest.path,
                    str(ctx.attr.val_split_percent),
                    str(ctx.attr.seed),
                ]

    ctx.actions.run(
        inputs = rosbag_jsons + metadata_jsons + [ctx.executable.merge_tool],
        outputs = [output_train_file, output_val_file, output_train_manifest, output_val_manifest],
        executable = ctx.executable.merge_tool,
        arguments = arguments,
    )

    return [DefaultInfo(files = depset([
        output_train_file,
        output_val_file,
        output_train_manifest,
        output_val_manifest,
    ]))]

merge_annotations = rule(
    implementation = _merge_annotations_impl,
    attrs = {
        "inputs": attr.label_list(
            allow_files = True,
            mandatory = True,
            doc = "List of rosbag.json files to merge",
        ),
        "metadata": attr.label_list(
            allow_files = True,
            mandatory = True,
            doc = "List of metadata.json files to merge",
        ),
        "merge_tool": attr.label(
            doc = "C++ merge_annotations binary",
            executable = True,
            cfg = "exec",
            allow_files = True,
            mandatory = True,
        ),
        "val_split_percent": attr.int(mandatory = True),
        "seed": attr.int(mandatory = True),
        "name_prefix": attr.string(
            doc = "Prefix used to name output files and group under 'annos/' subdir"
        ),
    },
)

