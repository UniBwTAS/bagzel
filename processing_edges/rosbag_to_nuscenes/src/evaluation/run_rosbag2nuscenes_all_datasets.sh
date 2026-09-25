#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run rosbag2nuscenes benchmark for small, medium, and large datasets.

Usage:
  run_rosbag2nuscenes_all_datasets.sh [options]

Options:
  --workspace PATH           Workspace path (default: /home/lepo/git/pas-mono-intern)
  --eval-root PATH           Evaluation root (default: /home/lepo/git/bagzel_eval)
  --dataset-name NAME        Dataset folder name (default: 2025-04-23_13-56-29_tas)
  --cold-runs N              Cold runs per dataset (default: 3)
  --warm-runs N              Warm runs per dataset (default: 3)
  --incremental-runs N       Incremental runs per dataset (default: 3)
  --pause-seconds N          Pause between datasets in seconds (default: 45)
  --dry-run                  Print commands without executing
  -h, --help                 Show this help
EOF
}

WORKSPACE="/home/lepo/git/pas-mono-intern"
EVAL_ROOT="/home/lepo/git/bagzel_eval"
DATASET_NAME="2025-04-23_13-56-29_tas"
COLD_RUNS=3
WARM_RUNS=3
INCREMENTAL_RUNS=3
PAUSE_SECONDS=45
DRY_RUN=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_SCRIPT="$SCRIPT_DIR/run_bazel_build_benchmark.sh"
CONVERTER="$SCRIPT_DIR/../rosbag_to_nuscenes.py"
PARAM_FILE="$SCRIPT_DIR/nuscenes_param.json"
ENV_FILE="$SCRIPT_DIR/environment.yml"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      WORKSPACE="${2:-}"; shift 2 ;;
    --eval-root)
      EVAL_ROOT="${2:-}"; shift 2 ;;
    --dataset-name)
      DATASET_NAME="${2:-}"; shift 2 ;;
    --cold-runs)
      COLD_RUNS="${2:-}"; shift 2 ;;
    --warm-runs)
      WARM_RUNS="${2:-}"; shift 2 ;;
    --incremental-runs)
      INCREMENTAL_RUNS="${2:-}"; shift 2 ;;
    --pause-seconds)
      PAUSE_SECONDS="${2:-}"; shift 2 ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage
      exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

if [[ ! -x "$BENCH_SCRIPT" ]]; then
  echo "Benchmark script not found or not executable: $BENCH_SCRIPT" >&2
  exit 1
fi
if [[ ! -f "$CONVERTER" ]]; then
  echo "Converter file not found: $CONVERTER" >&2
  exit 1
fi
if [[ ! -f "$PARAM_FILE" ]]; then
  echo "Param file not found: $PARAM_FILE" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

run_dataset() {
  local size="$1"
  local input_root="$EVAL_ROOT/$size/$DATASET_NAME"
  local output_dir="$EVAL_ROOT/$size/build/rosbag2nuscenes_benchmark"
  local rosbag_output_root="$EVAL_ROOT/$size/build/rosbag2nuscenes_output"
  local db3_file="$input_root/ros2/ros2bag/ros2bag.db3"
  local incremental_cmd
  incremental_cmd="f=\"$db3_file\"; v=\$(sqlite3 \"\$f\" \"PRAGMA user_version;\"); sqlite3 \"\$f\" \"PRAGMA user_version=\$((v+1));\""

  if [[ ! -d "$input_root" ]]; then
    echo "Missing dataset directory: $input_root" >&2
    exit 1
  fi

  local cmd=(
    "$BENCH_SCRIPT"
    --mode rosbag2nuscenes
    --workspace "$WORKSPACE"
    --output-dir "$output_dir"
    --input-root "$input_root"
    --rosbag-output-root "$rosbag_output_root"
    --converter "$CONVERTER"
    --param-file "$PARAM_FILE"
    --env-file "$ENV_FILE"
    --cold-runs "$COLD_RUNS"
    --warm-runs "$WARM_RUNS"
    --incremental-runs "$INCREMENTAL_RUNS"
    --incremental-cmd "$incremental_cmd"
  )

  echo "=== Running $size dataset ==="
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '%q ' "${cmd[@]}"
    echo
  else
    "${cmd[@]}"
  fi
}

run_dataset "small"
if [[ "$PAUSE_SECONDS" -gt 0 ]]; then
  echo "Pausing ${PAUSE_SECONDS}s before medium..."
  sleep "$PAUSE_SECONDS"
fi

run_dataset "medium"
if [[ "$PAUSE_SECONDS" -gt 0 ]]; then
  echo "Pausing ${PAUSE_SECONDS}s before large..."
  sleep "$PAUSE_SECONDS"
fi

run_dataset "large"

echo "All dataset runs completed."
