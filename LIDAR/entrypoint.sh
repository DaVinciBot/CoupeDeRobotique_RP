#!/bin/bash

# Source the ROS environments
source /opt/ros/jazzy/setup.bash
source /work/install/setup.bash

# Start the SICK driver in the background (nohup keeps it alive)
nohup ros2 run sick_scan_xd sick_generic_caller \
  /work/src/sick_scan_xd/launch/sick_tim_5xx.launch \
  hostname:=192.168.0.1 use_binary_protocol:=true > /dev/null 2>&1 &

# Wait (up to ~30 s) until the /scan topic is published by the driver
for i in $(seq 1 30); do
  if ros2 topic list | grep -q "scan"; then
    echo "Driver is publishing /scan. Starting the bridge..."
    break
  fi
  sleep 1
done

# Start the bridge in the foreground (keeps the container alive)
python3 /work/bridge.py
