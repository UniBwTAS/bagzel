<!--
SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

# Contributing to Bagzel

Thank you for your interest in contributing to **Bagzel**!  
This document describes how to report issues, propose changes, and work with the codebase.

---

## 📣 Ways to Contribute

- **Report bugs** and unexpected behaviour
- **Improve documentation** (README, docs/, examples)
- **Add or improve features** (new extraction steps, new dataset formats, performance improvements)
- **Improve tests** and CI robustness

No contribution is too small — typo fixes and clarifications in documentation are very welcome.

---

## 🐛 Reporting Issues

Before opening a new issue:

1. **Search existing issues** to see if your problem has already been reported or discussed.
2. If not, open a new issue and include:
   - A clear and concise **description** of the problem
   - Steps to **reproduce**
   - What you **expected** to happen
   - What actually **happened**
   - Your environment (OS, Bazel version, Python version, ROS version(s))

If the issue is related to a specific dataset or bag, please mention:
- Which dataset/bag you used
- Whether it is publicly available or internal

---

## 🔧 Development Setup

1. **Clone the repository**

```bash
git clone https://github.com/UniBwTAS/bagzel.git
cd bagzel
```

2. **Fetch large files via Git LFS**

```bash
git lfs install
git lfs pull
```

3. **Install dependencies**

Runtime and development dependencies are managed via Bazel where possible.  
If Python tooling is needed (e.g. linters or formatters), follow `docs/bazel` and/or project-specific documentation.

4. **Verify Bazel works**

Run a small build or test to check your setup:

```bash
bazel query //...
```

or

```bash
bazel test //...
```

4. **Verify that the licensing setup works**

Run a small test to validate your configuration:

```bash
reuse --root ./bagzel lint
```

---

## 🧹 Code Style and Quality

- Follow the existing **structure and style** in the files you modify.
- Prefer **small, focused changes** over large refactorings.
- For Python code:
  - Keep functions small and well documented.
  - Avoid introducing new dependencies unless necessary.
- For Starlark (Bazel) code:
  - Use macros where it improves reuse and clarity.
  - Keep public macros documented (parameters, expected usage, example).

If you introduce new public APIs (macros, rules, or Python entrypoints), please add short docstrings and, if possible, a small example in `docs/` or in a minimal Bazel target.

---

## 🔁 Git Workflow

1. **Create a branch**

   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes** and commit them with clear messages, e.g.

   ```
   Add nuScenes export macro for ROS 2 bags
   ```

   or

   ```
   Fix path handling in external_repository local_repo
   ```

3. **Rebase** on the latest `main` (or relevant base branch) before opening a PR.

4. **Open a Pull Request**

   In your PR description, please include:

   - What the change does
   - Why it is needed / what problem it solves
   - How it was tested (commands, environment)
   - Any limitations or follow-up work

PRs that are easy to review — small, well explained, with tests — are merged much faster.

---

## 🙌 Code Review

All changes are reviewed before being merged.

- Be open to feedback and ready to adjust your changes.
- Reviewers may ask for additional tests, documentation, or refactoring.
- If a change is controversial or non-trivial, consider starting with an issue or a design discussion before implementing it.

---

## 🤝 Acknowledgements

By contributing to Bagzel, you help improve reproducible data workflows for robotics and autonomous systems.  
Thank you for your time, ideas, and energy!
