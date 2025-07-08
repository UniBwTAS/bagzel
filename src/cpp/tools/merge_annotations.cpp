// SPDX-FileCopyrightText: 2025 Leon Pohl <leon.pohl@unibw.de>
//
// SPDX-License-Identifier: Apache-2.0

#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <random>
#include <algorithm>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include <filesystem>

namespace fs = std::filesystem;
using json = nlohmann::json;

// Load all annotations from multiple JSON files
std::vector<json> load_annotations_from_files(const std::vector<fs::path>& input_files) {
    std::vector<json> all_annotations;

    for (const auto& file_path : input_files) {
        std::ifstream input_file(file_path);
        if (!input_file.is_open()) {
            std::cerr << "⚠️ WARNING: Could not open " << file_path << ". Skipping." << std::endl;
            continue;
        }

        try {
            json annotations;
            input_file >> annotations;

            if (annotations.is_array()) {
                for (const auto& ann : annotations) {
                    all_annotations.push_back(ann);
                }
            } else {
                std::cerr << "⚠️ WARNING: Expected array in file " << file_path << ". Skipping." << std::endl;
            }
        } catch (json::parse_error& e) {
            std::cerr << "⚠️ WARNING: Failed to parse " << file_path << ": " << e.what() << std::endl;
        }
    }

    return all_annotations;
}

// Save JSON data to file
void save_json(const fs::path& path, const std::vector<json>& data) {
    std::ofstream out_file(path);
    if (!out_file.is_open()) {
        throw std::runtime_error("Failed to open output file: " + path.string());
    }
    out_file << std::setw(4) << json(data) << std::endl;
}

// Generate a manifest entry
json generate_manifest_entry(const fs::path& file_path, const std::vector<fs::path>& metadata_paths) {
    std::ifstream input(file_path);
    if (!input.is_open()) {
        throw std::runtime_error("Cannot open file: " + file_path.string());
    }

    json annotations;
    input >> annotations;

    size_t num_sequences = annotations.is_array() ? annotations.size() : 0;
    size_t num_frames = 0;

    for (const auto& seq : annotations) {
        if (seq.contains("num_frames") && seq["num_frames"].is_number()) {
            num_frames += seq["num_frames"].get<size_t>();
        }
    }

    std::string bag_name = "UNKNOWN";
    double duration = 0.0;
    json gps_start = nullptr;

    for (const auto& meta_path : metadata_paths) {
        std::ifstream meta_file(meta_path);
        if (!meta_file.is_open()) continue;

        try {
            json meta;
            meta_file >> meta;

            if (meta.contains("bag_file") && meta.contains("name") && meta.contains("duration_sec")) {
                fs::path bag_path = meta["bag_file"].get<std::string>();
                std::string name = meta["name"].get<std::string>();

                if (file_path.string().find(name) != std::string::npos ||
                    bag_path.parent_path() == file_path.parent_path().parent_path()) {
                    bag_name = name;
                    duration = meta["duration_sec"].get<double>();

                    if (meta.contains("gps_start")) {
                        gps_start = meta["gps_start"];
                    }

                    break;
                }
            }
        } catch (...) {
            continue;
        }
    }

    return {
        {"file", file_path.string()},
        {"num_sequences", num_sequences},
        {"num_frames", num_frames},
        {"duration_sec", duration},
        {"bag_name", bag_name},
        {"gps_start", gps_start}
    };
}

double compute_total_duration(const std::vector<json>& entries) {
    double total = 0.0;
    for (const auto& entry : entries) {
        if (entry.contains("duration_sec")) {
            total += entry["duration_sec"].get<double>();
        }
    }
    return total;
}

int main(int argc, char* argv[]) {
    if (argc < 8) {
        std::cerr << "Usage: " << argv[0]
                  << " <input*.json> <meta*.json> <train_output.json> <val_output.json> <train_manifest.json> <val_manifest.json> <val_percent> <seed>" << std::endl;
        return 1;
    }

    try {
        int total_args = argc;
        int extra_args = 6; // 4 output files + val_percent + seed
        int data_args = total_args - 1 - extra_args;

        if (data_args % 2 != 0) {
            throw std::invalid_argument("Mismatched number of annotation and metadata files.");
        }

        int num_inputs = data_args / 2;

        std::vector<fs::path> input_files;
        std::vector<fs::path> metadata_files;

        for (int i = 1; i <= num_inputs; ++i)
            input_files.emplace_back(argv[i]);

        for (int i = 1 + num_inputs; i <= data_args; ++i)
            metadata_files.emplace_back(argv[i]);

        fs::path train_output = argv[argc - 6];
        fs::path val_output = argv[argc - 5];
        fs::path train_manifest_output = argv[argc - 4];
        fs::path val_manifest_output = argv[argc - 3];
        int val_percent = std::stoi(argv[argc - 2]);
        int seed = std::stoi(argv[argc - 1]);

        if (val_percent < 0 || val_percent > 100) {
            throw std::invalid_argument("Validation split percent must be between 0 and 100.");
        }

        double val_ratio = val_percent / 100.0;

        // Count sequences
        std::vector<std::pair<fs::path, size_t>> file_sequence_counts;
        size_t total_sequences = 0;

        for (const auto& file : input_files) {
            std::ifstream f(file);
            json annotations;
            f >> annotations;
            size_t count = annotations.is_array() ? annotations.size() : 0;
            file_sequence_counts.emplace_back(file, count);
            total_sequences += count;
        }

        size_t target_val_sequences = static_cast<size_t>(val_ratio * total_sequences);

        // Shuffle and split
        std::mt19937 rng(seed);
        std::shuffle(file_sequence_counts.begin(), file_sequence_counts.end(), rng);

        std::vector<fs::path> val_files;
        std::vector<fs::path> train_files;
        size_t val_sequences = 0;

        for (const auto& [file, count] : file_sequence_counts) {
            if (val_sequences < target_val_sequences || val_files.empty()) {
                val_files.push_back(file);
                val_sequences += count;
            } else {
                train_files.push_back(file);
            }
        }

        // Load and save annotations
        auto train_annotations = load_annotations_from_files(train_files);
        auto val_annotations = load_annotations_from_files(val_files);

        save_json(train_output, train_annotations);
        save_json(val_output, val_annotations);

        // Generate and save manifests
        std::vector<json> train_manifest, val_manifest;

        for (const auto& file : train_files)
            train_manifest.push_back(generate_manifest_entry(file, metadata_files));

        for (const auto& file : val_files)
            val_manifest.push_back(generate_manifest_entry(file, metadata_files));

        double train_duration = compute_total_duration(train_manifest);
        double val_duration = compute_total_duration(val_manifest);
        double actual_ratio = static_cast<double>(val_annotations.size()) /
                              (train_annotations.size() + val_annotations.size());

        train_manifest.push_back({
            {"summary", {
                {"total_files", train_files.size()},
                {"total_sequences", train_annotations.size()},
                {"total_duration_sec", train_duration}
            }}
        });

        val_manifest.push_back({
            {"summary", {
                {"total_files", val_files.size()},
                {"total_sequences", val_annotations.size()},
                {"total_duration_sec", val_duration},
                {"target_val_ratio_percent", val_percent},
                {"actual_val_ratio_percent", actual_ratio * 100.0}
            }}
        });

        save_json(train_manifest_output, train_manifest);
        save_json(val_manifest_output, val_manifest);

        // Report
        std::cout << "✅ Smart split complete:" << std::endl;
        std::cout << "   🏋️‍♂️ Train files: " << train_files.size() << ", sequences: " << train_annotations.size() << std::endl;
        std::cout << "   🧪 Val files: " << val_files.size() << ", sequences: " << val_annotations.size() << std::endl;
        std::cout << "   🗂️  Manifests saved as: " << train_manifest_output.filename() << " and " << val_manifest_output.filename() << std::endl;
        std::cout << "   ⏱️ Total train duration: " << train_duration << " sec" << std::endl;
        std::cout << "   ⏱️ Total val duration: " << val_duration << " sec" << std::endl;
        std::cout << "   🎯 Target val ratio: " << val_percent << "%, actual: " << (actual_ratio * 100.0) << "%" << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "❌ ERROR: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
