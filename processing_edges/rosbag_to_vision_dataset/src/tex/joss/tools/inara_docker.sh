#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <paper.md> <output.{pdf,tex}> [preprint_pdf]" >&2
  exit 2
fi

PAPER_MD="$1"
OUT_PATH="$2"
MODE="${3:-auto}"
IMAGE="${INARA_DOCKER_IMAGE:-openjournals/inara:latest}"

SRCDIR="$(dirname "$PAPER_MD")"
ABS_SRCDIR="$(cd "$SRCDIR" && pwd)"
BASENAME="$(basename "$PAPER_MD")"
BASEROOT="${BASENAME%.md}"
WORKDIR="$(mktemp -d)"
CONTAINER_IDS=()

cleanup() {
  for container_id in "${CONTAINER_IDS[@]}"; do
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  done
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

case "$MODE:$OUT_PATH" in
  preprint_pdf:*.pdf)
    INARA_OUTPUT="preprint"
    EXPECTED_NAME="${BASEROOT}.preprint.pdf"
    PREPRINT_TEX_NAME="${BASEROOT}.preprint.tex"
    ;;
  *:*.pdf)
    INARA_OUTPUT="pdf"
    EXPECTED_NAME="${BASEROOT}.pdf"
    ;;
  *:*.tex)
    INARA_OUTPUT="preprint"
    EXPECTED_NAME="${BASEROOT}.preprint.tex"
    ;;
  *)
    echo "unsupported output or mode: $MODE:$OUT_PATH" >&2
    exit 2
    ;;
esac

command -v docker >/dev/null 2>&1 || {
  echo "docker not found in PATH" >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "docker daemon is not reachable" >&2
  exit 1
}

# Bazel inputs may be symlinks into the execroot. Dereference them before
# transferring the source tree into Docker so this also works with a host
# Docker daemon accessed from a CI runner container.
cp -LR "$ABS_SRCDIR/." "$WORKDIR/"

run_inara() {
  local container_id
  container_id="$(
    docker create \
      -w /data \
      -e JOURNAL=joss \
      "$IMAGE" \
      -o "$INARA_OUTPUT" \
      "$BASENAME"
  )"
  CONTAINER_IDS+=("$container_id")
  docker cp "$WORKDIR/." "$container_id:/data"
  docker start -a "$container_id"
  docker cp "$container_id:/data/." "$WORKDIR/"
}

compile_preprint() {
  local container_id
  container_id="$(
    docker create \
      -w /data \
      --entrypoint latexmk \
      "$IMAGE" \
      -interaction=nonstopmode \
      -halt-on-error \
      -lualatex \
      "$PREPRINT_TEX_NAME"
  )"
  CONTAINER_IDS+=("$container_id")
  docker cp "$WORKDIR/." "$container_id:/data"
  docker start -a "$container_id"
  docker cp "$container_id:/data/." "$WORKDIR/"
}

echo "[inara] source: $ABS_SRCDIR/$BASENAME"
echo "[inara] image:  $IMAGE"
echo "[inara] mode:   $MODE ($INARA_OUTPUT)"

run_inara
if [[ "$MODE" == "preprint_pdf" ]]; then
  compile_preprint
fi

if [[ ! -f "$WORKDIR/$EXPECTED_NAME" ]]; then
  echo "expected output not found: $WORKDIR/$EXPECTED_NAME" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_PATH")"
cp "$WORKDIR/$EXPECTED_NAME" "$OUT_PATH"
echo "[inara] output: $OUT_PATH"
