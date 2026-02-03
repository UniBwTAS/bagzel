<!--
SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->
This is a legacy config file location. It exists to keep the rosbag_to_nuscenes extractor self-contained and runnable without Bazel. In the Bazel integration, config files live in the bazel-config module, and the parameter file is generated from Starlark.