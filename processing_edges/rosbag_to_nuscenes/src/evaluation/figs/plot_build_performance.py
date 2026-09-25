#!/usr/bin/env python3
"""Create build-performance bar and scaling plots from benchmark CSVs.

Supported input schemas:
1) Tidy:
   method,mode,dataset_gb,time_s
2) Unified benchmark output:
   mode,phase,wall_s,status,command,...
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate grouped bar and scaling plots for build times."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-csv",
        type=Path,
        help="Single CSV file.",
    )
    input_group.add_argument(
        "--input-dir",
        type=Path,
        help="Directory containing CSV files. All *.csv files are loaded.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where figures are written.",
    )
    parser.add_argument(
        "--bar-dataset-gb",
        type=float,
        default=None,
        help="Dataset size for grouped bar chart. Defaults to largest size in CSV.",
    )
    parser.add_argument(
        "--title-prefix",
        default="Build Performance",
        help="Prefix for chart titles.",
    )
    parser.add_argument(
        "--dataset-gb",
        type=float,
        default=None,
        help=(
            "Dataset size in GB for unified benchmark CSVs that do not contain "
            "a dataset_gb column."
        ),
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["pdf"],
        help="Output formats, e.g. pdf png svg. Default: pdf",
    )
    parser.add_argument(
        "--y-scale",
        choices=["linear", "log"],
        default="linear",
        help="Y-axis scale for both plots. Default: linear",
    )
    parser.add_argument(
        "--error-bars",
        choices=["none", "minmax", "iqr"],
        default="minmax",
        help="Error bar style from repeated runs. Default: minmax",
    )
    return parser.parse_args()


def _infer_method_from_unified_row(row: dict[str, str]) -> str:
    mode = row.get("mode", "").strip().lower()
    if mode == "rosbag2nuscenes":
        return "rosbag2nuscenes"
    if mode == "bazel":
        cmd = row.get("command", "")
        if "--unix_digest_hash_attribute_name=user.bagzel_hash" in cmd:
            return "bagzel_xattr"
        return "bagzel"
    return mode or "unknown"


def load_rows(path: Path, dataset_gb_override: float | None) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        tidy_required = {"method", "mode", "dataset_gb", "time_s"}
        unified_required = {"mode", "phase", "wall_s"}

        if tidy_required.issubset(fieldnames):
            rows = [row for row in reader]
        elif unified_required.issubset(fieldnames):
            rows = []
            for row in reader:
                status = row.get("status", "").strip().upper()
                if status and status != "OK":
                    continue
                dataset_gb = row.get("dataset_gb", "").strip()
                if not dataset_gb:
                    if dataset_gb_override is None:
                        raise ValueError(
                            "Unified benchmark CSV has no 'dataset_gb' column. "
                            "Provide --dataset-gb."
                        )
                    dataset_gb = str(dataset_gb_override)
                rows.append(
                    {
                        "method": _infer_method_from_unified_row(row),
                        "mode": row["phase"],
                        "dataset_gb": dataset_gb,
                        "time_s": row["wall_s"],
                    }
                )
        else:
            msg = (
                "Unsupported CSV schema. Expected either "
                "['method','mode','dataset_gb','time_s'] or "
                "['mode','phase','wall_s',...]."
            )
            raise ValueError(msg)
    if not rows:
        raise ValueError("Input CSV is empty.")
    return rows


def resolve_input_csv_paths(input_csv: Path | None, input_dir: Path | None) -> list[Path]:
    if input_csv is not None:
        if not input_csv.is_file():
            raise ValueError(f"Input CSV does not exist: {input_csv}")
        return [input_csv]
    if input_dir is None or not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    paths = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    if not paths:
        raise ValueError(f"No CSV files found in directory: {input_dir}")
    return paths


def aggregate_stats(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str, float], dict[str, float]]:
    buckets: dict[tuple[str, str, float], list[float]] = defaultdict(list)
    for row in rows:
        key = (
            row["method"].strip(),
            row["mode"].strip().lower(),
            float(row["dataset_gb"]),
        )
        buckets[key].append(float(row["time_s"]))
    stats: dict[tuple[str, str, float], dict[str, float]] = {}
    for key, values in buckets.items():
        arr = np.array(values, dtype=float)
        stats[key] = {
            "median": float(median(values)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "q1": float(np.percentile(arr, 25)),
            "q3": float(np.percentile(arr, 75)),
        }
    return stats


def _error_components(stat: dict[str, float], error_bars: str) -> tuple[float, float]:
    if error_bars == "none":
        return (0.0, 0.0)
    if error_bars == "minmax":
        return (stat["median"] - stat["min"], stat["max"] - stat["median"])
    if error_bars == "iqr":
        return (stat["median"] - stat["q1"], stat["q3"] - stat["median"])
    raise ValueError(f"Unsupported error bar type: {error_bars}")


def make_bar_plot(
    stats: dict[tuple[str, str, float], dict[str, float]],
    dataset_size: float,
    output_dir: Path,
    title_prefix: str,
    formats: list[str],
    y_scale: str,
    error_bars: str,
) -> list[Path]:
    mode_order = {"cold": 0, "warm": 1, "incremental": 2}
    modes = sorted(
        {mode for _, mode, ds in stats if ds == dataset_size},
        key=lambda m: (mode_order.get(m, 999), m),
    )
    methods = sorted({method for method, _, ds in stats if ds == dataset_size})
    if not modes or not methods:
        raise ValueError(f"No rows found for dataset_gb={dataset_size}.")

    x = np.arange(len(modes))
    width = 0.8 / len(methods)

    fig, ax = plt.subplots(figsize=(9, 5.2))
    for i, method in enumerate(methods):
        vals: list[float] = []
        lowers: list[float] = []
        uppers: list[float] = []
        for mode in modes:
            stat = stats.get((method, mode, dataset_size))
            if stat is None:
                vals.append(np.nan)
                lowers.append(np.nan)
                uppers.append(np.nan)
                continue
            vals.append(stat["median"])
            lower, upper = _error_components(stat, error_bars)
            lowers.append(lower)
            uppers.append(upper)

        yerr = None
        if error_bars != "none":
            yerr = np.array([lowers, uppers], dtype=float)

        ax.bar(
            x + (i - (len(methods) - 1) / 2) * width,
            vals,
            width,
            label=method,
            yerr=yerr,
            capsize=3 if yerr is not None else 0,
            error_kw={"elinewidth": 1.1, "alpha": 0.9},
        )

    ax.set_xticks(x)
    ax.set_xticklabels([m.capitalize() for m in modes])
    ax.set_ylabel("Build Time (s)")
    ax.set_yscale(y_scale)
    ax.set_title(f"{title_prefix}: Cold/Warm/Incremental @ {dataset_size:g} GB")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(frameon=True, ncol=min(len(methods), 3))
    fig.tight_layout()

    out_paths: list[Path] = []
    for fmt in formats:
        out_path = output_dir / f"build_time_bar.{fmt}"
        if fmt.lower() in {"png", "jpg", "jpeg", "tif", "tiff", "webp"}:
            fig.savefig(out_path, dpi=220)
        else:
            fig.savefig(out_path)
        out_paths.append(out_path)
    plt.close(fig)
    return out_paths


def make_scaling_plot(
    stats: dict[tuple[str, str, float], dict[str, float]],
    output_dir: Path,
    title_prefix: str,
    formats: list[str],
    y_scale: str,
    error_bars: str,
) -> list[Path]:
    mode_order = {"cold": 0, "warm": 1, "incremental": 2}
    modes = sorted({mode for _, mode, _ in stats}, key=lambda m: (mode_order.get(m, 999), m))
    methods = sorted({method for method, _, _ in stats})

    fig, axes = plt.subplots(
        1, len(modes), figsize=(5.8 * len(modes), 4.8), sharey=True
    )
    if len(modes) == 1:
        axes = [axes]

    for ax, mode in zip(axes, modes):
        for method in methods:
            xs = sorted({ds for m, mo, ds in stats if m == method and mo == mode})
            ys = [stats[(method, mode, ds)]["median"] for ds in xs]
            if xs:
                if error_bars == "none":
                    ax.plot(xs, ys, marker="o", linewidth=2, label=method)
                else:
                    lowers = []
                    uppers = []
                    for ds in xs:
                        lower, upper = _error_components(stats[(method, mode, ds)], error_bars)
                        lowers.append(lower)
                        uppers.append(upper)
                    ax.errorbar(
                        xs,
                        ys,
                        yerr=np.array([lowers, uppers], dtype=float),
                        marker="o",
                        linewidth=2,
                        capsize=3,
                        label=method,
                    )
        ax.set_title(mode.capitalize())
        ax.set_xlabel("Dataset Size (GB)")
        ax.set_yscale(y_scale)
        ax.grid(True, linestyle="--", alpha=0.35)

    axes[0].set_ylabel("Build Time (s)")
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", ncol=min(len(labels), 4), frameon=True)
    fig.suptitle(f"{title_prefix}: Scaling by Dataset Size")
    fig.tight_layout(rect=[0, 0, 1, 0.92])

    out_paths: list[Path] = []
    for fmt in formats:
        out_path = output_dir / f"build_time_scaling.{fmt}"
        if fmt.lower() in {"png", "jpg", "jpeg", "tif", "tiff", "webp"}:
            fig.savefig(out_path, dpi=220)
        else:
            fig.savefig(out_path)
        out_paths.append(out_path)
    plt.close(fig)
    return out_paths


def main() -> None:
    args = parse_args()
    input_paths = resolve_input_csv_paths(args.input_csv, args.input_dir)
    rows: list[dict[str, str]] = []
    for path in input_paths:
        rows.extend(load_rows(path, args.dataset_gb))

    stats = aggregate_stats(rows)
    dataset_sizes = sorted({float(r["dataset_gb"]) for r in rows})
    bar_dataset = args.bar_dataset_gb if args.bar_dataset_gb is not None else dataset_sizes[-1]

    formats = [f.lower().lstrip(".") for f in args.formats]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bar_paths = make_bar_plot(
        stats,
        bar_dataset,
        args.output_dir,
        args.title_prefix,
        formats,
        args.y_scale,
        args.error_bars,
    )
    scaling_paths = make_scaling_plot(
        stats,
        args.output_dir,
        args.title_prefix,
        formats,
        args.y_scale,
        args.error_bars,
    )

    for p in bar_paths:
        print(f"Wrote bar chart: {p}")
    for p in scaling_paths:
        print(f"Wrote scaling chart: {p}")
    print(f"Loaded {len(input_paths)} CSV file(s).")


if __name__ == "__main__":
    main()
