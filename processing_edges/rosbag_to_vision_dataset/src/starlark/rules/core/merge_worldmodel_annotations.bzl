# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _merge_worldmodel_annotations_impl(ctx):
    name_prefix = ctx.attr.name_prefix or ctx.label.name

    rosbag_jsons = ctx.files.inputs
    metadata_jsons = ctx.files.metadata
    if not rosbag_jsons:
        fail("No rosbag.json files provided")

    # --- Outputs depend on mode ---
    if ctx.attr.single:
        output_merged_file = ctx.actions.declare_file(
            "annos/worldmodel/{}_merged.json".format(name_prefix)
        )
        output_merged_manifest = ctx.actions.declare_file(
            "annos/worldmodel/{}_merged_manifest.json".format(name_prefix)
        )

        arguments = (
            ["--single"] +
            [f.path for f in rosbag_jsons] +
            [f.path for f in metadata_jsons] + [
                output_merged_file.path,
                output_merged_manifest.path,
            ]
        )

        outputs = [output_merged_file, output_merged_manifest]

    else:
        output_train_file = ctx.actions.declare_file(
            "annos/worldmodel/{}_train.json".format(name_prefix)
        )
        output_val_file = ctx.actions.declare_file(
            "annos/worldmodel/{}_val.json".format(name_prefix)
        )
        output_train_manifest = ctx.actions.declare_file(
            "annos/worldmodel/{}_train_manifest.json".format(name_prefix)
        )
        output_val_manifest = ctx.actions.declare_file(
            "annos/worldmodel/{}_val_manifest.json".format(name_prefix)
        )

        arguments = (
            [f.path for f in rosbag_jsons] +
            [f.path for f in metadata_jsons] + [
                output_train_file.path,
                output_val_file.path,
                output_train_manifest.path,
                output_val_manifest.path,
                str(ctx.attr.val_split_percent),
                str(ctx.attr.seed),
            ]
        )

        outputs = [
            output_train_file,
            output_val_file,
            output_train_manifest,
            output_val_manifest,
        ]

    ctx.actions.run(
        inputs = rosbag_jsons + metadata_jsons + [ctx.executable.merge_tool],
        outputs = outputs,
        executable = ctx.executable.merge_tool,
        arguments = arguments,
        progress_message = "Merging worldmodel annotations ({})".format(
            "single" if ctx.attr.single else "split"
        ),
    )

    return [DefaultInfo(files = depset(outputs))]

merge_worldmodel_annotations = rule(
    implementation = _merge_worldmodel_annotations_impl,
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
        # Backward compatible defaults; ignored in single mode
        "val_split_percent": attr.int(default = 20, doc = "Validation split percent (0-100)"),
        "seed": attr.int(default = 42, doc = "Random seed for split"),
        "single": attr.bool(
            default = False,
            doc = "If true, write a single merged file + manifest (uses --single)",
        ),
        "name_prefix": attr.string(
            doc = "Prefix for output files under 'annos/worldmodel/'"
        ),
    },
)
