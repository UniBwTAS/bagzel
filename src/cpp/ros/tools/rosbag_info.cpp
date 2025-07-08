// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <ros/ros.h>
#include <rosbag/bag.h>
#include <rosbag/view.h>
#include <std_msgs/String.h>
#include <boost/filesystem.hpp>

int main(int argc, char** argv) {
    ros::init(argc, argv, "rosbag_info_printer", ros::init_options::AnonymousName | ros::init_options::NoSigintHandler);

    if (argc < 2) {
        ROS_ERROR("Usage: rosrun <package_name> rosbag_info_printer <bag_file_path>");
        return 1;
    }

    std::string bag_file = argv[1];
    if (!boost::filesystem::exists(bag_file)) {
        ROS_ERROR("Bag file does not exist: %s", bag_file.c_str());
        return 1;
    }

    try {
        rosbag::Bag bag;
        bag.open(bag_file, rosbag::bagmode::Read);
        
        rosbag::View view(bag);

        ROS_INFO("Bag File: %s", bag_file.c_str());
        ROS_INFO("Total Topics: %lu", view.getConnections().size());
        
        for (const auto& connection : view.getConnections()) {
            ROS_INFO("Topic: %s | Type: %s", connection->topic.c_str(), connection->datatype.c_str());
        }

        ROS_INFO("Total Messages: %lu", view.size());

        ros::Time start_time = view.getBeginTime();
        ros::Time end_time = view.getEndTime();
        ROS_INFO("Start Time: %.6f", start_time.toSec());
        ROS_INFO("End Time: %.6f", end_time.toSec());
        ROS_INFO("Duration: %.6f seconds", (end_time - start_time).toSec());

        bag.close();
    } catch (const rosbag::BagException& e) {
        ROS_ERROR("Error reading bag file: %s", e.what());
        return 1;
    }
    
    return 0;
}