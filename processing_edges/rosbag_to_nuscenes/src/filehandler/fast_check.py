# SPDX-FileCopyrightText: 2026 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from rosbags.rosbag1.reader import Header, RecordType, ReaderError
from rosbags.typesys.msg import normalize_msgtype
import yaml
import struct
import os
from typing import BinaryIO, Dict, Set, Tuple


def get_rosbag2_info(path: Path):
    meta_file = path / 'metadata.yaml'
    if not meta_file.exists():
        raise FileNotFoundError(f"No metadata.yaml in {path}")
    with meta_file.open('r') as f:
        meta = yaml.safe_load(f)

    topics = {}

    for topic_info in meta['rosbag2_bagfile_information']['topics_with_message_count']:
        topics[topic_info['topic_metadata']['name']] = topic_info['topic_metadata']['type']

    return{
        "topics" : topics,
        "duration_s" : meta['rosbag2_bagfile_information']['files'][0]['duration']['nanoseconds']*1e-9,
        "start_time_ns" : int(meta['rosbag2_bagfile_information']['files'][0]['starting_time']['nanoseconds_since_epoch']),
        "end_time_ns" : int(meta['rosbag2_bagfile_information']['files'][0]['duration']['nanoseconds'])+int(meta['rosbag2_bagfile_information']['files'][0]['starting_time']['nanoseconds_since_epoch'])
    }


def getBagInfo(path: Path):
    if (path / 'metadata.yaml').exists():  # ROS 2
        return get_rosbag2_info(path)
    else:  # ROS 1
        return get_rosbag_info(path)




# Helper to deserialize a ROS time (uint32 seconds, uint32 nanoseconds)
def _read_ros_time(data: bytes) -> int:
    """Converts 8 bytes of ROS time to nanoseconds."""
    seconds, nanoseconds = struct.unpack('<LL', data)
    return seconds * 1_000_000_000 + nanoseconds


def _read_header(f: BinaryIO) -> Dict[str, bytes]:
    """Reads a rosbag record header, which is a key-value store."""
    header = {}
    try:
        header_len = struct.unpack('<L', f.read(4))[0]
        header_data = f.read(header_len)

        pos = 0
        while pos < header_len:
            field_len = struct.unpack_from('<L', header_data, pos)[0]
            pos += 4

            # Partition the field into 'key=value'
            key, sep, value = header_data[pos: pos + field_len].partition(b'=')
            if not sep:
                raise ValueError("Invalid header field format")

            header[key.decode('utf-8')] = value
            pos += field_len

    except (struct.error, IndexError, ValueError) as e:
        raise IOError("Failed to parse rosbag header record.") from e

    return header


def get_rosbag_info(bag_path: Path) -> Dict:
    """
    Rapidly extracts topic names and duration from a ROS1 bag.

    Args:
        bag_path: Path to the .bag file.

    Returns:
        A dictionary with 'topics' (a set of names) and 'duration_s' (in seconds).
    """
    min_start_ns = float('inf')
    max_end_ns = float('-inf')
    topics: Set[str] = set()

    with open(bag_path, 'rb') as f:
        # 1. Verify it's a ROS Bag
        magic = f.readline().strip()
        if magic != b'#ROSBAG V2.0':
            raise ValueError(f"Not a valid ROSBAG v2.0 file: {bag_path}")

        # 2. Read the main bag header to find the index position
        bag_header = _read_header(f)
        index_pos = int.from_bytes(bag_header['index_pos'], 'little')
        conn_count = int.from_bytes(bag_header['conn_count'], 'little')
        chunk_count = int.from_bytes(bag_header['chunk_count'], 'little')

        if index_pos == 0:
            raise ValueError("Bag is not indexed. Cannot read metadata.")

        # 3. Seek to the start of the index records
        f.seek(index_pos)

        # 4. Read all CONNECTION records to get topic names
        for _ in range(conn_count):
            # Each connection has a header and a data record (which is also a header)
            conn_header = _read_header(f)
            topics.add(conn_header['topic'].decode('utf-8'))
            _read_header(f)  # Skip the data record, we don't need msg_def

        # 5. Read all CHUNK_INFO records to get start/end times
        for _ in range(chunk_count):
            chunk_info_header = _read_header(f)

            # The actual connection counts are in the data part of the record
            data_len = struct.unpack('<L', f.read(4))[0]
            # We don't need to parse the counts, just skip the data
            f.seek(data_len, 1)

            # Extract times from the header
            start_time = _read_ros_time(chunk_info_header['start_time'])
            end_time = _read_ros_time(chunk_info_header['end_time'])

            if start_time < min_start_ns:
                min_start_ns = start_time
            if end_time > max_end_ns:
                max_end_ns = end_time

    duration_ns = max_end_ns - min_start_ns if chunk_count > 0 else 0

    return {
        'topics': topics,
        'duration_s': duration_ns / 1_000_000_000.0,
        'start_time_ns': int(min_start_ns),
        'end_time_ns': int(max_end_ns),
    }