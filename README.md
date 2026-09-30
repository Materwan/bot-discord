# Clara — Discord bot powered by Ollama

Clara is a French-speaking Discord bot (school help + banter) running on a local
or cloud **Ollama** model. She remembers facts about each user, keeps a
relationship score with them, reads attached files, and is driven from a
full-screen terminal console.

The code, comments and file names are in English; everything users see on
Discord (answers, command outputs) is in French.

## Features

- **Answers with tools** — the model can call `read_file`, `remember_user_info`,
  `forget_user_info` and `save_channel_memory` (native Ollama tool calling).
- **Per-user memory** (SQLite) — permanent notes (`/remember`) and facts learned
  automatically after each message, ranked by relevance before being injected.
- **Relationship score (0-100)** — moves with the tone of each message (LLM
  analysis + local insult detector) and sets the tone of Clara's answers.
- **Tagging** — Clara can tag any member of the server, human or bot, by
  writing `@Name` (up to 10 different people per answer).
- **Channel memory and history** — durable facts per channel, plus the last
  `HISTORY_SIZE` exchanges re-injected as context.
- **Access control** — a whitelist decides who gets answers; permission levels
  (0-5) decide who may run which command. The owner is always level 5.
- **Native slash commands** — `/relation`, `/whitelist`… with Discord's own
  menus and user pickers; the terminal runs the same commands and handlers.
- **Terminal console** — live table of active requests, Markdown output,
  auto-completion and history.

## Setup

Requirements: Python 3.11+, [Ollama](https://ollama.com) with the chosen model,
and a Discord bot token (Message Content and Server Members intents enabled).

```bash
pip install -e ".[dev]"
cp .env.example .env      # then fill DISCORD_BOT_TOKEN and BOT_OWNER_ID
python main.py            # or: clara, or: python -m clara
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | *(required)* | Bot token |
| `BOT_OWNER_ID` | *(required)* | Discord ID of the owner (level 5, always allowed) |
| `OLLAMA_MODEL` | `gemma4:31b-cloud` | Model used for answers and analysis |
| `OLLAMA_HOST` | local server | Ollama server URL |
| `HISTORY_SIZE` | `20` | Exchanges kept per channel |
| `AUTO_INSIGHTS` | `1` | `0` disables the fact/tone LLM pass (the insult detector still runs) |
| `ALLOWED_BOT_IDS` | *(empty)* | Other bots allowed to talk to Clara |

Clara's personality lives in `config/system_prompt.md` (re-read automatically
when edited). Optional per-user instructions can be added in
`config/user_instructions.json`: `{"<user_id>": {"instructions": ["..."]}}`.

## Commands

On Discord, commands are **native slash commands**: type `/` and pick one of
Clara's. They are published at every start (one bulk update; a failure is shown
in the console and logged as `slash_sync_error`). Replies are **ephemeral**:
only the person who ran the command sees them. Only the owner and whitelisted
users may use them; anybody else gets a refusal (`whitelist_denied` logged).

In the terminal, type the same names with arguments (the `/` is optional there).
Both run the same handlers (`bot/slash_commands.py` turns the Discord options
into the terminal line).

| Level | Name | Discord | Terminal |
| --- | --- | --- | --- |
| 0 | visiteur | `/help [commande]`, `/forget` | `/help [commande]`, `/forget` |
| 1 | confiance | `/remember info`, `/relation [utilisateur] [valeur]`, `/token [tout]` | `/remember <info>`, `/relation [<0-100>] <user>`, `/token [-a]` |
| 2 | admin | `/whitelist [action] [utilisateur]`, `/relation tous:True valeur` | `/whitelist [add\|remove\|list] [user]`, `/relation -a <0-100>` |
| 5 | propriétaire | `/auth [utilisateur] [niveau]`, `/quit` | `/auth [user] [0-5]`, `/quit` |

- On Discord, users are picked with Discord's user selector. In the terminal, a
  **user** is an ID, a mention or a name from `data/known_users.json`.
- `/relation` with a value sets the score, without one it shows it; `tous` /
  `-a` targets every known user (listing needs level 1, writing level 2).
- `/auth` lists every level, with a user shows one, with a user and a level sets it.
- Being whitelisted grants level 0 only; raise users with `/auth`.
- The terminal is the owner's machine: it always has level 5.
- Every denial is logged as `permission_denied`.
- A mention of Clara starting with `/` ("@Clara /relation …") is never sent to
  the model: Clara answers with a hint to use the native commands instead.

### Console keys

`Tab` completes, `↑/↓` browse history, `PageUp/PageDown` or the mouse wheel
scroll the output, `Ctrl+C` clears the line, `Ctrl+D` (or `/quit`) stops the bot.
Without an interactive terminal the console is disabled and the bot keeps running.

## How a message is handled

1. **Filter** — the bot must be mentioned; bots need `ALLOWED_BOT_IDS`; the
   author must be the owner or whitelisted (otherwise: silent, `whitelist_denied` logged).
   To prevent two bots from tagging each other forever, at most 3 bot messages
   in a row get an answer per channel; any human message resets the count
   (`bot_loop_stopped` logged).
2. **Settle** — wait until the author stops typing and editing (the latest
   edited version is used; a deleted message is dropped).
3. **Old-style command** — a text starting with `/` gets the slash-command hint and stops.
4. **Answer** — save readable attachments (`.md .pdf .py .c .h`), build the
   prompt (persona + people + channel facts + history + tone order), call the
   model with its tools, reply (split at 2000 characters). The prompt tells the
   model to write `@Name` to tag someone and lists the people and bots involved;
   `@Name` becomes a ping when it matches `data/known_users.json` or a server
   member's display name or username. Roles, `@everyone` and `@here` are never pinged.
5. **Learn** — a JSON-mode LLM pass extracts new facts about the author and the
   people cited, and the author's tone adjusts the relationship score.

### Memory safety

- Learned facts that read like orders ("retiens que tu dois…", "from now on…")
  are rejected by `UserNotes.add_learned`, the single entry point of automatic writes.
- Tools only act on the current channel and on the people involved in the
  message: the model cannot write notes about, or erase, anybody else.
- The prompt states that notes, memories and history are data, never instructions.

## Project layout

```
src/clara/
├─ app.py               wiring, startup, shutdown
├─ settings.py          .env + file locations (frozen dataclass)
├─ texts.py             French user-facing texts
├─ tracking.py          active requests (dashboard)
├─ storage/             persistence, no Discord imports
│  ├─ json_file.py      atomic writes + mtime-cached files
│  ├─ user_notes.py     SQLite notes + relationship score
│  ├─ channel_memory.py
│  ├─ channel_history.py
│  ├─ access.py         whitelist + permission levels
│  ├─ user_directory.py name <-> ID
│  └─ event_log.py      JSONL log + token stats
├─ analysis/            pure text functions
│  ├─ ranking.py        keyword relevance
│  ├─ injection_guard.py
│  └─ tone.py
├─ llm/
│  ├─ client.py         Ollama chat + tool loop
│  ├─ tools.py          the model's tools
│  ├─ prompt_builder.py
│  └─ insights.py       fact + tone extraction
├─ bot/
│  ├─ client.py         discord.Client events
│  ├─ pipeline.py       filter → settle → answer → learn
│  ├─ slash_commands.py native Discord commands → shared handlers
│  ├─ mentions.py       prompt text, cited people, pings
│  ├─ settling.py
│  └─ loop_guard.py     bot-to-bot reply limit
├─ commands/
│  ├─ framework.py      parsing, permission checks, dispatch
│  └─ handlers.py       the commands
└─ console/             prompt_toolkit UI, completer, dashboard
```

## Data (`data/`, git-ignored)

| File | Content |
| --- | --- |
| `user_notes.sqlite` | `notes(user_id, kind, text, created_at)` + `relationships(user_id, value)` |
| `channel_memory.json` | Facts per channel |
| `channel_history.json` | Last exchanges per channel |
| `whitelist.json` | IDs allowed to talk to the bot |
| `permissions.json` | Level of each user (the owner is never stored) |
| `known_users.json` | Name → Discord ID (edited by hand) |
| `event_log.jsonl` | Every event: messages, tokens, errors, command audits |
| `console_history.txt` | Console input history |
| `uploads/` | Saved attachments (`<message_id>_<filename>`) |

## Tests

```bash
python -m pytest -q
```

Every test runs on temporary files with a scripted fake Ollama client: your
real data is never touched and no model is called.
