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
#include <future>   // std::async
#include <thread>   // std::thread
#include <mutex>    // std::mutex
#include <atomic>   // std::atomic
#include <chrono>   // std::this_thread::sleep_for

namespace fs = boost::filesystem;

std::vector<std::string> getImportantBagPaths(const std::string& directory_path, const std::set<std::string>& important_topics) {
    std::vector<std::string> matching_bag_paths;
    std::mutex mutex;

    if (!fs::exists(directory_path) || !fs::is_directory(directory_path)) {
        std::cerr << "Error: Invalid directory: " << directory_path << std::endl;
        return matching_bag_paths;
    }

    std::vector<fs::path> bag_files;
    for (fs::recursive_directory_iterator it(directory_path), end; it != end; ++it) {
        if (fs::is_regular_file(*it) && it->path().extension() == ".bag") {
            bag_files.push_back(it->path());
        }
    }

    std::cout << "🔍 Found " << bag_files.size() << " bag files. Scanning in parallel...\n";

    std::atomic<int> count = 0;
    bool done = false;
    std::vector<std::future<void>> futures;

    // Start progress reporting thread
    std::thread progress_thread([&]() {
        while (!done) {
            int current = count.load();
            std::cout << "\r⏳ Progress: " << current << " / " << bag_files.size() << std::flush;
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }
        std::cout << "\r✅ Finished scanning " << bag_files.size() << " bags.                 \n";
    });

    // Launch worker threads
    for (const auto& path : bag_files) {
        futures.push_back(std::async(std::launch::async, [&path, &important_topics, &matching_bag_paths, &mutex, &count]() {
            std::string bag_path = path.string();
            try {
                rosbag::Bag bag;
                bag.open(bag_path, rosbag::bagmode::Read);
                rosbag::View view(bag);

                for (const auto& connection : view.getConnections()) {
                    if (important_topics.find(connection->topic) != important_topics.end()) {
                        std::lock_guard<std::mutex> lock(mutex);
                        matching_bag_paths.push_back(bag_path);
                        break;
                    }
                }

                bag.close();
            } catch (const rosbag::BagException& e) {
                std::lock_guard<std::mutex> lock(mutex);
                std::cerr << "\n⚠️  Warning: Failed to read bag " << bag_path << ": " << e.what() << std::endl;
            }
            ++count;
        }));
    }

    for (auto& f : futures) {
        f.get();
    }

    done = true;
    progress_thread.join();

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
        std::replace(relative_path.begin(), relative_path.end(), '\\', '/');

        if (relative_path.find(rosbag_dir) == 0) {
            relative_path = relative_path.substr(rosbag_dir.length());
            if (!relative_path.empty() && relative_path[0] == '/')
                relative_path = relative_path.substr(1);
        }

        out_file << "    \"" << relative_path << "\",\n";
    }
    out_file << "]\n";
    out_file.close();

    std::cout << "✅ Saved " << important_bags.size() << " valid bag paths to " << output_path << std::endl;
    return 0;
}
