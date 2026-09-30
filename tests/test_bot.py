import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

from clara import texts
from clara.bot import settling
from clara.bot.loop_guard import BotLoopGuard
from clara.bot.mentions import add_pings, find_cited_members, replace_mentions_with_names, strip_bot_mention
from clara.bot.pipeline import split_message
from clara.bot.settling import MessageSettler
from clara.storage.user_directory import UserDirectory
from clara.tracking import Phase
from conftest import BOT_ID, OWNER_ID, chat_response, make_message, make_user


@pytest.fixture(autouse=True)
def fast_settling(monkeypatch):
    monkeypatch.setattr(settling, "TYPING_QUIET_SECONDS", 0.05)
    monkeypatch.setattr(settling, "EDIT_QUIET_SECONDS", 0.05)


def mention(user_id: int) -> str:
    return f"<@{user_id}>"


# ----------------------------------------------------------------------
# Message splitting and mentions
# ----------------------------------------------------------------------
def test_split_message_prefers_line_breaks_then_spaces():
    assert split_message("court") == ["court"]
    assert split_message("aaaa\nbbbb", limit=6) == ["aaaa", "bbbb"]
    assert split_message("aaa bbb ccc", limit=8) == ["aaa bbb", "ccc"]
    assert split_message("x" * 10, limit=4) == ["xxxx", "xxxx", "xx"]
    assert all(len(chunk) <= 2000 for chunk in split_message("mot " * 1500))


def test_strip_and_replace_mentions():
    paul = make_user(2, "Paul")
    assert strip_bot_mention(f"{mention(9)} salut <@!9>", 9) == "salut"
    text = replace_mentions_with_names(f"tu connais {mention(2)} et <@!2> ?", [paul, make_user(9, "Clara")], 9)
    assert text == "tu connais Paul et Paul ?"


def test_find_cited_members_uses_mentions_and_typed_names():
    author, paul, marie = make_user(1, "Erwan"), make_user(2, "Paul"), make_user(3, "Marie-Anne")
    bot, other_bot, short = make_user(9, "Clara", bot=True), make_user(8, "Robot", bot=True), make_user(4, "Al")
    message = make_message(author, "", mentions=[paul, bot], members=[author, paul, marie, other_bot, short])

    cited = find_cited_members(message, "que penses-tu de marie-anne, Robot et Al ?", bot_id=9)
    assert [user.id for user in cited] == [2, 3, 8]  # other bots included, never Clara
    assert find_cited_members(message, "Paulette", bot_id=9) == [paul]  # mention only, no partial word


@pytest.fixture
def directory(tmp_path):
    path = tmp_path / "known_users.json"
    path.write_text(json.dumps({"Jean": 1, "Jean Pierre": 2, "Clara": 9}), encoding="utf-8")
    return UserDirectory(path)


def test_add_pings_uses_the_longest_known_name(directory):
    assert add_pings("Salut @Jean Pierre et @jean !", directory, [], bot_id=9) == "Salut <@2> et <@1> !"
    assert add_pings("@Clara @Inconnu <@5>", directory, [], bot_id=9) == "@Clara @Inconnu <@5>"


def test_add_pings_tags_server_members_and_bots(directory):
    members = [make_user(3, "Lucie"), make_user(8, "Veli", bot=True), make_user(9, "Clara", bot=True)]
    members[0].name = "lucie_du_78"
    text = "@lucie, @LUCIE_DU_78 et @Veli : venez ! @Clara"
    assert add_pings(text, directory, members, bot_id=9) == "<@3>, <@3> et <@8> : venez ! @Clara"


def test_add_pings_are_capped_per_reply(directory):
    members = [make_user(10 + i, f"Membre{i}") for i in range(4)]
    text = "@Membre0 @Membre1 @Membre0 @Membre2 @Membre3"
    assert add_pings(text, directory, members, bot_id=9, max_pings=2) == "<@10> <@11> <@10> @Membre2 @Membre3"


def test_loop_guard_limits_bot_streaks_per_channel():
    guard = BotLoopGuard(limit=2)
    assert guard.allow_bot_reply(1) and guard.allow_bot_reply(1)
    assert not guard.allow_bot_reply(1)
    assert guard.allow_bot_reply(2)  # other channels are independent
    guard.human_spoke(1)
    assert guard.allow_bot_reply(1)


# ----------------------------------------------------------------------
# Settling
# ----------------------------------------------------------------------
async def test_settle_waits_for_typing_and_returns_the_last_edit():
    settler = MessageSettler()
    author = make_user(1, "Erwan")
    message = make_message(author, "brouillon")
    edited = make_message(author, "version finale")
    settler.record_typing(message.channel.id, author.id)

    async def keep_typing_then_edit():
        await asyncio.sleep(0.03)
        settler.record_typing(message.channel.id, author.id)
        edited.id = message.id
        settler.record_edit(edited)

    task = asyncio.create_task(keep_typing_then_edit())
    assert await settler.settle(message) is edited
    await task


async def test_settle_returns_none_for_deleted_messages():
    settler = MessageSettler()
    message = make_message(make_user(1, "Erwan"), "")

    async def delete():
        await asyncio.sleep(0.01)
        settler.record_deletion(message.id)

    task = asyncio.create_task(delete())
    assert await settler.settle(message, expect_completion=True) is None
    await task


def test_edits_and_deletions_of_untracked_messages_are_ignored():
    settler = MessageSettler()
    settler.record_edit(make_message(make_user(1, "x"), "y", message_id=5))
    settler.record_deletion(5)
    assert not settler._last_edit and not settler._deleted


# ----------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------
async def test_whitelisted_user_gets_an_answer(app, ollama, bot_user, friend):
    app.whitelist.add(friend.id)
    ollama.queue(chat_response("Salut @Erwan !"), chat_response("{}"))
    app.settings.known_users_file.write_text(json.dumps({"Erwan": OWNER_ID}), encoding="utf-8")
    message = make_message(friend, f"{mention(BOT_ID)} salut", mentions=[bot_user])

    await app.pipeline.handle(message)

    message.reply.assert_awaited_once_with(f"Salut <@{OWNER_ID}> !")
    assert ollama.requests[0]["tools"] is not None  # the tools really reach the model
    assert ollama.requests[1]["format"] == "json"  # insight extraction
    assert [e.reply for e in app.channel_history.exchanges(message.channel.id)] == ["Salut @Erwan !"]
    assert app.stats.requests == 1
    assert len(app.tracker) == 0


async def test_non_whitelisted_user_is_ignored_and_logged(app, ollama, bot_user, friend):
    message = make_message(friend, f"{mention(BOT_ID)} salut", mentions=[bot_user])
    await app.pipeline.handle(message)
    message.reply.assert_not_awaited()
    assert ollama.requests == []
    assert [e["author_id"] for e in app.event_log.read("whitelist_denied")] == [friend.id]


async def test_messages_without_mention_or_from_bots_are_ignored(app, ollama, bot_user, owner):
    await app.pipeline.handle(make_message(owner, "salut"))
    other_bot = make_user(8000, "Robot", bot=True)
    await app.pipeline.handle(make_message(other_bot, f"{mention(BOT_ID)} salut", mentions=[bot_user]))
    assert ollama.requests == []


async def test_allowed_bots_may_talk(app, ollama, bot_user, settings, monkeypatch):
    other_bot = make_user(8000, "Robot", bot=True)
    monkeypatch.setattr(app, "settings", dataclasses.replace(settings, allowed_bot_ids=frozenset({8000})))
    app.whitelist.add(8000)
    ollama.queue(chat_response("bip"))
    message = make_message(other_bot, f"{mention(BOT_ID)} bip", mentions=[bot_user])
    await app.pipeline.handle(message)
    message.reply.assert_awaited_once_with("bip")


async def test_answer_can_tag_a_cited_bot(app, ollama, bot_user, owner):
    veli = make_user(8000, "Veli", bot=True)
    ollama.queue(chat_response("Coucou @Veli !"), chat_response("{}"))
    message = make_message(owner, f"{mention(BOT_ID)} dis bonjour à Veli", mentions=[bot_user], members=[owner, veli])
    await app.pipeline.handle(message)

    message.reply.assert_awaited_once_with("Coucou <@8000> !")
    prompt = ollama.requests[0]["messages"][1]["content"]
    assert "Personnes concernées par ce message : Erwan, Veli (bot)." in prompt
    assert "Informations sur Veli" not in prompt
    assert "- 8000 " not in ollama.requests[1]["messages"][1]["content"]  # bots get no insights


async def test_bot_to_bot_replies_stop_until_a_human_speaks(app, ollama, bot_user, owner, settings, monkeypatch):
    other_bot = make_user(8000, "Robot", bot=True)
    monkeypatch.setattr(app, "settings", dataclasses.replace(settings, allowed_bot_ids=frozenset({8000})))
    monkeypatch.setattr(app.pipeline, "loop_guard", BotLoopGuard(limit=2))
    app.whitelist.add(8000)

    def bot_message():
        message = make_message(other_bot, f"{mention(BOT_ID)} bip", mentions=[bot_user])
        message.channel.id = 42
        return message

    answered = []
    for _ in range(3):
        message = bot_message()
        await app.pipeline.handle(message)
        answered.append(message.reply.await_count == 1)
    assert answered == [True, True, False]
    assert [e["author_id"] for e in app.event_log.read("bot_loop_stopped")] == [8000]

    human_message = make_message(owner, "on continue ?")  # not even addressed to Clara
    human_message.channel.id = 42
    await app.pipeline.handle(human_message)
    message = bot_message()
    await app.pipeline.handle(message)
    message.reply.assert_awaited_once()


async def test_bare_command_words_go_to_the_model_even_for_the_owner(app, ollama, bot_user, owner):
    ollama.queue(chat_response("Quoi ?"))
    message = make_message(owner, f"{mention(BOT_ID)} whitelist add 42", mentions=[bot_user])
    await app.pipeline.handle(message)
    message.reply.assert_awaited_once_with("Quoi ?")
    assert 42 not in app.whitelist


@pytest.mark.parametrize("text", ["/whitelist add 42", "/nope"])
async def test_old_style_commands_get_a_hint_and_never_reach_the_model(app, ollama, bot_user, owner, text):
    message = make_message(owner, f"{mention(BOT_ID)} {text}", mentions=[bot_user])
    await app.pipeline.handle(message)
    message.reply.assert_awaited_once_with(texts.USE_SLASH_COMMANDS)
    assert ollama.requests == []
    assert 42 not in app.whitelist


async def test_llm_failure_replies_with_an_apology(app, ollama, bot_user, owner):
    ollama.queue(ConnectionError("down"), chat_response("{}"))
    message = make_message(owner, f"{mention(BOT_ID)} salut", mentions=[bot_user])
    await app.pipeline.handle(message)
    message.reply.assert_awaited_once_with(texts.ANSWER_FAILED)
    assert [e["error"] for e in app.event_log.read("error")] == ["ConnectionError('down')"]
    assert len(app.tracker) == 0


async def test_long_answers_are_split(app, ollama, bot_user, owner):
    ollama.queue(chat_response("a" * 2500))
    message = make_message(owner, f"{mention(BOT_ID)} long", mentions=[bot_user])
    await app.pipeline.handle(message)
    message.reply.assert_awaited_once_with("a" * 2000)
    message.channel.send.assert_awaited_once_with("a" * 500)


async def test_attachments_are_saved_and_announced(app, ollama, bot_user, owner, settings):
    async def save(path):
        path.write_text("contenu", encoding="utf-8")

    attachments = [SimpleNamespace(filename="cours.md", save=save), SimpleNamespace(filename="virus.exe", save=save)]
    ollama.queue(chat_response("lu"))
    message = make_message(owner, f"{mention(BOT_ID)} lis ça", mentions=[bot_user], message_id=77, attachments=attachments)
    await app.pipeline.handle(message)

    assert [p.name for p in settings.uploads_dir.iterdir()] == ["77_cours.md"]
    assert "77_cours.md" in ollama.requests[0]["messages"][1]["content"]


async def test_mention_added_by_edit_triggers_an_answer(app, ollama, bot_user, owner):
    ollama.queue(chat_response("vu"))
    before = make_message(owner, "salut")
    after = make_message(owner, f"salut {mention(BOT_ID)}", mentions=[bot_user])
    await app.pipeline.handle_edit(before, after)
    after.reply.assert_awaited_once_with("vu")


async def test_tool_phase_is_tracked_per_request(app, ollama, bot_user, owner):
    phases = []
    app.tracker.on_change(lambda: phases.extend(r.phase for r in app.tracker.active()))
    ollama.queue(
        chat_response(tool_calls=[("save_channel_memory", {"fact": "x"})]),
        chat_response("ok"),
    )
    message = make_message(owner, f"{mention(BOT_ID)} retiens", mentions=[bot_user])
    await app.pipeline.handle(message)
    assert phases == [Phase.PROCESSING, Phase.TOOL_CALLING, Phase.PROCESSING, Phase.ANSWERING]
