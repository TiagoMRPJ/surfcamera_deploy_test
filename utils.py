#! /usr/bin/env python3
import numpy as np
import math
import logging
from logging.handlers import RotatingFileHandler
import os
import time
import shutil

R = 6371 * 1000 # METERS

class Location:
	def __init__(self, lat, lon, alt=0):
		self.latitude = lat
		self.longitude = lon
		self.altitude = alt

def gps_to_cartesian(loc):
	lat = np.radians(loc.latitude)
	lon = np.radians(loc.longitude)
	x = R * np.cos(lat) * np.cos(lon)
	y = R * np.cos(lat) * np.sin(lon)
	z = R * np.sin(lat)
	return x, y, z


def get_angle_between_locations(l1, l2):
	if get_distance_between_locations(l1, l2) < 0.5:
		return 0
	lat1 = np.radians(l1.latitude)
	long1 = np.radians(l1.longitude)
	lat2 = np.radians(l2.latitude)
	long2 = np.radians(l2.longitude)
	dLon = long2 - long1
	y = np.sin(dLon) * np.cos(lat2)
	x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dLon)
	y *= -1
	x *= 1
	brng = np.arctan2(y, x)
	return round(brng, 2)


def get_distance_between_locations(loc0, loc1):
		'''
		Returns distance in same unit as R (in this case meters)
		'''
		latA = np.radians(loc0.latitude)
		lonA = np.radians(loc0.longitude)
		latB = np.radians(loc1.latitude)
		lonB = np.radians(loc1.longitude)
		dist = R * np.arccos(min(max(np.sin(latA) * np.sin(latB) + np.cos(latA) * np.cos(latB) * np.cos(lonA-lonB) , -1), 1))
		return dist

def linterpol(value, x1, x2, y1, y2):
	return y1 + (value - x1) * (y2 - y1) / (x2 - x1)

def normalize(value, range_min, range_max):
	return (value - range_min) / (range_max - range_min)
	
# Configure Flask and Werkzeug loggers
def configure_logging(log_file):
    # Set up a rotating file handler
    log_handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=3)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    ))

    # Remove existing handlers for the 'werkzeug' logger
    flask_logger = logging.getLogger('werkzeug')
    flask_logger.handlers.clear()
    flask_logger.addHandler(log_handler)
    flask_logger.setLevel(logging.INFO)

    # Remove existing handlers for the root logger (optional)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(log_handler)
    root_logger.setLevel(logging.INFO)

class courseCalculator:
	def __init__(self, GpsDB):
		self.gps_points = GpsDB
		self.prev_lat, self.prev_lon = 0, 0
		self.course = 0
		self.prev_course = 0
		self.course_alpha = 0.1
	
	def updateCourse(self):
		try:
			if self.prev_lat != 0 and self.prev_lon != 0:
				if get_distance_between_locations(Location(self.prev_lat, self.prev_lon), Location(self.gps_points.latest_gps_data['latitude'], self.gps_points.latest_gps_data['longitude'])) > 0.5:
					prev_loc = Location(self.prev_lat, self.prev_lon)
					loc = Location(self.gps_points.latest_gps_data['latitude'], self.gps_points.latest_gps_data['longitude'])
					self.course = get_angle_between_locations(loc, prev_loc)
					self.course = self.course_alpha * self.prev_course + (1 - self.course_alpha) * self.course
		except Exception as e:
			print(f"Error in updateCourse: {e}")
		self.prev_lat = self.gps_points.latest_gps_data['latitude']
		self.prev_lon = self.gps_points.latest_gps_data['longitude']
		self.prev_course = self.course
		return self.course
	
def is_surfer_incoming(camera_angle, surfer_course, threshold=np.radians(30)):
    """
    Determine if the surfer is moving toward the camera.

    :param camera_angle: Angle of the camera (radians, -π to π).
    :param surfer_course: Course of the surfer (radians, -π to π).
    :param threshold: Threshold angle to consider as "incoming" (radians).
    :return: True if the surfer is incoming, False otherwise.
    """
    # Calculate angular difference (-π to π)
    angular_difference = np.arctan2(
        np.sin(surfer_course - camera_angle),
        np.cos(surfer_course - camera_angle)
    )
    
    # Check if the difference is within the threshold
    return abs(angular_difference) <= threshold

def delete_old_videos(path: str, days: int = 7):
    """
    Delete subfolders in `path` that are older than `days` days.
    Each subfolder can contain video files or other data.
    """
    if not os.path.isdir(path):
        raise ValueError(f"{path} is not a valid directory")

    now = time.time()
    cutoff = now - (days * 86400)  # days → seconds

    for folder in os.listdir(path):
        folder_path = os.path.join(path, folder)
        if not os.path.isdir(folder_path):
            continue  # only care about subfolders

        # use folder's last modification time
        folder_mtime = os.path.getmtime(folder_path)

        if folder_mtime < cutoff:
            print(f"Deleting old folder: {folder_path}")
            shutil.rmtree(folder_path, ignore_errors=True)
            
import os

def trim_log_file(path: str, max_size_mb: int = 5):
    """
    If the log file at `path` exceeds `max_size_mb`, truncate it in-place
    (clear contents but keep file handle alive for processes already writing).
    """
    if not os.path.isfile(path):
        # Ensure the file exists (empty)
        open(path, 'w').close()
        return

    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > max_size_mb:
        print(f"Log file {path} exceeded {max_size_mb} MB, truncating...")
        with open(path, 'w'):
            pass  # opening with 'w' mode clears file but keeps it alive