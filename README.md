# Clara on Discord, on its own

**The Discord bot is now part of the Clara server**, which can run it itself: put `DISCORD_BOT_TOKEN` (and
`AUTO_START_DISCORD_BOT=true` to start it with the server) in `clara-server/.env`, and control it with `/discord` in
the server's console or on the web site's *Discord* page. See *Discord* in [clara-server's README](../clara-server/README.md):
that is also where everything the bot does is described.

This folder is for running the **same bot on another machine** than the server. It holds no code: it starts
`clara.discord_bot` from clara-server, which then reaches the server over HTTP with a client token.

```
 Discord ─── bot (this machine) ──HTTP──► Clara server ───► Ollama
```

**Never run it and the server's built-in bot with the same Discord token**: both would answer every message.

## Setup

On the **server** (`clara-server/.env`), give the bot a client token, kept to Discord accounts:

```
CLARA_TOKENS=...,discord:<a long random token>
CLARA_CLIENT_SURFACES=...,discord=discord
```

(`python -c "import secrets; print(secrets.token_urlsafe(32))"` makes one.) In the Discord developer portal, on the
*Bot* page, turn on the **Message Content** and **Server Members** intents.

Here, with the `clara-server` folder next to this one:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux: .venv/bin/pip
cp .env.example .env                              # DISCORD_BOT_TOKEN, CLARA_URL, CLARA_TOKEN
.venv/Scripts/python main.py                      # or: clara-discord
```

The log is printed and kept in `data/logs/clara-discord.log` (5 files of 5 MB). The bot's tests are clara-server's
(`tests/discord_bot/`).

The first bot (its own Ollama calls, memory, whitelist and terminal console), and the version before the code moved
to clara-server, are in this repository's git history. The data of the first one in `data/` (`user_notes.sqlite`...)
is not read any more.
