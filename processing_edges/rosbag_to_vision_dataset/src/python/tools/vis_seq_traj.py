# SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import sys
import json
import os
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # needed for 3D plotting
import numpy as np

if len(sys.argv) != 3:
    print("Usage: vis_seq_traj.py <sequences.json> <output_dir>")
    sys.exit(1)

json_path = sys.argv[1]
output_dir = sys.argv[2]

os.makedirs(output_dir, exist_ok=True)

with open(json_path, "r") as f:
    sequences = json.load(f)

for idx, seq in enumerate(sequences):
    traj = seq.get("trajectory", [])

    if not traj:
        print(f"⚠️ Sequence {idx} has no trajectory.")
        continue

    try:
        x = [p["x"] for p in traj]
        y = [p["y"] for p in traj]
        z = [p["z"] for p in traj]
    except KeyError:
        print(f"❌ Invalid trajectory format in sequence {idx}")
        continue

    x = np.array(x)
    y = np.array(y)
    z = np.array(z)

    x -= x[0]
    y -= y[0]
    z -= z[0]

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot(x, y, z, marker='o', label=f'Sequence {idx}')
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.set_zlabel("Z [m]")
    ax.set_title(f"3D Trajectory {idx}")
    ax.legend()

    output_path = os.path.join(output_dir, f"sequence_{idx:03d}_traj3d.png")
    plt.savefig(output_path)
    plt.close()
    print(f"✅ Saved: {output_path}")
