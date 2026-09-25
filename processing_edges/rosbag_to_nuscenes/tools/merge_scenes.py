# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import math
import os
import re
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import threading
import argparse
import csv
import uuid

try:
    import orjson
except ImportError:
    orjson = None

# --- Bag-distance splitting -------------------------------------------------
# Rosbags whose ego-traveled distance exceeds SPLIT_THRESHOLD_M get sliced
# into N-way virtual sub-scenes (A, B, C, ...) at merge time. Downstream map-
# render steps blow past OpenCV's CV_IO_MAX_IMAGE_PIXELS cap and PatchWork++
# starts hanging when the gridmap covers too much area; splitting upstream
# keeps each sub-scene under the rasterized-area budget.
#
# SCENE_CHUNK_STEP_SEC mirrors EXTRACTION.scene_length_sec used by
# rosbag_to_nuscenes.py (lines 285-293) to generate the original _<seconds>
# chunk suffix. Per-sub renumbering uses the same step starting from 0.
SPLIT_THRESHOLD_M = 5000.0
SCENE_CHUNK_STEP_SEC = 20
_CHUNK_TRAILING_INT_RE = re.compile(r"_(\d+)$")
_SUBSCENE_LETTER_RE = re.compile(r"_[A-Z]$")

def generate_token():
    return uuid.uuid4().hex


# Read token list
def load_tokens(path):
    with open(path, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def load_json(path):
    with open(path, 'rb') as f:
        if orjson is not None:
            return orjson.loads(f.read())
        return json.load(f)


def dump_json(path, data):
    with open(path, 'wb') as f:
        if orjson is not None:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        else:
            f.write(json.dumps(data, indent=2).encode('utf-8'))

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
        try:
            data = load_json(sensor_path)
        except Exception as e:
            print(f"Error loading {sensor_path}: {e}")
            continue

        for entry in data:
            token = entry.get("token")
            if token and token not in seen_tokens:
                seen_tokens.add(token)
                merged.append(entry)

    return merged

def merge_scenes(scene_dirs, output_dir, version_dir="v1.0-mini"):
    os.makedirs(output_dir, exist_ok=True)
    output_json_data = defaultdict(list)
    i = 0
    print("Processing scenes...")
    token_list = []
    created_dirs = set()

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
        for json_file in (scene_path / version_dir).glob("*.json"):
            # sensors must be handled separately
            if json_file.name == "sensor.json":
                continue
            try:
                data = load_json(json_file)
            except Exception as e:
                print(f"Error reading {json_file}: {e}")
                continue
            updated_data = replace_tokens(data, scene_token_map)
            output_json_data[json_file.name].extend(updated_data)

        for folder in ['samples', 'sweeps']:
            src_folder = scene_path / folder

            with os.scandir(src_folder) as sensor_dirs:
                for sensor_dir in sensor_dirs:
                    if not sensor_dir.is_dir():
                        continue
                    dest_sensor_dir = Path(output_dir) / folder / sensor_dir.name
                    if dest_sensor_dir not in created_dirs:
                        mkdir(dest_sensor_dir, exist_ok=True)
                        created_dirs.add(dest_sensor_dir)

                    with os.scandir(sensor_dir.path) as files:
                        for file in files:
                            if not file.is_file():
                                continue
                            dest_file = dest_sensor_dir / file.name
                            try:
                                link(file.path, dest_file)
                            except FileExistsError:
                                # File already hardlinked, skip
                                continue
                            except OSError as e:
                                print(f"Failed to link {file.path} → {dest_file}: {e}")

        can_bus_src = scene_path / "can_bus"
        can_bus_dest = Path(output_dir) / "can_bus"
        if can_bus_src.is_dir():
            if can_bus_dest not in created_dirs:
                mkdir(can_bus_dest, exist_ok=True)
                created_dirs.add(can_bus_dest)

            with os.scandir(can_bus_src) as can_files:
                for can_file in can_files:
                    if not can_file.is_file():
                        continue
                    dest_file = can_bus_dest / can_file.name
                    try:
                        link(can_file.path, dest_file)
                    except FileExistsError:
                        continue
                    except OSError as e:
                        print(f"Failed to link {can_file.path} → {dest_file}: {e}")


    print("\nWriting merged JSON files...")

    # Write merged JSON
    output_json_path = Path(output_dir) / version_dir
    output_json_path.mkdir(parents=True, exist_ok=True)
    for name, merged_data in output_json_data.items():
        dump_json(output_json_path / name, merged_data)

    # Collect all sensor.json paths
    sensor_jsons = []

    for scene_dir in scene_dirs:
        scene_path = Path(scene_dir)
        sensor_file = scene_path / version_dir / "sensor.json"
        sensor_jsons.append(sensor_file)

    # Merge them
    merged_sensor = merge_sensor_json(sensor_jsons)

    # Write the merged sensor.json
    output_json_path = Path(output_dir) / version_dir
    output_json_path.mkdir(parents=True, exist_ok=True)
    dump_json(output_json_path / "sensor.json", merged_sensor)


    # Write the merged tokens.txt
    with open(Path(output_dir) / "tokens.txt", 'w') as f:
        for token in token_list:
            f.write(f"{token}\n")

    print(f"\nDone. Merged dataset written to: {output_dir}")



def merge_scenes_mulithread(scene_dirs, output_dir, version_dir="v1.0-mini", rename_map=None):
    os.makedirs(output_dir, exist_ok=True)
    output_json_data = defaultdict(list)
    token_list = []
    created_dirs = set()
    created_dirs_lock = threading.Lock()
    # Original chunk basename -> new name (e.g. '<bag>_A_20'). Used to rewrite
    # scene.json's 'name' field for over-long bags split into sub-scenes.
    rename_map = rename_map or {}

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

        # If this chunk's bag was over the distance threshold, look up its
        # sub-scene name. Applied to scene.json's 'name' field below; all other
        # tables reference scenes by token (UUID), so no further rewrites.
        chunk_basename = scene_path.parent.name
        new_scene_name = rename_map.get(chunk_basename)

        # Process JSON files
        for json_file in (scene_path / version_dir).glob("*.json"):
            if json_file.name == "sensor.json":
                continue
            try:
                data = load_json(json_file)
            except Exception as e:
                print(f"Error reading {json_file}: {e}")
                continue
            if json_file.name == "scene.json" and new_scene_name is not None:
                for entry in data:
                    if entry.get("name") == chunk_basename:
                        entry["name"] = new_scene_name
            updated_data = replace_tokens(data, scene_token_map)
            local_json_data[json_file.name].extend(updated_data)

        # Process sensor/sample/sweep files
        for folder in ['samples', 'sweeps']:
            src_folder = scene_path / folder
            with os.scandir(src_folder) as sensor_dirs:
                for sensor_dir in sensor_dirs:
                    if not sensor_dir.is_dir():
                        continue
                    dest_sensor_dir = Path(output_dir) / folder / sensor_dir.name
                    if dest_sensor_dir not in created_dirs:
                        with created_dirs_lock:
                            if dest_sensor_dir not in created_dirs:
                                mkdir(dest_sensor_dir, exist_ok=True)
                                created_dirs.add(dest_sensor_dir)
                    with os.scandir(sensor_dir.path) as files:
                        for file in files:
                            if not file.is_file():
                                continue
                            dest_file = dest_sensor_dir / file.name
                            try:
                                link(file.path, dest_file)
                            except FileExistsError:
                                continue
                            except OSError as e:
                                print(f"Failed to link {file.path} → {dest_file}: {e}")

        can_bus_src = scene_path / "can_bus"
        can_bus_dest = Path(output_dir) / "can_bus"
        if can_bus_src.is_dir():
            if can_bus_dest not in created_dirs:
                with created_dirs_lock:
                    if can_bus_dest not in created_dirs:
                        mkdir(can_bus_dest, exist_ok=True)
                        created_dirs.add(can_bus_dest)

            with os.scandir(can_bus_src) as can_files:
                for can_file in can_files:
                    if not can_file.is_file():
                        continue
                    dest_file = can_bus_dest / can_file.name
                    try:
                        link(can_file.path, dest_file)
                    except FileExistsError:
                        continue
                    except OSError as e:
                        print(f"Failed to link {can_file.path} → {dest_file}: {e}")

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
    output_json_path = Path(output_dir) / version_dir
    output_json_path.mkdir(parents=True, exist_ok=True)

    for name, merged_data in output_json_data.items():
        json_path = output_json_path / name
        dump_json(json_path, merged_data)
        os.chmod(json_path, 0o644)

    # Merge sensor.json files
    sensor_jsons = [Path(scene) / version_dir / "sensor.json" for scene in scene_dirs]
    merged_sensor = merge_sensor_json(sensor_jsons)
    sensor_path = output_json_path / "sensor.json"
    dump_json(sensor_path, merged_sensor)
    os.chmod(sensor_path, 0o644)

    # Write tokens
    tokens_path = Path(output_dir) / "tokens.txt"
    with open(tokens_path, 'w') as f:
        for token in token_list:
            f.write(f"{token}\n")
    os.chmod(tokens_path, 0o644)

    print(f"\nDone. Merged dataset written to: {output_dir}")


def checkDirectory(path, n=40):
    # there is a subfolder "samples" and "sweeps".
    # each subfolder of "samples" should have >= n files

    if not os.path.isdir(path):
        return False

    if not os.path.isfile(os.path.join(path, "tokens.txt")):
        return False

    samples_path = os.path.join(path, "samples")
    if not os.path.isdir(samples_path):
        return False

    has_sensor_dir = False
    with os.scandir(samples_path) as sensors:
        for sensor in sensors:
            if not sensor.is_dir():
                continue
            has_sensor_dir = True
            file_count = 0
            with os.scandir(sensor.path) as files:
                for file in files:
                    if file.is_file():
                        file_count += 1
            if file_count < n:
                return False

    if not has_sensor_dir:
        return False

    #check if other files exist too? like all json files?

    return True

def get_scene_file_list(scene_dir):
    scene_path = Path(scene_dir)
    file_list = []

    for folder in ['samples', 'sweeps']:
        src_folder = scene_path / folder
        with os.scandir(src_folder) as sensors:
            for sensor_dir in sensors:
                if not sensor_dir.is_dir():
                    continue
                with os.scandir(sensor_dir.path) as files:
                    for file in files:
                        if file.is_file():
                            file_list.append(str(Path(folder) / sensor_dir.name / file.name))

    can_bus_dir = scene_path / "can_bus"
    if can_bus_dir.is_dir():
        with os.scandir(can_bus_dir) as can_files:
            for can_file in can_files:
                if can_file.is_file():
                    file_list.append(str(Path("can_bus") / can_file.name))

    file_list.sort()
    return file_list


def filter_duplicates(directories):
    unique_dirs = []
    seen_scene_files = set()
    seen_files = set()

    max_workers = min(32, (os.cpu_count() or 4) * 2)
    scene_files_by_dir = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_scene_file_list, dir): dir for dir in directories}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Filtering duplicates"):
            dir = futures[future]
            scene_files_by_dir[dir] = future.result()

    for dir in directories:
        scene_files = scene_files_by_dir[dir]
        scene_signature = tuple(scene_files)

        if scene_signature in seen_scene_files:
            continue

        if any(file in seen_files for file in scene_files):
            continue

        seen_scene_files.add(scene_signature)
        seen_files.update(scene_files)
        unique_dirs.append(dir)

    return unique_dirs


SCENES_CSV_FIELDS = [
    "scene",
    "date_processed",
    "num_keyframes",
    "duration",
    "distance_traveled",
    "num_bounding_boxes",
    "num_semantic_tiles",
    "urban/offroad",
    "boring",
]


def empty_scene_csv_row(scene_name):
    row = {field: "" for field in SCENES_CSV_FIELDS}
    row["scene"] = scene_name
    return row


def read_scene_names_from_csv(scenes_csv_path):
    if not scenes_csv_path.exists():
        return []

    with open(scenes_csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []

        scene_names = []
        for row in reader:
            scene_name = row.get("scene", "").strip()
            if scene_name and scene_name != "sum":
                scene_names.append(scene_name)
        return scene_names


def write_scenes_csv(scenes_csv_path, scene_names):
    unique_scene_names = sorted(dict.fromkeys(scene_names))
    rows = [empty_scene_csv_row("sum")]
    rows.extend(empty_scene_csv_row(scene_name) for scene_name in unique_scene_names)

    scenes_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(scenes_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCENES_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

# --- Bag-distance splitting helpers -----------------------------------------

def get_scene_name(scene_dir) -> str:
    """Base scene name from a chunk version-dir path.

    The chunk dir is named '<bag>_<N>' where N is the integer time-offset
    suffix added by rosbag_to_nuscenes.py. The 'scene' is everything before
    that suffix.
    """
    parent_name = Path(scene_dir).parent.name
    if "_" in parent_name:
        return "_".join(parent_name.split("_")[:-1])
    return parent_name


def _chunk_trailing_int(name: str) -> int:
    """Return the integer suffix N from a chunk dir basename like '<bag>_<N>'."""
    m = _CHUNK_TRAILING_INT_RE.search(name)
    return int(m.group(1)) if m else 0


def order_chunks_by_time(chunk_dirs):
    """Return chunk dirs sorted chronologically by their trailing _<int> suffix.

    chunk_dirs are version-dir paths (e.g. '<bag>_<N>/v1.0-mini'); the
    chronologically-ordering suffix lives on the parent name.
    """
    return sorted(chunk_dirs, key=lambda d: _chunk_trailing_int(Path(d).parent.name))


def chunk_distance_m(chunk_dir, version_dir="v1.0-mini") -> float:
    """Sum of Euclidean distances between successive ego_pose translations.

    On-disk layout per chunk:
        <bag>_<N>/
          v1.0-mini/           <- chunk_dir
            tokens.txt
            samples/  sweeps/  can_bus/
            v1.0-mini/         <- nuScenes metadata json
              ego_pose.json    <- read this
              scene.json
              ...

    chunk_dir is the OUTER v1.0-mini (matching the paths the merge code
    threads around); the metadata jsons live one level deeper at
    chunk_dir/<version_dir>/. Poses are not chronologically ordered in the
    file, so sort by timestamp before differencing.
    """
    ego_pose_path = Path(chunk_dir) / version_dir / "ego_pose.json"
    if not ego_pose_path.is_file():
        return 0.0
    try:
        poses = load_json(ego_pose_path)
    except Exception:
        return 0.0
    if not poses:
        return 0.0
    poses = sorted(poses, key=lambda p: p.get("timestamp", 0))
    total = 0.0
    prev = poses[0].get("translation")
    if not prev or len(prev) < 3:
        return 0.0
    for p in poses[1:]:
        t = p.get("translation")
        if not t or len(t) < 3:
            continue
        dx = t[0] - prev[0]
        dy = t[1] - prev[1]
        dz = t[2] - prev[2]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
        prev = t
    return total


def assign_subscene_labels(chunks_ordered, distances, threshold_m=SPLIT_THRESHOLD_M):
    """Allocate chunks into balanced N-way sub-scenes by cumulative distance.

    Returns a dict mapping chunk_dir -> (letter, seq_seconds), or empty dict
    if no split is needed (total distance below threshold, or only a single
    chunk so splitting would require slicing within a chunk).

    Algorithm: N = ceil(total / threshold_m), target = total / N. Walk chunks
    in order; chunk i goes to bucket min(N-1, floor(cumdist_before_i / target)).
    This keeps sub-scenes roughly equidistant without ever placing one chunk
    across two sub-scenes. Per-sub seq counters restart at 0 and step by
    SCENE_CHUNK_STEP_SEC.
    """
    total = sum(distances)
    if total <= threshold_m:
        return {}
    if len(chunks_ordered) <= 1:
        return {}
    n_subs = math.ceil(total / threshold_m)
    target = total / n_subs
    labels = {}
    sub_counters = [0] * n_subs
    cumdist = 0.0
    for chunk, dist in zip(chunks_ordered, distances):
        sub_idx = min(n_subs - 1, int(cumdist // target))
        letter = chr(ord("A") + sub_idx)
        seq = sub_counters[sub_idx] * SCENE_CHUNK_STEP_SEC
        sub_counters[sub_idx] += 1
        labels[chunk] = (letter, seq)
        cumdist += dist
    return labels


def build_rename_map(directories, version_dir):
    """Map original chunk basename ('<bag>_<N>') -> new name ('<bag>_<L>_<seq>').

    Groups directories by base scene name, computes per-chunk distance in
    parallel, and asks assign_subscene_labels which chunks (if any) need a
    sub-scene letter. Scenes that stay under the threshold do not appear in
    the returned map.
    """
    chunks_by_scene = defaultdict(list)
    for d in directories:
        chunks_by_scene[get_scene_name(d)].append(d)

    max_workers = min(32, (os.cpu_count() or 4) * 2)
    distances = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(chunk_distance_m, d, version_dir): d for d in directories}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Measuring bag distances"):
            d = futures[future]
            try:
                distances[d] = future.result()
            except Exception as e:
                print(f"Failed to compute distance for {d}: {e}")
                distances[d] = 0.0

    rename_map = {}
    split_summary = []
    for scene_name, chunks in chunks_by_scene.items():
        ordered = order_chunks_by_time(chunks)
        ordered_distances = [distances[c] for c in ordered]
        total = sum(ordered_distances)
        labels = assign_subscene_labels(ordered, ordered_distances)
        if not labels:
            if total > SPLIT_THRESHOLD_M:
                print(f"[warn] scene {scene_name} travels {total:.0f}m but cannot be "
                      f"split (only {len(chunks)} chunk(s)); will fall through with "
                      f"the same map-render risk that motivated splitting.")
            continue
        for chunk_dir, (letter, seq) in labels.items():
            old_basename = Path(chunk_dir).parent.name
            new_name = f"{scene_name}_{letter}_{seq}"
            rename_map[old_basename] = new_name
        n_subs = len({letter for letter, _ in labels.values()})
        split_summary.append((scene_name, total, n_subs, len(chunks)))

    if split_summary:
        print(f"Splitting {len(split_summary)} over-long scene(s) (>{SPLIT_THRESHOLD_M:.0f}m):")
        for scene_name, total, n_subs, n_chunks in split_summary:
            print(f"  {scene_name}: {total:.0f}m / {n_chunks} chunks -> {n_subs} sub-scenes")
    return rename_map


def scene_or_split_in_existing(base_name, existing_scenes) -> bool:
    """True if base_name or any '<base_name>_<letter>' sub-scene is in existing_scenes.

    Lets re-merging the same bag dedup correctly whether it was previously
    merged unsplit or split, including across format changes.
    """
    if base_name in existing_scenes:
        return True
    prefix = base_name + "_"
    expected_len = len(prefix) + 1
    for s in existing_scenes:
        if len(s) == expected_len and s.startswith(prefix) and "A" <= s[-1] <= "Z":
            return True
    return False


def subscene_name_from_new(new_chunk_name: str) -> str:
    """'<bag>_A_20' -> '<bag>_A'. Strip the trailing _<seq> suffix."""
    return _CHUNK_TRAILING_INT_RE.sub("", new_chunk_name)


# --- Main -------------------------------------------------------------------

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
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Only collect and count candidate scenes. Do not merge or link files."
    )
    parser.add_argument(
        "--reference_dataset_dir",
        type=str,
        default=None,
        help="Existing merged dataset used only for scenes.csv diff detection"
    )
    parser.add_argument(
        "--version",
        type=str,
        default="v1.0-mini",
        help="NuScenes metadata version directory to read and write"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="No-op the merge if <output_dir>/<version> already exists "
             "(downstream still runs via the afterok chain). Without this "
             "flag, an existing <version> dir is a hard error.",
    )

    args = parser.parse_args()

    directories = []
    print("Collecting scene directories...")
    base_path = args.base_path
    candidate_scene_dirs = []

    with os.scandir(base_path) as bag_entries:
        bag_dirs = [entry.path for entry in bag_entries if entry.is_dir()]

    for full_bag_path in tqdm(bag_dirs, desc="Scanning rosbags"):
        with os.scandir(full_bag_path) as scene_entries:
            for scene in scene_entries:
                if scene.is_dir():
                    candidate_scene_dirs.append(scene.path)

    for scene_path in tqdm(candidate_scene_dirs, desc="Checking scenes"):
        # Check if it's a directory and contains tokens.txt
        # We assume it's a valid scene directory if
        # it always has a version metadata folder inside
        full_path = os.path.join(scene_path, args.version)
        if checkDirectory(full_path, 40):
            directories.append(full_path)


    print(f"Found {len(directories)} scene directories to merge.")

    directories = filter_duplicates(directories)
    print(f"{len(directories)} unique scene directories after filtering duplicates.")

    version_dir = args.version
    if os.path.exists(os.path.join(args.output_dir, version_dir)):
        if args.resume:
            print(f"Metadata directory {version_dir} already exists at "
                  f"{args.output_dir} and --resume was passed. Nothing to merge.")
            raise SystemExit(0)
        raise RuntimeError(
            f"Metadata directory {version_dir} already exists in output dataset: "
            f"{args.output_dir}. This indicates the orchestrator's bump-to-next-_N "
            f"logic failed to produce a fresh dir."
        )

    scenes_csv_path = Path(args.output_dir) / "scenes.csv"
    reference_dataset_dir = Path(args.reference_dataset_dir) if args.reference_dataset_dir else Path(args.output_dir)
    reference_scene_names = read_scene_names_from_csv(reference_dataset_dir / "scenes.csv")
    output_existing_scene_names = read_scene_names_from_csv(scenes_csv_path)
    existing_scenes = set(reference_scene_names)

    # Detect over-long bags and assign sub-scene letters (A/B/C/...) before any
    # rewriting. Empty for bags under SPLIT_THRESHOLD_M. See module docstring.
    rename_map = build_rename_map(directories, version_dir)

    directories_to_merge = []
    new_scene_names = set()
    for d in directories:
        scene_name = get_scene_name(d)
        if scene_or_split_in_existing(scene_name, existing_scenes):
            continue
        directories_to_merge.append(d)
        chunk_basename = Path(d).parent.name
        new_name = rename_map.get(chunk_basename)
        if new_name is not None:
            new_scene_names.add(subscene_name_from_new(new_name))
        else:
            new_scene_names.add(scene_name)
    directories = directories_to_merge

    print(f"{len(directories)} unique scene directories after filtering existing scenes.")

    if not directories:
        print("No new scenes to merge.")
        raise SystemExit(0)

    if args.dry_run:
        print("Dry run enabled. No files were linked or written.")
        if rename_map:
            print(f"Rename map ({len(rename_map)} chunks across "
                  f"{len({subscene_name_from_new(v) for v in rename_map.values()})} sub-scenes):")
            for old in sorted(rename_map):
                print(f"  {old}  ->  {rename_map[old]}")
        else:
            print("No bags exceeded the split threshold; rename map is empty.")
        raise SystemExit(0)

    print("Starting merge...")
    merge_scenes_mulithread(directories, args.output_dir, version_dir, rename_map=rename_map)
    print(f"Merged scenes saved to {args.output_dir}")

    write_scenes_csv(scenes_csv_path, output_existing_scene_names + list(new_scene_names))
    print(f"Updated scenes.csv with {len(new_scene_names)} new scenes.")
