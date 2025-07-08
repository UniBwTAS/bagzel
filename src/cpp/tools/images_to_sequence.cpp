// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <iostream>
#include <filesystem>
#include <fstream>
#include <vector>
#include <regex>
#include <iomanip>
#include <nlohmann/json.hpp>
#include <unordered_map>
#include <sstream>
#include <limits>
#include <optional>

namespace fs = std::filesystem;
using json = nlohmann::json;

// ---------- Struct ----------
struct Pose6D {
    double x, y, z;
    double roll, pitch, yaw;
};

// ---------- Parse CSV ----------
std::unordered_map<uint64_t, Pose6D> parse_oxts_csv(const fs::path& csv_path) {
    std::unordered_map<uint64_t, Pose6D> traj_data;
    std::ifstream file(csv_path);
    std::string line;

    std::getline(file, line); // skip header

    while (std::getline(file, line)) {
        std::stringstream ss(line);
        std::string token;
        std::vector<std::string> tokens;

        while (std::getline(ss, token, ',')) {
            tokens.push_back(token);
        }

        // Expecting: timestamp,x,y,z,roll,pitch,yaw
        if (tokens.size() < 7) continue;

        try {
            uint64_t timestamp = std::stoull(tokens[0]);
            double x = std::stod(tokens[1]);
            double y = std::stod(tokens[2]);
            double z = std::stod(tokens[3]);
            double roll = std::stod(tokens[4]);
            double pitch = std::stod(tokens[5]);
            double yaw = std::stod(tokens[6]);

            traj_data[timestamp] = {x, y, z, roll, pitch, yaw};
        } catch (const std::exception& e) {
            std::cerr << "⚠️ Failed to parse line: " << line << " - " << e.what() << std::endl;
        }
    }

    return traj_data;
}

// ---------- Interpolate Pose ----------
std::optional<Pose6D> interpolate_pose(uint64_t ts,
                        const std::vector<std::pair<uint64_t, Pose6D>>& sorted_oxts) {
    if (sorted_oxts.empty()) {
        std::cerr << "⚠️ WARNING: Trajectory data is empty.\n";
        return std::nullopt;
    }

    if (ts < sorted_oxts.front().first || ts > sorted_oxts.back().first) {
        std::cerr << "⚠️ WARNING: Image timestamp " << ts
                  << " is outside trajectory bounds ["
                  << sorted_oxts.front().first << ", "
                  << sorted_oxts.back().first << "]\n";
        return std::nullopt;
    }

    for (size_t i = 0; i < sorted_oxts.size() - 1; ++i) {
        uint64_t t0 = sorted_oxts[i].first;
        uint64_t t1 = sorted_oxts[i + 1].first;

        if (t0 <= ts && ts <= t1) {
            double alpha = double(ts - t0) / (t1 - t0);
            const Pose6D& p0 = sorted_oxts[i].second;
            const Pose6D& p1 = sorted_oxts[i + 1].second;

            return Pose6D {
                p0.x + alpha * (p1.x - p0.x),
                p0.y + alpha * (p1.y - p0.y),
                p0.z + alpha * (p1.z - p0.z),
                p0.roll + alpha * (p1.roll - p0.roll),
                p0.pitch + alpha * (p1.pitch - p0.pitch),
                p0.yaw + alpha * (p1.yaw - p0.yaw),
            };
        }
    }

    std::cerr << "⚠️ WARNING: Failed to interpolate timestamp " << ts << ".\n";
    return std::nullopt;
}

// ---------- Extract Sorted Frames ----------
std::vector<std::pair<uint64_t, fs::path>> get_sorted_frames(const fs::path& images_dir) {
    std::vector<std::pair<uint64_t, fs::path>> numbered_frames;
    std::regex frame_regex(".*__(\\d{12,19})\\.png");

    for (const auto& entry : fs::directory_iterator(images_dir)) {
        if (!fs::is_regular_file(entry.status())) continue;

        std::string filename = entry.path().filename().string();
        std::smatch match;
        if (std::regex_match(filename, match, frame_regex)) {
            uint64_t timestamp = std::stoull(match[1].str());
            numbered_frames.emplace_back(timestamp, entry.path());
        }
    }

    std::sort(numbered_frames.begin(), numbered_frames.end());
    return numbered_frames;
}

// ---------- Create Sequences With Trajectory ----------
void create_sequences_with_symlinks(const fs::path& images_dir,
                                    const fs::path& oxts_csv_path,
                                    const fs::path& output_json_path,
                                    int sequence_length = 25)
{
    auto sorted_frames = get_sorted_frames(images_dir);
    json annotation_data;

    if (sorted_frames.empty()) {
        std::cerr << "⚠️ No frames found in " << images_dir << std::endl;
        std::ofstream json_file(output_json_path);
        json_file << std::setw(4) << json::array() << std::endl;
        return;
    }

    // Parse OXTS and convert to sorted vector
    auto oxts_data = parse_oxts_csv(oxts_csv_path);
    std::vector<std::pair<uint64_t, Pose6D>> sorted_oxts(oxts_data.begin(), oxts_data.end());
    std::sort(sorted_oxts.begin(), sorted_oxts.end(), [](const auto& a, const auto& b) {
        return a.first < b.first;
    });

    fs::path topic_dir = images_dir.filename();                           
    fs::path rosbag_dir = images_dir.parent_path().parent_path();         
    std::string rosbag_name = rosbag_dir.filename().string();             
    std::string topic_name = topic_dir.string();                          

    fs::path sequences_dir = rosbag_dir / "sequences" / topic_name;
    fs::create_directories(sequences_dir);

    size_t sequence_id = 0;
    size_t frame_index = 0;

    while (frame_index < sorted_frames.size()) {
        std::ostringstream folder_name;
        folder_name << std::setfill('0') << std::setw(3) << sequence_id;
        fs::path sequence_folder = sequences_dir / folder_name.str();
        fs::create_directories(sequence_folder);

        std::vector<std::string> frame_paths;
        std::vector<double> traj_xyz;
        std::vector<double> traj_rpy;
        std::vector<Pose6D> pose_sequence;
        size_t frames_in_this_sequence = 0;

        for (int i = 0; i < sequence_length && frame_index < sorted_frames.size(); ++i, ++frame_index) {
            uint64_t timestamp = sorted_frames[frame_index].first;
            fs::path image_path = sorted_frames[frame_index].second;

            auto maybe_pose = interpolate_pose(timestamp, sorted_oxts);
            if (!maybe_pose.has_value()) {
                continue;  // skip this frame
            }
            Pose6D current_pose = maybe_pose.value();
            pose_sequence.push_back(current_pose);

            fs::path image_filename = image_path.filename(); 
            fs::path link_path = sequence_folder / image_filename;

            try {
                fs::path relative_target = fs::path("..") / ".." / ".." / "images" / topic_name / image_filename;

                if (fs::exists(link_path)) fs::remove(link_path);
                fs::create_symlink(relative_target, link_path);
                frame_paths.push_back(image_path.string());
                frames_in_this_sequence++;
            } catch (const fs::filesystem_error& e) {
                std::cerr << "⚠️  Symlink creation failed: " << e.what() << std::endl;
            }
        }

        if (frames_in_this_sequence == 0) {
            std::cerr << "⚠️ Sequence " << sequence_id << " has no valid frames. Skipping.\n";
            continue;
        }

        // Compute relative trajectory
        if (!pose_sequence.empty()) {
            Pose6D origin = pose_sequence[0];
            for (const auto& p : pose_sequence) {
                traj_xyz.push_back(p.x - origin.x);
                traj_xyz.push_back(p.y - origin.y);
                traj_xyz.push_back(p.z - origin.z);

                traj_rpy.push_back(p.roll - origin.roll);
                traj_rpy.push_back(p.pitch - origin.pitch);
                traj_rpy.push_back(p.yaw - origin.yaw);
            }
        }

        std::vector<json> trajectory_table;
        for (size_t i = 0; i < pose_sequence.size(); ++i) {
            trajectory_table.push_back({
                {"frame", i},
                {"x", traj_xyz[i * 3 + 0]},
                {"y", traj_xyz[i * 3 + 1]},
                {"z", traj_xyz[i * 3 + 2]},
                {"roll", traj_rpy[i * 3 + 0]},
                {"pitch", traj_rpy[i * 3 + 1]},
                {"yaw", traj_rpy[i * 3 + 2]}
            });
        }

        annotation_data.push_back({
            {"num_frames", frames_in_this_sequence},
            {"frames", frame_paths},
            {"trajectory", trajectory_table}
        });


        sequence_id++;
    }

    std::ofstream json_file(output_json_path);
    json_file << std::setw(4) << annotation_data << std::endl;
    std::cout << "✅ Done. Created " << sequence_id << " sequences." << std::endl;
    std::cout << "📝 Annotation saved to: " << output_json_path << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0] << " <images_dir> <oxts_csv_path> <output_json_path> [sequence_length]" << std::endl;
        return 1;
    }

    fs::path images_dir = argv[1];
    fs::path oxts_csv_path = argv[2];
    fs::path output_json_path = argv[3];
    int sequence_length = (argc >= 5) ? std::stoi(argv[4]) : 25;

    create_sequences_with_symlinks(images_dir, oxts_csv_path, output_json_path, sequence_length);
    return 0;
}
