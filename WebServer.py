import json
from flask import render_template, Flask, send_from_directory, Response, jsonify, request
#from flask_cors import CORS
import time 
import db
import numpy as np
from utils import configure_logging

def main(d):
    conn = db.get_connection()
    gps_points = db.GPSData(conn)
    commands = db.Commands(conn)
    camera_state = db.CameraState(conn)
    webapp = db.WebApp(conn)
    
    app = Flask(__name__)
    
    def calibrationCoordsCal():
        '''
        Saves 15 gps samples and returns the average lat and lon
        '''
        calibrationBufferLAT = np.array([])    # [lats]
        calibrationBufferLON = np.array([])    # [lats]
        while len(calibrationBufferLAT) < 15:  # 5 seconds at 3 Hz to fill the buffer with samples
            time.sleep(0.01)
            if gps_points.new_reading:         # For every new_reading that comes in
                gps_points.new_reading = False
                calibrationBufferLAT = np.append(calibrationBufferLAT, gps_points.latest_gps_data['latitude'])
                calibrationBufferLON = np.append(calibrationBufferLON, gps_points.latest_gps_data['longitude'])
            
        avg_lat = np.average(calibrationBufferLAT)
        avg_lon = np.average(calibrationBufferLON)
        
        return avg_lat, avg_lon
    

    @app.route("/")
    def index():
        """Video streaming home page."""
        return render_template('index.html')

    @app.route('/start_recording', methods=["POST"])
    def start_recording():
        """Sets the db camera state to start recording"""
        print("---")
        print("Flask Start Recording")
        camera_state.start_recording = True
        return jsonify({ "success": camera_state.start_recording, "message": "OK" })

    @app.route('/stop_recording', methods=["POST"])
    def stop_recording():
        """Sets the db camera state to stop recording"""
        print("Flask Stop Recording")
        camera_state.start_recording = False
        return jsonify({ "success": camera_state.start_recording, "message": "OK" })
    
    @app.route('/enable_autorec', methods=["POST"])
    def enable_autorec():
        """Sets the db camera state to enable auto recording"""
        print("---")
        print("Flask Auto Recording")
        camera_state.enable_auto_recording = True
        return jsonify({ "success": camera_state.enable_auto_recording, "message": "OK" })
    
    @app.route('/disable_autorec', methods=["POST"])
    def disable_autorec():
        """Sets the db camera state to disable auto recording"""
        print("---")
        print("Flask Stop Auto Recording")
        camera_state.enable_auto_recording = False
        return jsonify({ "success": camera_state.enable_auto_recording, "message": "OK" })

    @app.route('/start_tracking', methods=["POST"])
    def start_tracking():
        """Start Tracking"""
        print("Flask Start Tracking")
        commands.tracking_enabled = True
        return jsonify({ "success": True, "message": "OK" })

    @app.route('/stop_tracking', methods=["POST"])
    def stop_tracking():
        """Put camera in idle mode."""
        print("Flask StopTracking")
        commands.tracking_enabled = False
        return jsonify({ "success": True, "message": "OK" })

    @app.route('/update_zoom_multiplier', methods=["POST"])
    def update_zoom_multiplier():
        zoom_multiplier = request.json.get('zoom_multiplier', 1)
        commands.camera_zoom_multiplier = zoom_multiplier
        #print(commands.camera_zoom_multiplier)
        print("Flask Updating Zoom Multiplier")
        return jsonify({"success": True, "message": "Values Updated!"})
    
    @app.route('/update_vertical_distance_value', methods=["POST"])
    def update_vertical_distance_value():
        vertical_distance_val = request.json.get('vertical_distance_value', 0)
        gps_points.camera_vertical_distance = vertical_distance_val
        print(vertical_distance_val)
        print("Flask Updating Vertical Distance")
        return jsonify({"success": True, "message": "Values Updated!"})
    
    @app.route('/increment', methods=['POST'])
    def increment():
        gps_points.camera_heading_angle += 0.0174532925/10   # 1 deg / 10
        gps_points.client.dump(["camera_heading_angle"], "db.txt")
        return jsonify({"success": True, "message": "Values Updated!"})

    @app.route('/decrement', methods=['POST'])
    def decrement():
        gps_points.camera_heading_angle -= 0.0174532925/10   # 1 deg / 10
        gps_points.client.dump(["camera_heading_angle"], "db.txt")
        return jsonify({"success": True, "message": "Values Updated!"})

    @app.route('/tilt_offset_plus', methods=['POST'])
    def tilt_offset_plus():
        gps_points.tilt_offset += 0.1
        gps_points.client.dump(["tilt_offset"], "db.txt")
        return jsonify({"success": True, "message": "Values Updated!"})

    @app.route('/tilt_offset_minus', methods=['POST'])
    def tilt_offset_minus():
        gps_points.tilt_offset -= 0.1
        gps_points.client.dump(["tilt_offset"], "db.txt")
        return jsonify({"success": True, "message": "Values Updated!"})
    

    @app.route('/calibrate_position', methods=["POST"])
    def calibrate_position():
        """Triggers the calibration method for the camera origin"""
        print("flask calibrate_position")
        commands.camera_calibrate_origin = True
        return jsonify({ "success": True, "message": "OK" })

    @app.route('/calibrate_heading', methods=["POST"])
    def calibrate_heading():
        """Triggers the calibration method for the camera heading"""
        print("flask calibrate_heading")
        commands.camera_calibrate_heading = True
        return jsonify({ "success": True, "message": "OK" })
    
    @app.route('/start_pairing', methods=["POST"])
    def start_pairing():
        """Triggers the pairing process"""
        print("flask start_pairing")
        commands.start_pairing = True
        return jsonify({ "success": True, "message": "OK" })
    
    @app.route('/cancel_pairing', methods=["POST"])
    def cancel_pairing():
        """Cancels the current pairing or process"""
        print("flask cancel_pairing")
        commands.cancel_pairing = True
        return jsonify({ "success": True, "message": "OK" })
    
    @app.route('/calibrate_pan_center', methods=["POST"])
    def calibrate_pan_center():
        """Triggers the calibration method for the pan center"""
        print("flask calibrate_pan_center")
        commands.calibrate_pan_center = True
        return jsonify({ "success": True, "message": "OK" })
    
    @app.route('/shutdown_surf')
    def shutdown_surf():
        """Route to shutdown system"""
        from subprocess import call
        import IOBoardDriver as IO
        frontboard = IO.FrontBoardDriver()
        frontboard.setShutdown(seconds=5)
        time.sleep(1)
        call("sudo shutdown -h now", shell=True)
        return jsonify({ "success": True, "message": "OK" })
    
    @app.route('/update_sessionid', methods=["POST"])
    def update_sessionid():
        """Route to SessionID """
        sessionid = request.json.get('sessionid', 0)
        camera_state.start_recording = False
        webapp.SessionID = sessionid
        webapp.client.dump(["SessionID"], "db.txt")
        print(f"Flask Updating SessionID {sessionid}")
        return jsonify({"success": True, "message": "Values Updated!"})
    
    @app.route('/get_tracking_state', methods=["GET"])
    def get_tracking_state():
        return jsonify({"success": True, "message": "OK", "state": commands.tracking_enabled })
    
    @app.route('/get_sessionid_state', methods=["GET"])
    def get_sessionid_state():
        return jsonify({"success": True, "message": "OK", "state": webapp.SessionID })
    
    @app.route('/get_verticaldist_state', methods=["GET"])
    def get_verticaldist_state():
        return jsonify({"success": True, "message": "OK", "state": gps_points.camera_vertical_distance })
    
    def start_server():
        print("starting server")
        app.run(host="0.0.0.0", port="5000", threaded=True)

    from multiprocessing import Process
    p_server = Process(target=start_server)
    p_server.start()
    try:
        while not d["stop"]:
            time.sleep(2)
    except KeyboardInterrupt:
        d["stop"] = True
        pass
    p_server.terminate()
    p_server.join()
    
    