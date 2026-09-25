# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import os
import random
import math
import numpy as np
import json
import copy

try:
    import yaml  # optional for backward compatibility
except ImportError:
    yaml = None

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import bisect

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

from datahandler.canmetahandler import MetaGenerator
from datahandler.feedbackhandler import FeedbackHandler
from datahandler.oxtshandler import OxtsHandler
from datahandler.ncom_parser import NComDecoder
from datahandler.ego_pose_global import build_record as build_ego_pose_global_record
from datahandler.ego_pose_source import PoseSeries

import cv2

def load_param_file(path) -> dict:
    path = Path(path)
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
    _param_cache: Dict[str, dict] = {}
    _bag_setup_cache: Dict[Tuple[str, ...], dict] = {}

    def __init__(self):
        # Default constructor, equivalent to C++ Bag2Scenes::Bag2Scenes()
        self.param_yaml_: dict = {}
        self.bag_ = None  # rosbag.Bag object


        self.frame_info_: Dict[str, dict] = {}
        self.topic_to_frame_: Dict[str, str] = {}
        self.frame_to_transform_: Dict[str, np.matrix] = {}
        self.frame_to_camera_calib_: Dict[str, dict] = {}

        self.previous_sample_token_: str = ""
        self.next_sample_token_: str = ""
        self.previous_sampled_timestamp_ = 0.0
        self.nbr_samples_: int = 0
        self.sensors_sampled_ = []
        self.sensors_sampled_valid_ = []
        self.sensors_sampled_valid_frames_: Set[str] = set()
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
        self.ego_pose_list: List[Tuple[int, str]] = []  # List of tuples (timestamp, token) for ego poses
        self.ego_pose_timestamps_: List[int] = []

        self.tokens_: List[str] = []
        self.created_dirs_ = set()

        self.connections_by_topic_: Dict[str, list] = {}
        self.scene_stream_cache_: Optional[dict] = None
        self.json_cache_: Dict[Path, Any] = {}
        self.dirty_json_paths_: Set[Path] = set()

        # --- OxTS-default ego_pose (sensor-timestamp-driven, interpolated) ---
        # Dataset-wide UTM datum so ego_pose stays local/small (float32-safe downstream).
        self.ego_pose_datum_: Optional[dict] = None
        # Per-recording OxTS-vs-odom decision (one bag == one recording == one instance).
        self.pose_source_decision_: Optional[dict] = None
        # Per-scene active source, its interpolation series, and the JSON list refs the
        # per-sample_data mints append into (persisted by the end-of-scene flush).
        self.active_pose_series_: Optional[PoseSeries] = None
        self.active_pose_mode_: Optional[str] = None
        self.ego_poses_ref_: Optional[list] = None
        self.ego_pose_global_ref_: Optional[list] = None
        self.ncom_series_: list = []
        self.ncom_ts_: list = []
        self.egopose_edge_holds_: int = 0
        self.egopose_minted_: int = 0
        self.camera_clock_anomaly_: int = 0

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

    @classmethod
    def _load_params_cached(cls, param_source) -> dict:
        if isinstance(param_source, dict):
            return copy.deepcopy(param_source)

        cache_key = os.fspath(param_source)
        if cache_key not in cls._param_cache:
            cls._param_cache[cache_key] = load_param_file(param_source)
        return copy.deepcopy(cls._param_cache[cache_key])

    @staticmethod
    def _bag_cache_key(bag_reader: AnyReader) -> Tuple[str, ...]:
        return tuple(os.fspath(path) for path in bag_reader.paths)

    @staticmethod
    def _build_sensor_defs(params: dict) -> List[dict]:
        sensor_defs = []
        for sensor_name, sensor_data in params.get("SENSOR_INFO", {}).items():
            sensor = SensorInfos()
            sensor.radar_id = sensor_data.get("RADAR_ID")
            sensor.sensor_name = sensor_name
            sensor.topic_name = sensor_data.get("TOPIC")
            sensor.frame_id = sensor_data.get("FRAME")
            sensor.token = sensor_data.get("TOKEN")
            sensor.setType(sensor_name)
            sensor_defs.append(
                {
                    "radar_id": sensor.radar_id,
                    "sensor_name": sensor.sensor_name,
                    "topic_name": sensor.topic_name,
                    "frame_id": sensor.frame_id,
                    "token": sensor.token,
                    "type": sensor.type,
                }
            )
        return sensor_defs

    @classmethod
    def _get_or_build_bag_setup(cls, bag_reader: AnyReader, params: dict) -> dict:
        cache_key = cls._bag_cache_key(bag_reader)
        cached = cls._bag_setup_cache.get(cache_key)
        if cached is not None:
            return cached

        connections_by_topic: Dict[str, list] = {}
        tf_connections = []
        caminfo_connections = []
        for connection in bag_reader.connections:
            connections_by_topic.setdefault(connection.topic, []).append(connection)
            if "tf_static" in connection.topic:
                tf_connections.append(connection)
            if "/camera_info" in connection.topic:
                caminfo_connections.append(connection)

        frame_to_transform = {}
        if tf_connections:
            tf_handler = TFHandler()
            for connection, _, rawdata in bag_reader.messages(connections=tf_connections):
                msg = bag_reader.deserialize(rawdata, connection.msgtype)
                tf_handler.addTF(msg, frame_to_transform)

        frame_to_camera_calib = {}
        if caminfo_connections:
            camerinfo_handler = CameraInfoHandler()
            for connection, _, rawdata in bag_reader.messages(connections=caminfo_connections):
                msg = bag_reader.deserialize(rawdata, connection.msgtype)
                camerinfo_handler.addCameraInfo(msg, frame_to_camera_calib, bag_reader.is2)

        cached = {
            "connections_by_topic": connections_by_topic,
            "frame_to_transform": frame_to_transform,
            "frame_to_camera_calib": frame_to_camera_calib,
            "sensor_defs": cls._build_sensor_defs(params),
        }
        cls._bag_setup_cache[cache_key] = cached
        return cached

    def writeTokenFile(self):
        """write a file which contains all tokens used for this conversion, makes is easier to merge different bags."""
        token_file_path = self.output_dir_ / "tokens.txt"

        # Assume `strings` is a very long list of strings
        with open(token_file_path, "w") as file:
            file.write("\n".join(self.tokens_) + "\n")

    def init(self, rosbag_name, rosbag_name_split_extension_, param_file: Union[Path, dict], output_dir: Path, bag_reader: AnyReader, start_time, end_time):
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
            self.param_yaml_ = self._load_params_cached(param_file)
        except Exception as e:
            logging.error(f"Error reading {param_file}: {e}")
            raise

        bag_setup = self._get_or_build_bag_setup(bag_reader, self.param_yaml_)
        self.connections_by_topic_ = bag_setup["connections_by_topic"]
        self.frame_to_transform_ = copy.deepcopy(bag_setup["frame_to_transform"])
        self.frame_to_camera_calib_ = copy.deepcopy(bag_setup["frame_to_camera_calib"])







        # Determine relevant topics from param_yaml_ before iterating for counts
        #convert to class SensorInfo (better readability

        for sensor_data in bag_setup["sensor_defs"]:
            sensor = SensorInfos()
            sensor.radar_id = sensor_data["radar_id"]
            sensor.sensor_name = sensor_data["sensor_name"]
            sensor.topic_name = sensor_data["topic_name"]
            sensor.frame_id = sensor_data["frame_id"]
            sensor.token = sensor_data["token"]
            sensor.type = sensor_data["type"]
            self.sensors_.append(sensor)

        self.bag_metas_.odom_topic =  self.param_yaml_.get("BAG_INFO").get("ODOM_TOPIC")
        self.bag_metas_.map =  self.param_yaml_.get("BAG_INFO").get("TRACK")
        self.bag_metas_.team =  self.param_yaml_.get("BAG_INFO").get("VEHICLE")
        self.bag_metas_.description =  self.param_yaml_.get("BAG_INFO").get("DESCRIPTION")
        self.bag_metas_.feedback_topic = self.param_yaml_.get("CAN_INFO").get("FEEDBACK_TOPIC")
        self.bag_metas_.oxts_topic = self.param_yaml_.get("CAN_INFO").get("OXTS_TOPIC")

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
        self.sensors_sampled_valid_frames_.clear()
        self.scene_stream_cache_ = None
        self.json_cache_.clear()
        self.dirty_json_paths_.clear()

        self.output_dir_ = output_dir
        self.v1_0_mini_dir_ = self.output_dir_ / "v1.0-mini"
        self.can_dir_ = self.output_dir_ / "can_bus"



#TODO! Instead of a parameter file, better write a meta-file of rosbag, similar to bagzel.
    #contains: Possible Sensor-data (write everything available), ...
    #TODO: different lidars (ouster?) radar, ...?
    #make extraction more readable
    def getAllInfos(self):
        return 0

    def getTransformations(self):
        # Transforms and camera calibrations are cached once per bag in init().
        return



    def writeEgoPoses(self):
        """Prepare the per-scene ego_pose source. Poses are NOT minted here anymore --
        they are minted per sample_data at each sensor frame's exact timestamp during
        writeSensorData (sensor-timestamp-driven, OxTS-interpolated with odom fallback).
        This loads the cumulative JSON lists, sets up the interpolation series + datum +
        per-recording source decision, and marks the files dirty so the end-of-scene
        flush persists the appended rows (mirrors the old load/append/save cadence)."""
        self.ego_poses_ref_ = self._load_json(self.v1_0_mini_dir_ / "ego_pose.json")
        # ego_pose_global: RTK global twin of each OxTS ego_pose (same token).
        self.ego_pose_global_ref_ = self._load_json(self.v1_0_mini_dir_ / "ego_pose_global.json")
        self._prepare_ego_pose_source()
        self._save_json(self.ego_poses_ref_, self.v1_0_mini_dir_ / "ego_pose.json")
        self._save_json(self.ego_pose_global_ref_, self.v1_0_mini_dir_ / "ego_pose_global.json")



    def convertCalibrationToNuscenes(self, calibration_data):
        k_matrix = calibration_data.get("K")
        if k_matrix is None:
            return []

        if hasattr(k_matrix, "copy"):
            k_matrix = k_matrix.copy()
        else:
            k_matrix = copy.deepcopy(k_matrix)

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

        
        self.writeCANFiles()


        self.getTransformations()

        # Write odometry data
        self.writeEgoPoses()

        # Write sensor data (mints one interpolated ego_pose per sample_data)
        self.writeSensorData()

        logging.info("[ego_pose] scene=%s minted=%d edge_holds=%d camera_clock_anomalies=%d",
                     self.bag_name_split_extension_, self.egopose_minted_,
                     self.egopose_edge_holds_, self.camera_clock_anomaly_)

        #write final scene file
        self.writeSceneFile()

        #write Taxonomy
        self.writeTaxonomyFiles()

        self.flush_json_cache()
        self.writeTokenFile()


    def _load_json(self, file_path: Path):
        file_path = Path(file_path)
        if file_path in self.json_cache_:
            return self.json_cache_[file_path]

        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    self.json_cache_[file_path] = data
                    return data
            except json.JSONDecodeError as e:
                logging.warning(f"Error decoding JSON from {file_path}: {e}. Write File.")
                self.json_cache_[file_path] = []
                return self.json_cache_[file_path]

        #logging.warning(f"File does not exist: {file_path}:  Write File.")

        self.json_cache_[file_path] = []
        return self.json_cache_[file_path]

    def _save_json(self, data, file_path: Path):
        file_path = Path(file_path)
        dir_path = os.path.dirname(file_path)
        if dir_path not in self.created_dirs_:
            os.makedirs(dir_path, exist_ok=True)
            self.created_dirs_.add(dir_path)

        self.json_cache_[file_path] = data
        self.dirty_json_paths_.add(file_path)

    def flush_json_cache(self):
        for file_path in sorted(self.dirty_json_paths_):
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.json_cache_[file_path], f, indent=4)
            except IOError as e:
                logging.error(f"Error writing JSON to {file_path}: {e}")
        self.dirty_json_paths_.clear()

    def _get_connections(self, *topics: str) -> list:
        connections = []
        for topic in topics:
            if topic:
                connections.extend(self.connections_by_topic_.get(topic, []))
        return connections

    def _build_scene_stream_cache(self):
        if self.scene_stream_cache_ is not None:
            return self.scene_stream_cache_

        feedback_topic = self.bag_metas_.feedback_topic
        odom_topic = self.bag_metas_.odom_topic
        oxts_topic = self.bag_metas_.oxts_topic

        connections = self._get_connections(feedback_topic, odom_topic, oxts_topic)
        ms_imu_json = []
        pose_json = []
        steeranglefeedback_json = []
        vehicle_monitor_json = []
        zoe_veh_info_json = []
        zoesensors_json = []
        ego_pose_entries = []

        feedback_handler = FeedbackHandler()
        odom_handler = OdomHandler()
        oxts_handler = OxtsHandler()
        ncom_decoder = NComDecoder()   # rich OxTS decode (GNSS/RTK) for ego_pose_global
        ncom_series = []
        # Odom poses keyed by BAG-RECEIVE time (the same clock sample_data timestamps use),
        # NOT the odom header stamp -- so the fallback interpolation lines up with sensors.
        odom_pose_series_raw = []
        final_odom_utime = 0

        # Warm up the NCOM status channels (fix mode / accuracy cycle over ~1s) with a
        # lead-in before the chunk start, so chunk-start ego_poses get fix_status/pos_std,
        # AND collect the warm-up ncom/odom into the series so poses can be interpolated
        # for sensor frames that straddle the chunk start (200 ms read margin, see below).
        warmup_start = max(self.bag_reader_.start_time, int(self.start_time_) - 2_000_000_000)
        if warmup_start < int(self.start_time_):
            for connection, timestamp, rawdata in self.bag_reader_.messages(
                connections=self._get_connections(oxts_topic, odom_topic),
                start=warmup_start,
                stop=int(self.start_time_),
            ):
                msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)
                if connection.topic == oxts_topic:
                    rec = ncom_decoder.feed(msg.payload, timestamp)
                    if rec is not None:
                        ncom_series.append(rec)
                elif connection.topic == odom_topic:
                    odom_handler.setOdom(msg, timestamp)
                    odom_pose_series_raw.append(
                        (int(timestamp), odom_handler.getOdomPosition(), odom_handler.getOdomQuaternion()))

        for connection, timestamp, rawdata in self.bag_reader_.messages(
            connections=connections,
            start=self.start_time_,
            stop=self.end_time_,
        ):
            msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)

            if connection.topic == feedback_topic:
                feedback_handler.addSteerAngleFeedback(msg, steeranglefeedback_json)
                feedback_handler.addVehicleMonitor(msg, vehicle_monitor_json)
                feedback_handler.addZoeSensors(msg, zoesensors_json)
                feedback_handler.addZoeVehicleInfo(msg, zoe_veh_info_json)
                continue

            if connection.topic == odom_topic:
                odom_handler.setOdom(msg, timestamp)
                final_odom_utime = int(odom_handler.getOdomStamp() // 1000)
                pose_json.append({
                    "accel": [0, 0, 0],
                    "orientation": odom_handler.getOdomQuaternion(),
                    "pos": odom_handler.getOdomPosition(),
                    "rotation_rate": odom_handler.getOdomTwistAngular(),
                    "utime": int(odom_handler.getOdomStamp() // 1000),
                    "vel": odom_handler.getOdomTwistLinear()
                })
                ego_pose_entries.append((
                    odom_handler.getOdomPosition(),
                    odom_handler.getOdomQuaternion(),
                    odom_handler.getOdomStamp(),
                ))
                odom_pose_series_raw.append(
                    (int(timestamp), odom_handler.getOdomPosition(), odom_handler.getOdomQuaternion()))
                continue

            if connection.topic == oxts_topic:
                ncom_rec = ncom_decoder.feed(msg.payload, timestamp)
                if ncom_rec is not None:
                    ncom_series.append(ncom_rec)
                success = oxts_handler.setOxts(msg.payload, timestamp)
                imu = oxts_handler.getImu()
                if not success:
                    continue

                ms_imu_json.append({
                    "linear_accel": [imu.linear_acceleration.x, imu.linear_acceleration.y, imu.linear_acceleration.z],
                    "q": [imu.orientation.w, imu.orientation.x, imu.orientation.y, imu.orientation.z],
                    "rotation_rate": [imu.angular_velocity.x, imu.angular_velocity.y, imu.angular_velocity.z],
                    "utime": None,
                })

        for imu_entry in ms_imu_json:
            imu_entry["utime"] = final_odom_utime

        ncom_series.sort(key=lambda r: r["bag_ts_ns"])
        if ncom_decoder.n_checksum_fail or ncom_decoder.n_bad_attitude or ncom_decoder.n_null_island:
            logging.info(
                "NCOM rejects: checksum=%d null_island=%d bad_attitude=%d out_of_range=%d",
                ncom_decoder.n_checksum_fail, ncom_decoder.n_null_island,
                ncom_decoder.n_bad_attitude, ncom_decoder.n_out_of_range,
            )

        odom_pose_series_raw.sort(key=lambda e: e[0])
        self.scene_stream_cache_ = {
            "ms_imu_json": ms_imu_json,
            "pose_json": pose_json,
            "steeranglefeedback_json": steeranglefeedback_json,
            "vehicle_monitor_json": vehicle_monitor_json,
            "zoe_veh_info_json": zoe_veh_info_json,
            "zoesensors_json": zoesensors_json,
            "ego_pose_entries": ego_pose_entries,
            "ncom_series": ncom_series,
            "odom_pose_series_raw": odom_pose_series_raw,
        }
        return self.scene_stream_cache_

    def writeLog(self):
        self.log_token_ = self.generateToken()
        log_file_path = self.output_dir_ / "v1.0-mini" / "log.json"
        logs = self._load_json(log_file_path)

        new_log = {
            "token": self.log_token_,
            "logfile": self.bag_name_split_extension_,#TODO
            "vehicle": self.bag_metas_.vehicle,
            "date_captured": self.bag_name_, #TODO,
            "location": self.bag_name_
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
            if not categories:
                categories = [{
                    "token": category_token,
                    "name": "default_category",  # Placeholder
                    "description": "Default category for generated data"
                }]
                self._save_json(categories, category_file)

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
            if not attributes:
                attributes = [{
                    "token": attribute_token,
                    "name": "default_attribute",  # Placeholder
                    "description": "Default attribute for generated data"
                }]
                self._save_json(attributes, attribute_file)

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
            if not visibilities:
                visibilities = [{
                    "token": visibility_token,
                    "description": "Default visibility level",
                    "level": "0-20"  # Placeholder, C++ leaves empty
                }]
                self._save_json(visibilities, visibility_file)

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
            if not instances:
                instances = [{
                    "token": instance_token,
                    "category_token": category_token,
                    "nbr_annotations": 0,
                    "first_annotation_token": "",  # Will be filled by annotation
                    "last_annotation_token": ""  # Will be filled by annotation
                }]
                self._save_json(instances, instance_file)

        # Sample Annotation
        annotation_file = self.v1_0_mini_dir_ / "sample_annotation.json"
        if not annotation_file.exists():
            annotations = []
            self._save_json(annotations, annotation_file)
        else:
            annotations = self._load_json(annotation_file)
            if annotations is None:
                annotations = []
                self._save_json(annotations, annotation_file)



    # ------------------------------------------------------------------
    # OxTS-default ego_pose: source setup, per-recording decision, datum,
    # and per-sample_data interpolated minting.
    # ------------------------------------------------------------------
    def _prepare_ego_pose_source(self):
        """Build the active interpolation series for this scene chunk and pick the source
        (OxTS preferred, odom fallback) consistently for the whole recording."""
        streams = self._build_scene_stream_cache()
        ncom_series = sorted(streams.get("ncom_series", []), key=lambda r: r["bag_ts_ns"])
        odom_raw = streams.get("odom_pose_series_raw", [])
        self.ncom_series_ = ncom_series
        self.ncom_ts_ = [r["bag_ts_ns"] for r in ncom_series]
        self.egopose_edge_holds_ = 0
        self.egopose_minted_ = 0
        self.camera_clock_anomaly_ = 0

        mode = self._ensure_source_decision()

        if mode == "oxts":
            datum = self._load_or_init_datum(ncom_series)
            # Guard: a recording in a different UTM zone than the dataset datum cannot be
            # rebased against it -- fall back to odom loudly rather than corrupt coordinates.
            rec_zone = None
            if ncom_series:
                rec_zone = build_ego_pose_global_record("", ncom_series[0], 0)["utm_zone"]
            if datum is None or (rec_zone is not None and rec_zone != datum["utm_zone"]):
                logging.warning("[ego_pose] scene=%s OxTS unusable (datum=%s rec_zone=%s) -> odom",
                                self.bag_name_split_extension_,
                                None if datum is None else datum["utm_zone"], rec_zone)
                mode = "odom"

        if mode == "oxts":
            ts, xyz, quat = [], [], []
            for r in ncom_series:
                rec = build_ego_pose_global_record("", r, int(r["bag_ts_ns"] // 1000))
                ts.append(int(r["bag_ts_ns"]))
                xyz.append(rec["translation"])       # absolute UTM, float64
                quat.append(rec["rotation"])          # [w,x,y,z]
            self.active_pose_series_ = PoseSeries(ts, xyz, quat) if ts else None
        else:
            ts = [e[0] for e in odom_raw]
            xyz = [e[1] for e in odom_raw]
            quat = [e[2] for e in odom_raw]
            self.active_pose_series_ = PoseSeries(ts, xyz, quat) if ts else None

        self.active_pose_mode_ = mode
        logging.info("[ego_pose] scene=%s source=%s ncom=%d odom=%d",
                     self.bag_name_split_extension_, mode, len(ncom_series), len(odom_raw))
        if self.active_pose_series_ is None:
            raise RuntimeError(
                f"No ego-pose source for scene {self.bag_name_split_extension_}: neither OxTS "
                f"({len(ncom_series)} recs) nor odom ({len(odom_raw)} recs) usable. Not silently skipping.")

    def _ensure_source_decision(self):
        """Decide OxTS-vs-odom once per recording (one bag == one instance), persisted to a
        sidecar so every chunk of the recording agrees (mixing frames is invalid)."""
        if self.pose_source_decision_ is not None:
            return self.pose_source_decision_["mode"]
        rec_id = self.bag_name_
        path = self.v1_0_mini_dir_ / "ego_pose_source.json"
        table = self._load_json(path)
        if not isinstance(table, dict):
            table = {}
        if rec_id in table:
            self.pose_source_decision_ = table[rec_id]
            return self.pose_source_decision_["mode"]
        recs = self._scan_recording_oxts()
        mode, cov, reason = self._decide_source(recs)
        decision = {"mode": mode, "coverage": cov, "reason": reason, "n_oxts": len(recs)}
        table[rec_id] = decision
        self._save_json(table, path)
        self.pose_source_decision_ = decision
        logging.warning("[ego_pose] recording=%s -> source=%s (coverage=%.3f, %s, n_oxts=%d)",
                        rec_id, mode, cov, reason, len(recs))
        return mode

    def _scan_recording_oxts(self):
        """One-time whole-bag OxTS scan (cached) so the source decision reflects the full
        recording, not just the first chunk."""
        if getattr(self, "recording_oxts_cache_", None) is not None:
            return self.recording_oxts_cache_
        dec = NComDecoder()
        recs = []
        oxts_topic = self.bag_metas_.oxts_topic
        conns = self._get_connections(oxts_topic)
        if conns:
            for connection, timestamp, rawdata in self.bag_reader_.messages(
                    connections=conns, start=self.bag_reader_.start_time, stop=self.bag_reader_.end_time):
                msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)
                r = dec.feed(msg.payload, timestamp)
                if r is not None:
                    recs.append(r)
        recs.sort(key=lambda r: r["bag_ts_ns"])
        self.recording_oxts_cache_ = recs
        return recs

    @staticmethod
    def _decide_source(recs, min_count=100, min_coverage=0.90,
                       max_gap_ns=1_000_000_000, min_rtk_fraction=0.5):
        """OxTS iff the stream is dense enough to interpolate and mostly DIFF/RTK-fixed."""
        if len(recs) < min_count:
            return "odom", 0.0, f"insufficient_oxts(<{min_count})"
        ts = [r["bag_ts_ns"] for r in recs]
        span = ts[-1] - ts[0]
        # coverage of the sampled span vs its own dense expectation (gap-limited density)
        max_gap = max((ts[i + 1] - ts[i] for i in range(len(ts) - 1)), default=0)
        # gps_pos_mode is None until the rotating status channel fills; treat as not-fixed.
        rtk_fraction = sum(1 for r in recs
                           if r["gps_pos_mode"] is not None and r["gps_pos_mode"] >= 4) / len(recs)
        # coverage here == fraction of expected ~100Hz samples actually present over the span
        expected = max(1, span / 10_000_000)   # 10 ms nominal spacing
        coverage = min(1.0, len(recs) / expected)
        if max_gap > max_gap_ns:
            return "odom", coverage, f"oxts_gap({max_gap/1e9:.2f}s)"
        if rtk_fraction < min_rtk_fraction:
            return "odom", coverage, f"low_fix_quality(rtk={rtk_fraction:.2f})"
        if coverage < min_coverage:
            return "odom", coverage, f"sparse_oxts({coverage:.2f})"
        return "oxts", coverage, f"ok(rtk={rtk_fraction:.2f})"

    def _load_or_init_datum(self, ncom_series):
        """Dataset-wide UTM datum (floored to int meters) so ego_pose stays local/small and
        the existing downstream float32 math stays sub-mm accurate. Initialized once from the
        first valid OxTS fix; read by every later scene/recording."""
        if self.ego_pose_datum_ is not None:
            return self.ego_pose_datum_
        path = self.v1_0_mini_dir_ / "ego_pose_datum.json"
        d = self._load_json(path)
        if isinstance(d, dict) and "e0" in d:
            self.ego_pose_datum_ = d
            return d
        if not ncom_series:
            return None
        rec = build_ego_pose_global_record("", ncom_series[0], 0)
        e, n, alt = rec["translation"]
        datum = {
            "utm_zone": rec["utm_zone"],
            "e0": float(math.floor(e)), "n0": float(math.floor(n)), "alt0": float(math.floor(alt)),
            "source": "first_valid_fix",
        }
        self._save_json(datum, path)
        self.ego_pose_datum_ = datum
        logging.warning("[ego_pose] initialized dataset datum zone=%d e0=%.0f n0=%.0f alt0=%.0f",
                        datum["utm_zone"], datum["e0"], datum["n0"], datum["alt0"])
        return datum

    def _mint_ego_pose(self, timestamp_ns, is_camera=False):
        """Mint one ego_pose at this sample_data's exact timestamp by interpolating the active
        source (lerp position + slerp rotation). Returns the new pose token."""
        t = int(timestamp_ns)
        series = self.active_pose_series_
        xyz, quat, bracketed = series.sample(t)
        if not bracketed:
            self.egopose_edge_holds_ += 1
            gap = min(abs(t - series.t_first), abs(t - series.t_last))
            if is_camera and gap > 1_000_000_000:
                self.camera_clock_anomaly_ += 1
                logging.error("[ego_pose] camera frame ts=%d is %.2fs outside the pose stream "
                              "(clock fault?) scene=%s", t, gap / 1e9, self.bag_name_split_extension_)
        token = self.generateToken()
        if self.active_pose_mode_ == "oxts":
            d = self.ego_pose_datum_
            local = [xyz[0] - d["e0"], xyz[1] - d["n0"], xyz[2] - d["alt0"]]
            if max(abs(v) for v in local) >= 1e4:
                raise RuntimeError(
                    f"ego_pose local coord {local} exceeds 10 km from the dataset datum "
                    f"(zone {d['utm_zone']}); a single dataset-wide datum is unsafe here "
                    f"(float32 downstream). Use per-recording datums. scene={self.bag_name_split_extension_}")
            self.ego_poses_ref_.append({
                "token": token, "translation": local, "rotation": quat, "timestamp": int(t // 1000)})
            nrec = self._nearest_ncom(self.ncom_series_, self.ncom_ts_, t)
            if nrec is not None:
                grec = build_ego_pose_global_record(token, nrec, int(t // 1000))
                grec["translation"] = [float(xyz[0]), float(xyz[1]), float(xyz[2])]  # interpolated abs UTM
                grec["rotation"] = quat
                self.ego_pose_global_ref_.append(grec)
        else:
            self.ego_poses_ref_.append({
                "token": token, "translation": [float(v) for v in xyz],
                "rotation": quat, "timestamp": int(t // 1000)})
        self.ego_pose_list.append((t, token))
        self.ego_pose_timestamps_.append(t)
        self.egopose_minted_ += 1
        return token

    @staticmethod
    def _nearest_ncom(series, ts_array, stamp_ns, max_gap_ns=100_000_000):
        # nearest OxTS sample in bag-receive time; None if no sample within max_gap
        idx = bisect.bisect_left(ts_array, stamp_ns)
        cands = [i for i in (idx - 1, idx) if 0 <= i < len(ts_array)]
        if not cands:
            return None
        best = min(cands, key=lambda i: abs(ts_array[i] - stamp_ns))
        if abs(ts_array[best] - stamp_ns) > max_gap_ns:
            return None
        return series[best]

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
        camera_topics = {sensor.topic_name for sensor in self.sensors_ if sensor.type == SensorType.CAMERA}
        lidar_topics = {sensor.topic_name for sensor in self.sensors_ if sensor.type == SensorType.LIDAR}

        # Initialize ImageHandler with the type store.
        image_handler = ImageHandler()
        lidar_handler = LidarHandler()
        # filter topics

        camera_images = []
        lidar_pointclouds = []
        previous_timestamp_per_topic = {}

        ## from message to image/pointcloud
        #just use camera or lidar topics
        connections = []
        for topic in camera_topics | lidar_topics:
            connections.extend(self.connections_by_topic_.get(topic, []))

        # Add an overlapping read margin so LiDAR sweeps straddling the start boundary have their early packets
        margin_ns = int(2e8)  # 200 ms margin
        read_start = max(0, self.start_time_ - margin_ns)

        for connection, timestamp, rawdata in self.bag_reader_.messages(connections=connections, start=read_start, stop=self.end_time_):

            msg = self.bag_reader_.deserialize(rawdata, connection.msgtype)
            frame_id = self.topic_to_frame_[connection.topic]

            if connection.topic in camera_topics:
                ##check timestamp. Sometimes they are corrupted
                header_stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
                header_stamp = int(header_stamp * 1e9)  # convert to nanoseconds

                if connection.topic in previous_timestamp_per_topic:
                    diff_to_previous = header_stamp - previous_timestamp_per_topic[connection.topic]
                    assert diff_to_previous >= -2e8, (
                        f"[INVALID SENSOR DATA] Non-monotonic timestamps on topic {connection.topic}: "
                        f"prev={previous_timestamp_per_topic[connection.topic]} current={header_stamp}"
                    )
                previous_timestamp_per_topic[connection.topic] = header_stamp

                # Only decode and rectify if the message belongs to this scene chunk to save CPU time
                if header_stamp >= self.start_time_:
                    image_handler.setImage(msg, timestamp)
                    image_handler.rectifyImage(self.frame_to_camera_calib_[frame_id])
                    camera_images.append([connection.topic, header_stamp, image_handler.getRectifiedImage()])

            elif connection.topic in lidar_topics:
                # Topic may carry either ethernet_msgs/Packets (a batch with a
                # .packets list) or a single ethernet_msgs/Packet; normalize to
                # a list so the decoder loop handles both message shapes.
                pkts = msg.packets if hasattr(msg, "packets") else [msg]
                for pkt in pkts:
                    pkt_stamp = pkt.header.stamp.sec + pkt.header.stamp.nanosec * 1e-9
                    pkt_stamp = int(pkt_stamp * 1e9)  # convert to nanoseconds

                    lidar_handler.addPacket(pkt, pkt_stamp)
                    pointcloud = lidar_handler.getPointCloud()

                    if pointcloud is None:
                        continue

                    lidar_stamp = lidar_handler.getTimestamp()
                    if lidar_stamp is None:
                        lidar_stamp = pkt_stamp

                    # Only add if the COMPLETED sweep belongs to the current scene chunk
                    if lidar_stamp >= self.start_time_:
                        lidar_pointclouds.append([connection.topic, int(lidar_stamp), pointcloud])

        # sort all sensor data by timestamp
        all_sensor_data = camera_images + lidar_pointclouds
        all_sensor_data.sort(key=lambda x: x[1])

        # DRY RUN: determine valid frames (if a sensor is missing, it might break the logic
        # therefore: use all frames, in which all sensors are available
        self.all_valid_samples_dry_run_.clear()
        self.sensors_sampled_valid_.clear()
        self.sensors_sampled_valid_frames_.clear()
        self.valid_samples_timestamp = self.start_time_

        for topic, timestamp, rawdata in all_sensor_data:
            frame = self.topic_to_frame_[topic]
            self.get_valid_scenes(frame, timestamp, (topic in lidar_topics)) #LiDAR is the trigger

        #select 40 equidistant frames for the samples
        resulting_samples = self.select_equidistant_scenes(self.all_valid_samples_dry_run_,40)
        if not resulting_samples and all_sensor_data:
            # Fallback for sparse or slightly misaligned bags: group nearby sensor
            # timestamps into coarse samples instead of returning an empty dataset.
            fallback_window_ns = int(2e8)
            fallback_samples = []
            current_sample = []
            current_frames = set()
            anchor_timestamp = None

            for topic, timestamp, _ in all_sensor_data:
                frame_id = self.topic_to_frame_[topic]
                if anchor_timestamp is None or timestamp - anchor_timestamp > fallback_window_ns:
                    if current_sample:
                        fallback_samples.append(current_sample)
                    current_sample = []
                    current_frames = set()
                    anchor_timestamp = timestamp

                if frame_id in current_frames:
                    continue

                current_sample.append((frame_id, timestamp))
                current_frames.add(frame_id)

            if current_sample:
                fallback_samples.append(current_sample)

            resulting_samples = fallback_samples
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
            self.sensors_sampled_valid_frames_.add(frame_id)
            self.valid_samples_timestamp = timestamp

            # only valid if all data is there
            if len(self.sensors_) == len(self.sensors_sampled_valid_):
                self.all_valid_samples_dry_run_.append(self.sensors_sampled_valid_.copy())

            self.sensors_sampled_valid_.clear()
            self.sensors_sampled_valid_frames_.clear()

            return True

        elif (frame_id not in self.sensors_sampled_valid_frames_) and (
                abs(time_diff) < (2e8)  # 0.2 seconds in nanoseconds
        ):
            self.sensors_sampled_valid_.append((frame_id, timestamp))
            self.sensors_sampled_valid_frames_.add(frame_id)
            return True

        return False


    def image_write(self, filename, image):
        cv2.imwrite(filename, image)


    def pointcloud_write(self, filename, pointcloud_data):
            # 20 bytes/point
            expected_dtype = np.dtype([('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('intensity', 'f4'), ('column', 'u2'), ('ring', 'u1'), ('return_type', 'u1')])
            data = pointcloud_data[['x', 'y', 'z', 'intensity', 'column', 'ring', 'return_type']].astype(expected_dtype)

            point_bytes = data.tobytes()

            with open(filename, 'wb') as f:
                f.write(point_bytes)


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

        # Mint one ego_pose per sample_data at its EXACT timestamp (interpolated from the
        # active source), instead of sharing one closest-snap pose across the whole sample.
        is_camera = self.frame_info_[frame_id]["modality"] == "camera"
        ego_pose_token = self._mint_ego_pose(int(timestamp), is_camera=is_camera)
        calibrated_sensor_token = self.frame_info_[frame_id]["calibrated_sensor_token"]

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
            "is_key_frame": bool(is_key_frame),
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




    def getFilename(self, frame_id: str, timestamp, is_keyframe: bool) -> str:
        sensor_dir = self.frame_info_[frame_id]["name"]
        modality = self.frame_info_[frame_id]["modality"]

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

    def getFakeRoute(self, pose_json):
            """
            This function "Fakes" the Route information, as we do not have a given route.
            For achieving this, we:
            1) subsample the already driven trajectory, such that its really sparse
            2) interpolate in between, such that its dense again, but has only very sparse points.

            This might work, or critically fail -- we will see

            :param pose_json:
            :return:
            """
            route = []
            route.append([pose_json[0]["pos"][0], pose_json[0]["pos"][1]])

            for odom in pose_json:

                dx = route[-1][0] - odom["pos"][0]
                dy = route[-1][1] - odom["pos"][1]
                dist2 = dx * dx + dy * dy

                if dist2 > 15 * 15:
                    route.append([odom["pos"][0], odom["pos"][1]])

            route.append([pose_json[-1]["pos"][0], pose_json[-1]["pos"][1]])

            # Stage 2: Interpolate between points (~0.5m spacing)
            interpolated_route = []
            spacing = 0.5  # meters

            for i in range(len(route) - 1):
                x0, y0 = route[i]
                x1, y1 = route[i + 1]

                dx = x1 - x0
                dy = y1 - y0
                segment_length = math.hypot(dx, dy)
                n_points = max(int(segment_length / spacing), 1)  # number of points to insert

                for j in range(n_points):
                    t = j / n_points
                    interpolated_route.append([x0 + t * dx, y0 + t * dy])

            # Add the last point
            interpolated_route.append(route[-1])
            return interpolated_route

    def writeCANFiles(self):
            scene_streams = self._build_scene_stream_cache()
            meta_handler = MetaGenerator()

            ms_imu_json = scene_streams["ms_imu_json"]
            pose_json = scene_streams["pose_json"]
            steeranglefeedback_json = scene_streams["steeranglefeedback_json"]
            vehicle_monitor_json = scene_streams["vehicle_monitor_json"]
            zoe_veh_info_json = scene_streams["zoe_veh_info_json"]
            zoesensors_json = scene_streams["zoesensors_json"]

            route_json = self.getFakeRoute(pose_json) if pose_json else []

            meta_json = meta_handler.compute_meta(
                ms_imu_json=ms_imu_json,
                pose_json=pose_json,
                steeranglefeedback_json=steeranglefeedback_json,
                vehicle_monitor_json=vehicle_monitor_json,
                zoe_veh_info_json=zoe_veh_info_json,
                zoesensors_json=zoesensors_json
            )

            ### DUMP ALL FILES
            scene_id = self.bag_name_split_extension_

            self._save_json(meta_json, self.can_dir_ / f"{scene_id}_meta.json")
            self._save_json(ms_imu_json, self.can_dir_ / f"{scene_id}_ms_imu.json")
            self._save_json(pose_json, self.can_dir_ / f"{scene_id}_pose.json")
            self._save_json(steeranglefeedback_json, self.can_dir_ / f"{scene_id}_steeranglefeedback.json")
            self._save_json(vehicle_monitor_json, self.can_dir_ / f"{scene_id}_vehicle_monitor.json")
            self._save_json(zoe_veh_info_json, self.can_dir_ / f"{scene_id}_zoe_veh_info.json")
            self._save_json(zoesensors_json, self.can_dir_ / f"{scene_id}_zoesensors.json")
            self._save_json(route_json, self.can_dir_ /  f"{scene_id}_route.json")
