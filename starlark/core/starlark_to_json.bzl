# SPDX-FileCopyrightText: 2026 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

def _json_escape(s):
    return (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
         .replace("\n", "\\n")
         .replace("\r", "\\r")
         .replace("\t", "\\t")
    )

def starlark_to_json(value):
    return json.encode(value)


def _write_text_file_impl(ctx):
    out = ctx.actions.declare_file(ctx.attr.out_name)
    ctx.actions.write(output = out, content = ctx.attr.content)
    return [DefaultInfo(files = depset([out]))]

write_text_file = rule(
    implementation = _write_text_file_impl,
    attrs = {
        "content": attr.string(mandatory = True),
        "out_name": attr.string(mandatory = True),
    },
)
