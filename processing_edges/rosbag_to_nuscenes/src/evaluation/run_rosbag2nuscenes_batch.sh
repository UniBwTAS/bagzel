#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run_rosbag2nuscenes_batch.sh \
    --input-root /path/to/search \
    --output-root /path/to/output \
    --converter /path/to/rosbag_to_nuscenes.py \
    --param-file /path/to/params.(yaml|yml|json) \
    [--run-label cold|warm|incremental] \
    [--env-file /path/to/environment.yml] \
    [--metrics-csv /path/to/metrics.csv] \
    [--python python3] \
    [--continue-on-error] \
    [--dry-run]

Description:
  Recursively scans --input-root for *.bag and *.db3 files and runs
  rosbag_to_nuscenes.py for each file.
  For --run-label cold, the conda env from --env-file is recreated.
  Emits per-file timing and throughput metrics to CSV for benchmarking.
EOF
}

INPUT_ROOT=""
OUTPUT_ROOT=""
CONVERTER=""
PARAM_FILE=""
PYTHON_BIN="python3"
CONTINUE_ON_ERROR=0
DRY_RUN=0
RUN_LABEL="unspecified"
METRICS_CSV=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/environment.yml"
CONDA_ENV_NAME=""
INSTALL_STATUS="skipped"
INSTALL_DUR=0
ACTIVE_PYTHON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-root)
      INPUT_ROOT="${2:-}"; shift 2 ;;
    --output-root)
      OUTPUT_ROOT="${2:-}"; shift 2 ;;
    --converter)
      CONVERTER="${2:-}"; shift 2 ;;
    --param-file)
      PARAM_FILE="${2:-}"; shift 2 ;;
    --run-label)
      RUN_LABEL="${2:-}"; shift 2 ;;
    --env-file)
      ENV_FILE="${2:-}"; shift 2 ;;
    --metrics-csv)
      METRICS_CSV="${2:-}"; shift 2 ;;
    --python)
      PYTHON_BIN="${2:-}"; shift 2 ;;
    --continue-on-error)
      CONTINUE_ON_ERROR=1; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

if [[ -z "$INPUT_ROOT" || -z "$OUTPUT_ROOT" || -z "$CONVERTER" || -z "$PARAM_FILE" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 2
fi

INPUT_ROOT="${INPUT_ROOT%/}"
OUTPUT_ROOT="${OUTPUT_ROOT%/}"

if [[ ! -d "$INPUT_ROOT" ]]; then
  echo "Input root does not exist: $INPUT_ROOT" >&2
  exit 1
fi
if [[ ! -f "$CONVERTER" ]]; then
  echo "Converter script does not exist: $CONVERTER" >&2
  exit 1
fi
if [[ ! -f "$PARAM_FILE" ]]; then
  echo "Param file does not exist: $PARAM_FILE" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file does not exist: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$OUTPUT_ROOT"

RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$OUTPUT_ROOT/batch_run_${RUN_TS}.log"
touch "$LOG_FILE"
if [[ -z "$METRICS_CSV" ]]; then
  METRICS_CSV="$OUTPUT_ROOT/batch_metrics_${RUN_TS}.csv"
fi
SUMMARY_FILE="$OUTPUT_ROOT/batch_summary_${RUN_TS}.txt"

csv_escape() {
  local s="${1//\"/\"\"}"
  printf '"%s"' "$s"
}

activate_conda_env() {
  local env_name="$1"
  local conda_base
  conda_base="$(conda info --base 2>/dev/null || true)"
  if [[ -z "$conda_base" || ! -f "$conda_base/etc/profile.d/conda.sh" ]]; then
    echo "Could not find conda initialization script for activation." >&2
    return 1
  fi
  # shellcheck disable=SC1090
  source "$conda_base/etc/profile.d/conda.sh"
  conda activate "$env_name"
}

CONDA_ENV_NAME="$(awk '/^name:[[:space:]]*/ {print $2; exit}' "$ENV_FILE")"
if [[ -z "$CONDA_ENV_NAME" ]]; then
  echo "Could not parse conda environment name from: $ENV_FILE" >&2
  exit 1
fi

if [[ "$RUN_LABEL" == "cold" ]]; then
  if ! command -v conda >/dev/null 2>&1; then
    echo "Conda is not available in PATH, but --run-label cold requires conda environment recreation." >&2
    exit 1
  fi

  echo "Cold run: recreating conda env '$CONDA_ENV_NAME' from $ENV_FILE" | tee -a "$LOG_FILE"
  INSTALL_STATUS="ok"

  if conda env list | awk '{print $1}' | grep -Fxq "$CONDA_ENV_NAME"; then
    echo "Removing existing conda env: $CONDA_ENV_NAME" | tee -a "$LOG_FILE"
    if ! conda env remove -n "$CONDA_ENV_NAME" -y >>"$LOG_FILE" 2>&1; then
      INSTALL_STATUS="failed_remove"
      INSTALL_DUR=0
      echo "Failed to remove existing conda env: $CONDA_ENV_NAME" | tee -a "$LOG_FILE"
      exit 1
    fi
  fi

  echo "Creating conda env from: $ENV_FILE" | tee -a "$LOG_FILE"
  install_start_ts=$(date +%s)
  if ! conda env create -f "$ENV_FILE" >>"$LOG_FILE" 2>&1; then
    INSTALL_STATUS="failed_create"
    INSTALL_DUR=$(( $(date +%s) - install_start_ts ))
    echo "Failed to create conda env from: $ENV_FILE" | tee -a "$LOG_FILE"
    exit 1
  fi

  INSTALL_DUR=$(( $(date +%s) - install_start_ts ))
  echo "Conda env ready: $CONDA_ENV_NAME (install ${INSTALL_DUR}s)" | tee -a "$LOG_FILE"
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "Conda is not available in PATH, cannot activate env: $CONDA_ENV_NAME" >&2
  exit 1
fi
if ! activate_conda_env "$CONDA_ENV_NAME" >>"$LOG_FILE" 2>&1; then
  echo "Failed to activate conda env: $CONDA_ENV_NAME" | tee -a "$LOG_FILE"
  exit 1
fi
echo "Activated conda env: $CONDA_ENV_NAME" | tee -a "$LOG_FILE"

if [[ -n "${CONDA_PREFIX:-}" && -x "$CONDA_PREFIX/bin/python" ]]; then
  ACTIVE_PYTHON="$CONDA_PREFIX/bin/python"
else
  ACTIVE_PYTHON="$PYTHON_BIN"
fi

mapfile -d '' FILES < <(
  find "$INPUT_ROOT" -type f \( -name '*.bag' -o -name '*.db3' \) -print0 | sort -z
)

TOTAL=${#FILES[@]}
if [[ "$TOTAL" -eq 0 ]]; then
  echo "No .bag or .db3 files found under $INPUT_ROOT"
  exit 0
fi

echo "Found $TOTAL input files." | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Metrics CSV: $METRICS_CSV" | tee -a "$LOG_FILE"
echo "Run label: $RUN_LABEL" | tee -a "$LOG_FILE"

echo "run_ts,run_label,run_id,total_runs,status,duration_s,input_file,input_bytes,input_mib,throughput_mib_s,output_dir" > "$METRICS_CSV"

OK=0
FAILED=0
FAILED_LIST=()
TOTAL_INPUT_BYTES=0
BATCH_START_TS=$(date +%s)

for idx in "${!FILES[@]}"; do
  input_file="${FILES[$idx]}"
  rel_path="${input_file#$INPUT_ROOT/}"
  rel_no_ext="${rel_path%.*}"
  output_dir="$OUTPUT_ROOT/$rel_no_ext"
  input_bytes=$(stat -c%s "$input_file" 2>/dev/null || echo 0)
  TOTAL_INPUT_BYTES=$((TOTAL_INPUT_BYTES + input_bytes))

  mkdir -p "$output_dir"
  run_id="$((idx + 1))/$TOTAL"
  echo "[$run_id] Processing: $input_file" | tee -a "$LOG_FILE"

  cmd=(
    --input_bag "$input_file"
    --output_dir "$output_dir"
    --param_file "$PARAM_FILE"
  )
  cmd=("$ACTIVE_PYTHON" "$CONVERTER" "${cmd[@]}")

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf 'DRY RUN: %q ' "${cmd[@]}" | tee -a "$LOG_FILE"
    echo | tee -a "$LOG_FILE"
    input_mib=$(awk -v b="$input_bytes" 'BEGIN { printf "%.3f", b/1048576 }')
    printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
      "$RUN_TS" \
      "$RUN_LABEL" \
      "$run_id" \
      "$TOTAL" \
      "DRY_RUN" \
      "0" \
      "$(csv_escape "$input_file")" \
      "$input_bytes" \
      "$input_mib" \
      "0" \
      "$(csv_escape "$output_dir")" >> "$METRICS_CSV"
    OK=$((OK + 1))
    continue
  fi

  start_ts=$(date +%s)
  if "${cmd[@]}" >>"$LOG_FILE" 2>&1; then
    end_ts=$(date +%s)
    dur=$((end_ts - start_ts))
    input_mib=$(awk -v b="$input_bytes" 'BEGIN { printf "%.3f", b/1048576 }')
    throughput_mib_s=$(awk -v mib="$input_mib" -v d="$dur" 'BEGIN { if (d > 0) printf "%.3f", mib/d; else print "0" }')
    echo "[$run_id] OK (${dur}s) -> $output_dir" | tee -a "$LOG_FILE"
    printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
      "$RUN_TS" \
      "$RUN_LABEL" \
      "$run_id" \
      "$TOTAL" \
      "OK" \
      "$dur" \
      "$(csv_escape "$input_file")" \
      "$input_bytes" \
      "$input_mib" \
      "$throughput_mib_s" \
      "$(csv_escape "$output_dir")" >> "$METRICS_CSV"
    OK=$((OK + 1))
  else
    end_ts=$(date +%s)
    dur=$((end_ts - start_ts))
    input_mib=$(awk -v b="$input_bytes" 'BEGIN { printf "%.3f", b/1048576 }')
    throughput_mib_s=$(awk -v mib="$input_mib" -v d="$dur" 'BEGIN { if (d > 0) printf "%.3f", mib/d; else print "0" }')
    echo "[$run_id] FAILED (${dur}s): $input_file" | tee -a "$LOG_FILE"
    printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
      "$RUN_TS" \
      "$RUN_LABEL" \
      "$run_id" \
      "$TOTAL" \
      "FAILED" \
      "$dur" \
      "$(csv_escape "$input_file")" \
      "$input_bytes" \
      "$input_mib" \
      "$throughput_mib_s" \
      "$(csv_escape "$output_dir")" >> "$METRICS_CSV"
    FAILED=$((FAILED + 1))
    FAILED_LIST+=("$input_file")
    if [[ "$CONTINUE_ON_ERROR" -ne 1 ]]; then
      echo "Stopping on first error. Use --continue-on-error to continue." | tee -a "$LOG_FILE"
      break
    fi
  fi
done

BATCH_END_TS=$(date +%s)
BATCH_DUR=$((BATCH_END_TS - BATCH_START_TS))
TOTAL_INPUT_GIB=$(awk -v b="$TOTAL_INPUT_BYTES" 'BEGIN { printf "%.3f", b/1073741824 }')
AVG_MIB_S=$(awk -F, 'NR>1 && $5=="OK" {sum+=$10; n++} END{if(n>0) printf "%.3f", sum/n; else print "0"}' "$METRICS_CSV")
P50_S=$(awk -F, 'NR>1 && $5=="OK" {print $6}' "$METRICS_CSV" | sort -n | awk '{
  a[NR]=$1
} END {
  if (NR==0) { print 0; exit }
  idx=int((NR+1)*0.50); if (idx<1) idx=1; if (idx>NR) idx=NR
  print a[idx]
}')
P90_S=$(awk -F, 'NR>1 && $5=="OK" {print $6}' "$METRICS_CSV" | sort -n | awk '{
  a[NR]=$1
} END {
  if (NR==0) { print 0; exit }
  idx=int((NR+1)*0.90); if (idx<1) idx=1; if (idx>NR) idx=NR
  print a[idx]
}')

echo "Done. Success: $OK, Failed: $FAILED, Total: $TOTAL, Batch wall time: ${BATCH_DUR}s" | tee -a "$LOG_FILE"
if [[ "$FAILED" -gt 0 ]]; then
  echo "Failed files:" | tee -a "$LOG_FILE"
  for f in "${FAILED_LIST[@]}"; do
    echo "  $f" | tee -a "$LOG_FILE"
  done
fi

{
  echo "run_ts=$RUN_TS"
  echo "run_label=$RUN_LABEL"
  echo "conda_env_file=$ENV_FILE"
  echo "conda_env_name=${CONDA_ENV_NAME:-n/a}"
  echo "conda_install_status=$INSTALL_STATUS"
  echo "conda_install_duration_s=$INSTALL_DUR"
  echo "total_files=$TOTAL"
  echo "success_files=$OK"
  echo "failed_files=$FAILED"
  echo "batch_wall_time_s=$BATCH_DUR"
  echo "total_input_gib=$TOTAL_INPUT_GIB"
  echo "avg_file_throughput_mib_s=$AVG_MIB_S"
  echo "p50_file_duration_s=$P50_S"
  echo "p90_file_duration_s=$P90_S"
  echo "metrics_csv=$METRICS_CSV"
  echo "log_file=$LOG_FILE"
} | tee "$SUMMARY_FILE"

echo "Summary file: $SUMMARY_FILE" | tee -a "$LOG_FILE"
