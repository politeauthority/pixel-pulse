#!/usr/bin/env python
"""
    Timelapse v.0.0.1

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
from polite_lib.file_tools import file_tools


INTERVAL_PHOTO = 10.0
INTERVAL_CHECK_IN = 500
WORK_DIR = '/home/comitup/raw_photos'
ROOM_ID = "!cdCwnaincUSIwCVjKh:squid-ink.us"
BUCKET_NAME = "corrine-joe"


class TimeLapse:

    def __init__(self, args):
        self.args = args
        self.started = arrow.utcnow()
        self.check_in_last = arrow.utcnow()
        self.check_in_interval = INTERVAL_CHECK_IN
        self.notify_last = arrow.utcnow()
        self.last_uploaded = None
        self.battery_level = None
        self.upload = True
        self.battery_level_change = None
        self.battery_levels = {}
        self.photos_taken = 0
        self.photos_uploaded = 0

    def main(self) -> bool:
        """Main entrypoint."""
        if self.args.test:
            self.take_test_shot()
            return True
        self.setup()
        if self.args.cleanup:
            self.cleanup()
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
                    self.matrix_checkin(camera)
                    path = camera.capture(gp.GP_CAPTURE_IMAGE)
                    camera_file = camera.file_get(
                        path.folder, path.name, gp.GP_FILE_TYPE_NORMAL)
                    local_path = template % self.count
                    camera_file.save(local_path)
                    print("Saved:\t%s" % local_path)
                    camera.file_delete(path.folder, path.name)
                    self.upload_photo(local_path)
                    self.photos_taken += 1
                    next_shot += INTERVAL_PHOTO
                    self.count += 1

                except KeyboardInterrupt:
                    print("Pausing\n")
                    cont = input("Resume?\t")
                    if cont in ["y", "yes"]:
                        print("Continuing time lapse")
                        continue
                    else:
                        print("Exiting time lapse")
                        self.prepare_exit()
                        break
        return True

    def matrix_checkin(self, camera: gp.camera.Camera) -> bool:
        """Process for managing check-ins. We'll capture battery level and send a message to Matrix
        stating the current state of the camera timelapse application.
        """
        now = arrow.now()
        diff = (now - self.check_in_last).seconds
        next_check_in = self.check_in_interval - diff
        print("\tNext Check In %s seconds" % next_check_in)
        text = camera.get_summary()
        battery_level = self._get_battery_level(str(text))
        override_time = False
        msg = f'<h2>Camera-Pi</h2>'
        # Handle Battery Checks
        if self.battery_level != battery_level:
            override_time = True
            self.battery_levels[battery_level] = arrow.now()
            if not self.battery_level:
                msg += f"<br>Battery at: {self.battery_level}%"
            else:
                msg += f"<br>Battery has <b>dropped</b> to: {self.battery_level}%"
            self.battery_level = battery_level
            self.battery_level_change = arrow.now()

        # Handle Disk Checks
        disk_warning = False
        disk_info = file_tools.get_disk_info()
        if disk_info["percent_available"] < 30:
            override_time = True
            disk_warning = True
            print("disk info issue!")

        if not override_time and diff < self.check_in_interval:
            return True

        print("Battery Level: %s" % battery_level)

        msg += f"<br>On Photo Frame: <b>{self.count}</b>"
        msg += f"<br><b>Session Photos Taken</b>: {self.photos_taken}"        
        msg += f"<br><b>Photos Uploaded</b>: {self.photos_uploaded}"
        msg += f"<br>Battery Level: <b>{self.battery_level}%</b>"
        msg += f"<br>Local Diskspace Available: "

        if disk_warning:
            msg += f"""<span style="color:red"><b>{disk_info["percent_available"]}%</b>"""
            msg += f"""</span>"""
            # msg += f"""{disk_info["file_system_available_human"]}</span>"""
        else:
            msg += f"""<span style="color:green"><b>{disk_info["percent_available"]}%</b>"""
            msg += f"""</span>"""
            # msg += f"""{disk_info["file_system_available_human"]}</span>"""

        battery_levels_str = {}
        for batt_level, batt_time in self.battery_levels.items():
            battery_levels_str[str(batt_level)] = date_utils.json_date_out(batt_time.datetime)

        seconds = (now - self.started).seconds
        elapsed = date_utils.elsapsed_time_human(seconds)
        msg += f"<br>Session Run Time: <b>{elapsed}</b>"
        msg += f"<br>Capture Group: <b>{self.args.name}</b>"
        msg += f"<br>Last Uploaded: {self.last_uploaded}"
        msg += f"<br>Batt Times<code>{str(battery_levels_str)}</code>"

        diff_notify = (now - self.notify_last).seconds 
        if diff_notify < 60:
            return True
        quigley_notify.send_notification(msg, room_id=ROOM_ID)
        self.check_in_last = arrow.now()
        self.cleanup()
        return True

    def prepare_exit(self) -> bool:
        msg = f'<h2>Camera-Pi</h2>'
        msg += f"<br>On Photo Frame: <b>{self.count}</b>"
        msg += f"<br>Capture Group: <b>{self.args.name}</b>"
        msg += f"<br>Last Uploaded: {self.last_uploaded}"
        msg += f"<br><b>Photos Taken</b>: {self.photos_taken}"
        quigley_notify.send_notification(msg, room_id=ROOM_ID)
        self.cleanup()

    def cleanup(self) -> bool:
        """Remove photos that have already been uploaded"""
        if not self.args.cleanup:
            return True
        print("Running cleanup")
        photo_files = os.listdir(self.photo_path)
        photo_number = self._get_next_photo_number()
        if photo_number == 0:
            return True
        last_photo_number = photo_number - 1
        deleted_photos = 0
        for photo_file in photo_files:
            if photo_file != "frame{:04d}.jpg".format(last_photo_number):
                full_path = os.path.join(self.photo_path, photo_file)
                # print("Removing: %s" % full_path)
                os.remove(full_path)
                deleted_photos += 1
        print("Deleted: %s" % deleted_photos)
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
        upload_start = arrow.utcnow()
        remote_phile = "raw_photos/%s/%s" % (
            self.args.name,
            local_file[local_file.rfind("/") + 1:]
        )
        uploaded = self.minio.upload_file(local_file, remote_phile, "image/jpeg")
        upload_end = arrow.utcnow()
        uploaded_diff = upload_end - upload_start
        public_photo = f"https://a1.alix.lol/{BUCKET_NAME}/{remote_phile}"
        self.last_uploaded = public_photo
        if uploaded:
            print("\tUploaded: %s" % public_photo)
            self.photos_uploaded += 1
            return True
        else:
            print("Error uploading to A1")
            return False

    def _setup_filesystem(self) -> bool:
        """Setup the directory for the raw photos and determine if we start the photo frame at 0 or
        further down the line.
        """
        self.photo_path = os.path.join(WORK_DIR, self.args.name)
        if not os.path.exists(self.photo_path):
            os.makedirs(self.photo_path)
        self.start_at = self._get_next_photo_number()
        print("Starting at frame: %s" % self.start_at)
        return True

    def _get_next_photo_number(self) -> int:
        """Check the photo path and get the last photo taken."""
        existing_files = os.listdir(self.photo_path)
        biggest_number = 0
        for phile in existing_files:
            if "frame" not in phile:
                continue
            try:
                number = int(phile[5:9])
            except ValueError:
                continue
            if number > biggest_number:
                biggest_number = number
        if biggest_number == 0:
            return 0
        else:
            return biggest_number + 1
        


def parse_args():
    """Parse CLI args"""
    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "name",
        nargs='?',
        default="all",
        help="Name of the photo series"),
    parser.add_argument(
        "--no-wan",
        action="store_true",
        help="Run in no wide area network mode")

    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help="Take a test shot")

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove raw photos off the disk")
    the_args = parser.parse_args()
    return the_args


if __name__ == "__main__":
    try:
        the_args = parse_args()
        # TimeLapse(the_args).upload_photo()
        TimeLapse(the_args).main()
    except Exception as e:
        msg = f'<h2>Camera-Pi</h2>'
        msg += f'<h4><span style="color:red"><b>RECORDING STOPPED</b></span></h4>'
        msg += f'<br>Recieved Error:<b/><code>{e}</code>'
        quigley_notify.send_notification(msg, room_id=ROOM_ID)


# End File: politeauthority/pixel-pulse/src/camera/timelapse.py
