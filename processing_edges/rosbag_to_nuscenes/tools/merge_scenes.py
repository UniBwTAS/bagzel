# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import threading
import argparse

global COUNTER
COUNTER = 0
counter_lock = threading.Lock()


# Alphanumeric generator starting from "b" + 31 zeros
def generate_token():
    global COUNTER
    with counter_lock:
        num = COUNTER
        COUNTER += 1
    prefix = 'b'
    rest = format(num, '0>31').lower()
    return prefix + rest


# Read token list
def load_tokens(path):
    with open(path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

# Recursive token replacement
def replace_tokens(data, token_map):
    if isinstance(data, dict):
        return {k: replace_tokens(v, token_map) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_tokens(v, token_map) for v in data]
    elif isinstance(data, str) and data in token_map:
        return token_map[data]
    return data

def merge_sensor_json(sensor_jsons):
    merged = []
    seen_tokens = set()

    for sensor_path in sensor_jsons:
        with open(sensor_path, 'r') as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"Error loading {sensor_path}: {e}")
                continue

            for entry in data:
                token = entry.get("token")
                if token and token not in seen_tokens:
                    seen_tokens.add(token)
                    merged.append(entry)

    return merged

def merge_scenes(scene_dirs, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    output_json_data = defaultdict(list)
    i = 0
    print("Processing scenes...")
    token_list = []

    #function caching
    link = os.link
    mkdir = os.makedirs

    for scene_dir in tqdm(scene_dirs):
        # status update

        scene_path = Path(scene_dir)
        tokens_file = scene_path / 'tokens.txt'

        old_tokens = load_tokens(tokens_file)

        scene_token_map = {}
        for old in old_tokens:
            token = generate_token()
            scene_token_map[old] = token
            token_list.append(token)


        # Process JSON files
        for json_file in (scene_path / "v1.0-mini").glob("*.json"):
            # sensors must be handled separately
            if json_file.name == "sensor.json":
                continue
            with open(json_file, 'r') as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print(f"Error reading {json_file}: {e}")
                    continue
                updated_data = replace_tokens(data, scene_token_map)
                output_json_data[json_file.name].extend(updated_data)

        for folder in ['samples', 'sweeps']:
            src_folder = scene_path / folder

            for sensor_dir in src_folder.iterdir():
                dest_sensor_dir = Path(output_dir) / folder / sensor_dir.name
                mkdir(dest_sensor_dir, exist_ok=True)  # faster than Path.mkdir in loops

                for file in sensor_dir.iterdir():
                    dest_file = dest_sensor_dir / file.name
                    try:
                        link(file, dest_file)
                    except FileExistsError:
                        # File already hardlinked, skip
                        continue
                    except OSError as e:
                        print(f"Failed to link {file} → {dest_file}: {e}")


    print("\nWriting merged JSON files...")

    # Write merged JSON
    output_json_path = Path(output_dir) / "v1.0-mini"
    output_json_path.mkdir(parents=True, exist_ok=True)
    for name, merged_data in output_json_data.items():
        with open(output_json_path / name, 'w') as f:
            json.dump(merged_data, f, indent=2)

    # Collect all sensor.json paths
    sensor_jsons = []

    for scene_dir in scene_dirs:
        scene_path = Path(scene_dir)
        sensor_file = scene_path / "v1.0-mini" / "sensor.json"
        sensor_jsons.append(sensor_file)

    # Merge them
    merged_sensor = merge_sensor_json(sensor_jsons)

    # Write the merged sensor.json
    output_json_path = Path(output_dir) / "v1.0-mini"
    output_json_path.mkdir(parents=True, exist_ok=True)
    with open(output_json_path / "sensor.json", 'w') as f:
        json.dump(merged_sensor, f, indent=2)


    # Write the merged tokens.txt
    with open(Path(output_dir) / "tokens.txt", 'w') as f:
        for token in token_list:
            f.write(f"{token}\n")

    print(f"\nDone. Merged dataset written to: {output_dir}")



def merge_scenes_mulithread(scene_dirs, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    output_json_data = defaultdict(list)
    token_list = []

    link = os.link
    mkdir = os.makedirs

    def process_scene(scene_dir):
        scene_path = Path(scene_dir)
        tokens_file = scene_path / 'tokens.txt'

        old_tokens = load_tokens(tokens_file)

        scene_token_map = {}
        local_tokens = []

        for old in old_tokens:
            token = generate_token()
            scene_token_map[old] = token
            local_tokens.append(token)

        local_json_data = defaultdict(list)

        # Process JSON files
        for json_file in (scene_path / "v1.0-mini").glob("*.json"):
            if json_file.name == "sensor.json":
                continue
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Error reading {json_file}: {e}")
                continue
            updated_data = replace_tokens(data, scene_token_map)
            local_json_data[json_file.name].extend(updated_data)

        # Process sensor/sample/sweep files
        for folder in ['samples', 'sweeps']:
            src_folder = scene_path / folder
            for sensor_dir in src_folder.iterdir():
                dest_sensor_dir = Path(output_dir) / folder / sensor_dir.name
                mkdir(dest_sensor_dir, exist_ok=True)
                for file in sensor_dir.iterdir():
                    dest_file = dest_sensor_dir / file.name
                    try:
                        link(file, dest_file)
                    except FileExistsError:
                        continue
                    except OSError as e:
                        print(f"Failed to link {file} → {dest_file}: {e}")

        return local_json_data, local_tokens

    print("Processing scenes...")
    max_workers = min(32, (os.cpu_count() or 4) * 2)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_scene, sd): sd for sd in scene_dirs}
        for future in tqdm(as_completed(futures), total=len(futures)):
            scene_json_data, scene_tokens = future.result()
            for k, v in scene_json_data.items():
                output_json_data[k].extend(v)
            token_list.extend(scene_tokens)

    print("\nWriting merged JSON files...")
    output_json_path = Path(output_dir) / "v1.0-mini"
    output_json_path.mkdir(parents=True, exist_ok=True)

    for name, merged_data in output_json_data.items():
        with open(output_json_path / name, 'w') as f:
            json.dump(merged_data, f, indent=2)

    # Merge sensor.json files
    sensor_jsons = [Path(scene) / "v1.0-mini" / "sensor.json" for scene in scene_dirs]
    merged_sensor = merge_sensor_json(sensor_jsons)
    with open(output_json_path / "sensor.json", 'w') as f:
        json.dump(merged_sensor, f, indent=2)

    # Write tokens
    with open(Path(output_dir) / "tokens.txt", 'w') as f:
        for token in token_list:
            f.write(f"{token}\n")

    print(f"\nDone. Merged dataset written to: {output_dir}")


def checkDirectory(path, n=40):
    # there is a subfolder "samples" and "sweeps".
    # each subfolder of "samples" should have >= n files

    if not os.path.isdir(path):
        return False

    if not os.path.isfile(os.path.join(full_path, "tokens.txt")):
        return False

    samples_path = os.path.join(path, "samples")
    if not os.path.isdir(samples_path):
        return False

    if len(os.listdir(samples_path)) == 0:
        return False

    for sensor in os.listdir(samples_path):
        sensor_path = os.path.join(samples_path, sensor)
        if os.path.isdir(sensor_path):
            files = os.listdir(sensor_path)
            if len(files) < n:
                return False

    #check if other files exist too? like all json files?

    return True

#idk why there are duplicates
#and idk why the previous script breaks on them
#BUT, one of the duplicates has a sample_data.json with an empty token

def filter_duplicates(directories):
    unique_dirs = []
    seen = set()

    for dir in directories:
        identifier = os.path.basename(os.path.dirname(dir))  # Get parent directory name, which is the scene-name /rosbag-stamp + scene-stamp

        if identifier not in seen:
            seen.add(identifier)
            unique_dirs.append(dir)

    return unique_dirs

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Merge scenes from directories containing tokens.txt")
    parser.add_argument(
        "--base_path",
        type=str,
        default="tas_nuscenes3",
        help="Base directory containing scene directories"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="tas_nuscenes_merged",
        help="Directory where merged scenes will be saved"
    )

    args = parser.parse_args()

    directories = []
    print("Collecting scene directories...")
    # List all entries inside base_path
    base_path = args.base_path
    bag_dirs = os.listdir(base_path)

    for bag in bag_dirs:

        fulL_bag_path = os.path.join(args.base_path, bag)

        for scene in os.listdir(fulL_bag_path):
            # print(scene)
            scene_path = os.path.join(fulL_bag_path, scene)

            # Check if it's a directory and contains tokens.txt
            # We assume it's a valid scene directory if
            # it always has a v1.0-mini folder inside
            full_path = os.path.join(scene_path, "v1.0-mini")
            if checkDirectory(full_path, 40):
                directories.append(full_path)


    print(f"Found {len(directories)} scene directories to merge.")

    directories = filter_duplicates(directories)
    print(f"{len(directories)} unique scene directories after filtering duplicates.")

    print("Starting merge...")
    merge_scenes_mulithread(directories, args.output_dir)
    print(f"Merged scenes saved to {args.output_dir}")
