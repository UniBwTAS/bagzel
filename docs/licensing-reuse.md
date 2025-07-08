<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

> **Note:** These are example developer commands and may need adaptation to your specific project structure or shell environment.

# 📄 REUSE Compliance Commands

This document provides example commands to help ensure your project complies with the [REUSE Specification](https://reuse.software/).

---

## ✅ Lint the Project

Check your project's SPDX headers and license metadata:

```bash
reuse --root ~/git/pas-mono-intern/cluster/bagzel lint
```

This verifies that:
- All files have valid SPDX headers
- Declared licenses match installed license texts
- There are no missing or conflicting tags

---

## ✍️ Annotate Files with SPDX Headers

Automatically add SPDX headers to all Bazel (`.bzl`) files:

```bash
reuse --root ~/git/pas-mono-intern/cluster/bagzel annotate \
  --skip-unrecognised \
  --copyright="Leon Pohl <leon.pohl@unibw.de>" \
  --license="Apache-2.0" \
  **/*.bzl
```

> Make sure your shell supports globstar (`**`) or manually specify the target files.

---

## 🧠 Tips

- You can add headers to other file types by adjusting the file pattern.
- Run `reuse spdx yourfile` to check the SPDX info for a specific file.
- Consider running `reuse lint` in CI to enforce compliance.

---
