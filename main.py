#! /usr/bin/python
import time
import sys

import Camera
import TrackingControlESPNOW_V2
import WebServer
import APIV2

from multiprocessing import Process, Manager
import redis
from db import RedisClient
import utils

# On boot, go through the recorded videos and delete older than 7 days
# Also go through logs and if file is too big delete the old things
utils.delete_old_videos(path='/home/idmind/surf_camera/videos', days=7) 
utils.trim_log_file(path='/home/idmind/surf_camera/logs/startbash.txt', max_size_mb = 3)

r = redis.Redis()
client = RedisClient(r)

PERSISTENT_FILENAME = "/home/idmind/surf_camera/db.txt"

PROCESSES = [
    WebServer, # Control Panel for manual control
    APIV2,       # Flask server API that serves the WebApp 
    Camera,    # Handles the recording, clipping and directory management of videos 
    TrackingControlESPNOW_V2 # Calculations based on gps coordinates: servo and autorecording controller
]

if __name__ == '__main__':
        
    manager = Manager()
    client.set_initial("stop_surf", False)
    d = manager.dict()
    d["stop"] = False
    client.load(PERSISTENT_FILENAME)
    
    process_list = []
    for p in PROCESSES:
        process_list.append(Process(target=p.main, args=(d,)))
        time.sleep(0.5)
    for p in process_list:
        p.start()
        time.sleep(0.5)
    try:
        # Keep the main process alive
        for process in process_list:
            process.join()
    except KeyboardInterrupt:
        # Graceful shutdown
        d["stop"] = True
        print("SHUTTING DOWN ALL PROCESSES")
        for process in process_list:
            process.join()
    finally:
        print("Graceful shutdown")