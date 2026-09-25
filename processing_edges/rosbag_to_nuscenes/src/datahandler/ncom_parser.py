#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Anton Backhaus <anton.backhaus@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0
"""Rich NCOM (OxTS structure-A, 72-byte) decoder.

Decodes the raw /bus/oxts/eth_ncom/bus_to_host ethernet_msgs/Packet payload,
including the rotating status channels (RTK pos mode, accuracy, sats, DOP,
diff-age, GPS time). Offsets/scales ported from io_oxts NComRxC. All float64.

Angles returned in radians, lat/lon in degrees (to match oxts_msgs/InsData).
"""
import struct
import math

RAD2DEG = 180.0 / math.pi
ACC2MPS2 = 1e-4
RATE2RPS = 1e-5
VEL2MPS = 1e-4
ANG2RAD = 1e-6
TIME2SEC = 1e-3
POSA2M = 1e-3
VELA2MPS = 1e-3
DIFFAGE2SEC = 1e-2
DOPFACTOR = 0.1
GPS_EPOCH_IN_UNIX_S = 315964800          # 1980-01-06 in unix seconds
NCOM_COUNT_TOO_OLD = 150
INV_INT24 = -8388608

# packet indices (fixed part)
PI_SYNC = 0
PI_TIME = 1
PI_ACCEL = 3
PI_RATE = 12
PI_NAV = 21
PI_LAT = 23
PI_LON = 31
PI_ALT = 39
PI_VEL = 43
PI_HEADING = 52
PI_PITCH = 55
PI_ROLL = 58
PI_CHAN = 62
PI_CHAN_PAYLOAD = 63


def _i24(b, o):
    v = b[o] | (b[o+1] << 8) | (b[o+2] << 16)
    if v & 0x800000:
        v -= 0x1000000
    return v


def _f64(b, o):
    return struct.unpack_from("<d", b, o)[0]


def _f32(b, o):
    return struct.unpack_from("<f", b, o)[0]


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


class NComDecoder:
    """Stateful: feed packets in time order; status-channel values persist."""

    def __init__(self):
        # channel-derived state (persist across packets)
        self.gps_pos_mode = None
        self.gps_vel_mode = None
        self.gps_att_mode = None
        self.num_sats = None
        self.acc_pos = [None, None, None]   # north, east, alt (m)
        self.diff_age = None                # s
        self.hdop = None
        self.pdop = None
        self.minutes = None                 # full minutes since GPS epoch (ch0, resync)
        self.utc_offset = -18               # GPS->UTC leap (18s for all >=2017 data); ch16 overrides
        self._abs_min = None                # running absolute minute (wrap-tracked)
        self._prev_ms = None                # previous ms-into-minute (for wrap detect)
        self.n_out_of_range = 0             # packets rejected for insane lat/lon (corruption)
        self.n_checksum_fail = 0            # packets failing NCOM checksum (malformed)
        self.n_null_island = 0             # packets with (0,0) position (no valid fix)
        self.n_bad_attitude = 0            # packets with INV_INT_24 / out-of-range roll/pitch

    def _decode_channel(self, b):
        ch = b[PI_CHAN]
        s = PI_CHAN_PAYLOAD  # payload byte index base; s+k == packet byte 63+k
        if ch == 0:
            self.minutes = struct.unpack_from("<i", b, s + 0)[0]
            if not (b[s + 4] & 0x80):
                self.num_sats = b[s + 4]
            if not (b[s + 5] & 0x80):
                self.gps_pos_mode = b[s + 5]
            if not (b[s + 6] & 0x80):
                self.gps_vel_mode = b[s + 6]
            if not (b[s + 7] & 0x80):
                self.gps_att_mode = b[s + 7]
        elif ch == 3:
            if b[s + 6] < NCOM_COUNT_TOO_OLD:
                self.acc_pos = [_u16(b, s + 0) * POSA2M,
                                _u16(b, s + 2) * POSA2M,
                                _u16(b, s + 4) * POSA2M]
        elif ch == 20:
            self.diff_age = _i16(b, s + 0) * DIFFAGE2SEC
        elif ch == 48:
            if b[s + 2] != 0xFF:
                self.hdop = b[s + 2] * DOPFACTOR
            if b[s + 3] != 0xFF:
                self.pdop = b[s + 3] * DOPFACTOR
        elif ch == 16:
            v = b[s + 7]
            if v & 0x01:
                self.utc_offset = (struct.unpack("b", bytes([v]))[0]) >> 1

    def _gps_time_ns(self, ms_sec, is_ch0):
        # Running absolute-minute counter: seed/resync from ch0's mMinutes, and
        # bump on the ms-into-minute wrap between ch0 packets. Packets arrive in
        # time order at ~100 Hz, so a wrap is a large drop in ms.
        if self.minutes is None:
            return None
        if self._abs_min is None:
            self._abs_min = self.minutes
        elif self._prev_ms is not None and ms_sec < self._prev_ms - 1.0:
            self._abs_min += 1
        if is_ch0:
            self._abs_min = self.minutes
        self._prev_ms = ms_sec
        t_sec = self._abs_min * 60.0 + ms_sec
        return int(t_sec * 1e9) + GPS_EPOCH_IN_UNIX_S * 1_000_000_000 + self.utc_offset * 1_000_000_000

    def feed(self, payload, bag_ts_ns):
        b = payload if isinstance(payload, (bytes, bytearray)) else bytes(payload)
        if len(b) != 72 or b[PI_SYNC] != 0xE7:
            return None
        # NCOM checksums are cumulative running sums from byte 1 (verified empirically
        # against known-good packets). Rejects malformed/corrupt packets.
        if ((sum(b[1:22]) & 0xFF) != b[22]
                or (sum(b[1:61]) & 0xFF) != b[61]
                or (sum(b[1:71]) & 0xFF) != b[71]):
            self.n_checksum_fail += 1
            return None
        nav = b[PI_NAV]
        # update rotating status channel first (time/minute lives here)
        self._decode_channel(b)
        ms_sec = _u16(b, PI_TIME) * TIME2SEC
        gps_time_ns = self._gps_time_ns(ms_sec, b[PI_CHAN] == 0)   # every packet: keep counter synced
        if nav < 2:   # NAVIGATION_STATUS_INIT: pose not valid
            return None
        lat = _f64(b, PI_LAT) * RAD2DEG
        lon = _f64(b, PI_LON) * RAD2DEG
        # (0,0) null-island = "no valid position" placeholder (well-formed packet)
        if abs(lat) < 1e-9 and abs(lon) < 1e-9:
            self.n_null_island += 1
            return None
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            self.n_out_of_range += 1
            return None
        alt = _f32(b, PI_ALT)
        # attitude: honor the OxTS INV_INT_24 "not available" sentinel + physical bound
        h_i, p_i, r_i = _i24(b, PI_HEADING), _i24(b, PI_PITCH), _i24(b, PI_ROLL)
        if INV_INT24 in (h_i, p_i, r_i):
            self.n_bad_attitude += 1
            return None
        heading = h_i * ANG2RAD   # rad (raw body yaw)
        pitch = p_i * ANG2RAD
        roll = r_i * ANG2RAD
        if abs(roll) > math.pi / 2 or abs(pitch) > math.pi / 2:  # impossible for a vehicle
            self.n_bad_attitude += 1
            return None
        vn = _i24(b, PI_VEL + 0) * VEL2MPS
        ve = _i24(b, PI_VEL + 3) * VEL2MPS
        vd = _i24(b, PI_VEL + 6) * VEL2MPS
        return dict(
            bag_ts_ns=int(bag_ts_ns),
            gps_time_ns=gps_time_ns,
            lat=lat, lon=lon, alt=alt,
            roll=roll, pitch=pitch, heading=heading,
            vn=vn, ve=ve, vd=vd,
            nav_mode=nav,
            gps_pos_mode=self.gps_pos_mode, gps_vel_mode=self.gps_vel_mode,
            gps_att_mode=self.gps_att_mode, num_sats=self.num_sats,
            acc_pos=list(self.acc_pos), diff_age=self.diff_age,
            hdop=self.hdop, pdop=self.pdop,
        )
