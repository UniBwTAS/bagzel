# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import numpy as np
from scipy.spatial.transform import Rotation


class TFHandler:
    def __from_transform_to_matrix(self, transform):
        translation = transform.translation
        rotation = transform.rotation

        matrix = np.eye(4)
        matrix[:3, 3] = [translation.x, translation.y, translation.z]

        rot = Rotation.from_quat([rotation.x, rotation.y, rotation.z, rotation.w])
        matrix[:3, :3] = rot.as_matrix()

        return matrix

    def __from_matrix_to_transform(self, matrix):
        translation = [matrix[0, 3], matrix[1, 3], matrix[2, 3]]

        rot = Rotation.from_matrix(matrix[:3, :3])
        quaternion = rot.as_quat()
        quaternion = [quaternion[3], quaternion[0], quaternion[1], quaternion[2]]

        return translation, quaternion

    def traverseTransforms(self, transformation, transforms, frame_id):
        for transform in transforms:
            if transform.child_frame_id == frame_id:
                current_transform = self.__from_transform_to_matrix(transform.transform)
                tf_matrix = current_transform @ transformation
                return self.traverseTransforms(tf_matrix, transforms, transform.header.frame_id)

        return transformation, frame_id

    def addTF(self, msg, x_to_baselink: dict):

        # Use a set for fast membership checks and uniqueness
        last_frames = set()

        for transform in msg.transforms:
            last_frames.add(transform.header.frame_id)
            last_frames.add(transform.child_frame_id)

        for frame in last_frames:
            resulting_frame = self.traverseTransforms(np.identity(4), msg.transforms, frame)
            t, r = self.__from_matrix_to_transform(resulting_frame[0])

            if frame in x_to_baselink:
                print("Warning: Frame", frame, "already exists in x_to_baselink. Overwriting with new transformation.")

            x_to_baselink[frame] = {"translation": t, "rotation": r}
