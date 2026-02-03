#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Args:
#   $1 = path to paper.md (in execroot)
#   $2 = output path (pdf or tex, in execroot)
PAPER_MD="$1"
OUT_PATH="$2"

SRCDIR="$(dirname "$PAPER_MD")"
ABS_SRCDIR="$(cd "$SRCDIR" && pwd)"
BASENAME="$(basename "$PAPER_MD")"
BASEROOT="${BASENAME%.md}"

echo "[inara] PAPER_MD:   $PAPER_MD"
echo "[inara] SRCDIR:     $SRCDIR"
echo "[inara] ABS_SRCDIR: $ABS_SRCDIR"
echo "[inara] OUT_PATH:   $OUT_PATH"

# Decide output mode based on OUT_PATH extension
case "$OUT_PATH" in
  *.pdf)
    INARA_OUTPUT="pdf"              # or "pdf,preprint" if you want both
    EXPECTED_NAME="${BASEROOT}.pdf" # name inside WORKDIR
    ;;
  *.tex)
    INARA_OUTPUT="preprint"
    EXPECTED_NAME="${BASEROOT}.preprint.tex"
    ;;
  *)
    echo "[inara][ERROR] Unknown output extension (expected .pdf or .tex): $OUT_PATH" >&2
    exit 1
    ;;
esac

# Decide whether we are in a Docker-outside-of-Docker CI setup
if [ -e "/build-temp" ]; then
  echo "[inara] Detected Docker-outside-of-Docker setup (CI)."

  if [ ! -w /build-temp ]; then
    echo "[inara][ERROR] /build-temp is not writable" >&2
    exit 1
  fi

  WORKDIR="/build-temp/inara.$$"
  mkdir -p "$WORKDIR"

  echo "[inara] Copying sources from $ABS_SRCDIR to $WORKDIR"
  cp -a "$ABS_SRCDIR/." "$WORKDIR/"

  DOCKER_MOUNT="build-temp:/build-temp"
  DOCKER_WORKDIR="$WORKDIR"
else
  echo "[inara] No /build-temp: running with direct Docker access (local dev)."

  WORKDIR="$ABS_SRCDIR"
  DOCKER_MOUNT="$ABS_SRCDIR:/data"
  DOCKER_WORKDIR="/data"
fi

EXPECTED_PATH="$WORKDIR/$EXPECTED_NAME"

echo "[inara] WORKDIR (host/container-visible): $WORKDIR"
echo "[inara] Docker mount: -v $DOCKER_MOUNT"
echo "[inara] Docker workdir: $DOCKER_WORKDIR"
echo "[inara] Inara output mode: $INARA_OUTPUT"
echo "[inara] Expected Inara artifact: $EXPECTED_PATH"

# Check that Docker is reachable
if docker info >/dev/null 2>&1; then
  echo "[inara] ✅ Docker daemon is reachable"
else
  echo "[inara] ❌ Docker daemon is NOT reachable" >&2
  exit 1
fi

# Run Inara
docker run --rm \
  -v "$DOCKER_MOUNT" \
  -w "$DOCKER_WORKDIR" \
  -u "$(id -u):$(id -g)" \
  -e JOURNAL=joss \
  openjournals/inara:latest \
  -o "$INARA_OUTPUT" \
  "$BASENAME"

# Move result into Bazel's declared output
if [ ! -f "$EXPECTED_PATH" ]; then
  echo "[inara][ERROR] Expected output not found at: $EXPECTED_PATH" >&2
  ls -la "$WORKDIR" || true
  exit 1
fi

echo "[inara] Moving $EXPECTED_PATH -> $OUT_PATH"
mv "$EXPECTED_PATH" "$OUT_PATH"

# Cleanup temporary workdir in CI
if [[ "$WORKDIR" == /build-temp/inara.* ]]; then
  echo "[inara] Cleaning up temporary workdir $WORKDIR"
  rm -rf "$WORKDIR"
fi

echo "[inara] Done."
