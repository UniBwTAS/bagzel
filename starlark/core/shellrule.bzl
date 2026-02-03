# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _shellrule_impl(ctx):
    outputs = []
    outputs.extend(ctx.outputs.out_files)
    for _out_dir in ctx.attr.out_dirs:
        out_dir = ctx.actions.declare_directory(_out_dir)
        for output in outputs:
            if output.path.startswith(out_dir.path + "/"):
                fail("output {} is nested within output directory {}; outputs cannot be nested within each other!".format(output.path, out_dir.path))
            if output.is_directory and out_dir.path.startswith(output.path + "/"):
                fail("output directory {} is nested within output directory {}; outputs cannot be nested within each other!".format(out_dir.path, output.path))
        outputs.append(out_dir)

    if not outputs:
        fail("No outputs specified: outputs must not be empty.")

    rule_dir = "/".join([ctx.bin_dir.path, ctx.label.workspace_root, ctx.label.package]).replace("//", "/")
    cmd = ctx.attr.cmd.replace("$(RULEDIR)", rule_dir)  # Replace $(RULEDIR) with the first output directory
    # Replace $(location <out_dir>) with the full path for each out_dir
    for out_dir in ctx.attr.out_dirs:
        location_str = "$(location {})".format(out_dir)
        out_dir_path = "/".join([rule_dir, out_dir])
        cmd = cmd.replace(location_str, out_dir_path)

    cmd = ctx.expand_location(cmd, targets = [ctx.attr.tool] if ctx.attr.tool else [])  # Expand any other locations in the command

    ctx.actions.run_shell(
        inputs = ctx.files.srcs,
        tools = [ctx.executable.tool] if ctx.attr.tool else [], # the golden hint: https://github.com/bazelbuild/bazel/issues/20805
        outputs = outputs,
        command = cmd,
    )

    return DefaultInfo(
        files = depset(outputs),
        runfiles = ctx.runfiles(ctx.files.tool),
    )


shellrule = rule(
    implementation = _shellrule_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = True, mandatory = True),
        "out_files": attr.output_list(),
        "out_dirs": attr.string_list(mandatory = True),
        "cmd": attr.string(mandatory = True),
        "tool" : attr.label(
            allow_files = True,
            executable=True,
            cfg = "exec",
            doc = "Optional tools that are required to run the command.",
        ),
    },
)