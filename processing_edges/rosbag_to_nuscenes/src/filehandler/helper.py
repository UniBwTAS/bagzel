# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

from enum import Enum

class SensorType(Enum):
    CAMERA = 0
    LIDAR = 1
    RADAR = 2

class MetaInfos:
    def __init__(self):
        self.vehicle = ""
        self.map = ""
        self.description = ""
        self.odom_topic = ""

class SampleHelper:
    def __init__(self):
        self.previous_sample_token = ""
        self.current_sample_token = ""
        self.next_sample_token = ""
        self.previous_sampled_timestamp = 0


class SensorInfos:
    def __init__(self):
        self.type = SensorType.CAMERA
        self.sensor_name: str = ""
        self.frame_id: str = ""
        self.topic_name: str = ""
        self.radar_id: str = ""
        self.token: str = ""

    def setType(self, sensor_string):
        lower_string = sensor_string.lower()
        if "lidar" in lower_string:
            self.type = SensorType.LIDAR
        if "radar" in lower_string:
            self.type = SensorType.RADAR
        if "cam" in lower_string:
            self.type = SensorType.CAMERA

def modalityToString(SensorType):
    if SensorType == SensorType.LIDAR:
        return "lidar"
    elif SensorType == SensorType.RADAR:
        return "radar"
    elif SensorType == SensorType.CAMERA:
        return "camera"