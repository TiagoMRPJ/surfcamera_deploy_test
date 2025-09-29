import db
import math
import utils
import time
import numpy as np
import IOBoardDriver as GPIO
import Zoom_CBN8125 as ZoomController
from utils import Location
from collections import deque
import json
from AutoRecording import AutoRecordingController
import logging

# Config log
logging.basicConfig(
    filename="/home/idmind/surfcamera_deploy_test/logs/tracking_log.txt",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger()

conn = db.get_connection()
gps_points = db.GPSData(conn)
commands = db.Commands(conn)
cam_state = db.CameraState(conn)
webapp = db.WebApp(conn)
autorec = AutoRecordingController(cam_state, gps_points)

IO = GPIO.FrontBoardDriver()

Zoom = ZoomController.SoarCameraZoomFocus()

lower_distance = 0
upper_distance = 0

# Logging function to save the data
def log_data(calculated_angle, actual_angle, pan_speed, file_path="recording_log.txt"):
    # Append the data to a file
    with open(file_path, "a+") as log_file:
        log_file.write(f"{time.time()}, {calculated_angle}, {actual_angle}, {pan_speed}\n")


distance_zoom_table = {
    1:1,
    15:1,
    25:2,
    50:4,
    75:4.5,
    100:5,
    120:7,
    140:9,
    160:11,
    215:13,
    300:15,
    600:25
    # Add as many mappings as needed, making sure they are ordered
}


def normalize_angle(angle):
    return (angle + 180) % 360 - 180

def latlon_to_meters(lat_diff, lon_diff, latitude):
    lat_meters = lat_diff * 111000
    lon_meters = lon_diff * 111000 * math.cos(math.radians(latitude))
    return lat_meters, lon_meters

def gpsDistance(lat1, lon1, lat2, lon2):
	lat1, lon1, lat2, lon2, = map(math.radians, [lat1, lon1, lat2, lon2])
	dlat = lat2 - lat1
	dlon = lon2 - lon1
	a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat1) * math.sin(dlon/2) **2
	c= 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
	distance = 6371 * c
	return distance

trackDistX = 1 # Initiated as non zero just to avoid errors 

def calibrationCoordsCal():
    '''
    Saves gps coordinates for a period of time and returns the average lat and lon
    '''
    calibrationBufferLAT = np.array([])    # [lats]
    calibrationBufferLON = np.array([])    # [lons]
    while len(calibrationBufferLAT) < 50: 
        time.sleep(0.15)
        if IO.getTrackerMessage():         # For every new_reading that comes in
            calibrationBufferLAT = np.append(calibrationBufferLAT, gps_points.latest_gps_data['latitude'])
            calibrationBufferLON = np.append(calibrationBufferLON, gps_points.latest_gps_data['longitude'])
        
    avg_lat = round( np.average(calibrationBufferLAT), 6)
    avg_lon = round( np.average(calibrationBufferLON), 6)
    
    return avg_lat, avg_lon
                
def panCalculations():
    global previous_smoothed_pan
    locationToTrack = Location(gps_points.latest_gps_data['latitude'], gps_points.latest_gps_data['longitude'])
    locationOrigin = Location(gps_points.camera_origin['latitude'], gps_points.camera_origin['longitude'])
    rotation = -np.degrees(utils.get_angle_between_locations(locationOrigin, locationToTrack) - gps_points.camera_heading_angle)
    rotation = normalize_angle(rotation)
    result = round(rotation, 4) 
    return result

previous_smoothed_tilt = 0
tilt_alpha = 0.33

def tiltCalculations():
    global trackDistX
    global previous_smoothed_tilt
    trackDistX = 1000 * gpsDistance(gps_points.camera_origin['latitude'], gps_points.camera_origin['longitude'],
                                    gps_points.latest_gps_data['latitude'], gps_points.latest_gps_data['longitude'])
    trackDistY = gps_points.camera_vertical_distance
    tiltAngle = np.degrees(math.atan2(trackDistX, trackDistY)) - 90
    tiltAngle = previous_smoothed_tilt * (1-tilt_alpha) + tiltAngle * tilt_alpha
    tiltAngle = round(tiltAngle, 2) # Round to 1 decimal place
    previous_smoothed_tilt = tiltAngle
    return -tiltAngle

def zoomCalculations():
    global trackDistX
    
    # Find between which 2 mapped values trackDistx fits. This assumes distance_zoom_table is sorted
    lower_distance = max([d for d in distance_zoom_table if d <= trackDistX], default=1)
    upper_distance = min([d for d in distance_zoom_table if d >= trackDistX], default=15)
    
    if lower_distance == upper_distance:
        new_zoom_level = distance_zoom_table[lower_distance]
    else:
        # Interpolate trackDistx based on the distance_zoom_table lookup values
        x0, y0 = lower_distance, distance_zoom_table[lower_distance]
        x1, y1 = upper_distance, distance_zoom_table[upper_distance]
        new_zoom_level = y0 + (trackDistX - x0) * (y1-y0) / (x1-x0)
        new_zoom_level = round(new_zoom_level * commands.camera_zoom_multiplier, 2)

    if commands.camera_zoom_value is None or abs(new_zoom_level - commands.camera_zoom_value) >= 0.25:
        new_zoom_level = round(new_zoom_level, 2) 
        Zoom.set_zoom_position(new_zoom_level)
        commands.camera_zoom_value = new_zoom_level
        
    return new_zoom_level

panBuffer = deque(maxlen=3)
timeBuffer = deque(maxlen=3)

def main(d):
    try:
        Zoom = ZoomController.SoarCameraZoomFocus()
        CourseCal = utils.courseCalculator(gps_points)
        course = 0
        
        error = 0           # Variables used for velocity PD controller
        previous_error  = 0
        delta_time = 1
        
        angleErrorThreshold = 4
        com_check_timer = 0 
        commands.speed_control_mode_threshold = 0.10 # Threshold for switching between velocity and position control
        
        panAngle = 0
        tiltAngle = 0
        last_read_time = 0
        panSpeed = 0    
        commands.tracking_enabled = False
        
        last_motor_update_time = 0
        MOTOR_UPDATE_FREQUENCY = 3 # Hz
        
        logger.info("Starting Tracking System")
        
        try:
            if int(gps_points.camera_origin['latitude']) == 38 : # Check if there's any calibration already done
                print("Previous Calibration Exists")
            else:
                print("No Previous Calibration")
        except:
            print("No Previous Calibration")
                    
        while not d["stop"]:
            time.sleep(0.01)
            
            
            if time.time() - com_check_timer >= 1:
                
                if time.time() - last_read_time >= 3:
                    IO.setBackPanelLEDs(first = False, second = False)
                else:
                    IO.setBackPanelLEDs(first = True, second = True)

                com_check_timer = time.time()
                    
            if commands.camera_calibrate_origin:         # Calibrate the camera origin coordinate
                commands.camera_calibrate_origin = False
                avg_lat, avg_lon = calibrationCoordsCal()

                gps_points.camera_origin = {
                                            'latitude': avg_lat,
                                            'longitude': avg_lon
                                            }
                print(f"Camera Origin {gps_points.camera_origin['latitude']}, {gps_points.camera_origin['longitude']} Calibrated")
                gps_points.client.dump(["camera_origin"], "db.txt")
                
            elif commands.camera_calibrate_heading:     # Calibrate the camera heading coordinate
                commands.camera_calibrate_heading = False
                avg_lat, avg_lon = calibrationCoordsCal()
                gps_points.camera_heading_coords = {
                                            'latitude': avg_lat,
                                            'longitude': avg_lon
                                            }
                cam_position = Location(gps_points.camera_origin['latitude'], gps_points.camera_origin['longitude'])
                cam_heading = Location(gps_points.camera_heading_coords['latitude'], gps_points.camera_heading_coords['longitude'])
                
                gps_points.camera_heading_angle = utils.get_angle_between_locations(cam_position, cam_heading)
                gps_points.client.dump(["camera_heading_angle"], "db.txt")
                
                print(f"Camera Heading Angle {gps_points.camera_heading_angle}")
                
                print("Camera Heading Calibration Complete")
                logger.info(f"Current Calibration ORIGIN {gps_points.camera_origin} ; Heading Angle {gps_points.camera_heading_angle}")
                
            elif commands.start_pairing:
                paired, pairing = IO.checkTrackerPairing()
                commands.start_pairing = False
                if not paired and not pairing:
                    IO.cancelTrackerPairing()
                    IO.startTrackerPairing()
                    print("Pairing Process Start")
                    
            elif commands.cancel_pairing:
                commands.cancel_pairing = False
                paired, pairing = IO.checkTrackerPairing()
                if paired:
                    IO.cancelTrackerPairing()
                    print("Paired Tracker removed from memory")
                    
            elif commands.calibrate_pan_center:
                commands.calibrate_pan_center = False
                IO.calibratePanCenter()
                
            elif commands.check_pairing:
                commands.check_pairing = False
                paired, pairing = IO.checkTrackerPairing()
                if paired:
                    webapp.IsPaired = True
                    print("Tracker is Paired")
                elif not paired and not pairing:
                    commands.start_pairing = True
                    webapp.IsPaired = False
                    print("No Tracker Paired. Starting Pairing Process")
                else:
                    webapp.IsPaired = False
                    print("Tracker Pairing is Ongoing")
                    
            if IO.getTrackerMessage():
                t = time.time()
                delta_time = t - last_read_time 
                last_read_time = t
                gps_points.last_gps_time = t
                            
                if commands.tracking_enabled:
                    panAngle = panCalculations()
                    tiltAngle = tiltCalculations()
                    if not cam_state.is_recording:
                        currentzoom = zoomCalculations()
                    #course = CourseCal.updateCourse() # Surfer course in radians

                    # Before appending the new value check if it follows the previous Trend
                    # If it does, append it to the array and continue as is
                    # If not, sudden change of direction or stop has occured -> clear buffer and start filling
                    
                    if time.time() - last_motor_update_time >= (1 / MOTOR_UPDATE_FREQUENCY):
                        last_motor_update_time = time.time()
                        
                        # Check if there is a trend in direction and if so calculate the pan speed
                        if tendency(panAngle, panBuffer):
                            panBuffer.append(panAngle)
                            timeBuffer.append(last_read_time)   
                            panSpeed = average_pan_speed(panBuffer, timeBuffer)
                        else:
                            panBuffer.clear()
                            timeBuffer.clear()
                            panBuffer.append(panAngle)
                            timeBuffer.append(last_read_time)   
                            panSpeed = average_pan_speed(panBuffer, timeBuffer)
                                        
                        if trackDistX >= 45:
                                                        
                            #camera_angle = utils.get_angle_between_locations(Location(gps_points.camera_origin['latitude'], gps_points.camera_origin['longitude']), Location(gps_points.latest_gps_data['latitude'], gps_points.latest_gps_data['longitude'])) 
                            if False and utils.is_surfer_incoming(camera_angle, course, threshold=np.radians(10)): # The surfer is coming straight towards the camera
                                IO.setPanVelocityControl() 
                                IO.setPanGoalVelocity(panSpeed)
                                IO.setTiltAngle(tilt = tiltAngle + gps_points.tilt_offset)   
                            
                            elif abs(panSpeed) >= commands.speed_control_mode_threshold and abs(IO.getCurrentPanAngle() - panAngle) < angleErrorThreshold:
                                ''' Velocity Control for a smooth pan movement at considerable speeds '''
                                '''
                                if abs(IO.getCurrentPanAngle() - panAngle) >= 2 and False:
                                    error = panAngle - IO.getCurrentPanAngle()
                                    derivative = abs(error - previous_error) / delta_time
                                    if panAngle < IO.getCurrentPanAngle() and panSpeed < 0:
                                        error = - error
                                    if error / panSpeed < 0:
                                        panSpeed = -panSpeed
                                    previous_error = error
                                    kp = 0.12 
                                    kd = 0.02
                                    adjustment = min(max(kp * error + derivative * kd, -0.3), 0.3)
                                    panSpeed = panSpeed * ( 1 + adjustment)
                                    panSpeed = min(max(panSpeed, -commands.max_pan_speed), commands.max_pan_speed)
                                '''
                                IO.setPanVelocityControl() 
                                IO.setPanGoalVelocity(panSpeed)
                                IO.setTiltAngle(tilt = tiltAngle + gps_points.tilt_offset)                        

                            else:
                                ''' Position Control at lower speeds or if error is too big'''
                                IO.setPanPositionControl()
                                IO.setAngles(pan = round(panAngle, 2), tilt = tiltAngle + gps_points.tilt_offset)
                            
                            print(f"Calc.Pan {panAngle} ; Act.Pan {IO.getCurrentPanAngle()} ; PanSpeed {panSpeed}; Tilt{tiltAngle + gps_points.tilt_offset}; Zoom: {currentzoom}")
                            
                            '''       AUTO RECORDING       '''  
                            autorec.check()       
                            
                        else:
                            print("Tracking is enabled but target is too close to track")
                            IO.setPanGoalVelocity(0)
                                       
                else:           # When the tracking is turned OFF go to standby position 
                    IO.setPanGoalVelocity(0)
                    IO.setPanPositionControl()
                    IO.setAngles(pan = 0, tilt= 5, pan_speed=1, tilt_speed=1)
                    panBuffer.clear()
                    timeBuffer.clear()
                                        
            else:       # No new readings, make sure pan doesnt keep on rotating endlessly
                if time.time() - last_read_time >= 6:
                    IO.setPanVelocityControl()
                    IO.setPanGoalVelocity(0)
                    autorec.manualStopRecording()
                
        IO.setPanGoalVelocity(0)
        IO.setPanPositionControl()
        IO.setAngles(0,5,2,2)
    
    except KeyboardInterrupt:
        IO.setPanGoalVelocity(0)
        IO.setPanPositionControl()
        IO.setAngles(0,5,2,2)
        time.sleep(2)
   
def average_pan_speed(pan_values, timestamps):
    if len(pan_values) != len(timestamps):
        raise ValueError("PAN values and timestamps arrays must be of the same length.")
    
    if len(pan_values) < 2:
        return 0
    
    total_distance = 0
    total_time = 0
    
    for i in range(1, len(pan_values)):
        distance = pan_values[i] - pan_values[i - 1]
        time = timestamps[i] - timestamps[i - 1]
        
        if time <= 0:
            raise ValueError("Timestamps must be in increasing order and have positive intervals.")
        
        total_distance += distance
        total_time += time
    
    average_speed = total_distance / total_time
    return round(average_speed * 1.1, 2)

def tendency(value, array):
    '''
    Checks if a new value to be inserted follows the general tendency of the array
    '''
    
    if len(array) < 2:  # too little values, assume no trend and return True to immediately keep appending the array 
        return True

    if abs(value - array[-1]) < 0.01: # If the values are practically identical, ignore tendency
        return False
    
    trend = 0
    diffs = [array[i] - array[i-1] for i in range(1, len(array))]
    if all(d > 0 for d in diffs):
        trend = 1     # there is a tendency (sign doesnt matter) so return True to keep appending
    elif all(d < 0 for d in diffs):
        trend = -1    # No clear trend in values, return False to immediately clear the array	
    last_val = array[-1]
    
    if(trend == 1 and value < last_val) or (trend == -1 and value > last_val):    # New val does not follow trend
        return False
    
    return True # this means the new value follows the trend --> return True
          






        
