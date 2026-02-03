# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

import os
import argparse

def print_tree(root, prefix=""):
    entries = sorted(os.listdir(root))
    for i, entry in enumerate(entries):
        path = os.path.join(root, entry)
        connector = "└── " if i == len(entries) - 1 else "├── "
        print(prefix + connector + entry)
        if os.path.isdir(path):
            extension = "    " if i == len(entries) - 1 else "│   "
            print_tree(path, prefix + extension)


def main():
    print("This script prints the directory tree of a given path.")
    parser = argparse.ArgumentParser(description="Print directory tree.")
    parser.add_argument('--src', help='source path to read rosbag1 or rosbag2 from')
    args = parser.parse_args()


    print_tree(args.src)


if __name__ == "__main__":
    main()
