// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <ros/ros.h>
#include <geometry_msgs/TransformStamped.h>
#include <geometry_msgs/PointStamped.h>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>
#include <tf2/LinearMath/Transform.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>

using json = nlohmann::json;

struct TrajectoryPoint {
    uint64_t timestamp_ns;
    double utm_e, utm_n, altitude;
};

// Inlined doTransform to avoid tf2_geometry_msgs
namespace tf2 {
inline void doTransform(
    const geometry_msgs::PointStamped& in,
    geometry_msgs::PointStamped& out,
    const geometry_msgs::TransformStamped& tf)
{
    tf2::Vector3 p(in.point.x, in.point.y, in.point.z);
    tf2::Quaternion q(tf.transform.rotation.x,
                      tf.transform.rotation.y,
                      tf.transform.rotation.z,
                      tf.transform.rotation.w);
    tf2::Vector3 t(tf.transform.translation.x,
                   tf.transform.translation.y,
                   tf.transform.translation.z);
    tf2::Transform tform(q, t);
    tf2::Vector3 p_out = tform * p;

    out.header = tf.header;
    out.point.x = p_out.x();
    out.point.y = p_out.y();
    out.point.z = p_out.z();
}
}

// Load trajectory CSV
std::vector<TrajectoryPoint> loadTrajectory(const std::string& path) {
    std::ifstream file(path);
    std::string line, header;
    std::getline(file, header); // skip header

    std::vector<TrajectoryPoint> points;
    while (std::getline(file, line)) {
        std::stringstream ss(line);
        std::string token;
        std::vector<std::string> tokens;
        while (std::getline(ss, token, ',')) tokens.push_back(token);
        if (tokens.size() < 6) continue;

        TrajectoryPoint pt;
        pt.timestamp_ns = std::stoull(tokens[0]);
        pt.altitude     = std::stod(tokens[3]);
        pt.utm_e        = std::stod(tokens[4]);
        pt.utm_n        = std::stod(tokens[5]);
        points.push_back(pt);
    }
    return points;
}

// Save transformed trajectory to CSV
void saveTrajectory(const std::string& path, const std::vector<TrajectoryPoint>& points) {
    std::ofstream file(path);
    file << "timestamp_ns,x,y,z\n";
    for (const auto& pt : points) {
        file << pt.timestamp_ns << "," << pt.utm_e << "," << pt.utm_n << "," << pt.altitude << "\n";
    }
}

// Parse a single JSON transform into geometry_msgs
geometry_msgs::TransformStamped parseTransform(const json& j) {
    geometry_msgs::TransformStamped tf;
    tf.header.frame_id = j["header"]["frame_id"];
    tf.child_frame_id = j["child_frame_id"];
    tf.header.stamp = ros::Time(j["header"]["stamp"]);

    tf.transform.translation.x = j["transform"]["translation"]["x"];
    tf.transform.translation.y = j["transform"]["translation"]["y"];
    tf.transform.translation.z = j["transform"]["translation"]["z"];

    tf.transform.rotation.x = j["transform"]["rotation"]["x"];
    tf.transform.rotation.y = j["transform"]["rotation"]["y"];
    tf.transform.rotation.z = j["transform"]["rotation"]["z"];
    tf.transform.rotation.w = j["transform"]["rotation"]["w"];

    return tf;
}

// Load transform array from JSON into TF buffer
void loadJsonTransforms(const std::string& path, tf2_ros::Buffer& buffer) {
    std::ifstream f(path);
    json j;
    f >> j;

    if (!j.contains("transforms") || !j["transforms"].is_array()) {
    throw std::runtime_error("Expected a 'transforms' array in the JSON.");
    }

    for (const auto& tf_msg : j["transforms"]) {
        auto tf = parseTransform(tf_msg);
        buffer.setTransform(tf, "json_loader");
    }
    std::cout << "Loaded " << j["transforms"].size() << " transforms from " << path << "\n";

}

int main(int argc, char** argv) {
    // ros::init(argc, argv, "offline_tf_transformer");
    // ros::NodeHandle nh;

    if (argc != 5) {
        std::cerr << "Usage: " << argv[0] << " <trajectory.csv> <tf_static.json> <tf_dynamic.json> <output.csv>\n";
        return 1;
    }

    std::string traj_file = argv[1];
    std::string static_tf_file = argv[2];
    std::string dynamic_tf_file = argv[3]; // ignored since transform is static
    std::string output_file = argv[4];

    // Setup TF buffer and listener
    tf2_ros::Buffer tf_buffer;
    // tf2_ros::TransformListener tf_listener(tf_buffer);  // unused but required

    loadJsonTransforms(static_tf_file, tf_buffer);
    // No need to load dynamic transforms

    auto points = loadTrajectory(traj_file);

    const std::string source_frame = "utm";
    const std::string target_frame = "utm_fix";

    geometry_msgs::TransformStamped tf;
    try {
        tf = tf_buffer.lookupTransform(target_frame, source_frame, ros::Time(0));  // static lookup
    } catch (const tf2::TransformException& ex) {
        ROS_ERROR("Failed to get static transform: %s", ex.what());
        return 1;
    }

    size_t total = points.size();
    size_t count = 0;

    for (auto& pt : points) {
        geometry_msgs::PointStamped input, output;
        input.header.frame_id = source_frame;
        input.point.x = pt.utm_e;
        input.point.y = pt.utm_n;
        input.point.z = pt.altitude;

        tf2::doTransform(input, output, tf);

        pt.utm_e = output.point.x;
        pt.utm_n = output.point.y;
        pt.altitude = output.point.z;

        count++;
        if (count % 1000 == 0 || count == total) {
            std::cout << "\rProcessing point " << count << " / " << total << std::flush;
        }
    }
    std::cout << std::endl;


    saveTrajectory(output_file, points);
    std::cout << "✅ Transformed trajectory written to " << output_file << "\n";
    return 0;
}
