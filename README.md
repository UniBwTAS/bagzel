<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

# 🥯 Bagzel: A Bazel-Powered Rosbag Extraction Pipeline

**Bagzel** is an efficient and reproducible data extraction pipeline for ROS 1 bag files, built on **Bazel**. It supports generating structured datasets—including image sequences, GPS logs, metadata, and map visualizations—from recorded robotic data.

---

## 🚀 Installation

### 🔧 Prerequisites

Make sure the following are installed on your system:

- **Bazel** ([installation guide](https://bazel.build/install))
- **git**
- **Git Large File Storage (LFS)** ([Git LFS installation guide](https://git-lfs.com))

To install Git LFS:
```bash
git lfs install
```

### 📥 Repository Setup

To obtain and prepare the source code:

```bash
git clone https://github.com/UniBwTAS/bagzel.git
cd bagzel
git lfs pull
```
>⚠️ Ensure you run `git lfs pull` to fetch large files such as bag files tracked via Git LFS.

## 🛠️ Build and Run: Minimal Working Example

To process a minimal dataset and generate all related build artifacts, run:

```bash
bazel build //data:rosbags_sub1_all
```

The resulting artifacts will be available under: 
```bazel-bin/data```

To explore available build targets, use:

```bash
bazel query //data:all
```
---

## 📚 Documentations
- [docs/declare-rosbag-artifacts.md](docs/declare-rosbag-artifacts.md) – Overview of the generated Bazel targets and data structure.

- [docs/cluster-deployment.md](docs/cluster-deployment.md) – Instructions for deploying the pipeline on a computing cluster. 

- [docs/bazel-profiling.md](docs/bazel-profiling.md) – Performance profiling with Bazel.

- [docs/update-python-deps.md](docs/update-python-deps.md) – Managing and updating Python dependencies using Bazel.

---

## 🧾 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](./LICENSES/Apache-2.0.txt) file for details.


