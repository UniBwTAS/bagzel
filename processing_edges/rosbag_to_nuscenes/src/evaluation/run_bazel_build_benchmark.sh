#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE_EOF'
Usage:
  run_bazel_build_benchmark.sh \
    --mode bazel|rosbag2nuscenes \
    [--workspace /path/to/workspace] \
    [--output-dir /path/to/output] \
    [--cold-runs 3] \
    [--warm-runs 3] \
    [--incremental-runs 3] \
    [--incremental-cmd "..."] \
    [--dry-run]

Bazel mode options:
  --mode bazel \
  --target @eval_data_small//:data_pipeline_processed__nuscenes_data \
  [--bazel bazel] \
  [--bazel-startup-flag --unix_digest_hash_attribute_name=user.bagzel_hash] \
  [--bazel-flag --config=...] \
  [--bazel-flag --remote_cache=...]

rosbag2nuscenes mode options:
  --mode rosbag2nuscenes \
  --input-root /path/to/bags \
  --rosbag-output-root /path/to/converter/output \
  --converter /path/to/rosbag_to_nuscenes.py \
  --param-file /path/to/params.(yaml|yml|json) \
  [--rosbag-script /path/to/run_rosbag2nuscenes_batch.sh] \
  [--env-file /path/to/environment.yml] \
  [--python python3] \
  [--continue-on-error]

Description:
  Unified benchmark driver for both Bagzel Bazel builds and rosbag2nuscenes
  baseline runs. Executes cold/warm/incremental phases and stores per-run
  metrics in one CSV + summary.

Phase behavior:
  cold:
    bazel mode: bazel shutdown + bazel clean --expunge before each run.
    rosbag2nuscenes mode: delegated to converter script via --run-label cold.
  warm:
    run with existing state.
  incremental:
    if --incremental-cmd is set, execute it before each run.
USAGE_EOF
}

MODE="bazel"
WORKSPACE="$(pwd)"
OUTPUT_DIR=""
COLD_RUNS=3
WARM_RUNS=3
INCREMENTAL_RUNS=3
INCREMENTAL_CMD=""
DRY_RUN=0

# bazel mode
TARGET=""
BAZEL_BIN="bazel"
BAZEL_STARTUP_FLAGS=()
BAZEL_FLAGS=()

# rosbag2nuscenes mode
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROSBAG_SCRIPT="$SCRIPT_DIR/run_rosbag2nuscenes_batch.sh"
INPUT_ROOT=""
ROSBAG_OUTPUT_ROOT=""
CONVERTER=""
PARAM_FILE=""
ENV_FILE="$SCRIPT_DIR/environment.yml"
PYTHON_BIN="python3"
CONTINUE_ON_ERROR=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"; shift 2 ;;
    --workspace)
      WORKSPACE="${2:-}"; shift 2 ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"; shift 2 ;;
    --cold-runs)
      COLD_RUNS="${2:-}"; shift 2 ;;
    --warm-runs)
      WARM_RUNS="${2:-}"; shift 2 ;;
    --incremental-runs)
      INCREMENTAL_RUNS="${2:-}"; shift 2 ;;
    --incremental-cmd)
      INCREMENTAL_CMD="${2:-}"; shift 2 ;;
    --dry-run)
      DRY_RUN=1; shift ;;

    --target)
      TARGET="${2:-}"; shift 2 ;;
    --bazel)
      BAZEL_BIN="${2:-}"; shift 2 ;;
    --bazel-startup-flag)
      BAZEL_STARTUP_FLAGS+=("${2:-}"); shift 2 ;;
    --bazel-flag)
      BAZEL_FLAGS+=("${2:-}"); shift 2 ;;

    --rosbag-script)
      ROSBAG_SCRIPT="${2:-}"; shift 2 ;;
    --input-root)
      INPUT_ROOT="${2:-}"; shift 2 ;;
    --rosbag-output-root)
      ROSBAG_OUTPUT_ROOT="${2:-}"; shift 2 ;;
    --converter)
      CONVERTER="${2:-}"; shift 2 ;;
    --param-file)
      PARAM_FILE="${2:-}"; shift 2 ;;
    --env-file)
      ENV_FILE="${2:-}"; shift 2 ;;
    --python)
      PYTHON_BIN="${2:-}"; shift 2 ;;
    --continue-on-error)
      CONTINUE_ON_ERROR=1; shift ;;

    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

if [[ "$MODE" != "bazel" && "$MODE" != "rosbag2nuscenes" ]]; then
  echo "Invalid --mode: $MODE (expected bazel|rosbag2nuscenes)" >&2
  exit 2
fi

if [[ ! -d "$WORKSPACE" ]]; then
  echo "Workspace does not exist: $WORKSPACE" >&2
  exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$WORKSPACE/build_benchmark"
fi
mkdir -p "$OUTPUT_DIR"

if [[ "$MODE" == "bazel" ]]; then
  if [[ -z "$TARGET" ]]; then
    echo "Missing required argument for bazel mode: --target" >&2
    exit 2
  fi
  if ! command -v "$BAZEL_BIN" >/dev/null 2>&1; then
    echo "Bazel binary not found: $BAZEL_BIN" >&2
    exit 1
  fi
else
  if [[ -z "$INPUT_ROOT" || -z "$ROSBAG_OUTPUT_ROOT" || -z "$CONVERTER" || -z "$PARAM_FILE" ]]; then
    echo "Missing required arguments for rosbag2nuscenes mode: --input-root --rosbag-output-root --converter --param-file" >&2
    exit 2
  fi
  if [[ ! -x "$ROSBAG_SCRIPT" ]]; then
    echo "Rosbag benchmark script does not exist or is not executable: $ROSBAG_SCRIPT" >&2
    exit 1
  fi
fi

RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$OUTPUT_DIR/unified_benchmark_${MODE}_${RUN_TS}.log"
CSV_FILE="$OUTPUT_DIR/unified_benchmark_${MODE}_${RUN_TS}.csv"
SUMMARY_FILE="$OUTPUT_DIR/unified_benchmark_${MODE}_${RUN_TS}.summary.txt"
METRICS_DIR="$OUTPUT_DIR/unified_benchmark_${MODE}_${RUN_TS}_metrics"
mkdir -p "$METRICS_DIR"
touch "$LOG_FILE"

echo "run_ts,mode,phase,run,status,wall_s,user_s,sys_s,maxrss_kb,workspace,main_target,command,artifact_1,artifact_2,artifact_3" > "$CSV_FILE"

csv_escape() {
  local s="${1//\"/\"\"}"
  printf '"%s"' "$s"
}

apply_incremental_change() {
  local phase="$1"
  local run_idx="$2"
  if [[ "$phase" == "incremental" && -n "$INCREMENTAL_CMD" ]]; then
    echo "[incremental $run_idx] Applying change: $INCREMENTAL_CMD" | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      if ! (cd "$WORKSPACE" && bash -lc "$INCREMENTAL_CMD") >>"$LOG_FILE" 2>&1; then
        echo "[incremental $run_idx] FAILED to apply incremental change command." | tee -a "$LOG_FILE"
        return 1
      fi
    fi
  fi
}

run_once_bazel() {
  local phase="$1"
  local run_idx="$2"
  local status="OK"
  local tmp_time run_base profile_file bep_file exec_log_file
  tmp_time="$(mktemp)"
  run_base="$METRICS_DIR/${phase}_run_${run_idx}"
  profile_file="${run_base}.profile.json.gz"
  bep_file="${run_base}.bep.json"
  exec_log_file="${run_base}.execution_log.json"

  local cmd=(
    "$BAZEL_BIN"
    "${BAZEL_STARTUP_FLAGS[@]}"
    build "$TARGET"
    "--profile=$profile_file"
    "--build_event_json_file=$bep_file"
    "--execution_log_json_file=$exec_log_file"
    "${BAZEL_FLAGS[@]}"
  )

  echo "[$phase $run_idx] Running Bazel build for target: $TARGET" | tee -a "$LOG_FILE"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[%s %s] DRY RUN: %q ' "$phase" "$run_idx" "${cmd[@]}" | tee -a "$LOG_FILE"
    echo | tee -a "$LOG_FILE"
    echo "$RUN_TS,$MODE,$phase,$run_idx,DRY_RUN,0,0,0,0,$(csv_escape "$WORKSPACE"),$(csv_escape "$TARGET"),$(csv_escape "${cmd[*]}"),$(csv_escape "$profile_file"),$(csv_escape "$bep_file"),$(csv_escape "$exec_log_file")" >> "$CSV_FILE"
    rm -f "$tmp_time"
    return 0
  fi

  if /usr/bin/time -f "wall_s=%e user_s=%U sys_s=%S maxrss_kb=%M exit=%x" -o "$tmp_time" "${cmd[@]}" >>"$LOG_FILE" 2>&1; then
    status="OK"
  else
    status="FAILED"
  fi

  local wall_s user_s sys_s maxrss_kb
  wall_s="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^wall_s=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  user_s="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^user_s=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  sys_s="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^sys_s=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  maxrss_kb="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^maxrss_kb=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  rm -f "$tmp_time"

  wall_s="${wall_s:-0}"; user_s="${user_s:-0}"; sys_s="${sys_s:-0}"; maxrss_kb="${maxrss_kb:-0}"

  echo "[$phase $run_idx] $status wall=${wall_s}s user=${user_s}s sys=${sys_s}s rss=${maxrss_kb}KB" | tee -a "$LOG_FILE"
  echo "$RUN_TS,$MODE,$phase,$run_idx,$status,$wall_s,$user_s,$sys_s,$maxrss_kb,$(csv_escape "$WORKSPACE"),$(csv_escape "$TARGET"),$(csv_escape "${cmd[*]}"),$(csv_escape "$profile_file"),$(csv_escape "$bep_file"),$(csv_escape "$exec_log_file")" >> "$CSV_FILE"

  [[ "$status" == "OK" ]]
}

run_once_rosbag() {
  local phase="$1"
  local run_idx="$2"
  local status="OK"
  local tmp_time metrics_csv run_output_root
  tmp_time="$(mktemp)"
  metrics_csv="$METRICS_DIR/${phase}_run_${run_idx}.rosbag_metrics.csv"
  run_output_root="$ROSBAG_OUTPUT_ROOT/$RUN_TS/${phase}_run_${run_idx}"

  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$run_output_root"
  fi

  local cmd=(
    "$ROSBAG_SCRIPT"
    --input-root "$INPUT_ROOT"
    --output-root "$run_output_root"
    --converter "$CONVERTER"
    --param-file "$PARAM_FILE"
    --run-label "$phase"
    --env-file "$ENV_FILE"
    --python "$PYTHON_BIN"
    --metrics-csv "$metrics_csv"
  )
  if [[ "$CONTINUE_ON_ERROR" -eq 1 ]]; then
    cmd+=(--continue-on-error)
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    cmd+=(--dry-run)
  fi

  echo "[$phase $run_idx] Running rosbag2nuscenes batch benchmark" | tee -a "$LOG_FILE"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[%s %s] DRY RUN: %q ' "$phase" "$run_idx" "${cmd[@]}" | tee -a "$LOG_FILE"
    echo | tee -a "$LOG_FILE"
    echo "$RUN_TS,$MODE,$phase,$run_idx,DRY_RUN,0,0,0,0,$(csv_escape "$WORKSPACE"),$(csv_escape "$run_output_root"),$(csv_escape "${cmd[*]}"),$(csv_escape "$metrics_csv"),$(csv_escape ""),$(csv_escape "")" >> "$CSV_FILE"
    rm -f "$tmp_time"
    return 0
  fi

  if /usr/bin/time -f "wall_s=%e user_s=%U sys_s=%S maxrss_kb=%M exit=%x" -o "$tmp_time" "${cmd[@]}" >>"$LOG_FILE" 2>&1; then
    status="OK"
  else
    status="FAILED"
  fi

  local wall_s user_s sys_s maxrss_kb
  wall_s="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^wall_s=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  user_s="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^user_s=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  sys_s="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^sys_s=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  maxrss_kb="$(awk '{for(i=1;i<=NF;i++) if($i ~ /^maxrss_kb=/){split($i,a,"="); print a[2]}}' "$tmp_time")"
  rm -f "$tmp_time"

  wall_s="${wall_s:-0}"; user_s="${user_s:-0}"; sys_s="${sys_s:-0}"; maxrss_kb="${maxrss_kb:-0}"

  echo "[$phase $run_idx] $status wall=${wall_s}s user=${user_s}s sys=${sys_s}s rss=${maxrss_kb}KB" | tee -a "$LOG_FILE"
  echo "$RUN_TS,$MODE,$phase,$run_idx,$status,$wall_s,$user_s,$sys_s,$maxrss_kb,$(csv_escape "$WORKSPACE"),$(csv_escape "$run_output_root"),$(csv_escape "${cmd[*]}"),$(csv_escape "$metrics_csv"),$(csv_escape ""),$(csv_escape "")" >> "$CSV_FILE"

  [[ "$status" == "OK" ]]
}

run_phase() {
  local phase="$1"
  local runs="$2"
  local i

  if [[ "$runs" -le 0 ]]; then
    return 0
  fi

  for ((i = 1; i <= runs; i++)); do
    if [[ "$MODE" == "bazel" && "$phase" == "cold" ]]; then
      echo "[cold $i] bazel shutdown + bazel clean --expunge" | tee -a "$LOG_FILE"
      if [[ "$DRY_RUN" -eq 0 ]]; then
        (cd "$WORKSPACE" && "$BAZEL_BIN" shutdown) >>"$LOG_FILE" 2>&1 || true
        (cd "$WORKSPACE" && "$BAZEL_BIN" clean --expunge) >>"$LOG_FILE" 2>&1
      fi
    fi

    if ! apply_incremental_change "$phase" "$i"; then
      echo "Stopping: incremental change failed in phase '$phase' run $i." | tee -a "$LOG_FILE"
      return 1
    fi

    if [[ "$MODE" == "bazel" ]]; then
      if ! (cd "$WORKSPACE" && run_once_bazel "$phase" "$i"); then
        echo "Stopping on first failure in phase '$phase' run $i." | tee -a "$LOG_FILE"
        return 1
      fi
    else
      if ! (cd "$WORKSPACE" && run_once_rosbag "$phase" "$i"); then
        echo "Stopping on first failure in phase '$phase' run $i." | tee -a "$LOG_FILE"
        return 1
      fi
    fi
  done
}

phase_stats() {
  local phase="$1"
  awk -F, -v p="$phase" '
    NR > 1 && $3 == p && $5 == "OK" {
      n++
      vals[n] = $6 + 0
      sum += $6 + 0
    }
    END {
      if (n == 0) {
        printf "count=0 avg_s=0 median_s=0\n"
        exit
      }
      for (i = 1; i <= n; i++) {
        for (j = i + 1; j <= n; j++) {
          if (vals[j] < vals[i]) {
            t = vals[i]; vals[i] = vals[j]; vals[j] = t
          }
        }
      }
      mid = int((n + 1) / 2)
      if (n % 2 == 1) {
        med = vals[mid]
      } else {
        med = (vals[mid] + vals[mid + 1]) / 2
      }
      printf "count=%d avg_s=%.3f median_s=%.3f\n", n, sum / n, med
    }
  ' "$CSV_FILE"
}

echo "Mode: $MODE" | tee -a "$LOG_FILE"
echo "Workspace: $WORKSPACE" | tee -a "$LOG_FILE"
if [[ "$MODE" == "bazel" ]]; then
  BAZEL_VERSION="$(cd "$WORKSPACE" && "$BAZEL_BIN" --version 2>/dev/null || true)"
  if [[ -z "$BAZEL_VERSION" ]]; then
    BAZEL_VERSION="unknown"
  fi
  echo "Bazel: $BAZEL_BIN ($BAZEL_VERSION)" | tee -a "$LOG_FILE"
  echo "Target: $TARGET" | tee -a "$LOG_FILE"
  if [[ "${#BAZEL_STARTUP_FLAGS[@]}" -gt 0 ]]; then
    echo "Bazel startup flags: ${BAZEL_STARTUP_FLAGS[*]}" | tee -a "$LOG_FILE"
  fi
  if [[ "${#BAZEL_FLAGS[@]}" -gt 0 ]]; then
    echo "Bazel build flags: ${BAZEL_FLAGS[*]}" | tee -a "$LOG_FILE"
  fi
else
  echo "Rosbag script: $ROSBAG_SCRIPT" | tee -a "$LOG_FILE"
  echo "Input root: $INPUT_ROOT" | tee -a "$LOG_FILE"
  echo "Rosbag output root: $ROSBAG_OUTPUT_ROOT" | tee -a "$LOG_FILE"
  echo "Converter: $CONVERTER" | tee -a "$LOG_FILE"
  echo "Param file: $PARAM_FILE" | tee -a "$LOG_FILE"
  echo "Env file: $ENV_FILE" | tee -a "$LOG_FILE"
  echo "Python: $PYTHON_BIN" | tee -a "$LOG_FILE"
fi
if [[ -n "$INCREMENTAL_CMD" ]]; then
  echo "Incremental cmd: $INCREMENTAL_CMD" | tee -a "$LOG_FILE"
fi
echo "Runs: cold=$COLD_RUNS warm=$WARM_RUNS incremental=$INCREMENTAL_RUNS" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "CSV: $CSV_FILE" | tee -a "$LOG_FILE"
echo "Metrics dir: $METRICS_DIR" | tee -a "$LOG_FILE"

run_phase cold "$COLD_RUNS"
run_phase warm "$WARM_RUNS"
run_phase incremental "$INCREMENTAL_RUNS"

{
  echo "run_ts=$RUN_TS"
  echo "mode=$MODE"
  echo "workspace=$WORKSPACE"
  echo "cold_runs=$COLD_RUNS"
  echo "warm_runs=$WARM_RUNS"
  echo "incremental_runs=$INCREMENTAL_RUNS"
  echo "incremental_cmd=${INCREMENTAL_CMD:-none}"
  if [[ "$MODE" == "bazel" ]]; then
    echo "target=$TARGET"
    echo "bazel_bin=$BAZEL_BIN"
  else
    echo "rosbag_script=$ROSBAG_SCRIPT"
    echo "input_root=$INPUT_ROOT"
    echo "rosbag_output_root=$ROSBAG_OUTPUT_ROOT"
    echo "converter=$CONVERTER"
    echo "param_file=$PARAM_FILE"
    echo "env_file=$ENV_FILE"
  fi
  echo "cold_stats $(phase_stats cold)"
  echo "warm_stats $(phase_stats warm)"
  echo "incremental_stats $(phase_stats incremental)"
  echo "csv_file=$CSV_FILE"
  echo "log_file=$LOG_FILE"
  echo "metrics_dir=$METRICS_DIR"
} | tee "$SUMMARY_FILE"

echo "Summary file: $SUMMARY_FILE" | tee -a "$LOG_FILE"
