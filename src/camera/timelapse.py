#!/usr/bin/env python
"""
    Time Lapse Record v0.0.1

This works OK with my Canon SLR, but will probably need changes to work
with another camera.

"""

import argparse
from contextlib import contextmanager
import locale
import logging
import os
import time

import arrow
import gphoto2 as gp
from paho.mqtt import client as mqtt_client

from polite_lib.file_tools.minio import Minio
from polite_lib.notify import quigley_notify
from polite_lib.utils import date_utils


INTERVAL = 15.0
WORK_DIR = '/home/comitup/raw_photos'
ROOM_ID = "!cdCwnaincUSIwCVjKh:squid-ink.us"
BUCKET_NAME = "corrine-joe"


class TimeLapse:

    def __init__(self, args):
        self.args = args
        self.started = arrow.utcnow()
        self.check_in_last = arrow.utcnow()
        self.check_in_interval = 500
        self.notify_last = arrow.utcnow()
        self.last_uploaded = None
        self.battery_level = None
        self.battery_level_change = None
        self.battery_levels = {}

    def main(self) -> bool:
        """Main entrypoint."""
        if self.args.test:
            self.take_test_shot()
            return True
        self.setup()
        self.run_timelapse()
        return True

    def setup(self) -> bool:
        """Connect to the Minio bucket and run the file system setup."""
        self.minio = Minio()
        self.minio.connect(BUCKET_NAME)
        self._setup_filesystem()
        return True

    def take_test_shot(self) -> bool:
        local_path = "/home/comitup/raw_photos/test_shots/test0001.jpg"
        print(local_path)
        with self.configured_camera() as camera:
            self.empty_event_queue(camera)
            path = camera.capture(gp.GP_CAPTURE_IMAGE)
            camera_file = camera.file_get(
                path.folder, path.name, gp.GP_FILE_TYPE_NORMAL)
            camera_file.save(local_path)
            print("Saved:\t%s" % local_path)
            camera.file_delete(path.folder, path.name)

    @contextmanager
    def configured_camera(self):
        # initialise camera
        camera = gp.Camera()
        try:
            camera.init()
        except gp.GPhoto2Error as e:
            logging.error("Camera not connected: %s" % e)
        try:
            # adjust camera configuratiuon
            cfg = camera.get_config()
            capturetarget_cfg = cfg.get_child_by_name('capturetarget')
            capturetarget = capturetarget_cfg.get_value()
            capturetarget_cfg.set_value('Internal RAM')
            # camera dependent - 'imageformat' is 'imagequality' on some
            imageformat_cfg = cfg.get_child_by_name('imageformat')
            imageformat = imageformat_cfg.get_value()
            imageformat_cfg.set_value('Small Fine JPEG')
            camera.set_config(cfg)
            # use camera
            yield camera
        finally:
            # reset configuration
            capturetarget_cfg.set_value(capturetarget)
            imageformat_cfg.set_value(imageformat)
            camera.set_config(cfg)
            # free camera
            camera.exit()

    def empty_event_queue(self, camera):
        while True:
            type_, data = camera.wait_for_event(10)
            if type_ == gp.GP_EVENT_TIMEOUT:
                return
            if type_ == gp.GP_EVENT_FILE_ADDED:
                # get a second image if camera is set to raw + jpeg
                print('Unexpected new file', data.folder + data.name)

    def snap_sample_photo(self):
        """Take a sample photo, to help set the frame."""
        template = os.path.join(WORK_DIR, "test_photo.jpg")
        with self.configured_camera() as camera:
            path = camera.capture(gp.GP_CAPTURE_IMAGE)
            print('capture', path.folder + path.name)
            camera_file = camera.file_get(
                path.folder, path.name, gp.GP_FILE_TYPE_NORMAL)
            camera_file.save(template)
            camera.file_delete(path.folder, path.name)

    def run_timelapse(self) -> bool:
        """Primary lool for running the timelapse. Most of the script time takes place here."""
        locale.setlocale(locale.LC_ALL, '')
        template = os.path.join(self.photo_path, 'frame%04d.jpg')
        next_shot = time.time() + 1.0
        self.count = self.start_at
        with self.configured_camera() as camera:
            while True:
                try:
                    self.empty_event_queue(camera)
                    while True:
                        sleep = next_shot - time.time()
                        if sleep < 0.0:
                            break
                        time.sleep(sleep)
                    self.checkin(camera)
                    path = camera.capture(gp.GP_CAPTURE_IMAGE)
                    camera_file = camera.file_get(
                        path.folder, path.name, gp.GP_FILE_TYPE_NORMAL)
                    local_path = template % self.count
                    camera_file.save(local_path)
                    print("Saved:\t%s" % local_path)
                    camera.file_delete(path.folder, path.name)
                    self.upload_photo(local_path)
                    next_shot += INTERVAL
                    self.count += 1
                except KeyboardInterrupt:
                    print("Pausing")
                    cont = input("Continue?")
                    if cont in ["y", "yes"]:
                        continue
                    else:
                        break
        return True

    def checkin(self, camera: gp.camera.Camera) -> bool:
        """Process for managing check-ins. We'll capture battery level and send a message to Matrix
        stating the current state of the camera timelapse application.
        """
        now = arrow.utcnow()
        diff = (now - self.check_in_last).seconds
        next_check_in = self.check_in_interval - diff 
        print("\tNext Check In %s seconds" % next_check_in)
        # if diff > (self.check_in_interval / 2):
        #     return True
        text = camera.get_summary()
        battery_level = self._get_battery_level(str(text))
        override_time = False
        msg = ""
        if self.battery_level != battery_level:
            override_time = True
            self.battery_levels[battery_level] = arrow.utcnow()
            if not self.battery_level:
                msg += f"<br>Battery at: {self.battery_level}%"
            else:
                msg += f"<br>Battery has <b>dropped</b> to: {self.battery_level}%"
            self.battery_level = battery_level
            self.battery_level_change = arrow.utcnow()

        if not override_time and diff < self.check_in_interval:
            return True

        print("Battery Level: %s" % battery_level)
        msg += f"<b>Camera-Pi</b><br>On photo: {self.count}<br>Last Uploaded: {self.last_uploaded}"
        msg += f"<br>Battery level: {self.battery_level}%"
        msg += str(self.battery_levels)
        seconds = (now - self.started).seconds
        elapsed = date_utils.elsapsed_time_human(seconds)
        msg += f"Running: {elapsed}"

        diff_notify = (now - self.notify_last).seconds 
        if diff_notify < 60:
            return True
        quigley_notify.send_notification(msg, room_id=ROOM_ID)
        self.check_in_last = arrow.utcnow()

        return True

    def _get_battery_level(self, camera_info: str) -> int:
        battery_segment = camera_info[
            camera_info.find("Battery Level"):]
        battery_value = battery_segment[
            battery_segment.find("value: ") + 7:battery_segment.find("%")]
        try:
            battery_value = int(battery_value)
        except Exception as e:
            print(e)
        return battery_value

    def upload_photo(self, local_file: str) -> bool:
        """Upload a photo to backblaze."""
        remote_phile = "raw_photos/%s/%s" % (
            self.args.name,
            local_file[local_file.rfind("/") + 1:]
        )
        uploaded = self.minio.upload_file(local_file, remote_phile, "image/jpeg")
        public_photo = f"https://a1.alix.lol/{BUCKET_NAME}/{remote_phile}"
        self.last_uploaded = public_photo
        if uploaded:
            print("\tUploaded: %s" % public_photo)
            return True
        else:
            print("Error uploading to b2")
            return False

    def _setup_filesystem(self) -> bool:
        """Setup the directory for the raw photos and determine if we start the photo frame at 0 or
        further down the line.
        """
        self.photo_path = os.path.join(WORK_DIR, self.args.name)
        if not os.path.exists(self.photo_path):
            os.makedirs(self.photo_path)
        existing_files = os.listdir(self.photo_path)
        if not existing_files:
            self.start_at = 0
            return True
        biggest_number = 0
        for phile in existing_files:
            try:
                number = int(phile[5:9])
            except ValueError:
                continue
            if number > biggest_number:
                biggest_number = number
        self.start_at = biggest_number + 1
        print("Starting at frame: %s" % self.start_at)
        return True


def parse_args():
    """Parse CLI args"""
    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "name",
        nargs='?',
        default="all",
        help="Name of the photo series"),
    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help="Take a test shot")
    the_args = parser.parse_args()
    return the_args


if __name__ == "__main__":
    the_args = parse_args()
    # TimeLapse(the_args).upload_photo()
    TimeLapse(the_args).main()

