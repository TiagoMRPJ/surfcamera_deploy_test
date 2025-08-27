import threading
import time
import db
import subprocess
import time
import os

BUFFER_TIME_BEFORE = 8
#BUFFER_TIME_AFTER = 3
MINIMUM_CLIP_TIME = 3 
MAXIMUM_CLIP_TIME = 45

os.umask(0o000)

# Function to start recording
def start_recording(rtsp_url, output_file):
    # Command to start recording
    command = [
        'ffmpeg',
        '-i', rtsp_url,
        '-c:v', 'copy',  # Copy video stream to maintain quality
        '-y',  # Overwrite output file if it exists
        output_file
    ]
    
    # Start ffmpeg process in the background
    ffmpeg_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"Output file: {output_file}")
    return ffmpeg_process

# Function to stop recording
def stop_recording(ffmpeg_process):
    # Terminate ffmpeg process
    ffmpeg_process.terminate()
    try:
        ffmpeg_process.wait(timeout=2)
        print("Recording stopped.")
    except subprocess.TimeoutExpired:
        ffmpeg_process.kill()
        print("Recording forcefully stopped.")
        
def clip_video(input_file, output_file, start_time):
        
    # Calculate the start and stop times with the buffer
    start_time_with_buffer = max(0, start_time - BUFFER_TIME_BEFORE)  # Ensure the start time doesn't go below 0

    # Check if input exists:
    if not os.path.exists(input_file):
        print("Invalid input_file for clipping")
        return 
        
    # Construct the ffmpeg command
    command = [
        'ffmpeg',
        '-i', input_file,
        '-ss', str(start_time_with_buffer),  # Starting time of the clip
        #'-to', str(stop_time_with_buffer),   # Ending time of the clip, if we omit it clips to the end
        '-c', 'copy',                        # Copy video without re-encoding
        '-y',                                # Overwrite output file if it exists
        output_file
    ]

    # Run the ffmpeg command as a subprocess (.run so we wait for each to end)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if result.returncode != 0 :
        print(f"FFMPEG error while clipping: {result.stderr.decode('utf-8')}")
    else:
         print(f"Clip saved to {output_file}")
   
    # Delete the original large file after clipping	
    if os.path.exists(input_file):
        os.remove(input_file)
        print(f"Deleted original file: {input_file}")
    
def convert_to_seconds(stmp):
    hours = int(stmp[:2])
    minutes = int(stmp[2:4])
    seconds = int(stmp[4:])

    # Convert to total seconds
    result = hours * 3600 + minutes * 60 + seconds
    if result > 0:
        return result 
    
def create_directory_if_not_exists(directory_path):
    os.makedirs(directory_path, exist_ok=True)
    #print(f"Directory '{directory_path}' is ready.")
    
def count_files_in_directory(directory_path):
    try:
        return len([f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))])
    except FileNotFoundError:
        print(f"Directory '{directory_path}' not found.")
        return 0
    
class Cam():

    def __init__(self, q_frame = None):
        self.running = False  
        conn = db.get_connection()
        self.camera_state = db.CameraState(conn)
        self.commands = db.Commands(conn)
        self.webapp = db.WebApp(conn)
        self.camera_state.is_recording = False
        self.camera_state.start_recording = False
        self.rtsp_url = 'rtsp://admin:IDMind2000!@192.168.1.68'
        
    def start(self, nr=0):
        self.run = True
        self.capture_thread = None
        self.nr = nr
        self.capture_thread = threading.Thread(target = self.worker)
        self.capture_thread.start()

    def stop(self): 
        self.run = False		
        try:
            self.capture_thread.join()
        except:
            pass
        
        while self.running:
            time.sleep(0.01)

    def worker(self):
        self.running = True
        recording = False
        self.videoInitialTimeStamp = 0
        self.waveTimeStamp = 0
        self.camera_state.wave_nr = 0
        self.recording_process = False
        cur_dir = "/home/idmind/surf_camera/videos/other"
        
        while(self.run):
            time.sleep(0.02)
                            
            if self.webapp.SessionID != "-1":
                new_dir = f"/home/idmind/surf_camera/videos/{self.webapp.SessionID}"
            else:
                new_dir = f"/home/idmind/surf_camera/videos/other"

            if new_dir != cur_dir:
                cur_dir = new_dir
                create_directory_if_not_exists(cur_dir)
                self.camera_state.wave_nr = count_files_in_directory(cur_dir)
                print(f"Current Recording Directory: {cur_dir}")
                if self.recording_process:
                    stop_recording(self.recording_process)
                    recording = False
                    self.camera_state.is_recording = False
                    if os.path.exists(self.camera_state.video_file_path): # Delete the temp file
                        os.remove(self.camera_state.video_file_path)
                    
            if self.commands.tracking_enabled:
                            
                if not recording:
                    print("Camera started recording temp video")
                    ''' Start Recording a Video '''
                    recording = True
                    self.videoInitialTimeStamp = time.strftime('%H%M%S', time.localtime())
                    self.camera_state.video_file_path = os.path.join(cur_dir, f"temp_{self.camera_state.wave_nr}.mp4")
                    self.recording_process = start_recording(self.rtsp_url, self.camera_state.video_file_path)
                
                if recording and self.camera_state.start_recording and not self.camera_state.is_recording:
                    ''' Start Wave Event '''
                    print("Start Wave Event")
                    timeStamp = time.strftime('%H%M%S', time.localtime())
                    self.camera_state.timeStamp = timeStamp # This goes to the GPS logging part
                    self.camera_state.is_recording = True
                    self.waveTimeStamp = timeStamp
                
                if recording and not self.camera_state.start_recording and self.camera_state.is_recording:
                    ''' Stop Wave Event '''
                    
                    if convert_to_seconds(time.strftime('%H%M%S', time.localtime())) - convert_to_seconds(self.waveTimeStamp) > MINIMUM_CLIP_TIME: 
                        outputf = os.path.join(cur_dir, f"{self.camera_state.wave_nr}.mp4")
                        self.camera_state.wave_nr += 1
                        stop_recording(self.recording_process)
                        self.camera_state.is_recording = False
                        recording = False
                        startt = convert_to_seconds(self.waveTimeStamp) - convert_to_seconds(self.videoInitialTimeStamp)
                        clip_video(input_file = self.camera_state.video_file_path, output_file = outputf, start_time = startt)
                        print("Stop Wave Event")
                    else:
                        print("Wave Event too short, ignoring")
                        stop_recording(self.recording_process)
                        self.camera_state.is_recording = False
                        recording = False
                        if os.path.exists(self.camera_state.video_file_path):
                            os.remove(self.camera_state.video_file_path)
                            print(f"Deleted original file: {self.camera_state.video_file_path}")
                        
            if not self.commands.tracking_enabled and recording:
                print("Stop Tracking and Recording")
                stop_recording(self.recording_process)
                recording = False
                if os.path.exists(self.camera_state.video_file_path):
                    os.remove(self.camera_state.video_file_path)
                    print(f"Deleted original file: {self.camera_state.video_file_path}")
                    
        self.running = False

def main(d):
    c = Cam()

    print("Starting cam")
    c.start()
    time.sleep(2)         # should be implemented with queue/signals but good enough for testing
    print("Cam is operational")
 
    try:
        while not d["stop"]:
            time.sleep(0.01)
            if not c.running:
                    break
    except KeyboardInterrupt:
        d["stop"] = True
        pass

    if c.commands.tracking_enabled:
        c.commands.tracking_enabled = False # This will force the camera to stop the current recording
        time.sleep(2)
        
    print("Stopping camera")
    c.stop()
 
if __name__ == "__main__":
    main({"stop":False})
