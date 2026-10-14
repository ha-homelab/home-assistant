"""Run the notification-frames oracle using the locked Linux Atheris engine."""

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with atheris.instrument_imports():
    from fuzz.oracles import notification_frames


if __name__ == "__main__":
    atheris.Setup(sys.argv, atheris.instrument_func(notification_frames))
    atheris.Fuzz()
