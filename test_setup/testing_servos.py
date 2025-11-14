import time, redis
import sys
import os

## Make sure to adjust this path as needed
sys.path.append(os.path.join(os.path.dirname(__file__), '/home/idmind/surfcamera_deploy_test')) 

import IOBoardDriver as GPIO
import Zoom_CBN8125 as ZoomController

def main():
    IO = GPIO.FrontBoardDriver()
    Zoom = ZoomController.SoarCameraZoomFocus()

    r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

    last_auto_time = 0
    auto_wait_time = 0
    auto_step_index = 0

    auto_sequence = [
        # Pan, Tilt, Pan Speed, Tilt Speed, Zoom, Wait Time (seconds)
        {"pan": 0,   "tilt": 0,  "pan_speed": 1,   "tilt_speed": 1,   "zoom": 1, "wait": 5},
        {"pan": 20,  "tilt": 10, "pan_speed": 0.5, "tilt_speed": 0.5, "zoom": 1, "wait": 45},
        {"pan": -20, "tilt": 5,  "pan_speed": 1,   "tilt_speed": 1,   "zoom": 1, "wait": 45},
        {"pan": 0,   "tilt": 15, "pan_speed": 0.8, "tilt_speed": 0.8, "zoom": 1, "wait": 45}
    ]

    while True:
        time.sleep(0.2)
        auto_mode = r.get("auto_mode")
        manual_mode = r.get("manual_mode")
        
        if manual_mode == "1":
            zoom_command = r.get("zoom_command")
            if zoom_command:
                Zoom.set_zoom_position(float(zoom_command))
                r.set("zoom_command", "")
            
            pan_command = r.get("pan_command")
            tilt_command = r.get("tilt_command")
            velocity_command = r.get("velocity_command")
            
            if pan_command and tilt_command:
                pan = float(pan_command)
                tilt = float(tilt_command)
                velocity = float(velocity_command) if velocity_command else None
                IO.setAngles(pan, tilt, velocity)
                time.sleep(0.01)  # small delay to ensure command is processed
                r.set("pan_command", "")
                r.set("tilt_command", "")
                r.set("velocity_command", "")
                    
        if auto_mode == "1":
            auto_time = time.time()
            if auto_time - last_auto_time > auto_wait_time:
                step = auto_sequence[auto_step_index]
                IO.setAngles(step["pan"], step["tilt"], step["pan_speed"], step["tilt_speed"])
                Zoom.set_zoom(step["zoom"])
                auto_wait_time = step["wait"]
                last_auto_time = auto_time
                auto_step_index += 1
                if auto_step_index >= len(auto_sequence):
                    auto_step_index = 0
            
        if auto_mode == "0" and manual_mode == "0":
            IO.setAngles(0, 0, 2)  # default position
            Zoom.set_zoom(1)  # default zoom level
            
if __name__ == "__main__":
    main()
            
            
