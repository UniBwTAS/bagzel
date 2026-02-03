# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

from rosbags.image import message_to_cvimage

import numpy as np
import cv2

class ImageHandler:
    def __init__(self):
        self.__image = None
        self.__camera_info = None

        self.__timestamp = None
        self.__rectified_image = None



    def setImage(self, msg, timestamp):
        self.__image = message_to_cvimage(msg, 'bgr8')
        self.__timestamp = timestamp # msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

    def rectifyImage(self, calibration):
        K = np.array(calibration.get("K"), dtype=np.float32).copy()  # Intrinsics
        D = np.array(calibration.get("D"), dtype=np.float32)  # Distortion coeffs
        R = np.array(calibration.get("R", np.eye(3)), dtype=np.float32)
        #K = np.array(calibration.get("K"), dtype=np.float32).copy()
        K[0, 2] -= calibration.get("x_offset", 0)  # adjust cx
        K[1, 2] -= calibration.get("y_offset", 0)  # adjust cy
        # Use actual image size if not provided
        width = calibration.get("width", self.__image.shape[1])
        height = calibration.get("height", self.__image.shape[0])
        image_size = (width, height)

        map1, map2 = cv2.initUndistortRectifyMap(K, D, R, K, image_size, cv2.CV_32FC1)
        rectified = cv2.remap(self.__image, map1, map2, interpolation=cv2.INTER_LINEAR)

        # Safe ROI cropping: full width and 1000 height from top
        x, y, w, h = calibration.get("x_offset", 0), calibration.get("y_offset", 0), calibration.get("roi_width", width), calibration.get("roi_height", height)

        rectified = rectified[0:h, 0:w]

        self.__rectified_image = rectified

    def write(self, filename):
        return cv2.imwrite(filename, self.__rectified_image)

    def getImage(self):
        return self.__image
    def getTimestamp(self):
        return self.__timestamp
    def getWidth(self):
        return self.__rectified_image.shape[1]
    def getHeight(self):
        return self.__rectified_image.shape[0]
    def getRectifiedImage(self):
        return self.__rectified_image