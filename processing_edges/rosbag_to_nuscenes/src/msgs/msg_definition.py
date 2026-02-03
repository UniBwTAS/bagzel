# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

ETHERNET_MSG_PACKET = """
Header header
uint8[4] sender_ip
uint16 sender_port
uint8[4] receiver_ip
uint16 receiver_port
uint8[] payload
"""

ETHERNET_MSG_PACKETS = """
Packet[] packets
"""

# std_msgs/Header.msg
STD_MSG_HEADER = """
uint32 seq
time stamp
string frame_id
"""

# geometry_msgs/Point.msg
GEOMETRY_MSG_POINT = """
float64 x
float64 y
float64 z
"""

# geometry_msgs/Quaternion.msg
GEOMETRY_MSG_QUATERNION = """
float64 x
float64 y
float64 z
float64 w
"""

# geometry_msgs/Pose.msg
GEOMETRY_MSG_POSE = """
geometry_msgs/Point position
geometry_msgs/Quaternion orientation
"""

# geometry_msgs/PoseWithCovariance.msg
GEOMETRY_MSG_POSE_WITH_COVARIANCE = """
geometry_msgs/Pose pose
float64[36] covariance
"""

# geometry_msgs/Vector3.msg
GEOMETRY_MSG_VECTOR3 = """
float64 x
float64 y
float64 z
"""

# geometry_msgs/Twist.msg
GEOMETRY_MSG_TWIST = """
geometry_msgs/Vector3 linear
geometry_msgs/Vector3 angular
"""

# geometry_msgs/TwistWithCovariance.msg
GEOMETRY_MSG_TWIST_WITH_COVARIANCE = """
geometry_msgs/Twist twist
float64[36] covariance
"""

# nav_msgs/Odometry.msg
NAV_MSG_ODOMETRY = """
std_msgs/Header header
string child_frame_id
geometry_msgs/PoseWithCovariance pose
geometry_msgs/TwistWithCovariance twist
"""

SENSOR_MSG_CAMERA_INFO_ADAPTED = """
std_msgs/Header header
uint32 height
uint32 width
string distortion_model
float64[] D
float64[9] K
float64[9] R
float64[12] P
uint32 binning_x
uint32 binning_y
sensor_msgs/RegionOfInterest roi
"""
