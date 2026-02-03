// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <rosbag/bag.h>
#include <rosbag/view.h>
#include <ethernet_msgs/Packet.h>
#include <boost/filesystem.hpp>
#include <nlohmann/json.hpp>

#include <fstream>
#include <iostream>
#include <iomanip>
#include <ctime>
#include <map>
#include <cmath>

// OxTS NCOM decoder
#include "NComRxC.h"

namespace fs = boost::filesystem;
using json = nlohmann::json;

// Format UNIX time as ISO 8601
std::string format_unix_time(double unix_time_sec) {
    std::time_t time = static_cast<std::time_t>(unix_time_sec);
    std::tm* tm_ptr = std::gmtime(&time);  // UTC time

    std::ostringstream oss;
    oss << std::put_time(tm_ptr, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}
int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <bag_file_path> <rosbag_name> [output_json_path]" << std::endl;
        return 1;
    }

    std::string bag_file = argv[1];
    std::string rosbag_name = argv[2];
    std::string output_file;

    if (argc >= 4) {
        output_file = argv[3];
    } else {
        output_file = fs::path(bag_file).replace_extension(".metadata.json").string();
    }

    if (!fs::exists(bag_file)) {
        std::cerr << "❌ Bag file does not exist: " << bag_file << std::endl;
        return 1;
    }

    try {
        rosbag::Bag bag;
        bag.open(bag_file, rosbag::bagmode::Read);

        rosbag::View view(bag);

        json metadata;
        metadata["bag_file"] = bag_file;
        metadata["name"] = rosbag_name;  // Use the provided name argument
        metadata["total_messages"] = view.size();

        double start_time = view.getBeginTime().toSec();
        double end_time = view.getEndTime().toSec();
        double duration = end_time - start_time;

        metadata["start_time"] = start_time;
        metadata["start_time_readable"] = format_unix_time(start_time);
        metadata["end_time"] = end_time;
        metadata["end_time_readable"] = format_unix_time(end_time);
        metadata["duration_sec"] = duration;

        std::time_t time = static_cast<std::time_t>(start_time);
        std::tm* tm_ptr = std::gmtime(&time);  // UTC
        int hour = tm_ptr->tm_hour;
        metadata["light"] = (hour >= 6 && hour < 18) ? "day" : "night";

        std::map<std::string, std::string> unique_topics;
        for (const auto& connection : view.getConnections()) {
            unique_topics[connection->topic] = connection->datatype;
        }

        metadata["total_topics"] = unique_topics.size();

        json topic_list = json::array();
        for (const auto& pair : unique_topics) {
            topic_list.push_back({
                {"name", pair.first},
                {"type", pair.second}
            });
        }
        metadata["topics"] = topic_list;

        const std::string kGpsTopic = "/bus/oxts/eth_ncom/bus_to_host";
        const size_t expected_payload_size = 72;
        NComRxC* decoder = NComCreateNComRxC();
        ros::Time last_stamp;
        bool got_first_fix = false;

        double first_lat = 0, first_lon = 0, first_alt = 0;
        double last_lat = 0, last_lon = 0, last_alt = 0;

        rosbag::View gps_view(bag, rosbag::TopicQuery(kGpsTopic));
        for (const rosbag::MessageInstance& m : gps_view) {
            auto pkt = m.instantiate<ethernet_msgs::Packet>();
            if (!pkt) continue;

            ros::Time current_stamp = m.getTime();
            if (!last_stamp.isZero() && std::abs((current_stamp - last_stamp).toSec()) > 1.0) {
                NComInvalidate(decoder);
            }
            last_stamp = current_stamp;

            const uint8_t* raw = pkt->payload.data();
            size_t length = pkt->payload.size();
            if (length != expected_payload_size) continue;

            int result = NComNewChars(decoder, raw, length);
            if (result == COM_NEW_UPDATE &&
                decoder->mIsLatValid && decoder->mIsLonValid && decoder->mIsAltValid) {

                if (!got_first_fix) {
                    first_lat = decoder->mLat;
                    first_lon = decoder->mLon;
                    first_alt = decoder->mAlt;
                    got_first_fix = true;
                }

                last_lat = decoder->mLat;
                last_lon = decoder->mLon;
                last_alt = decoder->mAlt;
            }
        }

        if (got_first_fix) {
            metadata["gps_start"] = {
                {"lat", first_lat},
                {"lon", first_lon},
                {"alt", first_alt}
            };
            metadata["gps_end"] = {
                {"lat", last_lat},
                {"lon", last_lon},
                {"alt", last_alt}
            };
        } else {
            metadata["gps_start"] = nullptr;
            metadata["gps_end"] = nullptr;
        }

        NComDestroyNComRxC(decoder);
        bag.close();

        std::ofstream out(output_file);
        out << std::setw(4) << metadata << std::endl;

        std::cout << "✅ Metadata written to: " << output_file << std::endl;

    } catch (const rosbag::BagException& e) {
        std::cerr << "❌ Error reading bag file: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
