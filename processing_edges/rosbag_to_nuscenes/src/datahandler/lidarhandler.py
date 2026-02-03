# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import velodyne_decoder as vd
import numpy as np


class LidarHandler:
    def __init__(self):
        self.__pointcloud = np.ndarray(shape=(0, 4), dtype=np.float32)  # Initialize with an empty array
        self.__start_stamp = None
        self.__cut_angle = 180
        self.__start_angle = None
        self.__decoder = vd.ScanDecoder()
        self.__config = vd.Config()
        self.__config.cut_angle = self.__cut_angle
        self.__frame_id = None


        self.__stream_decoder = vd.StreamDecoder(self.__config)


    def addPacket(self, msg, timestamp):

        self.__frame_id = msg.header.frame_id
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9 ## sec + nanosec
        self.__pointcloud  = self.__stream_decoder.decode(stamp, msg.payload, as_pcl_structs=True)
        if(self.__pointcloud is not None):
#            print(self.__pointcloud[0].device)
            self.__start_stamp = timestamp #self.__pointcloud[0].host
            self.__pointcloud = self.__pointcloud[1]

    #returns [timestamp, pointcloud] or None if rotation not finished
    def getPointCloud(self):
        return self.__pointcloud

    def getTimestamp(self):
        return self.__start_stamp

    def getFrameId(self):
        return self.__frame_id

#

    """
    def visualize(self):

        # points = np.vstack(points)
        # points_np = np.array(points, dtype=np.float32)

        # print(points_np)
        # pcd = o3d.geometry.PointCloud()
        # pcd.points = o3d.utility.Vector3dVector(points_np)
        # o3d.visualization.draw_geometries([pcd])

        points = self.__pointcloud
        pcd = np.zeros((points.shape[0], 4), dtype=np.float32)
        pcd[:, 0] = points['x']
        pcd[:, 1] = points['y']
        pcd[:, 2] = points['z']
        pcd[:, 3] = points['intensity']
        import open3d as o3d
        point_cloud = o3d.geometry.PointCloud()
        point_cloud.points = o3d.utility.Vector3dVector(pcd[:, :3])
        o3d.visualization.draw_geometries([point_cloud], window_name="Lidar Point Cloud", width=800, height=600)
    """

    def write(self, filename):

        expected_dtype = np.dtype([('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('intensity', 'f4')])
        data = self.__pointcloud[['x', 'y', 'z', 'intensity']].astype(expected_dtype)

        num_points = data.shape[0]
        point_bytes = data.tobytes()
        padding = b'\x00' * 4

        with open(filename, 'wb') as f:
            for i in range(num_points):
                start = i * 16
                f.write(point_bytes[start:start + 16])
                f.write(padding)
