import redis
import pickle
import json

def get_connection():
    return redis.Redis()


class RedisClient:

    def __init__(self, connection):
        """Initialize client."""
        self.r = connection

    def set(self, key, value, **kwargs):
        """Store a value in Redis."""
        return self.r.set(key, pickle.dumps(value), **kwargs)

    def set_initial(self, key, value):
        """Store a value in Redis."""
        if not self.get(key):
            self.set(key, value)

    def get(self, key):
        """Retrieve a value from Redis."""
        val = self.r.get(key)
        if val:
            return pickle.loads(val)
        return None

    """ def dump(self, keys, filename):
        data = {}
        for k in keys:
            data[k] = self.get(k)
        print("storing configuration: %s" % json.dumps(data, indent=2))
        with open(filename, "w") as fp:
            json.dump(data, fp, indent=2) """
            
            
    def dump(self, keys, filename):
        # Load existing data from file if it exists
        try:
            with open(filename, "r") as fp:
                existing_data = json.load(fp)
        except FileNotFoundError:
            existing_data = {}  # If file doesn't exist, start with empty data
        
        # Retrieve and merge the new data
        new_data = {}
        for k in keys:
            new_data[k] = self.get(k)
        
        # Merge existing data with new data
        merged_data = {**existing_data, **new_data}
        
        # Print and write the merged data to file
        print("Storing configuration: %s" % json.dumps(merged_data, indent=2))
        with open(filename, "w") as fp:
            json.dump(merged_data, fp, indent=2)

    def load(self, filename):
        data = {}
        with open(filename) as fp:
            data = json.load(fp)
        print("configuration loaded: %s" % json.dumps(data, indent=2))
        for k in data:
            self.set(k, data[k])
            

class GPSData:
    def  __init__(self, connection):
        self.client = RedisClient(connection)
        #self.client.set_initial("camera_origin", { "latitude": 0, "longitude": 0 })          # Coordinates of the camera's location -> Calibrate to change this
        #self.client.set_initial("camera_heading_angle", 0)
        self.client.set_initial("latest_gps_data", { "latitude": 0, "longitude": 0})         # Latest coordinates received from the Tracker
        self.client.set_initial("reads_per_second", 0)                                       # Variable to store how many readings per second we're taking from the radio
        self.client.set_initial("gps_fix", False)                                            # Flag to indicate th
        self.client.set_initial("transmission_fix", False)  
        self.client.set_initial("new_reading", False)                 # Flag to indicate a new reading has come in
        self.client.set_initial("tilt_offset", 0)                    # Used to manually fine adjust tilt calibration
        self.client.set_initial("camera_vertical_distance", 8)        # Variable to store the fixed value of the camera vertical position 
        self.client.set_initial("last_gps_time", 0)
        
    @property
    def camera_origin(self):
        return self.client.get("camera_origin")

    @camera_origin.setter
    def camera_origin(self, value):
        self.client.set("camera_origin", value)
        
    @property
    def gpslogfile(self):
        return self.client.get("gpslogfile")

    @gpslogfile.setter
    def gpslogfile(self, value):
        self.client.set("gpslogfile", value)    
    
        
    @property
    def camera_heading_coords(self):
        return self.client.get("camera_heading_coords")

    @camera_heading_coords.setter
    def camera_heading_coords(self, value):
        self.client.set("camera_heading_coords", value)
        
    @property
    def camera_heading_angle(self):
        return self.client.get("camera_heading_angle")

    @camera_heading_angle.setter
    def camera_heading_angle(self, value):
        self.client.set("camera_heading_angle", value)
        
    @property
    def latest_gps_data(self):
        return self.client.get("latest_gps_data")

    @latest_gps_data.setter
    def latest_gps_data(self, value):
        self.client.set("latest_gps_data", value)
        
    @property
    def gps_fix(self):
        return self.client.get("gps_fix")

    @gps_fix.setter
    def gps_fix(self, value):
        self.client.set("gps_fix", value)
        
    @property
    def transmission_fix(self):
        return self.client.get("transmission_fix")

    @transmission_fix.setter
    def transmission_fix(self, value):
        self.client.set("transmission_fix", value)
        
    @property
    def new_reading(self):
        return self.client.get("new_reading")

    @new_reading.setter
    def new_reading(self, value):
        self.client.set("new_reading", value)
        
    @property
    def tilt_offset(self):
        return self.client.get("tilt_offset")

    @tilt_offset.setter
    def tilt_offset(self, value):
        self.client.set("tilt_offset", value)
        
    @property
    def camera_vertical_distance(self):
        return self.client.get("camera_vertical_distance")

    @camera_vertical_distance.setter
    def camera_vertical_distance(self, value):
        self.client.set("camera_vertical_distance", value)
        
    @property
    def last_gps_time(self):
        return self.client.get("last_gps_time")

    @last_gps_time.setter
    def last_gps_time(self, value):
        self.client.set("last_gps_time", value)
        
    @property
    def gps_course(self):
        return self.client.get("gps_course")

    @gps_course.setter
    def gps_course(self, value):
        self.client.set("gps_course", value)
        
class Commands:
    def  __init__(self, connection):
        self.client = RedisClient(connection)
        self.client.set_initial("camera_calibrate_origin", False)     # Flag utilized to start the origin calibration process
        self.client.set_initial("camera_calibrate_heading", False)    # Flag utilized to start the heading calibration process
        self.client.set_initial("camera_zoom_value", 1)
        self.client.set_initial("camera_zoom_multiplier", 1)          # Used to increase/decrease the calculated zoom by a factor of 0.8-1.2x
        self.client.set_initial("tracking_enabled", False)            # Flag utilized to toggle tracking        
        self.client.set_initial("speed_control_mode_threshold", 0.3)  # Pan Speed to toggle velocity mode or position
        self.client.set_initial("max_pan_speed", 6)                   # Max pan speed when in position mode
        self.client.set_initial("start_pairing", False)
        self.client.set_initial("cancel_pairing", False)
    
    @property
    def camera_calibrate_origin(self):
        return self.client.get("camera_calibrate_origin")

    @camera_calibrate_origin.setter
    def camera_calibrate_origin(self, value):
        self.client.set("camera_calibrate_origin", value)
        
    @property
    def camera_calibrate_heading(self):
        return self.client.get("camera_calibrate_heading")

    @camera_calibrate_heading.setter
    def camera_calibrate_heading(self, value):
        self.client.set("camera_calibrate_heading", value)
        
    @property
    def camera_zoom_value(self):
        return self.client.get("camera_zoom_value")

    @camera_zoom_value.setter
    def camera_zoom_value(self, value):
        self.client.set("camera_zoom_value", value)
        
    @property
    def camera_zoom_multiplier(self):
        return self.client.get("camera_zoom_multiplier")

    @camera_zoom_multiplier.setter
    def camera_zoom_multiplier(self, value):
        self.client.set("camera_zoom_multiplier", value)
        
    @property
    def tracking_enabled(self):
        return self.client.get("tracking_enabled")

    @tracking_enabled.setter
    def tracking_enabled(self, value):
        self.client.set("tracking_enabled", value)
        
    @property
    def speed_control_mode_threshold(self):
        return self.client.get("speed_control_mode_threshold")

    @speed_control_mode_threshold.setter
    def speed_control_mode_threshold(self, value):
        self.client.set("speed_control_mode_threshold", value)
        
    @property
    def max_pan_speed(self):
        return self.client.get("max_pan_speed")

    @max_pan_speed.setter
    def max_pan_speed(self, value):
        self.client.set("max_pan_speed", value)
        
    @property
    def start_pairing(self):
        return self.client.get("start_pairing")

    @start_pairing.setter
    def start_pairing(self, value):
        self.client.set("start_pairing", value)
        
    @property
    def cancel_pairing(self):
        return self.client.get("cancel_pairing")

    @cancel_pairing.setter
    def cancel_pairing(self, value):
        self.client.set("cancel_pairing", value)
        
class CameraState:
    def __init__(self, connection):
        self.client = RedisClient(connection)
        self.client.set_initial("start_recording", False)
        self.client.set_initial("is_recording", False)
        self.client.set_initial("enable_auto_recording", False)
        self.client.set_initial("timeStamp", 0)
        self.client.set_initial("video_file_path", "")
    
    @property
    def wave_nr(self):
        return self.client.get("wave_nr")

    @wave_nr.setter
    def wave_nr(self, v):
        self.client.set("wave_nr", v) 
        
    @property
    def video_file_path(self):
        return self.client.get("video_file_path")

    @video_file_path.setter
    def video_file_path(self, v):
        self.client.set("video_file_path", v)        

    @property
    def is_recording(self):
        return self.client.get("is_recording")

    @is_recording.setter
    def is_recording(self, v):
        self.client.set("is_recording", v)

    @property
    def image(self):
        return self.client.get("state_image")

    @image.setter
    def image(self, v):
        self.client.set("state_image", v)

    @property
    def start_recording(self):
        return self.client.get("start_recording")

    @start_recording.setter
    def start_recording(self, v):
        self.client.set("start_recording", v)
        
    @property
    def enable_auto_recording(self):
        return self.client.get("enable_auto_recording")

    @enable_auto_recording.setter
    def enable_auto_recording(self, v):
        self.client.set("enable_auto_recording", v)
        
    @property
    def timeStamp(self):
        return self.client.get("timeStamp")

    @timeStamp.setter
    def timeStamp(self, v):
        self.client.set("timeStamp", v)
        

class WebApp:
    '''
    Handles everything related to the WebApp functioning and camera unit identification
    
    '''
    def __init__(self, connection):
        self.client = RedisClient(connection)
        self.client.set_initial("CameraID", 1) # Unique Camera Identifier
        self.client.set_initial("CameraSecurityToken", 'xxx')
        self.client.set_initial("SessionID", -1) # Indicates the current SessionID: Also tells if there's a session in place or not. If SessionID is -1 there's no session
        self.client.set_initial("SessionStartTime", 0)
        self.client.set_initial("Uploading_Route", '')
        self.client.set_initial("ErrorStates", '')
        self.client.set_initial("IsPaired", '')

    @property
    def CameraID(self):
        return self.client.get("CameraID")

    @CameraID.setter
    def CameraID(self, v):
        self.client.set("CameraID", v)
        
    @property
    def CameraSecurityToken(self):
        return self.client.get("CameraSecurityToken")

    @CameraSecurityToken.setter
    def CameraSecurityToken(self, v):
        self.client.set("CameraSecurityToken", v)

    @property
    def ngrok_url(self):
        return self.client.get("ngrok_url")

    @ngrok_url.setter
    def ngrok_url(self, v):
        self.client.set("ngrok_url", v)

    @property
    def SessionID(self):
        return self.client.get("SessionID")

    @SessionID.setter
    def SessionID(self, v):
        self.client.set("SessionID", v)

    @property
    def SessionStartTime(self):
        return self.client.get("SessionStartTime")

    @SessionStartTime.setter
    def SessionStartTime(self, v):
        self.client.set("SessionStartTime", v)
        
    @property
    def uploading_route(self):
        return self.client.get("uploading_route")

    @uploading_route.setter
    def uploading_route(self, v):
        self.client.set("uploading_route", v)
        
    @property
    def session_type(self):
        return self.client.get("session_type")

    @session_type.setter
    def session_type(self, v):
        self.client.set("session_type", v)
        
    @property
    def ErrorStates(self):
        return self.client.get("ErrorStates")

    @ErrorStates.setter
    def ErrorStates(self, v):
        self.client.set("ErrorStates", v)
        
    @property
    def IsPaired(self):
        return self.client.get("IsPaired")

    @IsPaired.setter
    def IsPaired(self, v):
        self.client.set("IsPaired", v)
        
        
        
        