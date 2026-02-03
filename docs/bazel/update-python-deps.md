<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

## 📦 Python Dependency Management with Bazel

Python dependencies are defined in [`processing_edges/rosbag_to_vision_dataset/third_party/python/requirements.in`](processing_edges/rosbag_to_vision_dataset/third_party/python/requirements.in) using the `pip-compile` format.

To update the lock files:

```bash
bazel run @bagzel//processing_edges/rosbag_to_vision_dataset/third_party/python:requirements.update
```

This will generate or update:

- `requirements_lock.txt` — the locked dependency versions (Linux/macOS)
- `requirements_windows.txt` — the equivalent for Windows platforms

> **Note:** This update step must be run manually whenever `requirements.in` changes.  
> The lock files are not updated automatically during a regular Bazel build.
