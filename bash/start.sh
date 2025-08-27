#!/bin/bash

#bash update_local_repo.sh

# Define the serial devices you want to check
SERIAL_DEVICES=("/dev/ttyUSB0" "/dev/ttyUSB1")

# Maximum time to wait in seconds
MAX_WAIT=60

# Start time
START_TIME=$(date +%s)

# Check for each serial device
for SERIAL_DEVICE in "${SERIAL_DEVICES[@]}"; do
    echo "Checking for serial device $SERIAL_DEVICE..."
    while [ ! -e $SERIAL_DEVICE ]; do
        # Check elapsed time
        CURRENT_TIME=$(date +%s)
        ELAPSED_TIME=$((CURRENT_TIME - START_TIME))

        # Break if time limit exceeded
        if [ $ELAPSED_TIME -ge $MAX_WAIT ]; then
            echo "Timeout reached. Could not find $SERIAL_DEVICE."
            exit 1
        fi

        sleep 1
    done
done

echo "All devices checked successfully. Running main.py"
cd /home/idmind/surf_camera
sudo python main.py
