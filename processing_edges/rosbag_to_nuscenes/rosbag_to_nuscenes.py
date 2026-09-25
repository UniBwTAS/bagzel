# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import sys
import time
import math
import json

try:
    import yaml  # keep optional backward compat
except ImportError:
    yaml = None

from pathlib import Path

original_open = Path.open

def patched_open(self, mode='r', buffering=-1, *args, **kwargs):
    # Force a larger buffer size only for binary reads
    if 'b' in mode and buffering == -1:
        buffering = 32 * 1024 * 1024
    return original_open(self, mode, buffering, *args, **kwargs)

Path.open = patched_open


from rosbags.highlevel import AnyReader

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from filehandler.nuscenes_files import *
from filehandler.fast_check import *
from msgs.helper import get_full_typestore
import shutil
import argparse
import stat

def getNecessaryTopics(params):
    topiclist = []
    for sensor_name, sensor_data in params.get("SENSOR_INFO", {}).items():
        topiclist.append(sensor_data.get("TOPIC"))

    return topiclist

def load_params(param_file: str) -> dict:
    suffix = Path(param_file).suffix.lower()

    if suffix == ".json":
        with open(param_file, "r", encoding="utf-8") as f:
            return json.load(f)

    if suffix in (".yml", ".yaml"):
        if yaml is None:
            raise RuntimeError("Param file is YAML but PyYAML is not installed.")
        with open(param_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Fallback: try JSON then YAML (useful if the extension is odd)
    with open(param_file, "r", encoding="utf-8") as f:
        txt = f.read()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        if yaml is None:
            raise
        return yaml.safe_load(txt)


def load_blacklist(blacklist_file: str) -> list:
    """Read blacklist words (one per line), lowercased. Missing file -> []."""
    if not os.path.isfile(blacklist_file):
        return []
    with open(blacklist_file, "r", encoding="utf-8") as f:
        words = []
        for line in f:
            word = line.strip().lower()
            if word and not word.startswith("#"):
                words.append(word)
        return words


def isBagValid(params, bag_info, min_bag_duration_sec: float):
    relevant_topics = getNecessaryTopics(params)

    list_of_missing_topics = []
    for topic in relevant_topics:
        if topic not in bag_info['topics']:
            list_of_missing_topics.append(topic)

    if len(list_of_missing_topics) > 0:
        print("Following topics are missing:")
        print(list_of_missing_topics)
        print("Return")
        return False

    if bag_info['duration_s'] < min_bag_duration_sec:
        print(f"Bag is too short! duration={bag_info['duration_s']:.2f}s < {min_bag_duration_sec:.2f}s. Return")
        return False

    return True


def get_ego_distance_xy(reader: AnyReader, odom_topic: str) -> float:
    odom_connections = [c for c in reader.connections if c.topic == odom_topic]
    if not odom_connections:
        print(f"Missing odom topic in bag: {odom_topic}")
        return 0.0

    first_xy = None
    last_xy = None

    for connection, _, rawdata in reader.messages(connections=odom_connections):
        msg = reader.deserialize(rawdata, connection.msgtype)
        try:
            pos = msg.pose.pose.position
            xy = (float(pos.x), float(pos.y))
        except Exception:
            return 0.0

        if first_xy is None:
            first_xy = xy
        last_xy = xy

    if first_xy is None or last_xy is None:
        return 0.0

    return math.hypot(last_xy[0] - first_xy[0], last_xy[1] - first_xy[1])


def checkMotion(reader: AnyReader, odom_topic: str, min_ego_distance_m: float) -> bool:
    if min_ego_distance_m <= 0 or not odom_topic:
        return True

    ego_distance_m = get_ego_distance_xy(reader, odom_topic)
    if ego_distance_m < min_ego_distance_m:
        print(f"Bag skipped: ego moved {ego_distance_m:.2f} m (< {min_ego_distance_m:.2f} m)")
        return False

    return True



def getPath(path: str) -> Path:
    """
    Returns a Path object from a string path.
    If it is a directory, it is assumed to be a ROS2 bag directory (holding metadata.yaml), we return it as-is
    If file ends with .db3 or .mcap, it is assumed to be a ROS2 bag storage file, we return the parent directory
    If the file ends with .bag, it is assumed to be a ROS1 bag file, we return the filename
    :param path: The path as a string.
    :return: A Path object.
    """
    p = Path(path)
    if p.is_dir():
        return p
    if p.suffix in ('.db3', '.mcap'):
        return p.parent
    elif p.suffix == '.bag':
        return p
    else:
        raise ValueError(f"Unsupported file type: {p.suffix}. Expected .db3, .mcap, .bag, or a rosbag2 directory")



def main():
    parser = argparse.ArgumentParser(description="Convert ROS bag to NuScenes-like scenes.")
    parser.add_argument(
        '--input_bag',
        type=str,
        required=True,
        help='Path to the ROS bag directory or bag file (.db3, .mcap, or .bag).'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default='tas_scenes',
        help='Output directory for the converted scenes.'
    )
    parser.add_argument(
        '--param_file',
        type=str,
        default=None,
        help=(
            'Path to the parameter JSON file. '
            'If omitted, defaults to param/nuscenes_param.json relative to this script. '
            'If provided as a relative path (e.g. from Bazel $(location ...)), it is resolved relative to CWD.'
        ),
    )
    parser.add_argument(
        '--blacklist_file',
        type=str,
        default=None,
        help=(
            'Path to a blacklist text file (one word per line). '
            'If omitted, defaults to param/blacklist.txt relative to this script. '
            'Bags whose full path contains any blacklist word (case-insensitive) are skipped.'
        ),
    )

    args = parser.parse_args()
    args.output_dir = args.output_dir.replace("//", "/")

    # Ensure output dir exists (so chmod doesn't fail)
    os.makedirs(args.output_dir, exist_ok=True)

    # Resolve param file:
    # - If user provides it, interpret relative paths relative to CWD (Bazel-friendly).
    # - If not provided, fall back to script-relative default.
    if args.param_file is None:
        ws = os.path.dirname(os.path.abspath(__file__))
        param_file = os.path.join(ws, "param", "param.yaml")
    else:
        # Expand ~ and env vars, then resolve relative to current working directory
        param_file = os.path.expanduser(os.path.expandvars(args.param_file))
        param_file = os.path.abspath(param_file)

    if not os.path.isfile(param_file):
        raise FileNotFoundError(
            f"Parameter file not found: {param_file}\n"
            f"  (cwd={os.getcwd()}, arg={args.param_file})"
        )
    
    params = load_params(param_file)
    ex = params.get("EXTRACTION", {})

    min_bag_duration_sec = float(ex.get("min_bag_duration_sec", 20.2))
    scene_length_sec = float(ex.get("scene_length_sec", 20))

    if scene_length_sec <= 0:
        raise ValueError(f"EXTRACTION.scene_length_sec must be > 0, got {scene_length_sec}")
    if min_bag_duration_sec < 0:
        raise ValueError(f"EXTRACTION.min_bag_duration_sec must be >= 0, got {min_bag_duration_sec}")


    path = getPath(args.input_bag)

    # Skip blacklisted bags: if any blacklist word appears (case-insensitive) in
    # the full bag path. The output dir already exists (created above), so the
    # Bazel-declared output stays satisfied even though we produce no scenes.
    if args.blacklist_file is None:
        ws = os.path.dirname(os.path.abspath(__file__))
        blacklist_file = os.path.join(ws, "param", "blacklist.txt")
    else:
        blacklist_file = os.path.abspath(os.path.expanduser(os.path.expandvars(args.blacklist_file)))

    hay = str(args.input_bag).lower()
    for word in load_blacklist(blacklist_file):
        if word in hay:
            print(f"SKIPPED (blacklist '{word}'): {args.input_bag}")
            return

    # Apply permissions to output dir
    os.chmod(args.output_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    try:
        bag_infos = getBagInfo(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        print("INVALID")
        return

    if not isBagValid(params, bag_infos, min_bag_duration_sec):
        return

    with AnyReader([path]) as reader:
        odom_topic = params.get("BAG_INFO", {}).get("ODOM_TOPIC")
        min_ego_distance_m = float(ex.get("min_ego_distance_m", 0))

        if not checkMotion(reader, odom_topic, min_ego_distance_m):
            return

        bag_name = reader.paths[0].stem

        iteration_step = int(scene_length_sec * 1e9)  # 20 seconds

        # Prefer skipping the first 500 ms so the first scene begins on a
        # complete LiDAR rotation. For short bags, keep the scene at the
        # beginning of the bag instead of shifting it to the tail, otherwise
        # sparse camera frames can fall completely outside the exported window.
        available_duration_ns = reader.end_time - reader.start_time
        preferred_start_offset_ns = int(5e8)
        if available_duration_ns >= preferred_start_offset_ns + iteration_step:
            start_offset_ns = preferred_start_offset_ns
        else:
            start_offset_ns = 0
        actual_start_time = reader.start_time + start_offset_ns

        extension = 0
        for timestamp in range(actual_start_time, reader.end_time, iteration_step):
            bag_name_with_time_extension = bag_name + "_" + str(extension)
            full_output_path = Path(args.output_dir) / bag_name_with_time_extension / "v1.0-mini"

            if timestamp + iteration_step > reader.end_time:
                break

            extension = int(extension + scene_length_sec)
            try:
                converter = Bag2Scenes()
                converter.init(
                    bag_name,
                    bag_name_with_time_extension,
                    params,
                    full_output_path,
                    reader,
                    timestamp,
                    timestamp + iteration_step,
                )
                converter.writeScene()
            except Exception as e:
                if full_output_path.exists() and full_output_path.is_dir():
                    shutil.rmtree(full_output_path)
                print(f"Error during scene creation: {e}")
                print("remove scene: ", full_output_path)


if __name__ == "__main__":
    main()
