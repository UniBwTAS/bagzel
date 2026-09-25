#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Anton Backhaus <anton.backhaus@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0
"""Backfill ego_pose_global.json for a dataset that was converted BEFORE the
converter emitted it natively.

For each recording in <dataroot>/<version> that has a source bag, parse the raw
OxTS NCOM stream, nearest-join to that recording's existing ego_pose rows
(bag-receive clock), and emit one ego_pose_global row per ego_pose (same token).
Resumable (per-recording partials); sequential (one bag at a time) to stay gentle
on shared storage. Reuses the converter's validated parser/builder:
  src/datahandler/ncom_parser.py   (NComDecoder)
  src/datahandler/ego_pose_global.py (build_record)

Run in an env with: rosbags, pyproj, scipy, numpy, nuscenes-devkit.

  python backfill_ego_pose_global.py <dataroot> --version v1.0-mini \
      --streams-root /mnt/beegfs/ssd/lrt81/streams --workdir /tmp/egoglobal --write
"""
import argparse
import bisect
import glob
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from rosbags.highlevel import AnyReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from datahandler.ncom_parser import NComDecoder            # noqa: E402
from datahandler.ego_pose_global import build_record       # noqa: E402

NCOM_TOPIC = "/bus/oxts/eth_ncom/bus_to_host"
MAX_JOIN_MS = 100.0
GPSX = {0: "NONE", 3: "SPS", 4: "DIFF", 5: "RTK_FLOAT", 6: "RTK_INT"}


def scene_base(name):
    m = re.match(r"^(.*)_(\d+)$", name)
    return m.group(1) if m else name


def bag_stem(p):
    b = os.path.basename(p)
    if b.endswith((".mcap", ".db3")):
        return os.path.basename(os.path.dirname(p)).split(".")[0]
    return b.rsplit(".", 1)[0]


def bag_open_path(p):
    return os.path.dirname(p) if p.endswith((".mcap", ".db3")) else p


def build_bag_index(streams_root, cache_file):
    if cache_file.exists():
        return cache_file.read_text().splitlines()
    paths = []
    for ext in ("*.mcap", "*.bag", "*.db3"):
        paths += glob.glob(os.path.join(streams_root, "**", ext), recursive=True)
    cache_file.write_text("\n".join(paths))
    return paths


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataroot", type=Path)
    ap.add_argument("--version", default="v1.0-mini")
    ap.add_argument("--streams-root", type=Path, required=True, help="root to glob for source bags")
    ap.add_argument("--workdir", type=Path, required=True, help="dir for partials + cache (resumable)")
    ap.add_argument("--write", action="store_true", help="write ego_pose_global.json into the version dir")
    return ap.parse_args()


def main():
    args = parse_args()
    meta = args.dataroot / args.version
    partials = args.workdir / "partials"
    partials.mkdir(parents=True, exist_ok=True)

    # stem -> bag paths
    stem2paths = defaultdict(list)
    for line in build_bag_index(args.streams_root, args.workdir / "bag_index.txt"):
        line = line.strip()
        if line:
            stem2paths[bag_stem(line)].append(line)

    def resolve_bag(rec):
        if rec in stem2paths:
            return stem2paths[rec]
        for suf in ("_utc_psync", "_psync", "_Freiheit", "_freiheit"):
            if rec.endswith(suf) and rec[:-len(suf)] in stem2paths:
                return stem2paths[rec[:-len(suf)]]
        return []

    # recording -> {ego_pose_token: timestamp_us} via NuScenes (built once, cached)
    cache = args.workdir / "rec_ego.json"
    if cache.exists():
        rec2ego = json.loads(cache.read_text())
    else:
        from nuscenes import NuScenes
        print(f"[setup] loading NuScenes {args.version}", flush=True)
        nusc = NuScenes(args.version, dataroot=str(args.dataroot), verbose=False)
        base_by_scene = {s["token"]: scene_base(s["name"]) for s in nusc.scene}
        sample2base = {s["token"]: base_by_scene[s["scene_token"]] for s in nusc.sample}
        ego_ts = {e["token"]: int(e["timestamp"]) for e in nusc.ego_pose}
        rec2ego = defaultdict(dict)
        for sd in nusc.sample_data:
            base = sample2base.get(sd["sample_token"])
            ep = sd.get("ego_pose_token")
            if base and ep in ego_ts:
                rec2ego[base][ep] = ego_ts[ep]
        rec2ego = dict(rec2ego)
        cache.write_text(json.dumps(rec2ego))
    print(f"[setup] {len(rec2ego)} recordings, {sum(len(v) for v in rec2ego.values())} ego_pose rows", flush=True)

    todo = [r for r in sorted(rec2ego) if resolve_bag(r)]
    unmatched = [r for r in rec2ego if not resolve_bag(r)]
    print(f"[setup] recordings={len(rec2ego)} with-bag={len(todo)} unmatched={len(unmatched)}", flush=True)

    for i, rec in enumerate(todo):
        out = partials / (rec.replace("/", "_") + ".json")
        if out.exists():
            continue
        bag = max(resolve_bag(rec), key=lambda p: os.path.getsize(p))  # ambiguous -> largest
        ego = rec2ego[rec]
        t0 = time.time()
        dec = NComDecoder(); ncom = []
        try:
            with AnyReader([Path(bag_open_path(bag))]) as reader:
                conns = [c for c in reader.connections if c.topic == NCOM_TOPIC]
                if not conns:
                    out.write_text(json.dumps({"recording": rec, "bag": bag, "error": "no NCOM topic", "rows": []}))
                    print(f"[{i+1}/{len(todo)}] {rec}: NO NCOM topic", flush=True)
                    continue
                for conn, ts, rd in reader.messages(connections=conns):
                    r = dec.feed(reader.deserialize(rd, conn.msgtype).payload, ts)
                    if r:
                        ncom.append(r)
        except Exception as e:
            out.write_text(json.dumps({"recording": rec, "bag": bag, "error": repr(e)[:300], "rows": []}))
            print(f"[{i+1}/{len(todo)}] {rec}: ERROR {repr(e)[:120]}", flush=True)
            continue
        ncom.sort(key=lambda r: r["bag_ts_ns"])
        nts = [r["bag_ts_ns"] for r in ncom]
        rows = []; gaps = 0
        for tok, ts_us in ego.items():
            t_ns = int(ts_us) * 1000
            j = bisect.bisect_left(nts, t_ns)
            cands = [k for k in (j - 1, j) if 0 <= k < len(nts)]
            if not cands or abs(nts[min(cands, key=lambda k: abs(nts[k] - t_ns))] - t_ns) / 1e6 > MAX_JOIN_MS:
                gaps += 1
                continue
            k = min(cands, key=lambda k: abs(nts[k] - t_ns))
            rows.append(build_record(tok, ncom[k], int(ts_us)))
        out.write_text(json.dumps({"recording": rec, "bag": bag, "n_ego": len(ego), "n_rows": len(rows),
                                   "gaps": gaps, "corrupt_pkts": dec.n_out_of_range,
                                   "checksum_fail": dec.n_checksum_fail, "bad_attitude": dec.n_bad_attitude,
                                   "null_island": dec.n_null_island, "rows": rows}))
        print(f"[{i+1}/{len(todo)}] {rec}: {len(rows)}/{len(ego)} rows, gaps={gaps}, "
              f"fix={dict(Counter(r['fix_status'] for r in rows))}, {time.time()-t0:.0f}s", flush=True)

    # aggregate + integrity + report
    allrows, errors = [], {}
    for p in sorted(partials.glob("*.json")):
        d = json.loads(p.read_text())
        (errors.__setitem__(d["recording"], d["error"]) if d.get("error") else allrows.extend(d["rows"]))
    ego_tokens = {e["token"] for e in json.loads((meta / "ego_pose.json").read_text())}
    toks = [r["token"] for r in allrows]
    dup = len(toks) - len(set(toks))
    foreign = sum(1 for t in set(toks) if t not in ego_tokens)
    fix = Counter(r["fix_status"] for r in allrows)
    rtk = sum(v for k, v in fix.items() if k in (5, 6))
    print(f"\n=== aggregate ({args.version}) ===")
    print(f"  rows={len(allrows)} unique={len(set(toks))} dup={dup} foreign={foreign} | errors={len(errors)}")
    print("  fix: " + ", ".join(f"{GPSX.get(k,k)}={v}" for k, v in fix.most_common())
          + f" | RTK {100*rtk/max(1,len(allrows)):.1f}%")
    if errors:
        print("  no-data recordings: " + ", ".join(sorted(errors)))
    if args.write:
        if dup or foreign:
            raise SystemExit("refusing to write: duplicate or foreign tokens")
        out_file = meta / "ego_pose_global.json"
        if out_file.exists():
            shutil.move(out_file, str(out_file) + ".bak")
        out_file.write_text(json.dumps(sorted(allrows, key=lambda r: r["timestamp"]), indent=2) + "\n")
        print(f"  WROTE {len(allrows)} rows -> {out_file}")
    else:
        print("  (dry run; pass --write to emit ego_pose_global.json)")


if __name__ == "__main__":
    main()
