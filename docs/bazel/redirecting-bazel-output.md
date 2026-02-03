<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

## Redirecting Bazel Output to other directory or BeeGFS

By default, Bazel places its outputs and cache in a directory under the user’s home directory, which is often too small for large data builds. You can redirect Bazel’s output to BeeGFS using either `--output_user_root` (recommended) or `--output_base`.

### Using `user.bazelrc` (recommended)

Create a `user.bazelrc` file in the `bagzel` repository and add:

```bash
startup --output_user_root=/mnt/beegfs/ssd/lrt81/datasets/bazel_output_rosbagsDataset
```

This is the simplest and most portable way to ensure Bazel stores all build outputs on BeeGFS.

> If you need even more control over the internal directory layout, you can use `--output_base` instead, but `--output_user_root` is sufficient for most cases.

---
