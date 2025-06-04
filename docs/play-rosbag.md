# Play a rosbag
```bash
bazel run rosbag_play -- /home/lepo/git/pas-mono-intern/cluster/bagzel/data/rosbags/2024-06-26_15-08-50_tas/2024-06-26-15-08-51.bag --clock
```

# Record a rosbag
```bash
bazel run rosbag_record -- -a --duration 10 -o /home/lepo/git/pas-mono-intern/cluster/bagzel/data/output/
```

Fix clock issue

```bash
rosparam set use_sim_time true 
```
