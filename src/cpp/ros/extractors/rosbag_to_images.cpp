// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <ros/ros.h>
#include <rosbag/bag.h>
#include <rosbag/view.h>
#include <sensor_msgs/Image.h>
#include <cv_bridge/cv_bridge.h>
#include <opencv2/opencv.hpp>
#include <boost/filesystem.hpp>
#include <map>
#include <algorithm>
#include <iostream>

namespace fs = boost::filesystem;

int main(int argc, char** argv) {
    if (argc < 4) {
        ROS_ERROR("Usage: bazel run //src:rosbag_to_images <bag_file> <image_topic1> [<image_topic2> ...] <output_directory>");
        return 1;
    }

    std::string bag_file = argv[1];
    std::vector<std::string> image_topics;
    for (int i = 2; i < argc - 1; ++i) {
        image_topics.push_back(argv[i]);
    }
    std::string output_dir = argv[argc - 1];

    if (!fs::exists(bag_file)) {
        ROS_WARN("Bag file does not exist: %s — skipping extraction to avoid pipeline failure.", bag_file.c_str());
        return 0;  // Don't crash the pipeline, just log and exit
    }

    bool single_topic = (image_topics.size() == 1);

    try {
        rosbag::Bag bag;
        bag.open(bag_file, rosbag::bagmode::Read);
        
        rosbag::View view(bag, rosbag::TopicQuery(image_topics));
        std::map<std::string, int> topic_frame_count;

        for (const rosbag::MessageInstance& msg : view) {
            std::string topic_name = msg.getTopic();
            sensor_msgs::ImageConstPtr img_msg = msg.instantiate<sensor_msgs::Image>();
        
            if (img_msg) {
                try {
                    cv_bridge::CvImageConstPtr cv_ptr = cv_bridge::toCvShare(img_msg, "bgr8");
        
                    std::string topic_folder = topic_name;
                    if (!topic_folder.empty() && topic_folder[0] == '/') topic_folder = topic_folder.substr(1);
                    std::replace(topic_folder.begin(), topic_folder.end(), '/', '_');

                    fs::path topic_output;
                    if (single_topic) {
                        topic_output = fs::path(output_dir);
                    } else {
                        topic_output = fs::path(output_dir) / "images" / topic_folder;
                    }

                    fs::create_directories(topic_output);

                    int frame_count = topic_frame_count[topic_name]++;

                    // Format timestamp (nanoseconds)
                    ros::Time stamp = msg.getTime();
                    uint64_t timestamp_ns = static_cast<uint64_t>(stamp.sec) * 1'000'000'000ULL + static_cast<uint64_t>(stamp.nsec);

                    // Format topic name (e.g. "/stereo/left/image_raw" -> "stereo_left_image_raw")
                    std::string topic_clean = topic_name;
                    if (!topic_clean.empty() && topic_clean[0] == '/') topic_clean = topic_clean.substr(1);
                    std::replace(topic_clean.begin(), topic_clean.end(), '/', '_');

                    // Format bag session identifier (optional: derive from bag filename or log start time)
                    std::string session_id = fs::path(bag_file).stem().string(); // e.g., "drive_01_2024_03_14"

                    std::ostringstream filename;
                    filename << topic_output.string()
                            << "/" << session_id
                            << "__" << topic_clean
                            << "__" << timestamp_ns
                            << ".png";

                    cv::imwrite(filename.str(), cv_ptr->image);
                } catch (const cv_bridge::Exception& e) {
                    ROS_ERROR("cv_bridge exception: %s", e.what());
                }
            }
        }

        bag.close();

        int total_frames = 0;
        std::cout << "[INFO] Frame extraction complete. Topics extracted: " << topic_frame_count.size() << "\n";

        for (const auto& pair : topic_frame_count) {
            const std::string& topic_name = pair.first;
            int frame_count = pair.second;

            std::string topic_folder = topic_name;
            if (!topic_folder.empty() && topic_folder[0] == '/') topic_folder = topic_folder.substr(1);
            std::replace(topic_folder.begin(), topic_folder.end(), '/', '_');

            fs::path path_display = single_topic 
                ? fs::path(output_dir)
                : fs::path(output_dir) / "images" / topic_folder;

            std::cout << "[INFO] " << topic_name << " → " << path_display.string()
                      << " (" << frame_count << " frames)\n";

            total_frames += frame_count;
        }

        std::cout << "[INFO] Total frames: " << total_frames << "\n";

    } catch (const rosbag::BagException& e) {
        ROS_WARN("Error reading bag file: %s — skipping extraction.", e.what());
        return 0;  // Graceful skip
    } catch (const std::exception& e) {
        ROS_WARN("Unhandled exception: %s — skipping extraction.", e.what());
        return 0;
    }

    return 0;
}
