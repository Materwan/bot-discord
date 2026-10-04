"""`python main.py` starts Clara's Discord bot on its own, talking to a Clara server over HTTP.

The code is clara-server's (clara.discord_bot); this folder only holds the configuration (.env) and the log (data/).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
os.environ.setdefault("CLARA_DISCORD_DATA_DIR", str(HERE / "data"))

try:
    from clara.discord_bot.standalone import run
except ImportError:
    raise SystemExit("clara-server is not installed here: pip install -r requirements.txt") from None

run()
