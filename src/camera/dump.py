#!/usr/bin/env python
"""
    Dump
    WIP

"""

import argparse
from contextlib import contextmanager

import gphoto2 as gp

from polite_lib.file_tools.minio import Minio
from polite_lib.notify import quigley_notify
from polite_lib.utils import date_utils
from polite_lib.file_tools import file_tools


INTERVAL_PHOTO = 10.0
INTERVAL_CHECK_IN = 500
WORK_DIR = '/home/comitup/raw_photos'
ROOM_ID = "!cdCwnaincUSIwCVjKh:squid-ink.us"
BUCKET_NAME = "corrine-joe"


class Dump:

    def __init__(self, args):
        self.args = args

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
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove raw photos off the disk")
    the_args = parser.parse_args()
    return the_args


if __name__ == "__main__":
    the_args = parse_args()
    # TimeLapse(the_args).upload_photo()
    TimeLapse(the_args).main()


# End File: politeauthority/pixel-pulse/src/camera/dump.py
