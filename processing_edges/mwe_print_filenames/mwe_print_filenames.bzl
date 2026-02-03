# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

load("@bagzel//starlark/core:slurmrule.bzl", "slurmrule")

# Default printing tool (can be overridden by passing `tool=...`)
_DEFAULT_PRINT_TOOL = "@bagzel//processing-edges/mwe_print_filenames:mwe_print_filenames"

def print_nuscenes(input_nuscenes_target, stem, tool = _DEFAULT_PRINT_TOOL):
    """
    Create a slurm target that prints filenames from a NuScenes-producing target.

    Args:
        input_nuscenes_target: Label of the nuscenes-producing target.
        stem:                 String used to name the print target and output dir.
        tool:                 Label of the executable that prints filenames.
                              Defaults to `_DEFAULT_PRINT_TOOL`.
    """

    target_name = "{}_print".format(stem)

    slurmrule(
        name = target_name,
        # As soon as the target is built, the file will be available via $(location ...).
        srcs = [input_nuscenes_target],
        out_dirs = ["output/{}".format(stem)],
        tool = tool,
        cmd = "$(location {tool}) --src $(location {src})".format(
            tool = tool,
            src = input_nuscenes_target,
        ),
        after = input_nuscenes_target,
    )

    return target_name

