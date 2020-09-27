import asyncio
import json
from threading import Lock, Thread
from time import time

import numpy as np
import pyrealsense2 as rs
import websockets

# Declare pointcloud object, for calculating pointclouds and texture mappings
pc = rs.pointcloud()

# Keeping the depth frames in a global variable
last_pointcloud_points = None
lock = Lock()

# Cnfigure the pipeline to stream at specific resoultion
config = rs.config()
xres, yres = 424, 240 # Set resolution
# xres, yres = 640, 360 # Set resolution
config.enable_stream(rs.stream.depth, xres, yres, rs.format.z16, 15)
pipeline = rs.pipeline()
pipeline_profile = pipeline.start(config)

# Set filter options here
filters = []
decimate = rs.decimation_filter()
decimate.set_option(rs.option.filter_magnitude, 2)
filters.append(decimate)
filters.append(rs.temporal_filter())

# Advanced mode configuration from json
advanced_json = 'device_config/HighAccuracy.json'
# advanced_json = 'device_config/ShortRangePreset.json'
with open(advanced_json, 'r') as file: # Load json file 
    json_text = file.read().strip()
device = pipeline_profile.get_device() # Get the active profile 
advanced_mode = rs.rs400_advanced_mode(device)
advanced_mode.load_json(json_text)

print ('Realsense Device Started %s' %device )

print (' -- -- --')

# Create a separate thread for reading the latest frame.
# This thread also performs heavy computation such that the retrival is fast.

def get_frame_in_background():
    while True:
        global last_pointcloud_points, lock
        time_start = time()

        # Get Frame and apply filters
        frames = pipeline.wait_for_frames()
        # frames = device_manager.poll_frames()
        depth = frames.get_depth_frame()
        for filter in filters:
            depth = filter.process(depth)

        # Compute point cloud and format to list of xyz values
        pointcloud = pc.calculate(depth)
        points = np.asanyarray(pointcloud.get_vertices()).tolist()

        # Cull points that are not zero
        point_xyz = []
        for pt in points:
            if pt[0] != 0:
                point_xyz.append([pt[0],pt[1],pt[2]])

        # Write result to global variable
        lock.acquire()
        last_pointcloud_points = point_xyz
        lock.release()
        # print ('Number of Points in PC: %i' % len(point_xyz))
        print ('Last frame processing took = %3i ms (%ipoints)       \r' %  (((time()-time_start) * 1000), len(point_xyz)) , end='' )

Thread(target = get_frame_in_background).start()


async def websocket_reply(websocket, path):
    received = await websocket.recv()
    try : 
        filter_magnitude = int(received)
        if filter_magnitude > 0 and filter_magnitude < 12:
            decimate.set_option(rs.option.filter_magnitude, filter_magnitude)
    except ValueError  :
        pass
    
    time_start = time()
    lock.acquire()
    result = last_pointcloud_points
    lock.release()
    await websocket.send(json.dumps(result))
    print ('Retrieval Processing Time = %i ms (%ipoints)' %  (((time()-time_start) * 1000), len(result)) )

start_server = websockets.serve(websocket_reply, "localhost", 8787)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
