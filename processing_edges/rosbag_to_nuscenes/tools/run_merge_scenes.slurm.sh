#!/bin/bash
#SBATCH --job-name=nuscenes_merge
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --output=cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/logs/%x_%j.out
#SBATCH --error=cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/logs/%x_%j.err

set -e

# Activate the MS3D conda env so `python` resolves to one with orjson +
# tqdm + nuscenes-devkit. Without this the SLURM job inherits the submit-shell
# PATH, which usually does NOT have conda activated, and the job fails
# immediately with `python: command not found`.
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate MS3D
set -u

echo "Starting data merge..."

python cluster/bagzel/opensource/processing_edges/rosbag_to_nuscenes/tools/merge_scenes.py "$@"

echo "Data merging finished successfully!"
