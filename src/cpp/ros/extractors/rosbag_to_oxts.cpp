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
#include <cmath>
#include <string>

// OxTS NCOM SDK
#include "NComRxC.h"

// GeographicLib for UTM
#include <GeographicLib/UTMUPS.hpp>

namespace fs = boost::filesystem;
const std::string kGpsTopic = "/bus/oxts/eth_ncom/bus_to_host";
const size_t expected_payload_size = 72;
const double time_jump_threshold_sec = 1.0;

// Convert boost::array<uint8_t, 4> to string
std::string ipToString(const boost::array<uint8_t, 4>& ip) {
    return std::to_string(ip[0]) + "." +
           std::to_string(ip[1]) + "." +
           std::to_string(ip[2]) + "." +
           std::to_string(ip[3]);
}

int main(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0] << " <bag_file> <output_csv> <filter_ip>" << std::endl;
        return 1;
    }

    std::string bag_file = argv[1];
    std::string output_path = argv[2];
    std::string filter_ip = argv[3];

    std::ofstream outfile(output_path);
    outfile << std::fixed << std::setprecision(15);
    outfile << "timestamp_ns,latitude,longitude,altitude,utm_e,utm_n,utm_z,utm_zone,pitch,roll,yaw\n";

    try {
        rosbag::Bag bag;
        bag.open(bag_file, rosbag::bagmode::Read);
        rosbag::View view(bag, rosbag::TopicQuery(kGpsTopic));

        NComRxC* decoder = NComCreateNComRxC();
        ros::Time last_stamp;

        for (const rosbag::MessageInstance& m : view) {
            auto pkt = m.instantiate<ethernet_msgs::Packet>();
            if (!pkt) continue;

            std::string sender_ip_str = ipToString(pkt->sender_ip);
            if (sender_ip_str != filter_ip) {
                continue;  // Skip packets from other IPs
            }

            ros::Time current_stamp = m.getTime();
            if (!last_stamp.isZero() && std::abs((current_stamp - last_stamp).toSec()) > time_jump_threshold_sec) {
                std::cerr << "[WARN] Time jump detected. Resetting decoder." << std::endl;
                NComInvalidate(decoder);
            }
            last_stamp = current_stamp;

            const uint8_t* raw = pkt->payload.data();
            size_t length = pkt->payload.size();

            if (length != expected_payload_size) {
                std::cerr << "[WARN] Skipping packet with unexpected size: " << length << std::endl;
                continue;
            }

            int result = NComNewChars(decoder, raw, length);
            if (result == COM_NEW_UPDATE) {
                if (decoder->mIsLatValid && decoder->mIsLonValid && decoder->mIsAltValid) {
                    double utm_e = 0.0, utm_n = 0.0;
                    int zone = 0;
                    bool northp = true;

                    try {
                        GeographicLib::UTMUPS::Forward(decoder->mLat, decoder->mLon, zone, northp, utm_e, utm_n);
                    } catch (const std::exception& e) {
                        std::cerr << "[ERROR] UTM conversion failed: " << e.what() << std::endl;
                        continue;
                    }

                    double utm_z = decoder->mAlt;  // Use altitude directly as Z in UTM-style Cartesian coords

                    uint64_t timestamp_ns = static_cast<uint64_t>(current_stamp.sec) * 1'000'000'000ULL + current_stamp.nsec;

                    outfile << timestamp_ns << ","
                            << decoder->mLat << ","
                            << decoder->mLon << ","
                            << decoder->mAlt << ","
                            << utm_e << ","
                            << utm_n << ","
                            << utm_z << ","
                            << (northp ? std::to_string(zone) + "N" : std::to_string(zone) + "S") << ","
                            << decoder->mPitch << ","
                            << decoder->mRoll << ","
                            << decoder->mHeading << "\n";
                } else {
                    std::cerr << "[INFO] Ignored packet: invalid lat/lon/alt." << std::endl;
                }
            } else {
                std::cerr << "[ERROR] Decoder did not return COM_NEW_UPDATE. Result: " << result << std::endl;
            }
        }

        NComDestroyNComRxC(decoder);
        bag.close();
        outfile.close();

        std::cout << "✅ Finished decoding NCOM packets to: " << output_path << std::endl;

    } catch (const rosbag::BagException& e) {
        std::cerr << "❌ Failed to read bag: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
