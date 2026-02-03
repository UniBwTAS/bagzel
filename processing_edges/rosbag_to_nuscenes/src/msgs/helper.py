# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

from rosbags.typesys import get_types_from_msg, get_typestore, Stores
from msgs.msg_definition import *


def get_full_typestore():
    # Register all messages
    typestore = get_typestore(Stores.LATEST)

    typestore.register(get_types_from_msg(GEOMETRY_MSG_POINT, 'geometry_msgs/msg/Point'))
    typestore.register(get_types_from_msg(GEOMETRY_MSG_QUATERNION, 'geometry_msgs/msg/Quaternion'))
    typestore.register(get_types_from_msg(GEOMETRY_MSG_POSE, 'geometry_msgs/msg/Pose'))
    typestore.register(get_types_from_msg(GEOMETRY_MSG_POSE_WITH_COVARIANCE, 'geometry_msgs/msg/PoseWithCovariance'))
    typestore.register(get_types_from_msg(GEOMETRY_MSG_VECTOR3, 'geometry_msgs/msg/Vector3'))
    typestore.register(get_types_from_msg(GEOMETRY_MSG_TWIST, 'geometry_msgs/msg/Twist'))
    typestore.register(get_types_from_msg(GEOMETRY_MSG_TWIST_WITH_COVARIANCE, 'geometry_msgs/msg/TwistWithCovariance'))
    typestore.register(get_types_from_msg(NAV_MSG_ODOMETRY, 'nav_msgs/msg/Odometry'))
    # Register your custom message type
    typestore.register(get_types_from_msg(ETHERNET_MSG_PACKET, 'ethernet_msgs/msg/Packet'))
    typestore.register(get_types_from_msg(SENSOR_MSG_CAMERA_INFO_ADAPTED, "sensor_msgs/msg/CameraInfo"))

    return typestore
