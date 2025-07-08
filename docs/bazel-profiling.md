<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

### Commands for Bazel profiling
```bash
bazel build --profile=build.prof //data:sequence_all
bazel analyze-profile build.prof
```

### Bazel Analyzer

https://analyzer.engflow.com/