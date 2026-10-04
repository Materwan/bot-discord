# Clara on Discord

A thin client of the [Clara server](../clara-server): the bot keeps no memory, no history and no model of its own.
It passes Discord messages to the server and posts Clara's answers. Clara is the same everywhere: what she learns on
Discord she knows on the web site, in the desktop app and in the terminal, and the other way round.

```
 Discord ─── bot (this) ───► Clara server ───► Ollama
                                  │
                             SQLite memory
```

## Setup

On the **server** (`clara-server/.env`), give the bot a client token, and keep it to Discord accounts:

```
CLARA_TOKENS=...,discord:<a long random token>
CLARA_CLIENT_SURFACES=...,discord=discord
```

`python -c "import secrets; print(secrets.token_urlsafe(32))"` makes a token. Discord accounts must sign in before
they can talk (`CLARA_LOGIN_SURFACES=discord`, the default).

In the **Discord developer portal**, on the *Bot* page of your application, turn on the **Message Content** and
**Server Members** intents. Invite the bot with the `bot` and `applications.commands` scopes, and the permissions to
read and send messages (and read the message history).

Then here:

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Linux: .venv/bin/pip
cp .env.example .env                      # DISCORD_BOT_TOKEN, CLARA_URL, CLARA_TOKEN
.venv/Scripts/clara-discord               # or: python main.py, python -m clara_discord
```

The log is printed and kept in `data/logs/clara-discord.log` (5 files of 5 MB).

## Using it

**An account first.** Nobody can talk to Clara without one. `/register` opens a private form (user name, password
twice) and makes a Clara user: the same user name and password work on Clara's web site, the desktop app and the
terminal. Someone who already has a user signs in with `/login`. Somebody without an account who talks to Clara is
told so (at most once every 10 minutes), and nothing they write is sent to the server.

Discord cannot hide what is typed in a form: mind your screen when you type a password.

**Where Clara answers.**

| | |
| --- | --- |
| Private messages | every message |
| A server channel or thread | a message that mentions her (or her bot role), or replies to one of her messages |
| | any other message of a signed-in member, *if an administrator lets her chime in on that server*: she answers only when she has something worth adding |

Every message of a signed-in member is sent to the server, even when she does not answer, so that she follows the
conversation. While she is busy with a message of a channel, the others of that channel are only kept as context.
Bots are ignored.

**What Clara knows on a server.** The members who are signed in are listed to her, with what she remembers about
the people a message mentions or replies to. She can look up what she remembers about any other signed-in member.
Each channel is one conversation, shared by everybody in it.

**Pings.** Clara writes `@Name` and the bot turns it into a ping of the member with that name (display name or
user name; at most 10 people per answer). Roles, `@everyone` and `@here` are never pinged.

**Reminders** ("remind me tomorrow at 9 to call Paul") and notifications arrive as private messages. Reminders
that fire while the bot is off are sent when it is back (up to a week later).

### Commands

Replies to commands are only visible to whoever ran them. Command descriptions and the bot's own messages are in
French for people whose Discord is in French, in English otherwise.

| Command | |
| --- | --- |
| `/register` | make your Clara account (a form), and sign in |
| `/login` | sign in to an existing Clara account (a form) |
| `/logout` | sign out; what Clara knows about you stays with your account |
| `/me` | your account, linked accounts, your relationship with Clara and what she remembers, with a menu to make her forget something |
| `/remember <text>` | make her remember something about you |
| `/forget <memory>` | make her forget something (the list completes as you type) |
| `/reset` | clear the conversation of this channel (people who can manage the server only) or of your private messages; what she knows about each person is kept |
| `/help` | how to talk with her |

### Administration

It is on the server: its console, `clara-admin`, or the web site's *Admin* page.

| | |
| --- | --- |
| Chime in | `/chime` lists the Discord servers; `/chime <server> on\|off\|default`, `/chime default on\|off`; or *Admin > Spaces* |
| Relationship | `/relation [<person> [<0-100>\|+n\|-n\|reset]]`; or *Admin > People & memory* |
| Memories | `/facts <person>`, `/remember <person> <text>`, `/forget <person> <id>` |
| Accounts | `/user list` shows the Discord accounts signed in for each user; `/user logout <name>` signs them out, `/user disable <name>` bars someone |

## Layout

```
src/clara_discord/
  app.py        start: settings, log, the client
  settings.py   .env
  bot.py        the Discord client: gateway events, the servers it is in, background tasks
  routing.py    which messages are answered, observed or ignored (no Discord in it)
  handler.py    a message: what Clara is given (roster, people mentioned, the replied-to message), her answer
  commands.py   slash commands, sign-in forms, /me
  events.py     reminders and notifications -> private messages
  accounts.py   who is signed in (a copy of the server's), the language of each person
  api.py        every call to the Clara server
  mentions.py   <@id> -> @Name, @Name -> pings, long answers split
  texts.py      the bot's own texts, in French and English
```

Tests: `pytest` (no Discord, no server: both are faked). Lint: `ruff check .`.

The previous bot (its own Ollama calls, memory, whitelist and terminal console) is in the git history. Its data
in `data/` (`user_notes.sqlite`...) is not read any more.
