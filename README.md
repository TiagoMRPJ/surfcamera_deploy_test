### Surf Tracking PTZ Camera

The CAD project is available [here](https://cad.onshape.com/documents/b9eef313243f0363e667a5fc/w/e2e378e85b01eeafc1c8ea36/e/338bb7a3ad0a7d0ed4aa153e).

You can also access the assembly guide by clicking [here]. For building a new PTZ system both the assembly guide and this repository's README file should first be read and understood. The assembly guide focuses more on the mechanical assembly of the system aswell as the required setup and connections of the different electronic equipments, while this README file focuses on the Raspberry Pi 5 setup and software.

## Setup

# Image

Start by flashing a new SDCard with the "srcam" image which can be found on IDM-HP Backup harddrive or on IDM-TJ desktop. You can use the Raspberry Pi Imager software for this: 
- Raspberry Pi Device: Raspberry Pi 5
- Operating System: Use custom -> Select the srcam.img file
- Storage: Choose the mounted SDCard you wish to flash the image to.

This image already contains all necessary system configurations for the device to function as intended. When Raspberry Pi Imager prompts if you want to apply OS customisation settings, choose EDIT SETTINGS and confirm the following:

- Set Hostname: srcam{X}, where X corresponds to the camera number in question. This should make it easier to access them remotely and keep track;
- Set username and password: Username -> idmind ; Password -> asdf
- Configure wireless LAN: SSID -> IDMind ; Password -> {IDMind Network Password}
- Services: Make sure to Enable SSH and Use password authentication

# Install 

After finishing the SDCard image flashing, install it on your Raspberry Pi 5 and boot it up. You can connect it to a screen the first time, to make sure everything is working. 

You can now SSH into it using the username and password you configured previously. Do it, and navigate to /home/idmind/ and here run the `git` command to clone this repository. 

# Testing

For testing the system, the Raspberry Pi should first be properly connected to the Front IO Board, the IP Camera aswell as the Zoom Controller. Before working together, these other devices also need some setup of theyr own, which is thoroughly explained in the assembly guide.

After going through the necessary setup of those devices, and connecting everything together, you can power the system and begin testing. A good first test is to run the `start.sh` shell script and watch for the log output for errors or issues. These should point you in the right direction by themselves, most likely pointing to issues with communicating with one of the external devices. You'll know everything is setup and connected correctly once you're able to run that script without outputting any errors or warnings.

For testing the Pan and Tilt, you can go to /test_setup and run the `test_setup.sh` shell script. Then you can access the interface and try controlling the servos.

# Auto Start / Crontab

For the device application to start automatically sudo crontab must contain the following lines:

```
@reboot bash /home/idmind/surfcamera_deploy_test/bash/update_local_repo.sh >> /home/idmind/surfcamera_deploy_test/logs/updatelog.txt 2>&1
@reboot bash /home/idmind/surfcamera_deploy_test/bash/start.sh >> /home/idmind/surfcamera_deploy_test/logs/startbash.txt 2>&1
```

# IP Camera

The IP Camera connects directly to the Raspberry Pi through ethernet. The Raspberry Pi then serves as a proxy, routing the necessary ports from the IP Camera to the network (port 68 for http camera interface and port 554 for rtsp streaming). This is setup through NGINX and HAProxy on the Pi.

NGINX proxies the http interface:

```
sudo apt install nginx
sudo nano /etc/nginx/sites-available/camera_proxy
```

And add the following entry:
```
 server {
       listen 80;  # Change to the port you want to use
       server_name 0.0.0.0;  # Replace with your domain or PC1's IP
       location / {
           proxy_pass http://192.168.1.68:PORT;  # Replace PORT with the port the service is running on PC2
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
```

And HAProxy proxies the RTSP streaming:

```
sudo apt install haproxy
sudo nano /etc/haproxy/haproxy.cfg
```

Add the following:
```
frontend rtsp_frontend
    bind *:554
    mode tcp
    default_backend rtsp_backend
backend rtsp_backend
    mode tcp
    server slave <camera_ip>:554
```


## Overview of the different modules:

# db.py

**Defines a Redis based database for the system**
Redis is an in memory database which persists on disk. This makes it very low latency while at the same time having persistency. This database is used as the whole system's middleware, where different processes can query and modify the same data structures in a shared way. This implementation ensures that new data is processed as fast as possible abstracting away from managing concurrent memory access between processses. 

This specific implementation uses different classes for separating the database into different sections (GPSData, CameraState, WebApp), all running on the same RedisClient. The redis data-model is key based, meaning handling of the database fields is done similarly to a dictionary, but through the class implementation of each db section, we define each field as a property of the parent class, allowing abstraction from the set and get methods of the redis client. Initializng and accessing any defined database item is done in the following way: 

```
import db
conn = db.get_connection() # get a connection to the redis client
gps = db.GPSData(conn) # use the connection to access the gps db section
if gps.new_reading: # Access any field on the particular section of the db directly through the class
  gps.gps_fix = True # You can also write to fields in the same fashion
```

For data to persist it must be written to disk, through the "db.txt" file. For this, the "dump" method of the RedisClient class is called when necessary, like this `gps.client.dump(["new_reading"], "db.txt")`

# IOBoardDriver.py

**Handles serial communication between the Raspberry Pi and the Front IO Board.**

The Front IO Board not only supplies power for the system but is also responsible for the low level control of the servo's and radio communication with the tracker devices, while providing a number of serial commands for interfacing with these functionalities. This allows the Raspberry Pi to handle higher level control of the system, make use of the servo's and radio interface, while being abstracted from the specific implementations of those features.

The IOBoardDriver python module defines a class for handling serial communication, utilizing the provided commands and building upon them for providing some higher level functionality.

Here's a list of the main features of the class:
- Defining Dynamixel Write and Read methods, allowing to write and read specific memory registers on each servo;
- Higher level servo functions, allowing for precise control:
    - PID tuning;
    - Directly setting Pan and Tilt angles while controlling velocity profiles;
    - Velocity and Position servo control modes -> Use velocity control for pan smoothness;
- IO control that allows for control of LED's and reading Hall Sensor and Push Button states;
- Radio Communication of the Camera to the Trackers -> Start, Stop and Monitor Pairing process, and read latest tracker message;

# Zoom_CBN8125.py

**Handles Serial Communication between the Raspberry Pi and the SOAR CBN8125 Camera Zoom Controller**

The Zoom level of the IP Camera is controlled through an RS232 interface, so we use an USB-RS232 converter, for allowing the Raspberry Pi to send Zoom commands directly. This module defines a class that handles serial communication allowing to set the Zoom position (1x to 25x) directly.

# TrackingControlESPNOW_V2.py

**Main control logic loop for tracking** 

This module is responsible for processing GPS data from the tracker into actual Pan Tilt commands and applying them.
To simplify serial port access and make coding more manageable, this is also the only place where IOBoardDriver and ZoomDriver are accessed.

This control loop gets commands from other modules (through the redis database "Commands" section) to start/stop different processes related to the lower level drivers. Here is a list of the variables and theyr functionalities:

- `commands.camera_calibrate_origin`: Reads the next 50 tracker GPS messages to set the camera origin position for calibration;
- `commands.camera_calibrate_heading`: Reads the next 50 tracker GPS messages to set the camera heading for calibration;
- `commands.start_pairing`: Starts the pairing process on the microcontroller;
- `commands.cancel_pairing`: Removes current pair from memory;
- `commands.check_pairing`: Polls the microcontroller for pairing state, returns if there is a current pair or process is undergoing;
- `commands.calibrate_pan_center`: Starts the pan homing calibration;
- `commands.tracking_enabled`: While set as True, the Camera will read the tracker position and execute tracking calculations;

The loop constantly checks for new tracker messages, to update the time information regarding last message. 
While Tracking is enabled, any new received messages are processed for Pan, Tilt, Zoom and Automatic Recording calculations.

# Camera.py

**Defines the camera class responsible for accessing the rtsp stream and locally record videos** 

The camera class accesses the rtsp stream and uses ffmpeg commands for capturing and clipping videos. 
The `webapp.SessionID` redis database variable defines the name of the output folder for videos.

While tracking is enabled, a temporary video is constantly being recorded. Then, the `camera_state.start_recording` variable signals for start and stop times of the detected surfed wave (through the Auto Recording module). This way, the temporary video file can be clipped, and thus contain only the relevant content.

# AutoRecording.py

**Defines the autorecording class for signaling the start and end of waves**

On the Tracking Control loop, the tracker GPS coordinates are fed into this class, which will then be used for keeping track of the surfer's ground speed. With an exponential moving average and through the use of hysteresis conditions, the surfer's speed is enough for start and stop conditions detection.

This simple method is quite sensible to different ocean conditions and the surfer's experience levels, so it requires a lot of fine tuning. Also, it can often lead to a lot of false positive videos (the algorithm signals to record even though the surfer was only paddling, or being dragged by the current), and therefore could be improved by fusing more data and conditions.

# WebServer.py

**Creates a Flask WebServer for serving a local control interface**

The Flask Server runs on port 5000. The interface can be accessed through a web browser, and provides control of the different `commands` variables, `webapp.SessionID` field, etc... for locally controlling and utilizing the system.

# APIV2.py

**Creates a Flask WebServer for serving an API for automatic use of the PTZ system by the Kiosk System**

While the `WebServer.py` module is useful for using the camera as a standalone system, the `APIV2.py` module serves an API on port 53111 for control through HTTP requests, utilized by the Kiosk Computer for interfacing the full SurfRec autonomous system together. 

Available Endpoints:

- start_session -> Creates directories,
- init_pairing
- stop_session
- upload_session
- check_status
- check_pairing
- check_pair_state
- remote_reboot
