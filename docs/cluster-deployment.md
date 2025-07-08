<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

## ✅ Deployment on the DGX Cluster

To run the pipeline on the DGX cluster, ensure that Bazel is properly installed or that you are using a virtual environment that includes Bazel (e.g., via Anaconda).

You can find official Bazel installation instructions here:
🔗 https://bazel.build/install/ubuntu

---
### 1. Configure Bazel Output Location

Bazel stores all intermediate and final build artifacts (external dependencies, build outputs, logs, etc.) in an internal directory. If your builds involve large datasets or generate substantial outputs, it's critical to place this directory on a disk with sufficient space.

To specify a custom output location in a clean and portable way:
1. Create a file named `user.bazelrc` in the `rosbag-extractor` directory.
2. Add the following line to the file:
```batch
startup --output_user_root=/mnt/beegfs/ssd/lrt81/datasets/bazel_output_rosbagsDataset
```

> **This is the simplest and most portable approach** to redirect Bazel’s output to a different disk/folder.  
> If you need full control over the output path structure, you can alternatively use the more advanced `--output_base` startup flag.


---
### 2. Set Working Directory

Ensure that the `launch-rosbag-extractor.sh` script changes its working directory to the location of the `rosbag-extractor` directory. For example, in your SLURM batch script:

```bash
#SBATCH --chdir=<path-to>/rosbag-extractor
```

---

### 3. Logging
Logs will be automatically written to the logs/ folder in the current working directory.

---
### 4. Change Build Target

Adapt the Bazel build command to your specific build target. For example:
```batch
bazel build //data:rosbags_sub1_all
```
---
### 5. Start the pipeline with SLURM
```batch
sbatch launch-rosbag-extractor.sh
```
---