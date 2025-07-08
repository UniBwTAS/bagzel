<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

> **Note:** These are example developer commands and may need adaptation to your specific environment or system paths.

# 🕒 ROSBag Usage Guide with Bazel

This guide provides basic commands for **playing** and **recording** ROSBag files using `bazel` targets defined in this project.

---

## 🔁 Play a ROSBag

Make sure simulation time is enabled before running:

```bash
rosparam set use_sim_time true
```

Then run the playback:

```bash
bazel run rosbag_play -- /path/to/your/file.bag --clock
```

> Replace `/path/to/your/file.bag` with the path to your actual `.bag` file.

---

## 🎥 Record a ROSBag

Record all topics for 10 seconds into a custom output directory:

```bash
bazel run rosbag_record -- -a --duration 10 -o ./data/output/
```

> You can adjust the duration or output directory as needed.

---

## ✅ Notes

- These commands assume you have a working ROS environment and `roscore` is running.
- Paths are examples—please modify them to match your local setup.