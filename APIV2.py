import json
import sys
import os
import db # type: ignore
import time
import UploadAPI
#from SessionHandler import create_session_directories
from flask import Flask, jsonify, request, make_response
import threading

'''
Implements a Flask server to serve as a system API to be utilized by the WebApp.
Includes methods for starting and stopping the session. 
'''

def validID(id):
    try:
        if int(id) == -1:
            return False
        return True
    except:
        return False

def verifyAuthentication(r):
    try:
        headers = r.headers
        auth = headers.get("X-Api-Key") 
        if auth != webapp.CameraSecurityToken:
            return False
    except:
        return False
    headers = r.headers
    return True

conn = db.get_connection()
gps_points = db.GPSData(conn)
commands = db.Commands(conn)
camera_state = db.CameraState(conn)
webapp = db.WebApp(conn)

app = Flask(__name__)

@app.route('/start_session', methods=['POST'])
def start_session():
    
    """
    Route to start a new session.
    Receives:
    {'SessionID': , 'SessionType':}
    Returns: JSON containing a boolean to indicate success or not and in case of error an error message ("Invalid SessionID", "Session Already Established") 
    {'success': , 'message': } 
    """
    
    if not request.is_json:
        print("Bad JSON on request")
        return jsonify({"success": False, "message": "Invalid or missing JSON data"}), 400

    if not verifyAuthentication(request):
        return jsonify({"success": False, "message": "Wrong or None Authorization Header"}), 401

    # Retrieve the SessionID and Type
    SESSIONID = request.json.get('SessionID', -1)
    SESSIONTYPE = request.json.get('SessionType', 'Single')
    RESOLUTION = request.json.get('Resolution', '4K')
    
    if commands.tracking_enabled:
        print("Session Already Established")
        return jsonify({ "success": False, "message": "Session Already Established" }), 400
    if not validID(SESSIONID):
        print("Invalid SessionID Received")
        return jsonify({ "success": False, "message": "Invalid SessionID" }), 400
    
    webapp.SessionID = SESSIONID
    webapp.SessionStartTime = time.time()
    commands.tracking_enabled = True
    create_session_directories(webapp.SessionID)   # Create, if still doesnt exist, the local dirs for storing the sessions videos and gps logs
    print(f"Starting Session {SESSIONID} on {SESSIONTYPE} Mode")
    commands.client.dump(["tracking_enabled"], "db.txt")
    webapp.client.dump(["SessionID"], "db.txt")
    return jsonify({ "success": True, "message": "" }) , 200

@app.route('/init_pairing', methods=['POST'])
def init_pairing():
    """
    Route to initiate the pairing process.
    Receives: None
    Returns: JSON containing a boolean to indicate success or not and in case of error an error message ("Pairing Already In Progress", "Session Already Established") 
    {'success': , 'message': } 
    """
    print("Starting pairing process (KIOSK)")
    commands.cancel_pairing = True
    time.sleep(0.2)
    commands.start_pairing = True
    return jsonify({ "success": True, "message": "" }) , 200
    
@app.route('/stop_session', methods=['POST'])
def stop_session():
    """
    Route to stop the current session.
    Receives: SessionID associated with the current session
    {'SessionID': }
    Returns: JSON containing a boolean to indicate success or not and in case of error an error message ("No Current Session", "Invalid SessionID", "Wrong SessionID") 
    Also responds with how many videos were recorded in this session and theyr format (mp4, avi, etc).
    {'success': , 'message':, 'content_type': , 'video_count': } 
    """ 
    
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid or missing JSON data"}), 400
    
    if not verifyAuthentication(request):
        return jsonify({"success": False, "message": "Wrong or None Authorization Header"}), 401
    
    SessionID = request.json.get('SessionID', -1)    
    
    
    if not commands.tracking_enabled:
        print("No Current Session to Stop")
        return jsonify({ "success": False, "message": "No Current Session" }), 400
    if not validID(SessionID):
        print("Can't Stop Invalid SessionID")
        return jsonify({ "success": False, "message": "Invalid SessionID" }), 400
    #if int(SessionID) != int(webapp.SessionID):
    #    print("Can't Stop Wrong SessionID")
    #    return jsonify({ "success": False, "message": "Wrong SessionID" }), 400
        
    # Stop the current session
    print(f"Stopping Tracking Session {webapp.SessionID}")
    commands.tracking_enabled = False 
    commands.cancel_pairing = True
    time.sleep(0.5)
    ensure_no_temp(f"/home/idmind/surfcamera_deploy_test/videos/{SessionID}")
    time.sleep(0.5)
    file_count = get_file_count(f"/home/idmind/surfcamera_deploy_test/videos/{SessionID}")
    webapp.client.dump(["SessionID"], "db.txt")
    return jsonify({ "success": True, "message": "", "content_type": "video/mp4", "video_count": file_count}), 200

@app.route('/upload_session', methods=['POST'])
def upload_session():
    """
    Route to send the upload_urls for the camera to upload the stopped session videos.
    Returns: JSON containing a boolean to indicate success or not and in case of error an error message ("Invalid SessionID", "Session Already Established") 
    {'success': , 'message': }
    """
    
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid or missing JSON data"}), 400
    
    if not verifyAuthentication(request):
        return jsonify({"success": False, "message": "Wrong or None Authorization Header"}), 401
    
    SessionID = request.json.get('SessionID', -1)
    UPLOADURL = request.json.get('uploading_route', None)
    
    if UPLOADURL is None:
        print("No uploading_route field received")
        return jsonify({"success":False, "message": "uploading_route field missing"}), 400
    if int(SessionID) != int(webapp.SessionID):
        print("Wrong SessionID")
        return jsonify({ "success": False, "message": "Wrong SessionID" }), 400

    if len(UPLOADURL) == 0:
        print("There were no videos to upload")
        webapp.SessionID = -1    
        return jsonify({"success":True, "message": ""}), 200
    
    def background_upload():
        UploadAPI.upload_videos_in_directory(UPLOADURL, f"/home/idmind/surfcamera_deploy_test/videos/{SessionID}")
        
    threading.Thread(target=background_upload, daemon=True).start()
    
    response = jsonify({ "success": True, "message": "Uploading finished"}), 200
    webapp.SessionID = -1    
    webapp.client.dump(["SessionID"], "db.txt")
    commands.cancel_pairing = True
    time.sleep(0.2)
    commands.calibrate_pan_center = True
    print(f"Session {webapp.SessionID} finished successfully")
    
    return response
    
@app.route('/check_status', methods=['GET'])
def check_status():
    """
    Route to check if the camera is available for working or if not, why
    Returns: JSON with a bool indicating if the camera is currently on a session or not. If it is, for how long (in seconds) and to who it belongs
    {'available': bool, 'message': str}
    """
    
    if not verifyAuthentication(request):
        return jsonify({"success": False, "message": "Wrong or None Authorization Header"}), 401
    
    if not commands.tracking_enabled and webapp.ErrorStates == '':
        print("Camera is Available for Session")
        return jsonify({ "available": True}), 200
    if commands.tracking_enabled:
        print("Camera isnt available, session already established")
        return jsonify({"available": False, 'message': 'Session Already Established'}), 400
    if webapp.ErrorStates != '':
        print(f"Camera isnt available: {webapp.ErrorStates}")
        return jsonify({'available': False, 'message': webapp.ErrorStates}), 503
    
    return jsonify({ "available": True}), 200

@app.route('/check_pairing')
def check_pairing():
    commands.check_pairing = True
    time.sleep(0.25)
    return jsonify({'paired': webapp.IsPaired}), 200

@app.route('/remote_reboot')
def remote_reboot():
    '''
    Route to remotely reboot the system.
    '''
        
    if not verifyAuthentication(request):
        return jsonify({"success": False, "message": "Wrong or None Authorization Header"}), 401
    
    response = make_response(jsonify({"message": "Rebooting the system..."}), 200)

    import threading
    import os
    # Start a thread to delay the reboot, allowing the response to be sent first
    threading.Timer(1, os.system, args=['sudo reboot']).start()

    return response
    
def start_server():
    print("starting server")
    app.run(host="0.0.0.0", port="53111", threaded=True)

def main(d):
    from multiprocessing import Process
    import subprocess
    
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

def ensure_no_temp(path: str, valid_exts=('.mp4', '.mkv', '.avi', '.mov')):
    """
    Ensure that a folder only contains videos with numeric names and valid extensions.
    Example of valid: 0.mp4, 1.mkv, 2.avi, 3.mov
    Deletes anything else (like temp_0.mp4, abc.mp4, foo.txt).
    """
    if not os.path.isdir(path):
        raise ValueError(f"{path} is not a valid directory")

    for fname in os.listdir(path):
        fpath = os.path.join(path, fname)
        if not os.path.isfile(fpath):
            continue  # skip subfolders

        name, ext = os.path.splitext(fname)

        # keep only if filename is a number and extension is valid
        if not (name.isdigit() and ext.lower() in valid_exts):
            print(f"Deleting unexpected file: {fname}")
            os.remove(fpath)
    
def get_file_count(path):
    # Get a list of video files in the directory
    video_files = [file_name for file_name in os.listdir(path)
                   if os.path.isfile(os.path.join(path, file_name)) and file_name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov'))]

    return len(video_files)

def get_session_directory(sessionID, folder):
    return f"/home/idmind/surfcamera_deploy_test/{folder}/{sessionID}"

def create_video_directory(ID):
    dir_path = get_session_directory(ID , "videos")
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)
        print(f"Directory for {ID} videos created succesfully!")
    else:
        print(f"Directory for {ID} videos already exists! ")
        
def create_gps_logs_directory(ID):
    dir_path = get_session_directory(ID , "gps_logs")
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)
        print(f"Directory for {ID} gpslogs created succesfully!")
    else:
        print(f"Directory for {ID} gpslogs already exists! ")
        
def create_session_directories(sessionID):
    create_video_directory(sessionID)
    create_gps_logs_directory(sessionID)
        
#main({"stop": 0})
