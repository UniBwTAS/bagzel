# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import numpy as np



class CameraInfoHandler:

    def addCameraInfo(self, msg, frame_to_camera_calib_: dict, is_ros2: bool):
        if msg.header.frame_id not in frame_to_camera_calib_:


            frame_to_camera_calib_[msg.header.frame_id] = {
                'K': np.array(msg.K).reshape(3, 3),
                'D': np.array(msg.D),
                'R': np.array(msg.R).reshape(3, 3),
                'P': np.array(msg.P).reshape(3, 4),
                'width': msg.width,
                'height': msg.height,
                'distortion_model': msg.distortion_model,
                "x_offset": msg.roi.x_offset,
                "y_offset": msg.roi.y_offset,
                "roi_width": msg.roi.width,
                "roi_height": msg.roi.height
            }

