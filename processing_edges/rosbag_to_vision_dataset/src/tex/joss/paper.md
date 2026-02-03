<!--
SPDX-FileCopyrightText: 2026 Leon Pohl <leon.pohl@unibw.de>

SPDX-License-Identifier: Apache-2.0
-->

---
title: 'Bagzel: A Bazel Extension for Reproducible Dataset Builds from ROS 1 and ROS 2 Bags'
tags:
  - robotics
  - autonomous driving
  - robot operating system
  - ros
  - ros 2
  - dataset construction
  - data pipelines
  - machine learning
  - bazel
  - build systems
  - python
  - c++
authors:
  - name: Leon Pohl
    orcid: 0000-0002-0714-6921
    affiliation: "1"
  - name: Lukas Beer
    orcid: 0009-0007-1560-229X
    affiliation: "1"
  - name: George Sebastian
    orcid: 0009-0007-9361-0711
    affiliation: "1"
  - name: Mirko Maehlisch
    orcid: 0009-0008-5665-9732
    affiliation: "1"
affiliations:
 - name: Institute for Autonomous Driving, University of the Bundeswehr Munich, Germany
   index: 1
   ror: 05kkv3f82
date: 4 February 2026
bibliography: paper.bib
header-includes:
  - \usepackage{subcaption}
---

# Summary

Robotic systems such as autonomous vehicles, mobile manipulators, and service robots continuously record large amounts of multimodal sensor data. In the Robot Operating System (ROS) ecosystem [@ros:2009; @ros2:2022], these recordings are typically stored as bag files, i.e., ROS 1 rosbag files [@rosbag] and ROS 2 rosbag2 files [@ros2bag].
These bags act as system recorders for robotic platforms, capturing time-synchronized streams from cameras, LiDAR, radar, GNSS/IMU, and internal states. While bags are ideal for debugging, replay, and sharing, they are not directly suitable for use as training datasets, which require structured and reproducible representations. **Bagzel** is an open-source software that leverages the Bazel [@bazel] build system to transform collections of bag files into structured, standardized, and reproducible datasets, including exports in formats such as nuScenes [@nuscenes]. Within Bagzel, raw bags and derived data products (e.g., frames, trajectories, maps, labels, nuScenes-format datasets) are expressed as Bazel targets. By reusing Bazel’s artifact-based, incremental, and deterministic build model, Bagzel enables scalable and maintainable data pipelines. Furthermore, it introduces the concept of large-file hashing and cluster integration, enabling efficient handling of large raw bag files and compute resources. Bagzel is publicly available at https://github.com/UniBwTAS/bagzel.


# Statement of Need

Robotics research and development increasingly relies on supervised and self-supervised learning methods that consume large, diverse datasets. In ROS systems, such data is almost always first recorded as bag files. However, there is a substantial gap between these raw bag files and the curated datasets required for training and evaluating models. In practice, teams must extract task-specific subsets, maintain preprocessing pipelines, track provenance, and rerun expensive preprocessing after changes.

**Bagzel** addresses this gap by treating dataset construction from bags as a build process. Bagzel is a Bazel extension consisting of a set of Starlark rules plus supporting Python and C++ libraries. This lets users declare raw bags, preprocessing steps, and derived datasets (e.g., frames, trajectories, maps, labels, and nuScenes-format exports) as Bazel targets. It then reuses Bazel’s precise dependency tracking, incremental and parallel execution, and hermetic builds across local and cluster environments. This enables reproducible dataset generation by unifying raw data and code builds, supports scalable incremental retraining as new data becomes available, and integrates naturally with continuous integration and continuous deployment (CI/CD) workflows.

Bagzel targets robotics and machine learning (ML) practitioners working with ROS-based autonomy stacks in both academic and industrial settings, providing an open-source framework for scalable and reproducible dataset construction from bags.

# State of the Field

General ML workflow frameworks such as TensorFlow Extended (TFX) [@tfx], Kubeflow Pipelines [@kubeflow-pipelines], MLflow [@mlflow], and DVC [@dvc] provide abstractions for defining data processing graphs, tracking experiments, and integrating with CI/CD systems. While widely adopted, these frameworks are not tightly integrated with the ROS ecosystem and do not natively leverage Bazel’s build and dependency tracking model.

Within the ROS ecosystem, existing tools for extracting datasets from bag files are typically tailored to specific target formats or application scenarios. The work most closely related to Bagzel is rosbag2nuscenes [@Chrosniak:2023], which converts ROS 2 bag data into the nuScenes dataset format. Bagzel builds on this line of work by leveraging Bazel’s incremental build model and explicit dependency tracking to support reproducible and scalable dataset construction.

# Software Design

The full pipeline is structured into three stages: (i) training and architecture definition, (ii) dataset preparation and structuring, and (iii) training execution. Bagzel fills the gap in the dataset preparation stage. The overall concept is illustrated in \autoref{fig:concept}.

\begin{figure}[t]
  \centering
  \small
  \includegraphics[width=\linewidth]{figs/concept.pdf}
  \caption{Concept of treating model training as a Bazel build.
  The workflow is structured into three stages: (i) model architecture and training
  configuration expressed as Bazel targets, (ii) dataset preparation from bags via
  Bagzel rules, and (iii) training execution as Bazel actions. In this formulation,
  both datasets and model artifacts become build products, so changes to
  any input dependency automatically trigger incremental rebuilding of only the
  affected downstream artifacts.}
  \label{fig:concept}
\end{figure}

### Large-File Hashing

A practical challenge in Bazel is change detection for very large inputs. While Bazel normally hashes file contents byte-for-byte, robotics bag files may exceed 100 GB, making repeated hashing expensive in incremental builds. Therefore, Bagzel *optionally* supports an alternative digest mechanism for large inputs. A watchdog service records a digest for each file as an extended attribute (e.g., `user.bagzel_hash`) whenever a bag file is created or modified (\autoref{fig:hashing}). Bazel can be configured to use this attribute as the file’s digest via `--unix_digest_hash_attribute_name=user.bagzel_hash`, avoiding full file rehashing. Correctness relies on the attribute being updated on content changes. If the attribute is unavailable or missing, Bazel automatically falls back to its default hashing behavior.

\begin{figure}[t]
  \centering
  \small

  \begin{subfigure}{0.48\linewidth}
    \centering
    \includegraphics[width=\linewidth]{figs/hashing_b.pdf}
    \caption{Bagzel large-file hashing with extended attributes.}
    \label{fig:hashing-bagzel}
  \end{subfigure}
  \hfill
  \begin{subfigure}{0.48\linewidth}
    \centering
    \includegraphics[width=\linewidth]{figs/hashing_a.pdf}
    \caption{Standard Bazel full-file hashing.}
    \label{fig:hashing-standard}
  \end{subfigure}

  \caption{Comparison of hashing strategies for bag inputs in Bagzel.
  (a) Bagzel large-file hashing uses a file server watchdog and extended file attributes to cache content hashes and avoid rereading unchanged bag files.
  (b) Standard Bazel full-file hashing recomputes hashes over entire files and becomes expensive for large bag files.}
  \label{fig:hashing}
\end{figure}


### Cluster Integration with Bazel

\autoref{fig:cluster} illustrates an integration concept between Bazel and a Slurm compute cluster for large-scale training. All inputs to a training run, including source code, configuration files, and processed datasets, are modeled as Bazel dependencies. This allows Bazel to hash inputs, reuse cached model artifacts when inputs are unchanged, and trigger new training actions when they are not. Training is implemented as a thin wrapper that submits Slurm jobs and exposes model checkpoints and metrics as Bazel outputs. Therefore, launching a cluster training run reduces to invoking a standard Bazel build command. The same wrapper can also be executed directly via Slurm during development, enabling existing training pipelines to be incrementally upgraded to benefit from Bazel’s caching, reproducibility, and artifact management.

\begin{figure}[t]
  \centering
  \small
  \includegraphics[width=\linewidth]{figs/cluster.pdf}
  \caption{Conceptual Bazel–Slurm integration for training workloads. Bazel determines whether retraining is required based on hashed inputs and, when necessary, submits Slurm jobs that produce model artifacts and metrics as build outputs.}
  \label{fig:cluster}
\end{figure}

## Dataset Construction with Bagzel

Bagzel supports two dataset builds: (i) extraction of vision datasets from ROS 1 bags, including image streams, annotations, and maps (\autoref{fig:sample}); and (ii) export of synchronized multi-sensor logs from ROS 1 and ROS 2 bags to the nuScenes data format. Building the corresponding Bazel targets produces nuScenes-format datasets, from which synchronized camera views, LiDAR overlays, and bird’s-eye-view (BEV) representations can be rendered, as shown in \autoref{fig:nuscenes-bagzel}.

\begin{figure}[t]
  \centering
  \small
  \includegraphics[width=\linewidth]{figs/sample.pdf}
  \caption{Visual dataset generated with Bagzel from ROS 1 bag files.
Each bag is treated as a Bazel build target, and a single build invocation
produces structured artifacts such as image sequences, trajectories, maps,
metadata, and annotations.}
  \label{fig:sample}
\end{figure}


\newlength{\subfigSmall}
\setlength{\subfigSmall}{0.48\linewidth} 

\begin{figure}[t]
  \centering
  \small

  % Row 1: four camera views (each ~0.24\linewidth)
  \begin{subfigure}{\subfigSmall}
    \includegraphics[width=\linewidth]{figs/nuScenes/cam_front.jpg}
    \caption{}
  \end{subfigure}\hfill
  \begin{subfigure}{\subfigSmall}
    \includegraphics[width=\linewidth]{figs/nuScenes/cam_back.jpg}
    \caption{}
  \end{subfigure}\hfill
  \begin{subfigure}{\subfigSmall}
    \includegraphics[width=\linewidth]{figs/nuScenes/cam_left.jpg}
    \caption{}
  \end{subfigure}\hfill
  \begin{subfigure}{\subfigSmall}
    \includegraphics[width=\linewidth]{figs/nuScenes/cam_right.jpg}
    \caption{}
  \end{subfigure}

  \medskip

  % Row 2: LiDAR overlay (left) and BEV top-down (right) side-by-side
  \begin{subfigure}{\subfigSmall}
    \includegraphics[width=\linewidth]{figs/nuScenes/lidar_on_cam_front.jpg}
    \caption{}
  \end{subfigure}\hfill
  \begin{subfigure}{\subfigSmall}
    \includegraphics[width=\linewidth]{figs/nuScenes/lidar_bev.jpg}
    \caption{}
  \end{subfigure}

  \caption{NuScenes-format dataset generated with Bagzel from bag files.
The figure shows representative renderings derived from the dataset, including
(a–d) front, rear, left, and right camera views; (e) LiDAR returns overlaid in
image space; and (f) a bird’s-eye-view (BEV) LiDAR projection.}
  \label{fig:nuscenes-bagzel}
\end{figure}

# Research Impact Statement
Bagzel is used at the Institute for Autonomous Driving, University of the Bundeswehr Munich, to generate reproducible datasets from large ROS 1 and ROS 2 bag collections for autonomous driving research. It supports ongoing perception and localization projects where frequent dataset regeneration and retraining are required. The software has been presented at BazelCon 2025 [@pohlBazelCon:2025] and ROSCon DE & FR 2025 [@pohlRosCon:2025] and is released as open source with public documentation, enabling adoption by other research groups.

# AI Usage Disclosure
Generative AI tools were used in a limited capacity for code assistance and language editing. All generated content was reviewed, tested, and validated by the authors, who take full responsibility for the software and the manuscript.

# Acknowledgements

The authors acknowledge support from the Federal Office of Bundeswehr Equipment, Information Technology, and In-Service Support (BAAINBw). This work was also supported by dtec.bw, the Digitalization and Technology Research Center of the Bundeswehr, under project MORE. Dtec.bw is funded by the European Union through the NextGenerationEU program. We thank our colleagues at the Institute for Autonomous Driving, University of the Bundeswehr Munich, for feedback and for providing vehicles, data, and recording infrastructure. We also thank the ROS and Bazel open-source communities.

# References
