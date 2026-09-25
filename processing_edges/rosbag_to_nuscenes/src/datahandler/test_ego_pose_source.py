#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Anton Backhaus <anton.backhaus@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ego_pose_source (pure interpolation core)."""
import math

import numpy as np
from scipy.spatial.transform import Rotation

from ego_pose_source import PoseSeries, coverage


def _yaw_quat_wxyz(yaw):
    q = Rotation.from_euler("z", yaw).as_quat()  # xyzw
    return [q[3], q[0], q[1], q[2]]


def test_midpoint_translation_is_exact_lerp():
    s = PoseSeries([0, 10], [[0.0, 0.0, 0.0], [10.0, -20.0, 4.0]],
                   [_yaw_quat_wxyz(0.0), _yaw_quat_wxyz(0.0)])
    xyz, _, bracketed = s.sample(5)
    assert bracketed
    assert np.allclose(xyz, [5.0, -10.0, 2.0], atol=1e-12)


def test_quaternion_slerp_midpoint():
    # 0 -> 90 deg yaw, midpoint must be 45 deg
    s = PoseSeries([0, 100], [[0, 0, 0], [0, 0, 0]],
                   [_yaw_quat_wxyz(0.0), _yaw_quat_wxyz(math.pi / 2)])
    _, q, _ = s.sample(50)
    yaw = Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_euler("xyz")[2]
    assert abs(yaw - math.pi / 4) < 1e-9


def test_exact_sample_hits_node():
    s = PoseSeries([0, 10, 20], [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
                   [_yaw_quat_wxyz(0.0)] * 3)
    xyz, _, bracketed = s.sample(10)
    assert bracketed
    assert np.allclose(xyz, [1, 1, 1])


def test_edge_hold_flags_unbracketed():
    s = PoseSeries([100, 200], [[1, 1, 1], [2, 2, 2]],
                   [_yaw_quat_wxyz(0.0)] * 2)
    xyz, _, bracketed = s.sample(50)   # before span
    assert not bracketed
    assert np.allclose(xyz, [1, 1, 1])
    xyz2, _, bracketed2 = s.sample(300)  # after span
    assert not bracketed2
    assert np.allclose(xyz2, [2, 2, 2])


def test_float64_precision_preserved_on_utm_scale():
    # UTM-scale coordinates must interpolate without float32-style precision loss.
    e0, n0 = 5_300_000.0, 690_000.0
    s = PoseSeries([0, 1000], [[e0, n0, 300.0], [e0 + 30.0, n0 + 40.0, 300.5]],
                   [_yaw_quat_wxyz(0.0)] * 2)
    xyz, _, _ = s.sample(500)
    assert abs(xyz[0] - (e0 + 15.0)) < 1e-6
    assert abs(xyz[1] - (n0 + 20.0)) < 1e-6


def test_unsorted_input_is_sorted():
    s = PoseSeries([20, 0, 10], [[2, 2, 2], [0, 0, 0], [1, 1, 1]],
                   [_yaw_quat_wxyz(0.0)] * 3)
    xyz, _, _ = s.sample(5)
    assert np.allclose(xyz, [0.5, 0.5, 0.5])


def test_coverage():
    src = [100, 110, 120, 130, 140]
    assert coverage(src, [105, 115, 125]) == 1.0
    assert coverage(src, [90, 105, 200]) == 1.0 / 3.0
    assert coverage([], [1, 2]) == 0.0
    assert coverage(src, []) == 0.0


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
