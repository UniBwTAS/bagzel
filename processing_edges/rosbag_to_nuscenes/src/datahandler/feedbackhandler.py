import numpy as np
import math


def ros_time_to_utime(stamp):
    """Convert ROS timestamp to microseconds"""
    return int(stamp.sec * 1e6 + stamp.nanosec / 1e3)


class FeedbackHandler:
    def __init__(self):
        self.GEAR_MAP = {
            1: 0,  # PARK     → parked
            2: 7,  # REVERSE  → driving
            3: 0,  # NEUTRAL  → parked
            4: 7,  # DRIVE    → driving
            5: 7,  # SPORT    → driving
            6: 7,  # MANUAL   → driving
        }

    def addZoeVehicleInfo(self, msg, out_list: list):
        """
        Convert ROS Feedback to nuScenes zoe_veh_info format.
        Note: Many fields are unavailable in the ROS message and set to defaults.
        """
        wheel_map = {ws.id: ws.speed.mean for ws in msg.wheel_speed}

        entry = {
            "utime": ros_time_to_utime(msg.header.stamp),
            "FL_wheel_speed": wheel_map.get(0, 0.0),
            "FR_wheel_speed": wheel_map.get(1, 0.0),
            "RL_wheel_speed": wheel_map.get(2, 0.0),
            "RR_wheel_speed": wheel_map.get(3, 0.0),
            "left_solar": 0,  # NOT AVAILABLE - default
            "longitudinal_accel": msg.acceleration.mean,
            "meanEffTorque": msg.driving_torque.mean,
            "odom": 0,  # NOT AVAILABLE - default
            "odom_speed": 0.0,  # NOT AVAILABLE - default
            "pedal_cc": 0,  # NOT AVAILABLE - default
            "regen": 0,  # NOT AVAILABLE - default
            "requestedTorqueAfterProc": msg.driving_force_desired.mean,
            "right_solar": 0,  # NOT AVAILABLE - default
            "steer_corrected": 0.0,  # NOT AVAILABLE - default
            "steer_offset_can": 0.0,  # NOT AVAILABLE - default
            "steer_raw": msg.steering_angle_encoder_raw.mean,
            "transversal_accel": 0.0  # NOT AVAILABLE - default
        }

        out_list.append(entry)

    def addZoeSensors(self, msg, out_list: list):
        """Convert ROS Feedback to nuScenes zoesensors format"""
        entry = {
            "utime": ros_time_to_utime(msg.header.stamp),
            "brake_sensor": msg.brake_pedal.mean,
            "steering_sensor": msg.steering_angle_encoder_raw.mean,
            "throttle_sensor": msg.throttle_pedal.mean
        }
        out_list.append(entry)

    def addSteerAngleFeedback(self, msg, out_list: list):
        """Convert ROS Feedback to nuScenes steeranglefeedback format"""
        entry = {
            "utime": ros_time_to_utime(msg.header.stamp),
            "value": msg.onboard_steering_angle.mean
        }
        out_list.append(entry)

    def addVehicleMonitor(self, msg, out_list: list):
        """
        Convert a ROS Feedback message into a nuScenes vehicle_monitor entry
        and append it to out_list.
        """
        # Convert ROS time to microseconds (fixed to use ros_time_to_utime)
        utime = ros_time_to_utime(msg.header.stamp)

        # Compute vehicle_speed (m/s → km/h) - FIXED: unpack tuple
        success, velocity = self.get_mean_velocity(msg)
        vehicle_speed_kmh = velocity * 3.6 if success else 0.0

        # Map lights enum to nuScenes left/right signals
        left_signal, right_signal = self.map_lights(msg.lights)

        # Convert onboard_steering_angle from rad → deg (at 0.1 resolution)
        steering_deg = np.rad2deg(msg.onboard_steering_angle.mean)

        # Get wheel speeds for rear RPM
        wheel_map = {ws.id: ws.speed.mean for ws in msg.wheel_speed}
        rear_left_rpm = wheel_map.get(2, 0.0)  # Assuming id=2 is RL
        rear_right_rpm = wheel_map.get(3, 0.0)  # Assuming id=3 is RR

        # Derive brake_switch from brake pressure
        brake_switch = 2 if msg.brake_pressure.mean > 0.5 else 1

        # Build entry
        entry = {
            "utime": utime,
            "available_distance": 100,  # NOT AVAILABLE - default
            "battery_level": 100,  # NOT AVAILABLE - default
            "brake": msg.brake_pressure.mean,
            "brake_switch": brake_switch,
            "gear_position": self.GEAR_MAP.get(msg.gear_position, 0),
            "left_signal": left_signal,
            "rear_left_rpm": rear_left_rpm,
            "rear_right_rpm": rear_right_rpm,
            "right_signal": right_signal,
            "steering": steering_deg,
            "steering_speed": 0.0,  # NOT AVAILABLE - default to 0
            "throttle": msg.throttle_pedal.mean,
            "vehicle_speed": vehicle_speed_kmh,
            "yaw_rate": np.rad2deg(msg.onboard_yaw_rate_esp.mean),
        }

        out_list.append(entry)

    def get_mean_velocity(self, feedback):
        """
        Compute mean velocity from wheel speeds.
        Returns (success: bool, velocity: float)
        """
        summed_velocity = 0.0
        num_wheel_speeds = 0

        for ws in feedback.wheel_speed:
            v = ws.speed.mean

            # Accept only finite numeric values
            if v is None or not math.isfinite(v):
                continue

            summed_velocity += v
            num_wheel_speeds += 1

        # No valid wheel speeds
        if num_wheel_speeds == 0:
            return False, 0.0

        return True, summed_velocity / num_wheel_speeds

    def map_lights(self, lights_enum: int):
        """
        Convert ROS lights enum to nuScenes left/right signals.
        Returns (left_signal, right_signal)
        """
        left_signal = 0
        right_signal = 0

        if lights_enum == 8:  # BLINKER_LEFT
            left_signal = 1
        elif lights_enum == 9:  # BLINKER_RIGHT
            right_signal = 1
        elif lights_enum == 11:  # BLINKER_WARNING
            left_signal = 1
            right_signal = 1

        return left_signal, right_signal