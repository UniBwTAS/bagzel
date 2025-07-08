// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <rosbag/bag.h>
#include <rosbag/view.h>
#include <boost/filesystem.hpp>
#include <set>
#include <vector>
#include <string>
#include <iostream>
#include <fstream>
#include <chrono>

namespace fs = boost::filesystem;

std::vector<std::string> getImportantBagPaths(const std::string& directory_path, const std::set<std::string>& important_topics) {
    std::vector<std::string> matching_bag_paths;

    if (!fs::exists(directory_path) || !fs::is_directory(directory_path)) {
        std::cerr << "Error: Invalid directory: " << directory_path << std::endl;
        return matching_bag_paths;
    }

    // First, collect all .bag files
    std::vector<fs::path> bag_files;
    for (fs::recursive_directory_iterator it(directory_path), end; it != end; ++it) {
        if (fs::is_regular_file(*it) && it->path().extension() == ".bag") {
            bag_files.push_back(it->path());
        }
    }

    std::cout << "🔍 Found " << bag_files.size() << " bag files. Scanning...\n";

    int count = 0;
    for (const auto& path : bag_files) {
        ++count;
        std::string bag_path = path.string();
        std::cout << "\r⏳ Processing [" << count << "/" << bag_files.size() << "]: " << path.filename().string() << "       " << std::flush;

        try {
            rosbag::Bag bag;
            bag.open(bag_path, rosbag::bagmode::Read);
            rosbag::View view(bag);

            for (const auto& connection : view.getConnections()) {
                if (important_topics.find(connection->topic) != important_topics.end()) {
                    matching_bag_paths.push_back(bag_path);
                    break;
                }
            }

            bag.close();
        } catch (const rosbag::BagException& e) {
            std::cerr << "\n⚠️  Warning: Failed to read bag " << bag_path << ": " << e.what() << std::endl;
            continue;
        }
    }

    std::cout << "\n✅ Finished scanning bags.\n";
    return matching_bag_paths;
}


int main(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "Usage: ./rosbag_topic_filter <rosbag_dir> <output_bzl_path> <topic1> [<topic2> ...]" << std::endl;
        return 1;
    }

    std::string rosbag_dir = argv[1];
    std::string output_path = argv[2];

    std::set<std::string> important_topics;
    for (int i = 3; i < argc; ++i) {
        important_topics.insert(argv[i]);
    }

    auto start_time = std::chrono::steady_clock::now();
    std::vector<std::string> important_bags = getImportantBagPaths(rosbag_dir, important_topics);
    auto end_time = std::chrono::steady_clock::now();
    std::chrono::duration<double> duration = end_time - start_time;
    std::cout << "⏱️  Duration: " << duration.count() << " seconds\n";

    std::ofstream out_file(output_path);
    if (!out_file) {
        std::cerr << "Error: Could not open output file." << std::endl;
        return 1;
    }

    out_file << "VALID_ROSBAGS = [\n";
    for (const auto& path : important_bags) {
        std::string relative_path = path;
    
        // Normalize Windows-style slashes
        std::replace(relative_path.begin(), relative_path.end(), '\\', '/');
    
        // Remove the rosbag_dir prefix
        if (relative_path.find(rosbag_dir) == 0) {
            relative_path = relative_path.substr(rosbag_dir.length());
            if (!relative_path.empty() && relative_path[0] == '/')
                relative_path = relative_path.substr(1);  // remove leading slash
        }
    
        out_file << "    \"" << relative_path << "\",\n";
    }
    out_file << "]\n";  
    out_file.close();

    std::cout << "✅ Saved " << important_bags.size() << " valid bag paths to " << output_path << std::endl;

    return 0;
}
