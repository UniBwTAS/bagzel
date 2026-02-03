// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
// SPDX-License-Identifier: Apache-2.0

#include <ros/ros.h>
#include <sensor_msgs/CameraInfo.h>
#include <image_geometry/pinhole_camera_model.h>

#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.h>

#include <fstream>
#include <sstream>
#include <string>
#include <map>
#include <vector>
#include <nlohmann/json.hpp>
#include <regex>
#include <filesystem>
#include <iomanip>

namespace fs = std::filesystem;
using json = nlohmann::json;

struct Pose {
    ros::Time stamp;
    cv::Point3d position;
    cv::Matx33d rotation;
};

cv::Matx33d rpyToRotation(double roll, double pitch, double yaw) {
    double cr = cos(roll), sr = sin(roll);
    double cp = cos(pitch), sp = sin(pitch);
    double cy = cos(yaw), sy = sin(yaw);
    return {
        cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr,
        sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr,
        -sp,     cp * sr,                cp * cr
    };
}

std::map<ros::Time, Pose> loadPoseCSV(const std::string& path) {
    std::map<ros::Time, Pose> poses;
    std::ifstream file(path);
    std::string line;
    std::getline(file, line); // skip header
    while (std::getline(file, line)) {
        std::stringstream ss(line);
        std::string token;
        std::vector<std::string> tokens;
        while (std::getline(ss, token, ',')) tokens.push_back(token);
        if (tokens.size() < 7) continue;

        ros::Time stamp(std::stoll(tokens[0]) / 1e9);
        double x = std::stod(tokens[1]);
        double y = std::stod(tokens[2]);
        double z = std::stod(tokens[3]);
        double roll = std::stod(tokens[4]);
        double pitch = std::stod(tokens[5]);
        double yaw = std::stod(tokens[6]);

        Pose pose;
        pose.stamp = stamp;
        pose.position = {x, y, z};
        pose.rotation = rpyToRotation(roll, pitch, yaw);
        poses[stamp] = pose;
    }
    return poses;
}

sensor_msgs::CameraInfo loadCameraInfoJson(const std::string& path) {
    std::ifstream file(path);
    json j;
    file >> j;

    sensor_msgs::CameraInfo info;
    info.header.frame_id = j["header"]["frame_id"];
    info.width = j["width"];
    info.height = j["height"];
    info.distortion_model = j["distortion_model"];

    for (size_t i = 0; i < j["D"].size(); ++i) info.D.push_back(j["D"][i]);
    for (size_t i = 0; i < 9; ++i) info.K[i] = j["K"][i];
    for (size_t i = 0; i < 9; ++i) info.R[i] = j["R"][i];
    for (size_t i = 0; i < 12; ++i) info.P[i] = j["P"][i];

    if (j.contains("roi")) {
        info.roi.x_offset = j["roi"]["x_offset"];
        info.roi.y_offset = j["roi"]["y_offset"];
        info.roi.width    = j["roi"]["width"];
        info.roi.height   = j["roi"]["height"];
        info.roi.do_rectify = j["roi"]["do_rectify"];
    }

    return info;
}

ros::Time extractTimestampFromFilename(const std::string& filename) {
    std::regex pattern(R"__(.*__(\d{19})\.png)__");
    std::smatch match;
    if (std::regex_match(filename, match, pattern)) {
        std::string ts_str = match[1];
        int64_t ns = std::stoll(ts_str);
        return ros::Time(ns / 1e9);
    }
    ROS_ERROR("Could not extract timestamp from filename: %s", filename.c_str());
    return ros::Time(0);
}

cv::Scalar pickColor(ros::Time stamp, ros::Time image_time, ros::Time last_frame_time) {
    int segment_index = static_cast<int>((stamp - image_time).toSec()) / 2;
    bool after_last_frame = stamp > last_frame_time;

    if (!after_last_frame) {
        switch (segment_index % 6) {
            case 0: return cv::Scalar(200, 100, 100);
            case 1: return cv::Scalar(100, 150, 200);
            case 2: return cv::Scalar(150, 200, 150);
            case 3: return cv::Scalar(200, 180, 100);
            case 4: return cv::Scalar(180, 130, 200);
            default: return cv::Scalar(160, 160, 160);
        }
    } else {
        switch (segment_index % 6) {
            case 0: return cv::Scalar(0, 0, 255);
            case 1: return cv::Scalar(255, 0, 0);
            case 2: return cv::Scalar(0, 255, 255);
            case 3: return cv::Scalar(255, 255, 0);
            case 4: return cv::Scalar(255, 0, 255);
            default: return cv::Scalar(100, 100, 100);
        }
    }
}

int main(int argc, char** argv) {
    ros::init(argc, argv, "project_trajectory_to_image");

    if (argc != 6) {
        ROS_ERROR("Usage:\n"
                  "  project_trajectory_to_image <sequence.json> <rear.csv> <camera.csv> <camera_info.json> <output_dir>\n"
                  "  OR\n"
                  "  project_trajectory_to_image <rear.csv> <camera.csv> <camera_info.json> <input_image.png> <output_image.png>");
        return 1;
    }

    std::string arg1 = argv[1];

    if (arg1.size() > 5 && arg1.substr(arg1.size() - 5) == ".json") {
        // Mode A: sequence.json
        std::string seq_path = argv[1];
        std::string rear_path = argv[2];
        std::string cam_path = argv[3];
        std::string camera_info_path = argv[4];
        std::string output_dir = argv[5];

        std::ifstream f(seq_path);
        if (!f.is_open()) {
            ROS_ERROR("Could not open sequence.json: %s", seq_path.c_str());
            return 1;
        }

        json sequences;
        f >> sequences;

        auto rear_traj = loadPoseCSV(rear_path);
        auto cam_traj = loadPoseCSV(cam_path);
        auto cam_info = loadCameraInfoJson(camera_info_path);

        fs::create_directories(output_dir);
        image_geometry::PinholeCameraModel cam_model;
        cam_model.fromCameraInfo(cam_info);

        int idx = 0;
        for (const auto& seq : sequences) {
            if (!seq.contains("frames") || seq["frames"].empty()) continue;

            std::string img_path = seq["frames"][0];
            std::string last_img_path = seq["frames"].back();
            ros::Time image_time = extractTimestampFromFilename(img_path);
            ros::Time last_frame_time = extractTimestampFromFilename(last_img_path);

            cv::Mat image = cv::imread(img_path, cv::IMREAD_COLOR);
            if (image.empty()) continue;

            ros::Time best_time;
            double best_dt = std::numeric_limits<double>::max();
            for (const auto& [stamp, pose] : cam_traj) {
                double dt = std::abs((stamp - image_time).toSec());
                if (dt < best_dt) {
                    best_dt = dt;
                    best_time = stamp;
                }
            }

            const auto& cam_pose = cam_traj.at(best_time);
            cv::Matx33d R_cw = cam_pose.rotation.t();
            cv::Vec3d t_cw = -R_cw * cv::Vec3d(cam_pose.position);

            for (const auto& [stamp, pose] : rear_traj) {
                if ((stamp - image_time).toSec() < 0) continue;

                cv::Vec3d pos_vec(pose.position.x, pose.position.y, pose.position.z);
                cv::Vec3d p_c = R_cw * pos_vec + t_cw;
                if (p_c[2] <= 0) continue;

                cv::Point2d uv = cam_model.project3dToPixel(p_c);
                if (uv.x >= 0 && uv.x < image.cols && uv.y >= 0 && uv.y < image.rows) {
                    cv::circle(image, uv, 4, pickColor(stamp, image_time, last_frame_time), -1);
                }
            }

            std::ostringstream filename;
            filename << output_dir << "/sequence_" << std::setw(3) << std::setfill('0') << idx++ << ".png";
            cv::imwrite(filename.str(), image);
        }

        return 0;
    } else {
        // Mode B: single image
        std::string rear_path = argv[1];
        std::string cam_path = argv[2];
        std::string camera_info_path = argv[3];
        std::string input_img_path = argv[4];
        std::string output_img_path = argv[5];

        auto rear_traj = loadPoseCSV(rear_path);
        auto cam_traj = loadPoseCSV(cam_path);
        auto cam_info = loadCameraInfoJson(camera_info_path);

        cv::Mat image = cv::imread(input_img_path, cv::IMREAD_COLOR);
        if (image.empty()) {
            ROS_ERROR("Failed to load image.");
            return 1;
        }

        image_geometry::PinholeCameraModel cam_model;
        cam_model.fromCameraInfo(cam_info);

        ros::Time image_time = extractTimestampFromFilename(input_img_path);
        ros::Time last_frame_time = image_time;

        ros::Time best_time;
        double best_dt = std::numeric_limits<double>::max();
        for (const auto& [stamp, pose] : cam_traj) {
            double dt = std::abs((stamp - image_time).toSec());
            if (dt < best_dt) {
                best_dt = dt;
                best_time = stamp;
            }
        }

        const auto& cam_pose = cam_traj.at(best_time);
        cv::Matx33d R_cw = cam_pose.rotation.t();
        cv::Vec3d t_cw = -R_cw * cv::Vec3d(cam_pose.position);

        for (const auto& [stamp, pose] : rear_traj) {
            if ((stamp - image_time).toSec() < 0) continue;

            cv::Vec3d pos_vec(pose.position.x, pose.position.y, pose.position.z);
            cv::Vec3d p_c = R_cw * pos_vec + t_cw;
            if (p_c[2] <= 0) continue;

            cv::Point2d uv = cam_model.project3dToPixel(p_c);
            if (uv.x >= 0 && uv.x < image.cols && uv.y >= 0 && uv.y < image.rows) {
                cv::circle(image, uv, 4, pickColor(stamp, image_time, last_frame_time), -1);
            }
        }

        cv::imwrite(output_img_path, image);
        return 0;
    }
}
