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

namespace fs = boost::filesystem;

std::vector<std::string> getImportantBagPaths(const std::string& directory_path, const std::set<std::string>& important_topics) {
    std::vector<std::string> matching_bag_paths;

    if (!fs::exists(directory_path) || !fs::is_directory(directory_path)) {
        std::cerr << "Error: Invalid directory: " << directory_path << std::endl;
        return matching_bag_paths;
    }

    for (const auto& entry : fs::directory_iterator(directory_path)) {
        if (fs::is_regular_file(entry) && entry.path().extension() == ".bag") {
            std::string bag_path = entry.path().string();
            try {
                rosbag::Bag bag;
                bag.open(bag_path, rosbag::bagmode::Read);
                rosbag::View view(bag);

                for (const auto& connection : view.getConnections()) {
                    if (important_topics.find(connection->topic) != important_topics.end()) {
                        matching_bag_paths.push_back(bag_path);
                        break; // One match is enough
                    }
                }

                bag.close();
            } catch (const rosbag::BagException& e) {
                std::cerr << "Warning: Failed to read bag " << bag_path << ": " << e.what() << std::endl;
                continue;
            }
        }
    }

    return matching_bag_paths;
}

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: ./rosbag_topic_filter <rosbag_dir> <topic1> [<topic2> ...]" << std::endl;
        return 1;
    }

    std::string rosbag_dir = argv[1];

    std::set<std::string> important_topics;
    for (int i = 2; i < argc; ++i) {
        important_topics.insert(argv[i]);
    }

    std::vector<std::string> important_bags = getImportantBagPaths(rosbag_dir, important_topics);

    if (important_bags.empty()) {
        std::cout << "No bags contain the specified important topics." << std::endl;
    } else {
        for (const std::string& path : important_bags) {
            std::cout << path << std::endl;
        }
    }

    return 0;
}
