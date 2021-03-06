#!/usr/bin/env python

"""Spawn ego vehicle with sensors and publish sensor data in ROS"""

import random
import carla
import rospy
from sensor_msgs.msg import Image
import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError

rospy.init_node('simulator_ego_vehicle')
cv_bridge = CvBridge()

def get_cv_image(carla_image):
    cv_image = np.frombuffer(carla_image.raw_data, dtype=np.dtype("uint8"))
    cv_image = np.reshape(cv_image, (carla_image.height, carla_image.width, 4))
    cv_image = cv_image[:, :, :3]
    cv_image = cv_image[:, :, ::-1]
    return cv_image

def publish_image(carla_image, topic):
    try:
        cv_image = get_cv_image(carla_image)
        image_message = cv_bridge.cv2_to_imgmsg(cv_image, 'rgb8')
    except CvBridgeError as e:
        rospy.logerr(e)

    try:
        publisher = rospy.Publisher(topic, Image, queue_size=10)
        publisher.publish(image_message)
    except rospy.ROSInterruptException as e:
        rospy.logerr(e)

def publish_image_and_viz(carla_image, topic, camera_type):
    publish_image(carla_image, topic)

    # make depth and semantic segmentation images visualizable
    if camera_type == 'semantic_segmentation':
        carla_image.convert(carla.ColorConverter.CityScapesPalette)
    elif camera_type == 'depth':
        carla_image.convert(carla.ColorConverter.Depth)
    publish_image(carla_image, topic + '_viz')

def main():
    ego_vehicle = None
    camera_main_rgb = None
    camera_main_semantic_segmentation = None
    camera_main_depth = None
    camera_3pv_rgb = None # 3rd person view for observation and monitoring

    try:
        # create simulator client
        client = carla.Client('localhost', 2000)
        client.set_timeout(15.0)

        # get simulator world
        world = client.get_world()

        blueprint_library = world.get_blueprint_library()

        # spawn vehicle
        vehicle_blueprint = blueprint_library.find('vehicle.mercedesccc.mercedesccc') # https://carla.readthedocs.io/en/latest/bp_library/#vehicle
        vehicle_blueprint.set_attribute('role_name', 'ego_vehicle')
        if vehicle_blueprint.has_attribute('color'):
            color = random.choice(vehicle_blueprint.get_attribute('color').recommended_values)
            vehicle_blueprint.set_attribute('color', color)
        vehicle_transform = random.choice(world.get_map().get_spawn_points())
        ego_vehicle = world.spawn_actor(vehicle_blueprint, vehicle_transform)
        ego_vehicle.set_autopilot(False)
        
        def create_camera_blueprint(role_name, blueprint, fov):
            camera_blueprint = blueprint_library.find(blueprint)
            camera_blueprint.set_attribute('role_name', role_name)
            camera_blueprint.set_attribute('image_size_x', '720')
            camera_blueprint.set_attribute('image_size_y', '480')
            camera_blueprint.set_attribute('fov', fov) # sensor field of view
            camera_blueprint.set_attribute('sensor_tick', '0.1') # time in seconds between sensor captures
            return camera_blueprint

        camera_main_rgb_blueprint = create_camera_blueprint('ego_vehicle_camera_main_rgb', 'sensor.camera.rgb', '120')
        camera_main_semantic_segmentation_blueprint = create_camera_blueprint(
            'ego_vehicle_camera_main_semantic_segmentation', 'sensor.camera.semantic_segmentation', '120'
        )
        camera_main_depth_blueprint = create_camera_blueprint('ego_vehicle_camera_main_depth', 'sensor.camera.depth', '120')
        camera_3pv_rgb_blueprint = create_camera_blueprint('ego_vehicle_camera_3pv_rgb', 'sensor.camera.rgb', '90')

        # location: https://carla.readthedocs.io/en/latest/python_api/#carlalocationcarlavector3d-class
        # rotation: https://carla.readthedocs.io/en/latest/python_api/#carlarotation-class
        camera_main_transform = carla.Transform(carla.Location(x=0.5, y=0, z=2), carla.Rotation(pitch=0, yaw=0, roll=0))
        camera_3pv_transform = carla.Transform(carla.Location(x=-8, y=0, z=4), carla.Rotation(pitch=-15, yaw=0, roll=0))

        camera_main_rgb = world.spawn_actor(camera_main_rgb_blueprint, camera_main_transform, attach_to=ego_vehicle)
        camera_main_semantic_segmentation = world.spawn_actor(camera_main_semantic_segmentation_blueprint, camera_main_transform, attach_to=ego_vehicle)
        camera_main_depth = world.spawn_actor(camera_main_depth_blueprint, camera_main_transform, attach_to=ego_vehicle)
        camera_3pv_rgb = world.spawn_actor(camera_3pv_rgb_blueprint, camera_3pv_transform, attach_to=ego_vehicle)

        rospy.loginfo('Ego vehicle and sensors spawned')

        camera_main_rgb.listen(lambda carla_image: publish_image(carla_image, 'camera_main_rgb'))
        camera_main_semantic_segmentation.listen(
            lambda carla_image: publish_image_and_viz(carla_image, 'camera_main_semantic_segmentation', 'semantic_segmentation')
        )
        camera_main_depth.listen(lambda carla_image: publish_image_and_viz(carla_image, 'camera_main_depth', 'depth'))
        camera_3pv_rgb.listen(lambda carla_image: publish_image(carla_image, 'camera_3pv_rgb'))

        while True:
            world.wait_for_tick()

    finally:
        if ego_vehicle is not None:
            ego_vehicle.destroy()
        if camera_main_rgb is not None:
            camera_main_rgb.destroy()
        if camera_main_semantic_segmentation is not None:
            camera_main_semantic_segmentation.destroy()
        if camera_main_depth is not None:
            camera_main_depth.destroy()
        if camera_3pv_rgb is not None:
            camera_3pv_rgb.destroy()
        rospy.loginfo('Ego vehicle and sensors destroyed')


if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print('\ndone.')
