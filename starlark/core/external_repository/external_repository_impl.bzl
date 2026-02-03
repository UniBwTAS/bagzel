# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

load("@bazel_tools//tools/build_defs/repo:local.bzl", "new_local_repository")

# This checks if a path exists. If it exists, it creates a new local repository, based on a build-file
# if this path does not exist, if also creates a new local repository, but with the second buiild-file
# in this way, one can define the same target-name, so it builds with both


def _is_absolute(p):
    # POSIX + simple Windows drive check
    return (
        p.startswith("/") or
        (len(p) >= 3 and p[1] == ":" and (p[2] == "/" or p[2] == "\\"))
    )

def external_repository_impl(ctx):
    for module in ctx.modules:
        for package in module.tags.local_repo:
            p = package.path

            if _is_absolute(p):
                # Only absolute paths are safe to check with ctx.path(...)
                path_exists = ctx.path(p).exists
                # print("Path exists (absolute):", path_exists)

                if path_exists:
                    new_local_repository(
                        name = package.repo_name,
                        path = p,  # absolute data path
                        build_file = package.build_file,
                    )
                else:
                    new_local_repository(
                        name = package.repo_name,
                        path = "",  # empty repo
                        build_file = package.empty_build_file,
                    )
            else:
                # Relative path → workspace-relative. Don't use ctx.path()
                # here, just trust the workspace layout.
                # print("Using relative path (workspace-relative):", p)
                new_local_repository(
                    name = package.repo_name,
                    path = p,  # e.g. "cluster/bagzel/data/ros2bags"
                    build_file = package.build_file,
                )

local_repo = tag_class(
    attrs = {
        "repo_name": attr.string(mandatory = True),
        "build_file": attr.label(
            mandatory = True,
            allow_single_file = True,
        ),
        "empty_build_file": attr.label(
            mandatory = True,
            allow_single_file = True,
        ),
        "path": attr.string(mandatory = True),
    },
)