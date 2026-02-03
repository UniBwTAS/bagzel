# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import os
import random

import numpy as np
import json

try:
    import yaml  # optional for backward compatibility
except ImportError:
    yaml = None

import logging
from pathlib import Path

from itertools import chain


from filehandler.helper import SensorInfos
from filehandler.helper import modalityToString
from filehandler.helper import MetaInfos
from filehandler.helper import SensorType

from rosbags.highlevel import AnyReader

from datahandler.imagehandler import ImageHandler
from datahandler.lidarhandler import LidarHandler
from datahandler.odometryhandler import OdomHandler
from datahandler.tfhandler import TFHandler
from datahandler.camerainfohandler import CameraInfoHandler
import cv2

def load_param_file(path: Path) -> dict:
    suffix = path.suffix.lower()

    if suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if suffix in (".yml", ".yaml"):
        if yaml is None:
            raise RuntimeError("Param file is YAML but PyYAML is not installed.")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Fallback: try JSON then YAML (useful if extension is odd)
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        if yaml is None:
            raise
        return yaml.safe_load(txt)


class Bag2Scenes:
    def __init__(self):
        # Default constructor, equivalent to C++ Bag2Scenes::Bag2Scenes()
        self.param_yaml_: dict = {}
        self.bag_ = None  # rosbag.Bag object


        self.frame_info_: dict[str, dict] = {}
        self.topic_to_frame_: dict[str, str] = {}
        self.frame_to_transform_: dict[str, np.matrix] = {}
        self.frame_to_camera_calib_: dict[str, dict] = {}

        self.previous_sample_token_: str = ""
        self.next_sample_token_: str = ""
        self.previous_sampled_timestamp_ = 0.0
        self.nbr_samples_: int = 0
        self.sensors_sampled_ = []
        self.sensors_sampled_valid_ = []
        self.all_valid_samples_dry_run_ = []
        self.output_dir_: Path = Path()
        self.vehicle_name_: str = ""


        self.scene_token_: str = ""
        self.save_file_extension_: str = "mini"  # Derived from C++
        self.current_sample_token_: str = ""
        self.first_sample_token_: str = ""
        self.samples_ = []  # To store samples data for JSON output
        self.sample_data_ = []
        self.sensors_ = []
        self.written_calibrated_sensors_ = set()
        self.bag_metas_ = MetaInfos()

        self.log_token_: str = ""
        self.v1_0_mini_dir_: Path = Path()

        self.bag_reader_: AnyReader = None
        self.is_ros2_: bool = False
        self.bag_name_: str = ""
        self.bag_name_split_extension_: str = ""
        self.ego_pose_list: list[tuple[int, str]] = []  # List of tuples (timestamp, token) for ego poses

        self.tokens_: list = []
        self.created_dirs_ = set()

    @staticmethod
    def generateToken_static() -> str:
        """Generates a 32-character hex token."""
        first_char = random.choice('0123456789bcdef')  # excludes 'a'
        rest = ''.join(random.choice('0123456789abcdef') for _ in range(31))
        return first_char + rest

    def generateToken(self) -> str:
        """Instance method for consistency if needed, calls static method."""
        token =  self.generateToken_static()
        self.tokens_.append(token)
        return token

    def writeTokenFile(self):
        """write a file which contains all tokens used for this conversion, makes is easier to merge different bags."""
        token_file_path = self.output_dir_ / "tokens.txt"

        # Assume `strings` is a very long list of strings
        with open(token_file_path, "w") as file:
            file.write("\n".join(self.tokens_) + "\n")

    def init(self, rosbag_name, rosbag_name_split_extension_, param_file: Path, output_dir: Path, bag_reader: AnyReader, start_time, end_time):
        # srand(time(0)) or srand(start_time.sec)
        # Python's random module is automatically seeded if not explicitly done,
        # but for reproducibility based on start_time, we can seed it.
        random.seed(start_time)
        self.bag_name_ = rosbag_name
        self.bag_name_split_extension_ = rosbag_name_split_extension_
        self.bag_reader_ = bag_reader
        self.is_ros2_ = bag_reader.is2



        # Read Parameter File
        try:
            with open(param_file, 'r') as f:
                self.param_yaml_ = yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Error reading {param_file}: {e}")
            exit(1)







        # Determine relevant topics from param_yaml_ before iterating for counts
        #convert to class SensorInfo (better readability
        configured_topics = []
        for sensor_name, sensor_data in self.param_yaml_.get("SENSOR_INFO", {}).items():
            sensor = SensorInfos()
            sensor.radar_id = sensor_data.get("RADAR_ID")
            sensor.sensor_name = sensor_name
            sensor.topic_name =  sensor_data.get("TOPIC")
            sensor.frame_id = sensor_data.get("FRAME")
            sensor.token = sensor_data.get("TOKEN")
            sensor.setType(sensor_name)
            self.sensors_.append(sensor)

        self.bag_metas_.odom_topic =  self.param_yaml_.get("BAG_INFO").get("ODOM_TOPIC")
        self.bag_metas_.map =  self.param_yaml_.get("BAG_INFO").get("TRACK")
        self.bag_metas_.team =  self.param_yaml_.get("BAG_INFO").get("VEHICLE")
        self.bag_metas_.description =  self.param_yaml_.get("BAG_INFO").get("DESCRIPTION")

        # Process SENSO
        for sensor in self.sensors_:

            self.frame_info_[sensor.frame_id] = {
                "previous_timestamp": 0,
                "current_token": "",
                "previous_token": "",
                "next_token": self.generateToken(),
                "name": sensor.sensor_name,
                "sensor_token": sensor.token,
                "calibrated_sensor_token": self.generateToken(),
                "modality": modalityToString(sensor.type),
                "topic": sensor.topic_name,
            }
            self.topic_to_frame_[sensor.topic_name] = sensor.frame_id

        self.previous_sample_token_ = ""
        self.next_sample_token_ = self.generateToken()
        self.first_sample_token_ = self.next_sample_token_
        self.nbr_samples_ = 0
        self.start_time_ = start_time
        self.end_time_ = end_time


        self.previous_sampled_timestamp_ = self.start_time_
        self.previous_sampled_timestamp_dry_run_ = self.start_time_
        self.valid_samples_timestamp = self.start_time_

        self.output_dir_ = output_dir
        self.v1_0_mini_dir_ = self.output_dir_ / "v1.0-mini"



#TODO! Instead of a parameter file, better write a meta-file of rosbag, similar to bagzel.
    #contains: Possible Sensor-data (write everything available), ...
    #TODO: different lidars (ouster?) radar, ...?
    #make extraction more readable
    def getAllInfos(self):
        return 0

    def getTransformations(self):
        #get all extrinsic transformation
        tf_handler = TFHandler()

        tf_connections = [x for x in self.bag_reader_.connections if "tf_static" in x.topic]
        # len of connections:
        #tf_statics are only published in the beginning (normally)
        #thats why we read the full bag here, not only the given extraction of 20 seconds
        for connection, timestamp, rawdata in self.bag_reader_.messages(connections=tf_connections):
            msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)
            tf_handler.addTF(msg, self.frame_to_transform_)


        #get all intrinsic camera calibrations
        camerinfo_handler = CameraInfoHandler()

        caminfo_connections = [x for x in self.bag_reader_.connections if "/camera_info" in x.topic]

        for connection, timestamp, rawdata in self.bag_reader_.messages(connections=caminfo_connections, start=self.start_time_,
                                                                        stop=self.end_time_):
            msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)

            camerinfo_handler.addCameraInfo(msg, self.frame_to_camera_calib_, self.is_ros2_)



    def writeEgoPoses(self):
        ego_poses = self._load_json(self.v1_0_mini_dir_ / "ego_pose.json")
        self.addEgoPoses(ego_poses)  # This method will append to ego_poses and ego_poses_offsets
        self._save_json(ego_poses, self.v1_0_mini_dir_ / "ego_pose.json")



    def convertCalibrationToNuscenes(self, calibration_data):
        k_matrix = calibration_data.get("K")

        #add offset to K matrix
        k_matrix[0][2] -= calibration_data.get("x_offset", 0)
        k_matrix[1][2] -= calibration_data.get("y_offset", 0)
        #convert to list
        k_matrix = k_matrix.tolist()
        return k_matrix


    def writeCalibratedSensors(self, frame_id: str, camera_intrinsics=[]) -> str:

        #this writes the sensor, if not exists yet, and returns the sensor token.
        sensor_token = self.writeSensor(frame_id)

        output_dir = self.output_dir_
        calibrated_sensor_json_path = output_dir / "v1.0-mini/calibrated_sensor.json"
        calibrate_sensors = self._load_json(calibrated_sensor_json_path)

        new_calibrated_sensors = {
        "token": self.frame_info_[frame_id]["calibrated_sensor_token"],
        "sensor_token": sensor_token,
        "translation": self.frame_to_transform_[frame_id]["translation"],
        "rotation": self.frame_to_transform_[frame_id]["rotation"],
        "camera_intrinsic": camera_intrinsics
        }
        calibrate_sensors.append(new_calibrated_sensors)
        self._save_json(calibrate_sensors, calibrated_sensor_json_path)


    def writeSensor(self, frame_id: str) -> str:
        output_dir = self.output_dir_
        sensor_json_path = output_dir / "v1.0-mini/sensor.json"
        name = self.frame_info_[frame_id]["name"]
        modality = self.frame_info_[frame_id]["modality"]
        sensor_token = self.frame_info_[frame_id]["sensor_token"]

        sensors = self._load_json(sensor_json_path)

        # Check if a sensor already exists for this channel
        for sensor in sensors:
            if sensor.get("channel") == name:
                return sensor.get("token")

        # If not found, create a new sensor entry

        new_sensor = {
            "token": sensor_token,
            "channel": name,
            "modality": modality
        }
        # Append and save
        sensors.append(new_sensor)
        self._save_json(sensors, sensor_json_path)

        return sensor_token


    def writeSensorData(self):
        self.sample_data_ = self._load_json(self.v1_0_mini_dir_ / "sample_data.json")
        self.samples_ = self._load_json(self.v1_0_mini_dir_ / "sample.json")

        self.writeSampleData()  # This method will append to sample_data and self.samples_

        #delete last sample data next token
        if self.sample_data_:
            #get list of current sample from frame_info_
            current_sample_tokens = {info["current_token"] for info in self.frame_info_.values()}
            #iterate backwards through sample_data_ and remove entries which are not in current_sample_tokens
            #for frame_id, info in self.frame_info_.items():
            for data in reversed(self.sample_data_):
                if data["token"] in current_sample_tokens:
                    #remove from current_sample_tokens, so we do not need to check it again
                    current_sample_tokens.remove(data["token"])
                    print("From ", data["token"], " removed " , data["next"])
                    data["next"] = ""  # The very last sample_data in the entire collection


                if len(current_sample_tokens) == 0:
                    break


        # Save all updated JSON files
        self._save_json(self.sample_data_, self.v1_0_mini_dir_ / "sample_data.json")



        # Update last sample token and save samples_
        if self.samples_:
            self.samples_[-1]["next"] = ""  # The very last sample in the entire collection
        self._save_json(self.samples_, self.v1_0_mini_dir_ / "sample.json")


    # a scene consists of severel parts. Write Log, write, map, etc. then write data. and finally, write scene.
    # scene must be written in the end, because it has the start and end tokens.

    def writeSceneFile(self):
        scenes = self._load_json(self.v1_0_mini_dir_ / "scene.json")


        # Update scene metadata and save
        scene_entry = {
            "token": self.scene_token_,
            "log_token": self.log_token_,
            "first_sample_token": self.first_sample_token_,  # This should be the first sample token of THIS scene
            "nbr_samples": self.nbr_samples_,  # Number of samples in THIS scene
            "last_sample_token": self.current_sample_token_,  # Last sample token of THIS scene
            "name": self.bag_name_split_extension_,
            #"name": f"{self.bag_dir_.stem}_{self.save_file_extension_}",
            "description": self.bag_metas_.description
        }


        scenes.append(scene_entry)
        self._save_json(scenes, self.v1_0_mini_dir_ / "scene.json")


    def writeScene(self):
        self.scene_token_ = self.generateToken()

        #writes log and stores log_token
        self.writeLog()

        self.getTransformations()

        # Write odometry data
        self.writeEgoPoses()

        # Write sensor data
        self.writeSensorData()

        #write final scene file
        self.writeSceneFile()

        #write Taxonomy
        self.writeTaxonomyFiles()

        self.writeTokenFile()


    def _load_json(self, file_path: Path):
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logging.warning(f"Error decoding JSON from {file_path}: {e}. Write File.")
                return []

        #logging.warning(f"File does not exist: {file_path}:  Write File.")

        return []

    def _save_json(self, data, file_path: Path):
        dir_path = os.path.dirname(file_path)
        if dir_path not in self.created_dirs_:
            os.makedirs(dir_path, exist_ok=True)
            self.created_dirs_.add(dir_path)

        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            logging.error(f"Error writing JSON to {file_path}: {e}")

    def writeLog(self):
        self.log_token_ = self.generateToken()
        log_file_path = self.output_dir_ / "v1.0-mini" / "log.json"
        logs = self._load_json(log_file_path)

        new_log = {
            "token": self.log_token_,
            "logfile": self.bag_name_split_extension_,#TODO
            "vehicle": self.bag_metas_.vehicle,
            "date_captured": self.bag_name_, #TODO,
            "location": "boston-seaport" #self.bag_name_  # TODO
        }
        logs.append(new_log)
        self._save_json(logs, log_file_path)
        self.writeMap(self.log_token_)

    def writeMap(self, log_token: str):
        map_file_path = self.output_dir_ / "v1.0-mini" / "map.json"
        maps = self._load_json(map_file_path)

        track_category = self.bag_metas_.map

        for _map in maps:
            if _map.get("category") == track_category:
                if log_token not in _map.get("log_tokens", []):  # Avoid duplicates
                    _map.get("log_tokens", []).append(log_token)  # Ensure log_tokens is a list
                self._save_json(maps, map_file_path)
                return

        new_map = {
            "token": self.generateToken(),
            "log_tokens": [log_token],
            "category": track_category,
            "filename": ""#self.bag_name_ + "/dummyentry/map.bin" #dummy! how will it be with gridmap?
        }
        maps.append(new_map)
        self._save_json(maps, map_file_path)

    def writeTaxonomyFiles(self):

        # Category
        category_file = self.v1_0_mini_dir_ / "category.json"
        if not category_file.exists():
            category_token = self.generateToken()
            categories = [{
                "token": category_token,
                "name": "default_category",  # Placeholder
                "description": "Default category for generated data"
            }]
            self._save_json(categories, category_file)
        else:
            categories = self._load_json(category_file)
            category_token = categories[0][
                "token"] if categories else self.generateToken()  # Use existing or generate new

        # Attribute
        attribute_file = self.v1_0_mini_dir_ / "attribute.json"
        if not attribute_file.exists():
            attribute_token = self.generateToken()
            attributes = [{
                "token": attribute_token,
                "name": "default_attribute",  # Placeholder
                "description": "Default attribute for generated data"
            }]
            self._save_json(attributes, attribute_file)
        else:
            attributes = self._load_json(attribute_file)
            attribute_token = attributes[0]["token"] if attributes else self.generateToken()

        # Visibility
        visibility_file = self.v1_0_mini_dir_ / "visibility.json"
        if not visibility_file.exists():
            visibility_token = "1"  # C++ hardcodes "1"
            visibilities = [{
                "token": visibility_token,
                "description": "Default visibility level",
                "level": "0-20"  # Placeholder, C++ leaves empty
            }]
            self._save_json(visibilities, visibility_file)
        else:
            visibilities = self._load_json(visibility_file)
            visibility_token = visibilities[0]["token"] if visibilities else "1"

        # Instance
        instance_file = self.v1_0_mini_dir_ / "instance.json"
        # The C++ code creates an instance with a direct link to a (potentially not yet created) annotation.
        # This is a bit unusual. Usually, annotations link to instances.
        # For this re-write, we'll ensure an instance exists for the default annotation.
        if not instance_file.exists():
            instance_token = self.generateToken()
            instances = [{
                "token": instance_token,
                "category_token": category_token,
                "nbr_annotations": 0,
                "first_annotation_token": "",  # Will be filled by annotation
                "last_annotation_token": ""  # Will be filled by annotation
            }]
            self._save_json(instances, instance_file)
        else:
            instances = self._load_json(instance_file)
            instance_token = instances[0]["token"] if instances else self.generateToken()

        # Sample Annotation
        annotation_file = self.v1_0_mini_dir_ / "sample_annotation.json"
        if not annotation_file.exists():
            annotation_token = self.generateToken()
            annotations = [{
                "token": annotation_token,
                "sample_token": self.current_sample_token_ if self.current_sample_token_ else self.generateToken(),
                # Ensure a sample token exists
                "instance_token": instance_token,
                "visibility_token": visibility_token,
                "attribute_tokens": [attribute_token],
                "translation": [0.0, 0.0, 0.0],
                "size": [0.0, 0.0, 0.0],
                "rotation": [1.0, 0.0, 0.0, 0.0],
                "prev": "",
                "next": "",
                "num_lidar_pts": 0,
                "num_radar_pts": 0
            }]
            annotations = []
            self._save_json(annotations, annotation_file)

            # Update the instance with the first annotation token
            if instances:
                if not instances[0]["first_annotation_token"]:
                    instances[0]["first_annotation_token"] = annotation_token
                instances[0]["last_annotation_token"] = annotation_token
                instances[0]["nbr_annotations"] += 1
                self._save_json(instances, instance_file)



    def addEgoPoses(self, ego_poses):
        odom_topic = self.bag_metas_.odom_topic

        connections = [x for x in self.bag_reader_.connections if x.topic == odom_topic]
        #len of connections:
        #get number of odometry messages

        odom_handler = OdomHandler()
        for connection, timestamp, rawdata in self.bag_reader_.messages(connections=connections, start=self.start_time_, stop=self.end_time_):
            msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)
            odom_handler.setOdom(msg, timestamp)
            self.addEgoPose(odom_handler.getOdomPosition(), odom_handler.getOdomQuaternion(),odom_handler.getOdomStamp(), ego_poses)



    def addEgoPose(self, translation, rotation, stamp, ego_poses):

        pose_token = self.generateToken()
        ego_poses.append({
            "token": pose_token,
            "translation": translation,
            "rotation": rotation,
            "timestamp": int(stamp // 1000)
        })
        self.ego_pose_list.append((int(stamp), pose_token))

    from typing import List, Tuple

    def select_equidistant_scenes(self,
            scenes: List[List[Tuple[str, int]]],
            n: int = 39
    ) -> List[List[Tuple[str, int]]]:
        """
        Select exactly `n` unique scenes that are as evenly spaced in time as possible.

        Args:
            scenes: List of scenes, each a list of (frame_id, timestamp_ns).
            n: Number of scenes to select.
        Returns:
            List of selected scenes, sorted by minimal timestamp.
        """
        if not scenes:
            return []
        if n >= len(scenes):
            # If we don't have enough scenes, just return all sorted by time
            return sorted(scenes, key=lambda s: min(ts for _, ts in s))

        # Compute minimal timestamps and sort scenes by time
        min_stamps = [min(ts for _, ts in s) for s in scenes]
        sorted_scenes = [sc for _, sc in sorted(zip(min_stamps, scenes), key=lambda x: x[0])]

        # Choose N indices spaced evenly across the sorted list
        # np.linspace gives fractional positions; we round to nearest index
        indices = np.linspace(0, len(sorted_scenes) - 1, n, dtype=int)


        # Pick unique scenes using these indices
        chosen = [sorted_scenes[i] for i in np.unique(indices)]
        return chosen


    def validTimestamps(self, header_stamp, timestamp):
        diff = header_stamp - timestamp
        return abs(diff) < 1e8

    def writeSampleData(self):
        # get all camera topics from sensors (TODO: automatically detect camera topics from bag_reader_)
        camera_topics = [sensor.topic_name for sensor in self.sensors_ if sensor.type == SensorType.CAMERA]
        lidar_topics = [sensor.topic_name for sensor in self.sensors_ if sensor.type == SensorType.LIDAR]

        # Initialize ImageHandler with the type store.
        image_handler = ImageHandler()
        lidar_handler = LidarHandler()
        # filter topics

        camera_images = []
        lidar_pointclouds = []
        previous_timestamp = None


        ## from message to image/pointcloud
        #just use camera or lidar topics
        connections = [x for x in self.bag_reader_.connections if x.topic in camera_topics or x.topic in lidar_topics]

        for connection, timestamp, rawdata in self.bag_reader_.messages(connections=connections, start=self.start_time_, stop=self.end_time_):

            msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)
            frame_id = self.topic_to_frame_[connection.topic]

            ##check timestamp. Sometimes they are corrupted
            header_stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            header_stamp = int(header_stamp * 1e9)  # convert to nanoseconds
            if previous_timestamp is not None:
                diff_to_previous = previous_timestamp - header_stamp
                assert abs(diff_to_previous) < 2e8, "[INVALID SENSOR DATA] Non-monotonic timestamps detected, aborting."
            previous_timestamp = header_stamp


            if connection.topic in camera_topics:
                image_handler.setImage(msg, timestamp)
                image_handler.rectifyImage(self.frame_to_camera_calib_[frame_id])
                camera_images.append([connection.topic, header_stamp, image_handler.getRectifiedImage()])

            elif connection.topic in lidar_topics:
                lidar_handler.addPacket(msg, header_stamp)
                pointcloud = lidar_handler.getPointCloud()

                if pointcloud is None:
                    continue

                lidar_pointclouds.append([connection.topic, header_stamp, pointcloud])

        # sort all sensor data by timestamp
        all_sensor_data = camera_images + lidar_pointclouds
        all_sensor_data.sort(key=lambda x: x[1])


        # DRY RUN: determine valid frames (if a sensor is missing, it might break the logic
        # therefore: use all frames, in which all sensors are available
        for topic, timestamp, rawdata in all_sensor_data:
            frame = self.topic_to_frame_[topic]
            self.get_valid_scenes(frame, timestamp, (topic in lidar_topics)) #LiDAR is the trigger

        #select 40 equidistant frames for the samples
        resulting_samples = self.select_equidistant_scenes(self.all_valid_samples_dry_run_,40)
        #get the min timestamp of each scene, because thats the "start" of a sample.
        #its still iteratively looping through the data, thats why its needed
        min_pairs = {min(s, key=lambda x: x[1]) for s in resulting_samples}
        keyframes = set(chain.from_iterable(resulting_samples))
        initial_keyframe_set = False

        for topic, timestamp, data in all_sensor_data:
            # Check if the topic is a camera topic
            frame_id = self.topic_to_frame_[topic]

            isKeyframe = (self.topic_to_frame_[topic], timestamp) in keyframes
            isFirstKeyframe = (self.topic_to_frame_[topic], timestamp) in min_pairs

            if isFirstKeyframe or initial_keyframe_set:
                self.handleData(frame_id, timestamp, data, isKeyframe, isFirstKeyframe)
                initial_keyframe_set = True


    #only get scenes, which have all sensors available
    #here: the LiDAR is the trigger, it comes LAST.
    #If another sensor should be the trigger, it may need to be changed
    def get_valid_scenes(self, frame_id, timestamp, trigger_sensor = True):

        time_diff = (int(timestamp) - self.valid_samples_timestamp)
        if trigger_sensor:
            ###NEW KEYFRAME
            # check if len of sensor_sampled is equal to sensors_
            # if not: its invalid, and we do not need it
            self.sensors_sampled_valid_.append((frame_id, timestamp))
            self.valid_samples_timestamp = timestamp

            # only valid if all data is there
            if len(self.sensors_) == len(self.sensors_sampled_valid_):
                self.all_valid_samples_dry_run_.append(self.sensors_sampled_valid_.copy())

            self.sensors_sampled_valid_.clear()

            return True

        elif (frame_id not in [frame for frame, _ in self.sensors_sampled_valid_]) and (
                abs(time_diff) < (1e8)  # 0.1 seconds in nanoseconds
        ):
            self.sensors_sampled_valid_.append((frame_id, timestamp))
            return True

        return False


    def image_write(self, filename, image):
        cv2.imwrite(filename, image)


    def pointcloud_write(self, filename, pointcloud_data):
            # 20 bytes/point
            expected_dtype = np.dtype([('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('intensity', 'f4'), ('column', 'u2'), ('ring', 'u1'), ('return_type', 'u1')])
            data = pointcloud_data[['x', 'y', 'z', 'intensity', 'column', 'ring', 'return_type']].astype(expected_dtype)

            num_points = data.shape[0]
            point_bytes = data.tobytes()

            with open(filename, 'wb') as f:
                for i in range(num_points):
                    start = i * 20
                    f.write(point_bytes[start:start + 20])


    #"Handling" means: apply NuScenes Logic, write files, and write JSON entries

    def handleData(self, frame_id: str, timestamp: int, data, isKeyframe: bool, isFirstKeyframe: bool):
        file_extension = ""
        writer = None
        width = 0
        height = 0
        intrinsic = []

        if self.frame_info_[frame_id]["modality"] == "camera":
            file_extension = ".jpg"
            writer = self.image_write
            width = data.shape[1]
            height = data.shape[0]
            calibration = self.frame_to_camera_calib_.get(frame_id, {})
            intrinsic = self.convertCalibrationToNuscenes(calibration)

        elif self.frame_info_[frame_id]["modality"] == "lidar":
            file_extension = ".pcd.bin"
            writer = self.pointcloud_write
        else:
            print("Unknown modality:", self.frame_info_[frame_id]["modality"])


        if frame_id not in self.written_calibrated_sensors_:
            self.writeCalibratedSensors(frame_id, intrinsic)
            self.written_calibrated_sensors_.add(frame_id)

        is_keyframe = self.is_keyframe(frame_id, timestamp, isKeyframe, isFirstKeyframe)
        filename = self.getFilename(frame_id, timestamp, is_keyframe)
        dir_path = os.path.dirname(filename)

        if dir_path not in self.created_dirs_:
            os.makedirs(dir_path, exist_ok=True)
            self.created_dirs_.add(dir_path)

        writer(filename, data)
        sd = self.getSampleData(frame_id, timestamp, Path(filename), file_extension,
                                width, height, is_keyframe)
        self.sample_data_.append(sd)


    def getSampleData(self, frame_id, timestamp, output_filepath, file_extension, img_width, img_height, is_key_frame):
        self.updateFrameInfo(frame_id, timestamp)
        ego_pose_token = self.get_closest_ego_pose(int(timestamp))
        calibrated_sensor_token = self.frame_info_[frame_id]["calibrated_sensor_token"]  # Assuming sensor_token is the calibrated sensor token


        sample_data_entry = {
            "token": self.frame_info_[frame_id]["current_token"],
            "sample_token": self.current_sample_token_,
            "ego_pose_token": ego_pose_token,  # Link to the ego pose generated earlier
            "calibrated_sensor_token": calibrated_sensor_token,  # Link to calibrated sensor
            "filename": str(output_filepath.relative_to(self.output_dir_)),  # Path relative to output_dir
            "fileformat": file_extension,
            "width": img_width,
            "height": img_height,
            "timestamp": timestamp // 1000,
            "is_key_frame": "true" if is_key_frame else "false",
            "next": self.frame_info_[frame_id]["next_token"],
            "prev": self.frame_info_[frame_id]["previous_token"],
        }
        return sample_data_entry

    def updateFrameInfo(self, frame_id, timestamp):
        """Update the frame info for a given frame ID."""
        if frame_id in self.frame_info_:
            self.frame_info_[frame_id]["previous_timestamp"] = timestamp // 1000
            self.frame_info_[frame_id]["previous_token"] = self.frame_info_[frame_id]["current_token"]
            self.frame_info_[frame_id]["current_token"] = self.frame_info_[frame_id]["next_token"]
            self.frame_info_[frame_id]["next_token"] = self.generateToken()


    def prune_old_ego_poses(self, current_time: int, horizon_ns: int = 2e9):
        """Remove poses older than current_time - horizon_ms."""
        threshold = current_time - horizon_ns
        # Keep only poses newer than the threshold
        self.ego_pose_list = [
            (ts, token) for (ts, token) in self.ego_pose_list if ts >= threshold
        ]

    def get_closest_ego_pose(self, timestamp: int) -> str:
        if not self.ego_pose_list:
            self.waiting_timestamp = timestamp
            raise RuntimeError("No ego poses available")

        previous_token = None
        previous_time_difference = float('inf')

        for ts, token in self.ego_pose_list:
            if ts >= timestamp:
                if (ts - timestamp) < previous_time_difference:
                    return token
                else:
                    return previous_token if previous_token is not None else token
            previous_token = token
            previous_time_difference = timestamp - ts

        # If all timestamps are before the target, return the latest one
        return self.ego_pose_list[-1][1]

    def getFilename(self, frame_id: str, timestamp, is_keyframe: bool) -> str:
        sensor_dir = self.frame_info_[frame_id]["name"]
        modality = self.frame_info_[frame_id]["modality"]
        base_dir = ""
        if modality == "camera":
            file_extension = ".jpg"
        elif modality == "lidar":
            file_extension = ".pcd.bin"
        elif modality == "radar":
            file_extension = ".bin"
        else:
            print("Unknown modality:", modality)



        base_dir = "samples" if is_keyframe else "sweeps"

        return self.output_dir_.__str__()+"/"+ base_dir+"/"+ sensor_dir+"/"+(self.bag_name_split_extension_+"__"+sensor_dir+"__"+str(int(timestamp))+file_extension)

    def is_keyframe(self, frame_id, timestamp, isKeyframe, isFirstKeyframe):

        timediff = 5*1e8  # 0.5 seconds in nanoseconds
        if (isFirstKeyframe):

            self.previous_sampled_timestamp_ = self.previous_sampled_timestamp_ + int(timediff)
            self.nbr_samples_ += 1

            sample = {}
            self.current_sample_token_ = self.next_sample_token_
            sample["token"] = self.current_sample_token_
            sample["timestamp"] = timestamp // 1000# self.previous_sampled_timestamp_* 1e-9
            sample["scene_token"] = self.scene_token_
            sample["prev"] = self.previous_sample_token_

            self.previous_sample_token_ = self.current_sample_token_

            self.next_sample_token_ = self.generateToken()
            sample["next"] = self.next_sample_token_

            self.samples_.append(sample)

            self.sensors_sampled_.clear()
            self.sensors_sampled_.append(frame_id)
            return True
        elif (isKeyframe):
            self.sensors_sampled_.append(frame_id)
            return True

        return False

