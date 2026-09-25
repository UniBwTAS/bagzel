
Activate conda environment:
```bash
conda env list  
conda activate rosbag2nuscence-env
```


Run rosbag2NuScence benchmark (unified script, 3x cold/warm/incremental):
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode rosbag2nuscenes \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/small/build/rosbag2nuscenes_benchmark \
  --input-root /home/lepo/git/bagzel_eval/small/2025-04-23_13-56-29_tas \
  --rosbag-output-root /home/lepo/git/bagzel_eval/small/build/rosbag2nuscenes_output \
  --converter /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/rosbag_to_nuscenes.py \
  --param-file /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/nuscenes_param.json \
  --env-file /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/environment.yml \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/small/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```

Medium Dataset
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode rosbag2nuscenes \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/medium/build/rosbag2nuscenes_benchmark \
  --input-root /home/lepo/git/bagzel_eval/medium/2025-04-23_13-56-29_tas \
  --rosbag-output-root /home/lepo/git/bagzel_eval/medium/build/rosbag2nuscenes_output \
  --converter /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/rosbag_to_nuscenes.py \
  --param-file /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/nuscenes_param.json \
  --env-file /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/environment.yml \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/medium/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```

Large Dataset:
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode rosbag2nuscenes \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/large/build/rosbag2nuscenes_benchmark \
  --input-root /home/lepo/git/bagzel_eval/large/2025-04-23_13-56-29_tas \
  --rosbag-output-root /home/lepo/git/bagzel_eval/large/build/rosbag2nuscenes_output \
  --converter /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/rosbag_to_nuscenes.py \
  --param-file /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/nuscenes_param.json \
  --env-file /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/environment.yml \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/large/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```


Run Bazel benchmark (3x cold, 3x warm, 3x incremental):
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/small/build/bagzel \
  --target @eval_data_small//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4"\
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/small/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```
MEDIUM
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/medium/build/bagzel \
  --target @eval_data_medium//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/medium/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"' 
```
LARGE:

```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/large/build/bagzel \
  --target @eval_data_large//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/large/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```


Bazel Build with extended attributes:
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/small/build/bagzel_xattr \
  --target @eval_data_small//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-startup-flag --unix_digest_hash_attribute_name=user.bagzel_hash \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/small/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; cur=$(getfattr --only-values -n user.bagzel_hash "$f" 2>/dev/null || printf "%064d" 0); new=$(printf "%s" "$cur" | sha256sum | awk "{print \$1}"); setfattr -n user.bagzel_hash -v "$new" "$f"'

```

One file Bazel
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/one_file/build/bagzel \
  --target @eval_data_one//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/one_file/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```

One file Xattri:
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/one_file/build/bagzel_xattr \
  --target @eval_data_one//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-startup-flag --unix_digest_hash_attribute_name=user.bagzel_hash \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/one_file/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; cur=$(getfattr --only-values -n user.bagzel_hash "$f" 2>/dev/null || printf "%064d" 0); new=$(printf "%s" "$cur" | sha256sum | awk "{print \$1}"); setfattr -n user.bagzel_hash -v "$new" "$f"'
```


two file Bazel
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/two_files/build/bagzel \
  --target @eval_data_two//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/two_files/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```

two file Xattri:
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/two_files/build/bagzel_xattr \
  --target @eval_data_two//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-startup-flag --unix_digest_hash_attribute_name=user.bagzel_hash \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/two_files/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; cur=$(getfattr --only-values -n user.bagzel_hash "$f" 2>/dev/null || printf "%064d" 0); new=$(printf "%s" "$cur" | sha256sum | awk "{print \$1}"); setfattr -n user.bagzel_hash -v "$new" "$f"'
```


eight files Bazel
```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/eight_files/build/bagzel \
  --target @eval_data_eight//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/eight_files/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'
```

eight files Xattri:
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/eight_files/build/bagzel_xattr \
  --target @eval_data_eight//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-startup-flag --unix_digest_hash_attribute_name=user.bagzel_hash \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/eight_files/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; cur=$(getfattr --only-values -n user.bagzel_hash "$f" 2>/dev/null || printf "%064d" 0); new=$(printf "%s" "$cur" | sha256sum | awk "{print \$1}"); setfattr -n user.bagzel_hash -v "$new" "$f"'
```


Generate bar + scaling figures with matplotlib:
```bash
python /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/figs/plot_build_performance.py \
  --input-csv /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/figs/plot_example_data.csv \
  --output-dir /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/figs \
  --bar-dataset-gb 5 \
  --formats pdf \
  --title-prefix "Bagzel Evaluation"
```


Multi version

```bash

/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/multi_input/build/bagzel \
  --target @eval_data_multi//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/multi_input/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; v=$(sqlite3 "$f" "PRAGMA user_version;"); sqlite3 "$f" "PRAGMA user_version=$((v+1));"'

```

```bash
/home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/run_bazel_build_benchmark.sh \
  --mode bazel \
  --workspace /home/lepo/git/pas-mono-intern \
  --output-dir /home/lepo/git/bagzel_eval/input_granularity/multi_input/build/bagzel_xattr \
  --target @eval_data_multi//:data_pipeline_processed__nuscenes_data \
  --cold-runs 3 \
  --warm-runs 3 \
  --incremental-runs 3 \
  --bazel-startup-flag --unix_digest_hash_attribute_name=user.bagzel_hash \
  --bazel-flag "--jobs=4" \
  --incremental-cmd 'f=/home/lepo/git/bagzel_eval/input_granularity/multi_input/2025-04-23_13-56-29_tas/ros2/ros2bag/ros2bag.db3; cur=$(getfattr --only-values -n user.bagzel_hash "$f" 2>/dev/null || printf "%064d" 0); new=$(printf "%s" "$cur" | sha256sum | awk "{print \$1}"); setfattr -n user.bagzel_hash -v "$new" "$f"'

```


Analyze Bazel Profil

```bash
bazel analyze-profile /data/Bagzel_Evaluation/small/build/bagzel/bazel_benchmark_20260218_140602_metrics/incremental_run_2.profile.json.gz
``


Generate xattri hash:

```bash
bash /home/lepo/git/pas-mono-intern/cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/src/evaluation/create_xatrr_hash.sh /home/lepo/git/bagzel_eval/small/2025-04-23_13-56-29_tas
```

check attribute
```bash
getfattr -n user.bagzel_hash /data/Bagzel_Evaluation/small/2025-04-23_13-56-29_tas/ros1/ros1bag.bag 
```
