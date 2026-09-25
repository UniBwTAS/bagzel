#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import struct
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Quaternion:
    """Quaternion für Orientierung."""
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Vector3:
    """3D Vektor."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Pose:
    """Position und Orientierung."""
    position: Vector3
    orientation: Quaternion


@dataclass
class Twist:
    """Linear- und Winkelgeschwindigkeiten."""
    linear: Vector3
    angular: Vector3


@dataclass
class Odometry:
    """Odometry-Daten."""
    timestamp: float  # Unix timestamp in seconds
    frame_id: str
    child_frame_id: str
    pose: Pose
    pose_covariance: List[float]  # 6x6 flattened
    twist: Twist
    twist_covariance: List[float]  # 6x6 flattened


@dataclass
class Imu:
    """IMU-Daten."""
    timestamp: float  # Unix timestamp in seconds
    frame_id: str
    orientation: Quaternion
    orientation_covariance: List[float]  # 3x3 flattened
    angular_velocity: Vector3
    angular_velocity_covariance: List[float]  # 3x3 flattened
    linear_acceleration: Vector3
    linear_acceleration_covariance: List[float]  # 3x3 flattened


class OxtsHandler:
    """
    Parser für OXTS NCOM-Daten aus Ethernet-Paketen.
    Erstellt Odometry- und IMU-Daten aus den rohen NCOM-Paketen.
    """

    # Konstanten
    NCOM_SYNC = 0xE7
    NCOM_PACKET_LENGTH = 72

    # Skalierungsfaktoren aus ncomrx_c.cpp
    TIME2SEC = 1e-3
    ACC2MPS2 = 1e-4
    RATE2RPS = 1e-5
    VEL2MPS = 1e-4
    ANG2RAD = 1e-6
    DEG2RAD = np.pi / 180.0
    RAD2DEG = 180.0 / np.pi

    # Packet-Indizes
    PI_SYNC = 0
    PI_TIME = 1
    PI_ACCEL_X = 3
    PI_ACCEL_Y = 6
    PI_ACCEL_Z = 9
    PI_ANG_RATE_X = 12
    PI_ANG_RATE_Y = 15
    PI_ANG_RATE_Z = 18
    PI_INS_NAV_MODE = 21
    PI_POS_LAT = 23
    PI_POS_LON = 31
    PI_POS_ALT = 39
    PI_VEL_N = 43
    PI_VEL_E = 46
    PI_VEL_D = 49
    PI_ORIEN_H = 52
    PI_ORIEN_P = 55
    PI_ORIEN_R = 58

    def __init__(self, frame_id: str = "base_link", child_frame_id: str = "base_link"):
        """
        Initialisiert den Parser.

        Args:
            frame_id: Frame-ID für die Nachrichten
            child_frame_id: Child-Frame-ID für Odometry
        """
        self.frame_id = frame_id
        self.child_frame_id = child_frame_id

        # Interne Zustandsvariablen
        self.last_timestamp = None
        self.valid_data = False

        # Daten
        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.vn = 0.0
        self.ve = 0.0
        self.vd = 0.0
        self.heading = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self.ax = 0.0
        self.ay = 0.0
        self.az = 0.0
        self.wx = 0.0
        self.wy = 0.0
        self.wz = 0.0

        # Genauigkeiten (Standardwerte)
        self.pos_acc = 0.1  # m
        self.vel_acc = 0.05  # m/s
        self.ori_acc = 0.01  # rad
        self.acc_acc = 0.01  # m/s^2
        self.rate_acc = 0.000174533  # rad/s (0.01 deg/s)

        # Für Odometry-Berechnung
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0

        # Gravitationsvektor
        self.gravity = 9.81

    def setOxts(self, payload: bytes, timestamp) -> bool:
        """
        Verarbeitet ein Ethernet-Paket mit NCOM-Daten.

        Args:
            payload: Raw bytes des NCOM-Pakets (sollte 72 Bytes sein)
            timestamp: Unix timestamp in Sekunden

        Returns:
            True wenn erfolgreich geparst, False sonst
        """
        # Validierung
        if len(payload) != self.NCOM_PACKET_LENGTH:
            print("invalid length")
            return False

        if payload[self.PI_SYNC] != self.NCOM_SYNC:
            print("invalid sync")
            return False

        # Checksum-Validierung (vereinfacht)
        #if not self._calculate_checksum(payload):
        #    print("invalid checksum")
        #    return False

        self.last_timestamp = timestamp
        #print(self.last_timestamp)

        try:
            # Navigation Mode
            nav_mode = payload[self.PI_INS_NAV_MODE]

            # Beschleunigungen (IMU-Frame)
            ax_raw = self._read_int24(payload, self.PI_ACCEL_X)
            ay_raw = self._read_int24(payload, self.PI_ACCEL_Y)
            az_raw = self._read_int24(payload, self.PI_ACCEL_Z)

            if ax_raw != -8388608:  # INV_INT_24 check
                self.ax = ax_raw * self.ACC2MPS2
            if ay_raw != -8388608:
                self.ay = ay_raw * self.ACC2MPS2
            if az_raw != -8388608:
                self.az = az_raw * self.ACC2MPS2

            # Winkelgeschwindigkeiten
            wx_raw = self._read_int24(payload, self.PI_ANG_RATE_X)
            wy_raw = self._read_int24(payload, self.PI_ANG_RATE_Y)
            wz_raw = self._read_int24(payload, self.PI_ANG_RATE_Z)

            if wx_raw != -8388608:
                self.wx = wx_raw * self.RATE2RPS * self.RAD2DEG
            if wy_raw != -8388608:
                self.wy = wy_raw * self.RATE2RPS * self.RAD2DEG
            if wz_raw != -8388608:
                self.wz = wz_raw * self.RATE2RPS * self.RAD2DEG

            # Position und Orientierung (nur wenn Navigation Mode > 2)
            if nav_mode >= 2:
                self.lat = self._read_double(payload, self.PI_POS_LAT) * self.RAD2DEG
                self.lon = self._read_double(payload, self.PI_POS_LON) * self.RAD2DEG
                self.alt = self._read_float(payload, self.PI_POS_ALT)

                # Geschwindigkeiten (NED)
                vn_raw = self._read_int24(payload, self.PI_VEL_N)
                ve_raw = self._read_int24(payload, self.PI_VEL_E)
                vd_raw = self._read_int24(payload, self.PI_VEL_D)

                if vn_raw != -8388608:
                    self.vn = vn_raw * self.VEL2MPS
                if ve_raw != -8388608:
                    self.ve = ve_raw * self.VEL2MPS
                if vd_raw != -8388608:
                    self.vd = vd_raw * self.VEL2MPS

                # Orientierung
                h_raw = self._read_int24(payload, self.PI_ORIEN_H)
                p_raw = self._read_int24(payload, self.PI_ORIEN_P)
                r_raw = self._read_int24(payload, self.PI_ORIEN_R)

                if h_raw != -8388608:
                    heading_raw = h_raw * self.ANG2RAD * self.RAD2DEG
                    self.heading = heading_raw if heading_raw >= 0 else heading_raw + 360.0

                if p_raw != -8388608:
                    self.pitch = p_raw * self.ANG2RAD * self.RAD2DEG

                if r_raw != -8388608:
                    self.roll = r_raw * self.ANG2RAD * self.RAD2DEG

                # Lokale Koordinaten aktualisieren
                self._update_local_coordinates()

                self.valid_data = True
            else:
                self.valid_data = False

            return True

        except Exception as e:
            print(f"Error parsing NCOM packet: {e}")
            self.valid_data = False
            return False

    def getOdom(self) -> Optional[Odometry]:
        """
        Gibt Odometry-Daten zurück.

        Returns:
            Odometry-Objekt oder None wenn keine gültigen Daten
        """
        if not self.valid_data or self.last_timestamp is None:
            return None

        # Position
        position = Vector3(x=self.x, y=self.y, z=self.z)

        # Orientierung (Quaternion aus RPY)
        # Heading zeigt nach Norden, wir wollen Yaw nach Osten (ENU)
        yaw = (90.0 - self.heading) * self.DEG2RAD
        orientation = self._euler_to_quaternion(
            self.roll * self.DEG2RAD,
            -self.pitch * self.DEG2RAD,  # Pitch negativ für ENU
            yaw
        )

        pose = Pose(position=position, orientation=orientation)

        # Pose Kovarianz (6x6 = 36 Elemente)
        pose_cov = [0.0] * 36
        pose_cov[0] = self.pos_acc ** 2  # x
        pose_cov[7] = self.pos_acc ** 2  # y
        pose_cov[14] = self.pos_acc ** 2  # z
        pose_cov[21] = self.ori_acc ** 2  # roll
        pose_cov[28] = self.ori_acc ** 2  # pitch
        pose_cov[35] = self.ori_acc ** 2  # yaw

        # Geschwindigkeiten
        linear_vel = Vector3(x=self.vx, y=self.vy, z=self.vz)
        angular_vel = Vector3(
            x=self.wx * self.DEG2RAD,
            y=-self.wy * self.DEG2RAD,
            z=-self.wz * self.DEG2RAD
        )

        twist = Twist(linear=linear_vel, angular=angular_vel)

        # Twist Kovarianz (6x6 = 36 Elemente)
        twist_cov = [0.0] * 36
        twist_cov[0] = self.vel_acc ** 2  # vx
        twist_cov[7] = self.vel_acc ** 2  # vy
        twist_cov[14] = self.vel_acc ** 2  # vz
        twist_cov[21] = self.rate_acc ** 2  # wx
        twist_cov[28] = self.rate_acc ** 2  # wy
        twist_cov[35] = self.rate_acc ** 2  # wz

        return Odometry(
            timestamp=self.last_timestamp,
            frame_id="odom",
            child_frame_id=self.child_frame_id,
            pose=pose,
            pose_covariance=pose_cov,
            twist=twist,
            twist_covariance=twist_cov
        )

    def getImu(self) -> Optional[Imu]:
        """
        Gibt IMU-Daten zurück.

        Returns:
            Imu-Objekt oder None wenn kein Timestamp vorhanden
        """
        if self.last_timestamp is None:
            return None

        # Orientierung
        if self.valid_data:
            # Heading nach Norden -> Yaw nach Osten (ENU)
            yaw = (90.0 - self.heading) * self.DEG2RAD
            orientation = self._euler_to_quaternion(
                self.roll * self.DEG2RAD,
                -self.pitch * self.DEG2RAD,
                yaw
            )

            ori_cov = [0.0] * 9
            ori_cov[0] = self.ori_acc ** 2
            ori_cov[4] = self.ori_acc ** 2
            ori_cov[8] = self.ori_acc ** 2
        else:
            # Keine gültige Orientierung
            orientation = Quaternion()
            ori_cov = [-1.0] + [0.0] * 8  # -1 bedeutet keine Orientierung verfügbar

        # Winkelgeschwindigkeiten (Body-Frame)
        angular_velocity = Vector3(
            x=self.wx * self.DEG2RAD,
            y=-self.wy * self.DEG2RAD,  # y-Achse invertiert für ENU
            z=-self.wz * self.DEG2RAD  # z-Achse invertiert für ENU
        )

        ang_vel_cov = [0.0] * 9
        ang_vel_cov[0] = self.rate_acc ** 2
        ang_vel_cov[4] = self.rate_acc ** 2
        ang_vel_cov[8] = self.rate_acc ** 2

        # Beschleunigungen (Body-Frame)
        linear_acceleration = Vector3(
            x=self.ax,
            y=-self.ay,  # y invertiert für ENU
            z=-self.az  # z invertiert für ENU
        )

        lin_acc_cov = [0.0] * 9
        lin_acc_cov[0] = self.acc_acc ** 2
        lin_acc_cov[4] = self.acc_acc ** 2
        lin_acc_cov[8] = self.acc_acc ** 2

        return Imu(
            timestamp=self.last_timestamp,
            frame_id=self.frame_id,
            orientation=orientation,
            orientation_covariance=ori_cov,
            angular_velocity=angular_velocity,
            angular_velocity_covariance=ang_vel_cov,
            linear_acceleration=linear_acceleration,
            linear_acceleration_covariance=lin_acc_cov
        )

    # Hilfsfunktionen

    def _read_int24(self, data: bytes, offset: int) -> int:
        """Liest einen 24-Bit signed Integer (Little Endian)."""
        # 3 Bytes lesen und zu 4 Bytes erweitern
        b0 = data[offset]
        b1 = data[offset + 1]
        b2 = data[offset + 2]

        # Zu 32-bit Integer kombinieren
        value = b0 | (b1 << 8) | (b2 << 16)

        # Sign-Extension für 24-Bit
        if value & 0x800000:
            value |= 0xFF000000
            # Als signed interpretieren
            value = struct.unpack('i', struct.pack('I', value))[0]

        return value

    def _read_double(self, data: bytes, offset: int) -> float:
        """Liest einen 64-Bit Double (Little Endian)."""
        return struct.unpack_from('<d', data, offset)[0]

    def _read_float(self, data: bytes, offset: int) -> float:
        """Liest einen 32-Bit Float (Little Endian)."""
        return struct.unpack_from('<f', data, offset)[0]

    def _calculate_checksum(self, payload: bytes) -> bool:
        """Vereinfachte Checksum-Validierung."""
        # Checksum 3 (Bytes 61-71)
        checksum = 0
        for i in range(61, 71):
            checksum = (checksum + payload[i]) & 0xFF
        return checksum == payload[71]

    def _euler_to_quaternion(self, roll: float, pitch: float, yaw: float) -> Quaternion:
        """Konvertiert Euler-Winkel zu Quaternion."""
        cy = np.cos(yaw * 0.5)
        sy = np.sin(yaw * 0.5)
        cp = np.cos(pitch * 0.5)
        sp = np.sin(pitch * 0.5)
        cr = np.cos(roll * 0.5)
        sr = np.sin(roll * 0.5)

        q = Quaternion()
        q.w = cr * cp * cy + sr * sp * sy
        q.x = sr * cp * cy - cr * sp * sy
        q.y = cr * sp * cy + sr * cp * sy
        q.z = cr * cp * sy - sr * sp * cy

        return q

    def _update_local_coordinates(self):
        """
        Aktualisiert lokale Koordinaten aus Lat/Lon/Alt.
        Vereinfachte Transformation (keine echte UTM).
        """
        # Vereinfachte Projektion: Lat/Lon zu metrischen Koordinaten
        lat_rad = self.lat * self.DEG2RAD
        lon_rad = self.lon * self.DEG2RAD

        R = 6378137.0  # WGS84 Erdradius in Metern

        # Approximation (gut für kleine Bereiche)
        self.x = R * lon_rad * np.cos(lat_rad)
        self.y = R * lat_rad
        self.z = self.alt

        # Geschwindigkeiten von NED zu ENU transformieren
        self.vx = self.ve
        self.vy = self.vn
        self.vz = -self.vd


# Beispiel-Verwendung
if __name__ == "__main__":
    import time

    parser = OxtsParser(frame_id="base_link")

    # Beispiel: Dummy-Paket (in Realität käme dies von einem Ethernet-Socket)
    dummy_payload = bytes([0xE7] + [0] * 71)  # Sync-Byte + 71 weitere Bytes

    timestamp = time.time()

    if parser.setOxts(dummy_payload, timestamp):
        odom = parser.getOdom()
        imu = parser.getImu()

        if odom:
            print(f"Odometry:")
            print(
                f"  Position: x={odom.pose.position.x:.2f}, y={odom.pose.position.y:.2f}, z={odom.pose.position.z:.2f}")
            print(f"  Orientation: w={odom.pose.orientation.w:.3f}, x={odom.pose.orientation.x:.3f}, "
                  f"y={odom.pose.orientation.y:.3f}, z={odom.pose.orientation.z:.3f}")

        if imu:
            print(f"IMU:")
            print(f"  Linear Acc: x={imu.linear_acceleration.x:.2f}, y={imu.linear_acceleration.y:.2f}, "
                  f"z={imu.linear_acceleration.z:.2f}")
            print(f"  Angular Vel: x={imu.angular_velocity.x:.3f}, y={imu.angular_velocity.y:.3f}, "
                  f"z={imu.angular_velocity.z:.3f}")