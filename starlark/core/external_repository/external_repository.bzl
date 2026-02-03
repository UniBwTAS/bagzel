# SPDX-FileCopyrightText: 2026 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

load("@bagzel//starlark/core/external_repository:external_repository_impl.bzl",
     "external_repository_impl",
     "local_repo")

external_repository = module_extension(
    implementation = external_repository_impl,
    tag_classes = {"local_repo": local_repo},
)
