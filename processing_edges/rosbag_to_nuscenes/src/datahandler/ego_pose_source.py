#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Anton Backhaus <anton.backhaus@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0
"""Pose-source interpolation for sensor-timestamp-driven ego_poses.

The converter mints one ego_pose per sample_data at its exact (bag-receive-clock)
timestamp, with the pose value interpolated from a source stream:

  * OxTS/RTK  (preferred) -- dense ~100 Hz absolute-UTM poses (from ncom_parser +
    ego_pose_global.build_record), or
  * vehicle odometry (fallback) -- ~48 Hz local poses.

Both are far denser than the sensor frames they serve (~10-20 Hz lidar, ~9 Hz cam),
so linear position interpolation + quaternion slerp between the two bracketing source
samples is near-exact (~10-20 ms bracket).

This module is pure (no I/O): the datum file, the per-recording OxTS-vs-odom decision,
and its persistence live in the converter. Everything here operates on integer-ns
timelines and float64 poses. Quaternions are nuScenes order ``[w, x, y, z]``.
"""
from __future__ import annotations

import bisect
from typing import List, Sequence, Tuple

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def _wxyz_to_xyzw(q: Sequence[float]) -> List[float]:
    w, x, y, z = q
    return [x, y, z, w]


def _xyzw_to_wxyz(q: Sequence[float]) -> List[float]:
    x, y, z, w = q
    return [w, x, y, z]


class PoseSeries:
    """Time-ordered pose stream that samples by interpolation.

    Parameters
    ----------
    ts_ns : increasing integer nanosecond timestamps (bag-receive clock).
    translations : (N, 3) float64 -- absolute (UTM for OxTS) or local (odom).
    rotations_wxyz : (N, 4) float64 quaternions in ``[w, x, y, z]`` order.
    """

    def __init__(self, ts_ns: Sequence[int], translations, rotations_wxyz):
        ts = np.asarray(ts_ns, dtype=np.int64)
        xyz = np.asarray(translations, dtype=np.float64)
        quat_wxyz = np.asarray(rotations_wxyz, dtype=np.float64)
        if not (len(ts) == len(xyz) == len(quat_wxyz)):
            raise ValueError("ts, translations, rotations must be the same length")
        if len(ts) == 0:
            raise ValueError("PoseSeries needs at least one sample")
        if np.any(np.diff(ts) < 0):
            order = np.argsort(ts, kind="stable")
            ts, xyz, quat_wxyz = ts[order], xyz[order], quat_wxyz[order]
        self.ts = ts
        self.xyz = xyz
        # store as scipy Rotation (xyzw) for slerp
        self._rot = Rotation.from_quat(quat_wxyz[:, [1, 2, 3, 0]])
        self._ts_list = ts.tolist()

    def __len__(self) -> int:
        return len(self.ts)

    @property
    def t_first(self) -> int:
        return int(self.ts[0])

    @property
    def t_last(self) -> int:
        return int(self.ts[-1])

    def _bracket(self, t: int) -> Tuple[int, int, bool]:
        """Return (i0, i1, bracketed). If t is outside [t_first, t_last] the nearest
        endpoint index is returned in both slots and bracketed is False."""
        if t <= self.ts[0]:
            return 0, 0, t == self.ts[0]
        if t >= self.ts[-1]:
            n = len(self.ts) - 1
            return n, n, t == self.ts[-1]
        hi = bisect.bisect_left(self._ts_list, t)
        if self.ts[hi] == t:
            return hi, hi, True
        return hi - 1, hi, True

    def sample(self, t_ns: int) -> Tuple[List[float], List[float], bool]:
        """Interpolate the pose at t_ns.

        Returns (translation[3], rotation_wxyz[4], bracketed). When t is outside the
        series span, the nearest endpoint pose is held and bracketed is False (the
        caller must count/log this -- never a silent fallback to the other source).
        """
        t = int(t_ns)
        i0, i1, bracketed = self._bracket(t)
        if i0 == i1:
            xyz = self.xyz[i0]
            q_xyzw = self._rot[i0].as_quat()
            return xyz.tolist(), _xyzw_to_wxyz(q_xyzw), bracketed

        t0, t1 = int(self.ts[i0]), int(self.ts[i1])
        frac = (t - t0) / (t1 - t0)
        xyz = self.xyz[i0] + frac * (self.xyz[i1] - self.xyz[i0])
        slerp = Slerp([t0, t1], self._rot[[i0, i1]])
        q_xyzw = slerp([t]).as_quat()[0]
        return xyz.tolist(), _xyzw_to_wxyz(q_xyzw), True


def coverage(source_ts_ns: Sequence[int], sample_ts_ns: Sequence[int]) -> float:
    """Fraction of sample timestamps that fall inside the source span [first, last].

    Used for the per-recording OxTS-vs-odom decision: a recording uses OxTS only if
    (nearly) all of its sensor frames can be interpolated from the OxTS stream.
    """
    if len(sample_ts_ns) == 0:
        return 0.0
    if len(source_ts_ns) == 0:
        return 0.0
    lo, hi = int(min(source_ts_ns)), int(max(source_ts_ns))
    inside = sum(1 for t in sample_ts_ns if lo <= int(t) <= hi)
    return inside / len(sample_ts_ns)
