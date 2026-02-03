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

enum class Mode : uint8_t { Split, Single };

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
    if (argc < 2) {
        std::cerr
            << "Usage (split, default):\n  " << argv[0]
            << " [--single] <input*.json> <meta*.json> <train_output.json> <val_output.json> <train_manifest.json> <val_manifest.json> <val_percent> <seed>\n\n"
            << "Usage (single):\n  " << argv[0]
            << " --single <input*.json> <meta*.json> <output.json> <manifest.json>\n\n"
            << "Notes:\n"
            << "  - In both modes, pass all annotation files first, then all metadata files.\n"
            << "  - The boundary is inferred from the number of trailing args required by the chosen mode.\n";
        return 1;
    }

    try {
        // --- detect mode
        Mode mode = Mode::Split;
        std::vector<const char*> args;
        args.reserve(argc - 1);
        for (int i = 1; i < argc; ++i) {
            if (std::string(argv[i]) == "--single") {
                mode = Mode::Single;
            } else {
                args.push_back(argv[i]);
            }
        }

        // trailing outputs expected by each mode
        int trailing_needed = (mode == Mode::Split) ? 6 : 2; // split: 4 outputs + val_percent + seed; single: 1 output + 1 manifest

        if ((int)args.size() < trailing_needed + 2) {
            throw std::invalid_argument("Not enough arguments after accounting for outputs.");
        }

        // figure out how many input vs meta files:
        // for split: [... inputs][... metas][train.json val.json train.manifest val.manifest val% seed]
        // for single:[... inputs][... metas][output.json manifest.json]
        int data_args = (int)args.size() - trailing_needed;
        if (data_args % 2 != 0) {
            throw std::invalid_argument("Mismatched number of annotation and metadata files.");
        }
        int num_inputs = data_args / 2;

        std::vector<fs::path> input_files;
        std::vector<fs::path> metadata_files;
        input_files.reserve(num_inputs);
        metadata_files.reserve(num_inputs);

        for (int i = 0; i < num_inputs; ++i)
            input_files.emplace_back(args[i]);
        for (int i = num_inputs; i < data_args; ++i)
            metadata_files.emplace_back(args[i]);

        if (mode == Mode::Single) {
            fs::path out_annotations = args[data_args + 0];
            fs::path out_manifest    = args[data_args + 1];

            // ---- SINGLE MODE LOGIC ----
            // Load all annotations from all input files
            auto merged_annotations = load_annotations_from_files(input_files);
            save_json(out_annotations, merged_annotations);

            // Build manifest entries for every source file
            std::vector<json> manifest;
            for (const auto& file : input_files) {
                manifest.push_back(generate_manifest_entry(file, metadata_files));
            }

            double total_duration = compute_total_duration(manifest);
            manifest.push_back({
                {"summary", {
                    {"total_files", input_files.size()},
                    {"total_sequences", merged_annotations.size()},
                    {"total_duration_sec", total_duration}
                }}
            });

            save_json(out_manifest, manifest);

            std::cout << "✅ Single merge complete:\n"
                      << "   🗃️  Files: " << input_files.size() << ", sequences: " << merged_annotations.size() << "\n"
                      << "   🗂️  Manifest saved as: " << out_manifest.filename() << "\n"
                      << "   ⏱️  Total duration: " << total_duration << " sec\n";
            return 0;
        }

        // ---- SPLIT MODE (original behavior) ----
        fs::path train_output          = args[data_args + 0];
        fs::path val_output            = args[data_args + 1];
        fs::path train_manifest_output = args[data_args + 2];
        fs::path val_manifest_output   = args[data_args + 3];
        int val_percent                = std::stoi(args[data_args + 4]);
        int seed                       = std::stoi(args[data_args + 5]);

        if (val_percent < 0 || val_percent > 100) {
            throw std::invalid_argument("Validation split percent must be between 0 and 100.");
        }

        double val_ratio = val_percent / 100.0;

        // Count sequences per file
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
        auto val_annotations   = load_annotations_from_files(val_files);

        save_json(train_output, train_annotations);
        save_json(val_output, val_annotations);

        // Generate and save manifests
        std::vector<json> train_manifest, val_manifest;

        for (const auto& file : train_files)
            train_manifest.push_back(generate_manifest_entry(file, metadata_files));

        for (const auto& file : val_files)
            val_manifest.push_back(generate_manifest_entry(file, metadata_files));

        double train_duration = compute_total_duration(train_manifest);
        double val_duration   = compute_total_duration(val_manifest);
        double actual_ratio   = static_cast<double>(val_annotations.size()) /
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
        std::cout << "✅ Smart split complete:\n";
        std::cout << "   🏋️‍♂️ Train files: " << train_files.size() << ", sequences: " << train_annotations.size() << "\n";
        std::cout << "   🧪 Val files: " << val_files.size() << ", sequences: " << val_annotations.size() << "\n";
        std::cout << "   🗂️  Manifests saved as: " << train_manifest_output.filename() << " and " << val_manifest_output.filename() << "\n";
        std::cout << "   ⏱️ Total train duration: " << train_duration << " sec\n";
        std::cout << "   ⏱️ Total val duration: " << val_duration << " sec\n";
        std::cout << "   🎯 Target val ratio: " << val_percent << "%, actual: " << (actual_ratio * 100.0) << "%\n";

    } catch (const std::exception& e) {
        std::cerr << "❌ ERROR: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
