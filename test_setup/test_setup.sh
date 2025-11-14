#!/bin/bash

# Make this executable: chmod +x test_setup.sh

# Base directory where your scripts live
BASE_DIR="/home/idmind/surfcamera_deploy_test/test_setup"

echo "Starting RTSP MJPEG server..."
nohup python3 "$BASE_DIR/rtsp_mjpeg.py" 

echo "Starting Test UI..."
nohup python3 "$BASE_DIR/testing_ui.py" 

echo "Starting Test Servo Control..."
nohup python3 "$BASE_DIR/testing_servos.py" 

echo "All scripts started. Run each one manually if you run into issues."
