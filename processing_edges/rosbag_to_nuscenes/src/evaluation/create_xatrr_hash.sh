#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  create_xatrr_hash.sh <input-folder>

Description:
  Recursively finds *.bag and *.db3 files under <input-folder> and writes
  sha256(file_contents) to xattr: user.bagzel_hash.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 1 ]]; then
  echo "Error: expected exactly one argument: <input-folder>" >&2
  usage
  exit 2
fi

INPUT_ROOT="${1%/}"

if [[ ! -d "$INPUT_ROOT" ]]; then
  echo "Error: input folder does not exist: $INPUT_ROOT" >&2
  exit 1
fi

if ! command -v setfattr >/dev/null 2>&1; then
  echo "Error: setfattr not found in PATH." >&2
  exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "Error: sha256sum not found in PATH." >&2
  exit 1
fi

find "$INPUT_ROOT" -type f \( -name '*.bag' -o -name '*.db3' \) -print0 \
| while IFS= read -r -d '' f; do
  h="$(sha256sum "$f" | awk '{print $1}')"
  setfattr -n user.bagzel_hash -v "$h" "$f"
  printf 'Set user.bagzel_hash for: %s\n' "$f"
done
