#!/bin/bash

# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

#SBATCH --job-name=rosbag_pipeline
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gres=gpu:A100:0
#SBATCH --cpus-per-task=256
#SBATCH --output=./logs/%x-%j/%N.out
#SBATCH --error=./logs/%x-%j/%N.err
#SBATCH --chdir=/home/lepo/git/Vista/data/rosbag_extractor

set -x -e

# # Activate the Conda environment if needed
# echo "Activating Conda environment..."
# source ~/miniconda3/etc/profile.d/conda.sh
# conda activate vista || { echo "Failed to activate Conda environment"; exit 1; }

echo "START TIME: $(date)"

bazel build //data:rosbags_sub1_all

echo "END TIME: $(date)"
