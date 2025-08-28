# Surf Tracking PTZ Camera

The CAD project is available [here](https://cad.onshape.com/documents/b9eef313243f0363e667a5fc/w/e2e378e85b01eeafc1c8ea36/e/338bb7a3ad0a7d0ed4aa153e).

<details>

<summary>Tracker_Receiver</summary>

The folder contains the code that runs on both the tracker and receiver, for both the ESPNOW and RFM69HW radio control versions.

The ESPNOW version is currently under development.

RFM69HW is the currently implemented radio solution. 
The tracker code is to be uploaded into a Tracker Board, and handles GPS reading aswell as Radio communication and shutdown states.
The receiver code in this version runs on a dedicated ESP32 connected to an RFM69HW radio through airwires (there's currently no dedicated PCB for this). 
This ESP32 must then be connected to the camera through the external USB port.

The received GPS coordinates are then passed to the camera through the ESP32 USB-Serial interface.
</details>

Overview of the different modules:
<details>
<summary>RadioGps.py</summary>

**Runs a thread for communicating with the radio receiver**

The script starts by searching for the USB-Serial converter (CP2102N) on the ESP32 and establishing serial connection to it. 
The tracker is continuously broadcasting the most recent GPS data over the radio channel. The receiver picks it up and passes it onto the serial port. This happens at approximately 10hz.    
This data is sent from the receiver to the camera as 9 byte messages, containing the latitude (1st 4 bytes), longitude (2nd 4 bytes) and the number of sattelites the tracker is locked to (last byte).
Latitude and longitude are floating point numbers with 6 decimal places precision. For reducing the bandwidth (number of bytes transmitted each time) of both the radio and serial communication and evade from precision issues, theyr values are always represented with a 10000000 multiplicative factor, to eliminate the floating point.
When we receive the data on the Raspberry Pi, we decode it and only then remove this factor for obtaining the correct lat/lon values. 

This thread is continuously running, acquiring the most recent GPS data and updating the respective variables on the Redis DB. By monitoring the number of sattelites and time elapsed since last data point reception, we can detect and notify about issues with the Tracker.
</details>

<details>
<summary>db.py</summary>

**Defines a Redis based database for the system**
Redis is an in memory database which persists on disk. This makes it very low latency while at the same time having persistency. This database is used as the whole system's middleware, where different processes can query and modify the same data structures in a shared way. For example, the RadioGps thread is continuously receiving the latest gps data and stores the values in this DB where they are concurrently accessed by the TrackingControl process, which makes the necessary calculations based on the coordinates. This implementation ensures that new data is processed as fast as possible while easily managing concurrent memory access between processses. 

The specific implementation uses different classes for separating the database into different sections (GPSData, CameraState, WebApp), all running on the same RedisClient. The redis data-model is key based, meaning handling of the database fields is done similarly to a dictionary, but through the class implementation of each db section, we define each field as a property of the parent class, allowing abstraction from the set and get methods of the redis client. Initializng and accessing any defined database item is done in the following way: 
```
import db
conn = db.get_connection() # get a connection to the redis client
gps = db.GPSData(conn) # use the connection to access the gps db section
if gps.new_reading: # Access any field on the particular section of the db directly through the class
  gps.gps_fix = True
```

For data to persist it must be written to disk, through the "db.txt" file. For this, the "dump" method of the RedisClient class is called, like this `gps.client.dump(["new_reading"], "db.txt")`
</details>


<details>
<summary>crontab</summary>

For the device application to start automatically sudo crontab must contain

@reboot bash /home/idmind/surfcamera_deploy_test/bash/update_local_repo.sh
@reboot bash /home/idmind/surfcamera_deploy_test/bash/start.sh >> /home/idmind/surfcamera_deploy_test/logs/startbash.txt 2>&1

</details>

<details>
<summary>Proxys</summary>

The IP Camera is connected to the Raspberry Pi through ethernet. The Raspberry Pi then serves as a proxy, routing the necessary ports from the camera to the router (port 68 for http camera interface and port 554 for rtsp). This is done through NGINX and HAProxy.

sudo apt install nginx
sudo nano /etc/nginx/sites-available/camera_proxy
“
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
“
sudo systemctl enable nginx
sudo systemctl is-enabled nginx


And for HAProxy

sudo apt install haproxy
sudo nano /etc/haproxy/haproxy.cfg
“
frontend rtsp_frontend
    bind *:554
    mode tcp
    default_backend rtsp_backend
backend rtsp_backend
    mode tcp
    server slave <camera_ip>:554
“
sudo systemctl restart haproxy

</details>


