import json

import pytest

from clara import texts
from clara.commands.framework import CommandContext, Source
from clara.storage.access import OWNER_LEVEL
from types import SimpleNamespace

from conftest import OWNER_ID, make_user


@pytest.fixture
def console(app):
    return CommandContext(app, Source.CONSOLE, user_id=OWNER_ID)


def discord_ctx(app, user_id, guild=None, respond=None):
    return CommandContext(app, Source.DISCORD, user_id=user_id, guild=guild, respond=respond)


@pytest.fixture
def known_users(settings):
    settings.known_users_file.parent.mkdir(parents=True, exist_ok=True)
    settings.known_users_file.write_text(json.dumps({"Paul": 2000, "Marie": 3000}), encoding="utf-8")


# ----------------------------------------------------------------------
# Matching and dispatch
# ----------------------------------------------------------------------
def test_match_requires_slash_unless_bare_is_allowed(app):
    commands = app.commands
    assert commands.match("/help").name == "/help"
    assert commands.match("/HELP arg").name == "/help"
    assert commands.match("help") is None
    assert commands.match("help", allow_bare=True).name == "/help"
    assert commands.match("quit", allow_bare=True) is None  # /quit always needs the slash
    assert commands.match("/quit").name == "/quit"
    assert commands.match("") is None


async def test_unknown_command_in_console(app, console):
    assert await app.commands.run("/nope", console) == texts.UNKNOWN_COMMAND_NAMED.format(name="/nope")


async def test_help_lists_every_command_with_its_level(app, console):
    output = await app.commands.run("help", console)
    for name in app.commands.names:
        assert f"`{name}`" in output
    assert "*(propriétaire)*" in output
    assert "*(niveau 2 — admin)*" in output


async def test_help_for_one_command_and_dash_h(app, console):
    assert "**/whitelist**" in await app.commands.run("/help whitelist", console)
    assert "**/token**" in await app.commands.run("/token -h", console)
    assert "Commande inconnue" in await app.commands.run("/help nope", console)


async def test_argparse_errors_become_french_usage_messages(app, console):
    output = await app.commands.run("/auth 123 9", console)
    assert output.startswith("Usage : /auth")
    assert "choix invalide" in output


# ----------------------------------------------------------------------
# Permission levels
# ----------------------------------------------------------------------
async def test_level_too_low_is_denied_and_logged(app):
    output = await app.commands.run("/whitelist", discord_ctx(app, 5))
    assert output.startswith("**Accès refusé**")
    assert "niveau **2** (admin)" in output and "niveau **0** (visiteur)" in output
    assert [e["command"] for e in app.event_log.read("permission_denied")] == ["/whitelist"]


async def test_console_always_has_the_owner_level(app, console):
    assert console.level == OWNER_LEVEL
    assert discord_ctx(app, OWNER_ID).level == OWNER_LEVEL


# ----------------------------------------------------------------------
# /whitelist
# ----------------------------------------------------------------------
async def test_whitelist_add_list_remove(app, console, known_users):
    assert await app.commands.run("/whitelist", console) == texts.WHITELIST_EMPTY
    assert "ajouté" in await app.commands.run("/whitelist add 42", console)
    assert "déjà" in await app.commands.run("/whitelist add 42", console)
    assert "**Paul** (`2000`) ajouté" in await app.commands.run("/whitelist add Paul", console)
    listing = await app.commands.run("/whitelist list", console)
    assert "`42`" in listing and "**Paul**" in listing
    assert "retiré" in await app.commands.run("/whitelist remove 42", console)
    assert "n'était pas" in await app.commands.run("/whitelist remove 42", console)
    assert app.whitelist.ids == [2000]


async def test_whitelist_errors(app, console):
    assert "il manque l'utilisateur" in await app.commands.run("/whitelist add", console)
    assert "Utilisateur introuvable" in await app.commands.run("/whitelist add Inconnu", console)


# ----------------------------------------------------------------------
# /auth
# ----------------------------------------------------------------------
async def test_auth_set_show_and_list(app, console, known_users):
    assert "niveau 0 → **2** (admin)" in await app.commands.run("/auth Paul 2", console)
    assert app.permissions.level(2000) == 2
    assert "niveau **2** (admin)." in await app.commands.run("/auth 2000", console)
    listing = await app.commands.run("/auth", console)
    assert "(propriétaire), immuable" in listing and "**Paul** (`2000`) — **2** (admin)" in listing
    assert [e["level"] for e in app.event_log.read("auth")] == [2]


async def test_auth_cannot_change_the_owner(app, console):
    assert "Impossible de modifier" in await app.commands.run(f"/auth {OWNER_ID} 1", console)
    assert ", **immuable**" in await app.commands.run(f"/auth <@{OWNER_ID}>", console)


async def test_auth_is_owner_only(app):
    app.permissions.set_level(5, 4)
    assert "Accès refusé" in await app.commands.run("/auth 6 1", discord_ctx(app, 5))


async def test_user_resolved_from_server_members(app):
    member = make_user(4000, "Lucie")
    guild = SimpleNamespace(members=[member])
    output = await app.commands.run("/auth lucie 1", discord_ctx(app, OWNER_ID, guild))
    assert "**lucie** (`4000`)" in output
    assert app.permissions.level(4000) == 1


# ----------------------------------------------------------------------
# /relation
# ----------------------------------------------------------------------
async def test_relation_set_and_show(app, console, known_users):
    output = await app.commands.run("/relation 70 Paul", console)
    assert "**0 → 70** sur 100 — bonne" in output
    assert app.user_notes.relationship(2000) == 70
    assert "**70/100**" in await app.commands.run("/relation Paul", console)
    assert "**70 → 30**" in await app.commands.run("/relation Paul 30", console)  # reversed order


@pytest.mark.parametrize("line, expected", [
    ("/relation", "Usage : /relation"),
    ("/relation 70", "il manque l'utilisateur"),
    ("/relation 170 Paul", "`170` est hors bornes"),
    ("/relation abc Paul", "`abc` n'est pas un nombre"),
    ("/relation 50 Inconnu", "Utilisateur introuvable"),
])
async def test_relation_errors(app, console, known_users, line, expected):
    assert expected in await app.commands.run(line, console)


async def test_relation_all_lists_and_sets_every_known_user(app, console, known_users):
    app.whitelist.add(5000)
    listing = await app.commands.run("/relation -a", console)
    assert "**Relations (3)**" in listing

    assert "**3 utilisateur(s)** : **60/100**" in await app.commands.run("/relation -a 60", console)
    assert {app.user_notes.relationship(uid) for uid in (2000, 3000, 5000)} == {60}
    assert "tous" in await app.commands.run("/relation -a 60 Paul", console)


async def test_old_set_relation_name_is_unknown(app, console):
    assert "Commande inconnue" in await app.commands.run("/set_relation 70 Paul", console)


async def test_relation_all_write_needs_admin(app, known_users):
    app.permissions.set_level(5, 1)
    ctx = discord_ctx(app, 5)
    assert "**Relations" in await app.commands.run("/relation -a", ctx)
    assert "Accès refusé" in await app.commands.run("/relation -a 60", ctx)


# ----------------------------------------------------------------------
# /remember, /forget, /token, /quit
# ----------------------------------------------------------------------
async def test_remember_keeps_free_text_and_forget_erases(app):
    app.permissions.set_level(5, 1)
    ctx = discord_ctx(app, 5)
    assert await app.commands.run("/remember j'aime le café \"noir\"", ctx) == texts.REMEMBERED
    assert app.user_notes.notes(5) == ["j'aime le café \"noir\""]
    assert "Usage" in await app.commands.run("/remember", ctx)
    assert await app.commands.run("/forget", ctx) == texts.FORGOTTEN
    assert app.user_notes.notes(5) == []


async def test_remember_without_author_is_refused(app):
    ctx = CommandContext(app, Source.CONSOLE)
    assert await app.commands.run("/remember test", ctx) == texts.DISCORD_ONLY


async def test_token_session_and_all_logs(app, console):
    app.stats.add(10, 5)
    assert "1 requête(s) | tokens : 15" in await app.commands.run("/token", console)
    app.event_log.write("message", prompt_tokens=100, completion_tokens=50)
    assert "Total (logs) | 1 requête(s) | tokens : 150" in await app.commands.run("/token -a", console)


async def test_quit_from_discord_replies_before_closing(app, monkeypatch):
    events = []

    async def fake_stop():
        events.append("stopped")

    async def respond(text):
        events.append(text)

    monkeypatch.setattr(app, "stop", fake_stop)
    assert await app.commands.run("/quit", discord_ctx(app, OWNER_ID, respond=respond)) == ""
    assert events == [texts.STOPPING, "stopped"]
