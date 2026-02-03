// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <ros/ros.h>
#include <rosbag/bag.h>
#include <rosbag/view.h>
#include <tf2_msgs/TFMessage.h>
#include <geometry_msgs/TransformStamped.h>
#include <tf2_ros/buffer.h>
#include <tf2/LinearMath/Matrix3x3.h>

#include <fstream>
#include <iostream>
#include <vector>
#include <set>
#include <string>

void toRPY(const geometry_msgs::Quaternion& q, double& roll, double& pitch, double& yaw) {
    tf2::Quaternion tf_q(q.x, q.y, q.z, q.w);
    tf2::Matrix3x3(tf_q).getRPY(roll, pitch, yaw);
}

int main(int argc, char** argv) {
    ros::init(argc, argv, "rosbag_to_tf_trajectory");

    if (argc != 5) {
        std::cerr << "Usage: rosbag_to_tf_trajectory <input.bag> <output.csv> <target_frame> <reference_frame>\n";
        return 1;
    }

    std::string bag_path = argv[1];
    std::string output_csv = argv[2];
    std::string target_frame = argv[3];
    std::string reference_frame = argv[4];

    rosbag::Bag bag;
    try {
        bag.open(bag_path, rosbag::bagmode::Read);
    } catch (const rosbag::BagException& e) {
        std::cerr << "❌ Error opening bag: " << e.what() << "\n";
        return 1;
    }

    std::vector<std::string> static_topics{"/tf_static"};
    std::vector<std::string> dynamic_topics{"/tf"};

    rosbag::View static_view(bag, rosbag::TopicQuery(static_topics));
    rosbag::View dynamic_view(bag, rosbag::TopicQuery(dynamic_topics));

    tf2_ros::Buffer tf_buffer(ros::Duration(ros::DURATION_MAX));  // long buffer for full bag processing
    std::set<ros::Time> timestamps;

    // Load static transforms first
    ros::Time static_tf_stamp = ros::TIME_MAX;
    size_t static_count = 0;
    for (const rosbag::MessageInstance& m : static_view) {
        auto tf_msg = m.instantiate<tf2_msgs::TFMessage>();
        if (!tf_msg) continue;

        for (const auto& transform : tf_msg->transforms) {
            tf_buffer.setTransform(transform, "static_loader", true);
            static_tf_stamp = std::min(static_tf_stamp, transform.header.stamp);
            // std::cout << "[DEBUG] Static TF: " << transform.header.frame_id << " -> "
            //           << transform.child_frame_id << " at " << transform.header.stamp.toSec() << std::endl;
            static_count++;
        }
    }

    std::cout << "[DEBUG] Loaded " << static_count << " static TF messages.\n";

    // Load dynamic transforms
    size_t dynamic_count = 0;
    for (const rosbag::MessageInstance& m : dynamic_view) {
        auto tf_msg = m.instantiate<tf2_msgs::TFMessage>();
        if (!tf_msg) continue;

        for (const auto& transform : tf_msg->transforms) {
            tf_buffer.setTransform(transform, "dynamic_loader", false);
            timestamps.insert(transform.header.stamp);
            // std::cout << "[DEBUG] Dynamic TF: " << transform.header.frame_id << " -> "
            //           << transform.child_frame_id << " at " << transform.header.stamp.toSec() << std::endl;
            dynamic_count++;
        }
    }

    std::cout << "[DEBUG] Loaded " << dynamic_count << " dynamic TF messages.\n";

    bag.close();

    std::ofstream outfile(output_csv);
    outfile << std::fixed << std::setprecision(9);  // <<-- Add this line
    outfile << "timestamp,x,y,z,roll,pitch,yaw\n";

    size_t count = 0;
    for (const auto& t : timestamps) {
        // Skip timestamps earlier than the static TF
        if (t < static_tf_stamp) {
            std::cerr << "[SKIP] Timestamp " << t.toSec() << " is earlier than static TF availability.\n";
            continue;
        }

        try {
            auto tf = tf_buffer.lookupTransform(reference_frame, target_frame, t);
            const auto& trans = tf.transform.translation;
            const auto& rot = tf.transform.rotation;

            double roll, pitch, yaw;
            toRPY(rot, roll, pitch, yaw);

            outfile << tf.header.stamp.toNSec() << ","
                    << trans.x << "," << trans.y << "," << trans.z << ","
                    << roll << "," << pitch << "," << yaw << "\n";
        } catch (const tf2::TransformException& ex) {
            std::cerr << "[WARN] Skipped " << t.toSec() << ": " << ex.what() << "\n";
        }

        if (++count % 1000 == 0) {
            std::cout << "\rProcessed " << count << " timestamps..." << std::flush;
        }
    }

    std::cout << "\n✅ Extracted trajectory of '" << target_frame
              << "' in '" << reference_frame << "' into '" << output_csv << "'\n";

    outfile.close();
    return 0;
}
