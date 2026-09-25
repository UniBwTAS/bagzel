import numpy as np
from typing import List, Dict, Any


class MetaGenerator:
    """Generate nuScenes-style meta statistics for CAN bus messages"""

    def __init__(self):
        pass

    def compute_meta(
            self,
            ms_imu_json: List[Dict],
            pose_json: List[Dict],
            steeranglefeedback_json: List[Dict],
            vehicle_monitor_json: List[Dict],
            zoe_veh_info_json: List[Dict],
            zoesensors_json: List[Dict]
    ) -> Dict[str, Any]:
        """
        Compute meta statistics for all CAN message types.

        Returns a dictionary matching the nuScenes meta.json format with:
        - message_count: number of messages
        - message_freq: frequency in Hz
        - timespan: duration in seconds
        - var_stats: statistics for each variable
        """
        meta = {}

        if ms_imu_json:
            meta["MS_IMU"] = self._compute_message_stats(
                ms_imu_json,
                ["linear_accel", "q", "rotation_rate", "utime"]
            )

        if pose_json:
            meta["POSE"] = self._compute_message_stats(
                pose_json,
                ["accel", "orientation", "pos", "rotation_rate", "utime", "vel"]
            )

        if steeranglefeedback_json:
            meta["SteerAngleFeedback"] = self._compute_message_stats(
                steeranglefeedback_json,
                ["utime", "value"]
            )

        if vehicle_monitor_json:
            meta["VEHICLE_MONITOR"] = self._compute_message_stats(
                vehicle_monitor_json,
                ["available_distance", "battery_level", "brake", "brake_switch",
                 "gear_position", "left_signal", "rear_left_rpm", "rear_right_rpm",
                 "right_signal", "steering", "steering_speed", "throttle",
                 "utime", "vehicle_speed", "yaw_rate"]
            )

        if zoe_veh_info_json:
            meta["ZOE_VEH_INFO"] = self._compute_message_stats(
                zoe_veh_info_json,
                ["FL_wheel_speed", "FR_wheel_speed", "RL_wheel_speed", "RR_wheel_speed",
                 "left_solar", "longitudinal_accel", "meanEffTorque", "odom",
                 "odom_speed", "pedal_cc", "regen", "requestedTorqueAfterProc",
                 "right_solar", "steer_corrected", "steer_offset_can", "steer_raw",
                 "transversal_accel", "utime"]
            )

        if zoesensors_json:
            meta["ZoeSensors"] = self._compute_message_stats(
                zoesensors_json,
                ["brake_sensor", "steering_sensor", "throttle_sensor", "utime"]
            )

        return meta

    def _compute_message_stats(
            self,
            messages: List[Dict],
            fields: List[str]
    ) -> Dict[str, Any]:
        """
        Compute statistics for a single message type.

        Args:
            messages: List of message dictionaries
            fields: List of field names to compute stats for

        Returns:
            Dictionary with message_count, message_freq, timespan, and var_stats
        """
        if not messages:
            return {}

        message_count = len(messages)

        # Extract timestamps to compute timespan and frequency
        utimes = [msg["utime"] for msg in messages]
        timespan_us = utimes[-1] - utimes[0]
        timespan_s = timespan_us / 1e6

        # Compute message frequency
        message_freq = (message_count - 1) / timespan_s if timespan_s > 0 else 0

        # Compute variable statistics
        var_stats = {}
        for field in fields:
            var_stats[field] = self._compute_field_stats(messages, field)

        return {
            "message_count": message_count,
            "message_freq": message_freq,
            "timespan": timespan_s,
            "var_stats": var_stats
        }

    def _compute_field_stats(
            self,
            messages: List[Dict],
            field: str
    ) -> Dict[str, float]:
        """
        Compute statistics for a single field across all messages.

        For array fields (like linear_accel, pos, vel), computes stats on the norm.
        For scalar fields, computes stats on the value directly.

        Returns:
            Dictionary with max, max_diff, mean, mean_diff, min, min_diff, std, std_diff
        """
        # Extract values
        values = []
        for msg in messages:
            val = msg.get(field)
            if val is None:
                continue

            # Handle list/array fields by computing norm
            if isinstance(val, (list, tuple)):
                val = np.linalg.norm(val)

            values.append(float(val))

        if not values:
            return {
                "max": 0.0, "max_diff": 0.0,
                "mean": 0.0, "mean_diff": 0.0,
                "min": 0.0, "min_diff": 0.0,
                "std": 0.0, "std_diff": 0.0
            }

        values = np.array(values)

        # Compute differences between consecutive values
        diffs = np.diff(values)

        # Compute statistics
        stats = {
            "max": float(np.max(values)),
            "mean": float(np.mean(values)),
            "min": float(np.min(values)),
            "std": float(np.std(values))
        }

        if len(diffs) > 0:
            stats["max_diff"] = float(np.max(diffs))
            stats["mean_diff"] = float(np.mean(diffs))
            stats["min_diff"] = float(np.min(diffs))
            stats["std_diff"] = float(np.std(diffs))
        else:
            stats["max_diff"] = 0.0
            stats["mean_diff"] = 0.0
            stats["min_diff"] = 0.0
            stats["std_diff"] = 0.0

        return stats