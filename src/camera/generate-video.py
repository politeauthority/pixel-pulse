#!/usr/bin/env python
"""
    Generate Video
    Takes a directory and creates a video of the photos stored.

"""

import argparse
import os
import subprocess

# from polite_lib.file_tools.backblaze import Backblaze

WORK_DIR = "/Users/alix/Programming/repos/pixel-pulse/data"
OUT_DIR = "/Users/alix/Programming/repos/pixel-pulse/data/videos"
OUT_FILE = 'time_lapse.mp4'

TEMPLATE = os.path.join(WORK_DIR, 'frame%04d.jpg')


class GenerateVideo:

    def __init__(self, args):
        self.photo_path = os.path.join(WORK_DIR, "")
        self.args = args

    def main(self):
        """Main entrypoint."""
        self.generate_video()

    def generate_video(self):
        if not self.args.framerate:
            framerate = 24
        else:
            framerate = self.args.framerate

        template = os.path.join(WORK_DIR, self.args.name, 'frame%04d.jpg')
        outfile = os.path.join(OUT_DIR, "%s_%s" % (self.args.name, "time_lapse.mp4"))
        cmd = [
            'ffmpeg', '-r', str(framerate), '-i', template, '-c:v', 'h264', outfile]
        print(" ".join(cmd))
        if self.args.overwrite:
            cmd.append("-y")
        subprocess.check_call(cmd)


def parse_args():
    """Parse CLI args"""
    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "name",
        nargs='?',
        default="all",
        help="")
    parser.add_argument(
        "-o",
        "--overwrite",
        default=False,
        action="store_true",
        help=""
    )
    parser.add_argument(
        "-f",
        "--framerate",
        default=24,
        help=""
    )

    the_args = parser.parse_args()
    return the_args


if __name__ == "__main__":
    the_args = parse_args()
    GenerateVideo(the_args).main()

