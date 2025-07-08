// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <ros/ros.h>
#include <rosbag/bag.h>
#include <rosbag/view.h>
#include <tf2_msgs/TFMessage.h>
#include <sensor_msgs/CameraInfo.h>
#include <nlohmann/json.hpp>
#include <boost/filesystem.hpp>

#include <fstream>
#include <iostream>

using json = nlohmann::json;

void processTransforms(const std::vector<tf2_msgs::TFMessage>& messages, const std::string& type, const std::string& output_path) {
    json root;
    root["type"] = type;
    root["transforms"] = json::array();

    for (const auto& msg : messages) {
        for (const auto& transform : msg.transforms) {
            json transform_data;
            transform_data["header"]["stamp"] = transform.header.stamp.toSec();
            transform_data["header"]["frame_id"] = transform.header.frame_id;
            transform_data["child_frame_id"] = transform.child_frame_id;
            transform_data["transform"]["translation"] = {
                {"x", transform.transform.translation.x},
                {"y", transform.transform.translation.y},
                {"z", transform.transform.translation.z}
            };
            transform_data["transform"]["rotation"] = {
                {"x", transform.transform.rotation.x},
                {"y", transform.transform.rotation.y},
                {"z", transform.transform.rotation.z},
                {"w", transform.transform.rotation.w}
            };
            root["transforms"].push_back(transform_data);
        }
    }

    std::ofstream file(output_path);
    file << root.dump(4);
    file.close();
    ROS_INFO("Saved %s transforms to %s", type.c_str(), output_path.c_str());
}

void processCameraInfo(const std::vector<sensor_msgs::CameraInfo>& infos, const std::string& output_path) {
    if (infos.empty()) {
        std::cerr << "❌ No camera info messages found.\n";
        return;
    }

    const auto& cam = infos.front();  // Use the first one
    json cam_json;

    // Header
    cam_json["header"]["stamp"] = cam.header.stamp.toSec();
    cam_json["header"]["frame_id"] = cam.header.frame_id;

    // Basic info
    cam_json["height"] = cam.height;
    cam_json["width"] = cam.width;
    cam_json["distortion_model"] = cam.distortion_model;

    // Camera matrices
    cam_json["D"] = cam.D;
    cam_json["K"] = {cam.K[0], cam.K[1], cam.K[2],
                     cam.K[3], cam.K[4], cam.K[5],
                     cam.K[6], cam.K[7], cam.K[8]};
    cam_json["R"] = {cam.R[0], cam.R[1], cam.R[2],
                     cam.R[3], cam.R[4], cam.R[5],
                     cam.R[6], cam.R[7], cam.R[8]};
    cam_json["P"] = {cam.P[0], cam.P[1], cam.P[2], cam.P[3],
                     cam.P[4], cam.P[5], cam.P[6], cam.P[7],
                     cam.P[8], cam.P[9], cam.P[10], cam.P[11]};

    // Binning
    cam_json["binning_x"] = cam.binning_x;
    cam_json["binning_y"] = cam.binning_y;

    // ROI
    cam_json["roi"]["x_offset"] = cam.roi.x_offset;
    cam_json["roi"]["y_offset"] = cam.roi.y_offset;
    cam_json["roi"]["height"] = cam.roi.height;
    cam_json["roi"]["width"]  = cam.roi.width;
    cam_json["roi"]["do_rectify"] = cam.roi.do_rectify;

    // Save to file
    std::ofstream file(output_path);
    file << cam_json.dump(4);
    file.close();

    ROS_INFO("✅ Saved full camera info to %s", output_path.c_str());
}


int main(int argc, char** argv) {
    ros::init(argc, argv, "rosbag_to_json");

    if (argc != 5) {
        std::cerr << "Usage: rosbag_to_json <input.bag> <dynamic_output.json> <static_output.json> <camera_info.json>" << std::endl;
        return 1;
    }

    std::string bag_path = argv[1];
    std::string dynamic_output = argv[2];
    std::string static_output = argv[3];
    std::string camera_info_output = argv[4];

    if (!boost::filesystem::exists(bag_path)) {
        std::cerr << "Error: Bag file not found: " << bag_path << std::endl;
        return 1;
    }

    rosbag::Bag bag;
    try {
        bag.open(bag_path, rosbag::bagmode::Read);
    } catch (const rosbag::BagException& e) {
        std::cerr << "Failed to open bag: " << e.what() << std::endl;
        return 1;
    }

    std::vector<tf2_msgs::TFMessage> tf_msgs;
    std::vector<tf2_msgs::TFMessage> tf_static_msgs;
    std::vector<sensor_msgs::CameraInfo> camera_infos;

    rosbag::View view(bag);
    for (const rosbag::MessageInstance& m : view) {
        if (m.getTopic() == "/tf") {
            auto tf_msg = m.instantiate<tf2_msgs::TFMessage>();
            if (tf_msg) tf_msgs.push_back(*tf_msg);
        } else if (m.getTopic() == "/tf_static") {
            auto tf_msg = m.instantiate<tf2_msgs::TFMessage>();
            if (tf_msg) tf_static_msgs.push_back(*tf_msg);
        } else if (m.getTopic() == "/sensor/camera/surround/front/camera_info") {
            auto cam_msg = m.instantiate<sensor_msgs::CameraInfo>();
            if (cam_msg) camera_infos.push_back(*cam_msg);
        }
    }

    bag.close();

    processTransforms(tf_msgs, "dynamic", dynamic_output);
    processTransforms(tf_static_msgs, "static", static_output);
    processCameraInfo(camera_infos, camera_info_output);

    return 0;
}
