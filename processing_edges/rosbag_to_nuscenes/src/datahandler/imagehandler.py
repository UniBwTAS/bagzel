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
        self.__rectify_map_cache = {}


    def _normalize_array(self, value, shape=None):
        array = np.array(value, dtype=np.float32)
        if shape is not None:
            array = array.reshape(shape)
        return array

    def _build_rectify_cache_key(self, calibration):
        width = int(calibration.get("width", self.__image.shape[1]))
        height = int(calibration.get("height", self.__image.shape[0]))
        roi_width = int(calibration.get("roi_width", width) or width)
        roi_height = int(calibration.get("roi_height", height) or height)

        k = self._normalize_array(calibration.get("K"), (3, 3))
        d = self._normalize_array(calibration.get("D"))
        r = self._normalize_array(calibration.get("R", np.eye(3)), (3, 3))

        return (
            tuple(np.round(k.flatten(), decimals=8)),
            tuple(np.round(d.flatten(), decimals=8)),
            tuple(np.round(r.flatten(), decimals=8)),
            width,
            height,
            int(calibration.get("x_offset", 0)),
            int(calibration.get("y_offset", 0)),
            roi_width,
            roi_height,
        )

    def _get_rectify_maps(self, calibration):
        cache_key = self._build_rectify_cache_key(calibration)
        cached_maps = self.__rectify_map_cache.get(cache_key)
        if cached_maps is not None:
            return cached_maps

        k = self._normalize_array(calibration.get("K"), (3, 3)).copy()
        d = self._normalize_array(calibration.get("D"))
        r = self._normalize_array(calibration.get("R", np.eye(3)), (3, 3))

        width = int(calibration.get("width", self.__image.shape[1]))
        height = int(calibration.get("height", self.__image.shape[0]))
        image_size = (width, height)

        k[0, 2] -= calibration.get("x_offset", 0)
        k[1, 2] -= calibration.get("y_offset", 0)

        maps = cv2.initUndistortRectifyMap(k, d, r, k, image_size, cv2.CV_32FC1)
        self.__rectify_map_cache[cache_key] = maps
        return maps


    def setImage(self, msg, timestamp):
        self.__image = message_to_cvimage(msg, 'bgr8')
        self.__timestamp = timestamp # msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

    def rectifyImage(self, calibration):
        width = int(calibration.get("width", self.__image.shape[1]))
        height = int(calibration.get("height", self.__image.shape[0]))
        map1, map2 = self._get_rectify_maps(calibration)
        rectified = cv2.remap(self.__image, map1, map2, interpolation=cv2.INTER_LINEAR)

        # Safe ROI cropping: full width and 1000 height from top
        w = int(calibration.get("roi_width", width) or width)
        h = int(calibration.get("roi_height", height) or height)

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
