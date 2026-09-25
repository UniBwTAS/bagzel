#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Anton Backhaus <anton.backhaus@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0
"""Build an ego_pose_global.json record from a decoded NCOM sample.

Applies the io_oxts conventions validated against 2026 InsData / gps_odom:
  translation = [utm_e, utm_n, alt(geoid/NN)]        (pyproj EPSG:326zz, exact)
  rotation    = quat from (roll, -pitch, yaw), "xyz" intrinsic   (== io_oxts odom)
  heading     = wrap(pi/2 - ncom_heading)            (ins_pose.heading convention)
  yaw         = heading + UTM grid convergence
All float64. utm_zone from standard UTM rule (matches io_oxts for this fleet).
"""
import math
from pyproj import Transformer, Proj
from scipy.spatial.transform import Rotation

_tf = {}
_pj = {}


def utm_zone(lat, lon):
    return int((lon + 180.0) / 6.0) + 1


def _transformer(z):
    if z not in _tf:
        _tf[z] = Transformer.from_crs("EPSG:4326", f"EPSG:326{z:02d}", always_xy=True)
    return _tf[z]


def _projector(z):
    if z not in _pj:
        _pj[z] = Proj(proj="utm", zone=z, ellps="WGS84")
    return _pj[z]


def build_record(token, r, timestamp_us):
    """token: ego_pose token; r: NComDecoder.feed() dict; timestamp_us: paired ego_pose ts."""
    lat, lon, alt = r["lat"], r["lon"], r["alt"]
    z = utm_zone(lat, lon)
    e, n = _transformer(z).transform(lon, lat)
    conv = math.radians(_projector(z).get_factors(lon, lat).meridian_convergence)
    heading = (math.pi / 2.0) - r["heading"]
    heading = (heading + math.pi) % (2 * math.pi) - math.pi
    yaw = heading + conv
    roll = r["roll"]
    pitch = -r["pitch"]                       # InsData.pitch = -ncom_pitch
    q = Rotation.from_euler("xyz", [roll, pitch, yaw]).as_quat()   # xyzw, float64
    return {
        "token": token,
        "translation": [float(e), float(n), float(alt)],
        "rotation": [float(q[3]), float(q[0]), float(q[1]), float(q[2])],
        "timestamp": int(timestamp_us),
        "lat": float(lat), "lon": float(lon), "alt": float(alt),
        "roll": float(roll), "pitch": float(pitch), "yaw": float(yaw), "heading": float(heading),
        "utm_zone": int(z),
        "fix_status": r["gps_pos_mode"], "num_sats": r["num_sats"],
        "hdop": r["hdop"], "diff_age_s": r["diff_age"],
        "pos_std_m": r["acc_pos"], "gps_time_ns": r["gps_time_ns"],
    }
