"""Run the bot from the project root without installing it: `python main.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from clara.app import run  # noqa: E402

if __name__ == "__main__":
    run()
