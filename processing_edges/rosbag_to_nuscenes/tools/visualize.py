# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

from nuscenes.nuscenes import NuScenes
from nuscenes.utils.data_classes import RadarPointCloud
import numpy as np
#nusc = NuScenes(version='v1.0-mini', dataroot='/home/lube/playground/2023-02-23-13-37-10_20', verbose=True)
#nusc = NuScenes(version='v1.0-mini', dataroot='tas_nuscenes_merged', verbose=True)
nusc =  NuScenes(version='v1.0-mini', dataroot='/home/lube/git/pas2/pas-mono-intern/cluster/data-pipeline/processing-edges/rosbag_to_nuscenes/output_test/2024-02-12-12-31-06_0/v1.0-mini', verbose=True)

print("Initialized NuScenes dataset")
nusc.list_scenes()
print("Load specific scene")
my_scene = nusc.scene[0]
print(my_scene)
first_sample_token = my_scene['last_sample_token']
my_sample = nusc.get('sample', first_sample_token)

nusc.render_pointcloud_in_image(my_sample['token'], pointsensor_channel='LIDAR_TOP', camera_channel='CAM_FRONT')
nusc.render_pointcloud_in_image(my_sample['token'], pointsensor_channel='LIDAR_TOP', camera_channel='CAM_BACK')
nusc.render_pointcloud_in_image(my_sample['token'], pointsensor_channel='LIDAR_TOP', camera_channel='CAM_RIGHT')
nusc.render_pointcloud_in_image(my_sample['token'], pointsensor_channel='LIDAR_TOP', camera_channel='CAM_LEFT')

nusc.render_sample_data(my_sample['data']['LIDAR_TOP'], nsweeps=5, underlay_map=False, with_anns=False)
exit(0)


RadarPointCloud.disable_filters()
nusc.render_sample_data(my_sample['data']['LIDAR_TOP'], nsweeps=1, underlay_map=False, with_anns=False)
nusc.render_sample_data(my_sample['data']['RADAR_FRONT'], nsweeps=1, underlay_map=False, with_anns=False)
exit()
nusc.render_sample_data(my_sample['data']['RADAR_FRONT_LEFT'], nsweeps=1, underlay_map=False, with_anns=False)

nusc.render_sample_data(my_sample['data']['RADAR_FRONT_FAR'], nsweeps=1, underlay_map=False, with_anns=False)
import matplotlib.pyplot as plt

radars = ['RADAR_FRONT', 'RADAR_FRONT_LEFT', 'RADAR_FRONT_RIGHT', 'RADAR_BACK_LEFT', 'RADAR_BACK_RIGHT']

# Start with an empty list to collect all radar pointclouds
all_pc = []

# Loop through each radar channel
for radar in radars:
    radar_token = my_sample['data'][radar]
    radar_pc = RadarPointCloud.from_file(nusc.get_sample_data_path(radar_token)).points
    all_pc.append(radar_pc)

# Stack all radar point clouds horizontally (shape: 18 x N)
combined_pc = np.hstack(all_pc)
print(combined_pc)

# Plot X vs Y (vehicle-centric top-down view)
plt.figure(figsize=(8, 8))
plt.scatter(combined_pc[0, :], combined_pc[1, :], s=1)
plt.xlabel('X (m)')
plt.ylabel('Y (m)')
plt.title('All RADAR PointClouds (Vehicle Frame)')
plt.axis('equal')
plt.grid(True)
plt.show()


