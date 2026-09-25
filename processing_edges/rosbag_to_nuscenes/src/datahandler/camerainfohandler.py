# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import numpy as np


def _camera_info_field(msg, upper: str, lower: str):
    if hasattr(msg, upper):
        return getattr(msg, upper)
    if hasattr(msg, lower):
        return getattr(msg, lower)
    raise AttributeError("CameraInfo message is missing both '{}' and '{}'".format(upper, lower))


class CameraInfoHandler:

    def addCameraInfo(self, msg, frame_to_camera_calib_: dict, is_ros2: bool):
        del is_ros2

        if msg.header.frame_id not in frame_to_camera_calib_:
            k = _camera_info_field(msg, "K", "k")
            d = _camera_info_field(msg, "D", "d")
            r = _camera_info_field(msg, "R", "r")
            p = _camera_info_field(msg, "P", "p")

            frame_to_camera_calib_[msg.header.frame_id] = {
                "K": np.array(k).reshape(3, 3),
                "D": np.array(d),
                "R": np.array(r).reshape(3, 3),
                "P": np.array(p).reshape(3, 4),
                "width": msg.width,
                "height": msg.height,
                "distortion_model": msg.distortion_model,
                "x_offset": msg.roi.x_offset,
                "y_offset": msg.roi.y_offset,
                "roi_width": msg.roi.width,
                "roi_height": msg.roi.height,
            }
