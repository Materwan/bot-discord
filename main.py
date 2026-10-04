"""`python main.py` starts the bot (same as `clara-discord`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from clara_discord.app import run  # noqa: E402

run()
