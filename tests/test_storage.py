import json
import os

import pytest

from clara.storage.access import OWNER_LEVEL, Permissions, Whitelist
from clara.storage.channel_history import ChannelHistory, Exchange
from clara.storage.channel_memory import ChannelMemory
from clara.storage.event_log import EventLog, TokenStats
from clara.storage.json_file import CachedFile, read_json, write_json_atomic
from clara.storage.user_directory import UserDirectory


# ----------------------------------------------------------------------
# JSON helpers
# ----------------------------------------------------------------------
def test_read_json_returns_default_for_missing_or_broken_file(tmp_path):
    assert read_json(tmp_path / "missing.json", default=[]) == []
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert read_json(broken, default={}) == {}


def test_write_json_atomic_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "sub" / "data.json"
    write_json_atomic(path, {"é": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"é": 1}
    assert list(path.parent.iterdir()) == [path]


def test_cached_file_reparses_only_when_modified(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("one", encoding="utf-8")
    parse_calls = []
    cached = CachedFile(path, lambda text: parse_calls.append(text) or text, default="")

    assert cached.get() == "one"
    assert cached.get() == "one"
    assert parse_calls == ["one"]

    path.write_text("two", encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    assert cached.get() == "two"

    path.unlink()
    assert cached.get() == ""


# ----------------------------------------------------------------------
# Channel memory and history
# ----------------------------------------------------------------------
def test_channel_memory_adds_unique_facts_and_persists(tmp_path):
    path = tmp_path / "memory.json"
    memory = ChannelMemory(path)
    assert memory.add(1, "Le salon parle de maths")
    assert not memory.add(1, "Le salon parle de maths")
    assert not memory.add(1, "   ")
    assert ChannelMemory(path).facts(1) == ["Le salon parle de maths"]
    assert memory.facts(2) == []


def test_channel_memory_ignores_legacy_chat_entries_and_caps_facts(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"1": [{"role": "user", "content": "x"}, "fact"]}), encoding="utf-8")
    memory = ChannelMemory(path, max_facts=2)
    assert memory.facts(1) == ["fact"]
    memory.add(1, "b")
    memory.add(1, "c")
    assert memory.facts(1) == ["b", "c"]


def test_channel_history_keeps_last_entries_and_truncates(tmp_path):
    path = tmp_path / "history.json"
    history = ChannelHistory(path, max_entries=2)
    history.add(1, "Paul", "q1", "r1")
    history.add(1, "Paul", "q2", "r2")
    history.add(1, "Paul", "x" * 500, "r3")
    history.add(1, "Paul", "", "")  # ignored

    exchanges = ChannelHistory(path, max_entries=2).exchanges(1)
    assert [e.reply for e in exchanges] == ["r2", "r3"]
    assert len(exchanges[1].prompt) == 300

    history.clear(1)
    assert history.exchanges(1) == []


def test_channel_history_reads_the_existing_file_format(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"1": [{"author": "A", "prompt": "p", "reply": "r"}]}), encoding="utf-8")
    assert ChannelHistory(path).exchanges(1) == [Exchange("A", "p", "r")]


# ----------------------------------------------------------------------
# Whitelist and permissions
# ----------------------------------------------------------------------
def test_whitelist_add_remove_and_persist(tmp_path):
    path = tmp_path / "whitelist.json"
    whitelist = Whitelist(path)
    assert whitelist.add(5)
    assert not whitelist.add(5)
    assert 5 in whitelist and len(whitelist) == 1
    assert Whitelist(path).ids == [5]
    assert whitelist.remove(5)
    assert not whitelist.remove(5)
    assert Whitelist(path).ids == []


def test_whitelist_accepts_the_tolerated_dict_format(tmp_path):
    path = tmp_path / "whitelist.json"
    path.write_text(json.dumps({"ids": [1, "2", "bad"]}), encoding="utf-8")
    assert Whitelist(path).ids == [1, 2]


def test_permissions_owner_is_immutable_and_never_stored(tmp_path):
    path = tmp_path / "permissions.json"
    path.write_text(json.dumps({"42": 9, "7": 2, "1": 0, "x": 1}), encoding="utf-8")
    permissions = Permissions(path, owner_id=42)

    assert permissions.level(42) == OWNER_LEVEL
    assert permissions.level(7) == 2
    assert permissions.level(99) == 0
    assert permissions.level(None) == 0
    assert not permissions.set_level(42, 1)
    assert permissions.set_level(99, 3)
    assert permissions.entries == [(99, 3), (7, 2), (1, 0)]
    assert "42" not in json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(ValueError):
        permissions.set_level(99, 6)


# ----------------------------------------------------------------------
# User directory
# ----------------------------------------------------------------------
def test_user_directory_lookups_are_case_insensitive(tmp_path):
    path = tmp_path / "known_users.json"
    path.write_text(json.dumps({"Florian": 5, "Flo": 5, "Nathan": "6", "Bad": "x"}), encoding="utf-8")
    directory = UserDirectory(path)

    assert directory.id_for("florian") == 5
    assert directory.id_for(" FLO ") == 5
    assert directory.id_for("Unknown") is None
    assert directory.name_for(5) == "Florian"  # first registered name
    assert directory.ids() == {5, 6}
    assert directory.names() == ["Florian", "Flo", "Nathan"]


def test_user_directory_without_file_is_empty(tmp_path):
    directory = UserDirectory(tmp_path / "missing.json")
    assert directory.names() == [] and directory.id_for("x") is None


# ----------------------------------------------------------------------
# Event log and token stats
# ----------------------------------------------------------------------
def test_event_log_writes_and_filters_entries(tmp_path):
    log = EventLog(tmp_path / "log.jsonl")
    log.write("message", prompt_tokens=3, completion_tokens=4)
    log.write("error", error="boom")
    with log.path.open("a", encoding="utf-8") as file:
        file.write("garbage\n")
    log.write("message", prompt_tokens=1)

    assert len(list(log.read())) == 3
    stats = TokenStats.from_entries(log.read("message"))
    assert (stats.requests, stats.prompt_tokens, stats.completion_tokens) == (2, 4, 4)
    assert stats.total_tokens == 8
    assert stats.minutes_elapsed is None


def test_event_log_read_of_missing_file_is_empty(tmp_path):
    log = EventLog(tmp_path / "log.jsonl")
    assert list(log.read()) == []
