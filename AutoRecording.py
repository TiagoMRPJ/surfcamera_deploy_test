import time
import utils

class AutoRecordingController:
    def __init__(self, CameraStateDB, GpsDB):
        print("AutoRecordingController Initialized")
        self.cam_state = CameraStateDB
        self.gps_points = GpsDB

        # Different thresholds for start and stop
        self.threshold_speed_start = 2.5     # Speed above which recording starts
        self.threshold_speed_stop = 2.25     # Speed below which recording stops

        # Hysteresis timers (in seconds)
        self.threshold_start_hyster = 3.0    # Must stay above start threshold this long
        self.threshold_stop_hyster = 4.0     # Must stay below stop threshold this long

        # Timestamp placeholders
        self.timestamp_start_hyster = time.time()
        self.timestamp_stop_hyster = time.time()

        # GPS-related vars
        self.prev_lat, self.prev_lon = 0, 0
        self.prev_speed = 0
        self.gpsSpeed = 0
        self.prev_time = 0
        self.gpsSpeedAlpha = 0.66  # Exponential moving average

        # Camera control
        self.cam_state.enable_auto_recording = True

    def updateGPSSpeed(self):
        current_time = self.gps_points.last_gps_time
        try:
            if self.prev_lat != 0 and self.prev_lon != 0:
                prev_loc = utils.Location(self.prev_lat, self.prev_lon)
                loc = utils.Location(self.gps_points.latest_gps_data['latitude'], self.gps_points.latest_gps_data['longitude'])
                distance = utils.get_distance_between_locations(loc, prev_loc) # Returns distance in meters
                time_diff = (current_time - self.prev_time)
                if time_diff > 0 and distance >= 0:
                    self.gpsSpeed =  distance / time_diff
                    self.gpsSpeed =  self.gpsSpeedAlpha * self.prev_speed + (1 - self.gpsSpeedAlpha) * self.gpsSpeed
                    
            # Update previous values
            self.prev_lat = self.gps_points.latest_gps_data['latitude']
            self.prev_lon = self.gps_points.latest_gps_data['longitude']
            self.prev_time = current_time
            self.prev_speed = self.gpsSpeed
        except Exception as e:
            print("Error in updateGPSSpeed:", e)

    def check(self):
        self.updateGPSSpeed()
        print(f"GPS Speed: {self.gpsSpeed:.2f} m/s")

        current_time = time.time()

        # --- START CONDITION ---
        if self.gpsSpeed > self.threshold_speed_start:
            # Surfer is moving fast enough — refresh "start" timer
            self.timestamp_start_hyster = current_time

        # --- STOP CONDITION ---
        if self.gpsSpeed < self.threshold_speed_stop:
            # Surfer is slow enough — refresh "stop" timer
            self.timestamp_stop_hyster = current_time

        # Trigger recording start
        if (not self.cam_state.is_recording and current_time - self.timestamp_start_hyster > self.threshold_start_hyster):
            print("AutoRecording START Triggered")
            self.cam_state.start_recording = True

        # Trigger recording stop
        if (self.cam_state.is_recording and current_time - self.timestamp_stop_hyster > self.threshold_stop_hyster):
            print("AutoRecording STOP Triggered")
            self.cam_state.start_recording = False
            
    def manualStopRecording(self):
        if self.cam_state.start_recording:
            self.cam_state.start_recording = False

import os
       
def count_files_in_directory(directory_path):
    try:
        return len([f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))])
    except FileNotFoundError:
        print(f"Directory '{directory_path}' not found.")
        return 0
    
