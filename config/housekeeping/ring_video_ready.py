#!/usr/bin/env python3
"""Keep the existing Ring command valid while sharing bounded video startup."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('notification_video_ready.py')), run_name='__main__')
