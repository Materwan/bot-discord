from types import SimpleNamespace

from clara import texts
from conftest import OWNER_ID


class FakeResponse:
    def __init__(self, sent: list):
        self._sent = sent
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content, ephemeral=False):
        assert not self._done, "an interaction can only be answered once"
        self._done = True
        self._sent.append(("response", content, ephemeral))


class FakeInteraction:
    def __init__(self, user, guild=None):
        self.user = user
        self.guild = guild
        self.channel_id = 500
        self.command = None
        self.sent: list[tuple[str, str, bool]] = []
        self.response = FakeResponse(self.sent)

        async def followup_send(content, ephemeral=False):
            self.sent.append(("followup", content, ephemeral))

        self.followup = SimpleNamespace(send=followup_send)

    @property
    def texts(self) -> list[str]:
        return [content for _, content, _ in self.sent]


async def invoke(app, name: str, invoker, **options) -> FakeInteraction:
    interaction = FakeInteraction(invoker)
    await app.client.tree.get_command(name).callback(interaction, **options)
    return interaction


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------
def test_every_command_is_registered_with_a_valid_payload(app):
    tree = app.client.tree
    names = sorted(command.name for command in tree.get_commands())
    assert names == sorted(name.lstrip("/") for name in app.commands.names)

    payloads = {command.name: command.to_dict(tree) for command in tree.get_commands()}
    relation_options = {option["name"]: option for option in payloads["relation"]["options"]}
    assert set(relation_options) == {"utilisateur", "valeur", "tous"}
    assert (relation_options["valeur"]["min_value"], relation_options["valeur"]["max_value"]) == (0, 100)
    assert payloads["relation"]["description"] == "niveau de relation 0-100 avec un utilisateur"
    help_choices = [choice["value"] for choice in payloads["help"]["options"][0]["choices"]]
    assert help_choices == app.commands.names


# ----------------------------------------------------------------------
# Access
# ----------------------------------------------------------------------
async def test_non_whitelisted_users_are_refused_and_logged(app, friend):
    interaction = await invoke(app, "help", friend)
    assert interaction.sent == [("response", texts.NOT_ALLOWED, True)]
    assert [e["command"] for e in app.event_log.read("whitelist_denied")] == ["/help"]


async def test_permission_levels_still_apply(app, friend):
    app.whitelist.add(friend.id)
    interaction = await invoke(app, "whitelist", friend)
    assert interaction.texts[0].startswith("**Accès refusé**")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
async def test_relation_sets_and_shows_with_native_options(app, owner, friend):
    interaction = await invoke(app, "relation", owner, user=friend, value=70)
    assert "**0 → 70**" in interaction.texts[0]
    assert interaction.sent[0][2] is True  # ephemeral
    assert app.user_notes.relationship(friend.id) == 70

    interaction = await invoke(app, "relation", owner, user=friend)
    assert "**70/100**" in interaction.texts[0]

    interaction = await invoke(app, "relation", owner, value=70)
    assert texts.MISSING_USER in interaction.texts[0]


async def test_remember_keeps_free_text(app, owner):
    await invoke(app, "remember", owner, info="j'aime le café \"noir\" -a")
    assert app.user_notes.notes(OWNER_ID) == ["j'aime le café \"noir\" -a"]


async def test_whitelist_and_auth_take_discord_users(app, owner, friend):
    await invoke(app, "whitelist", owner, action="add", user=friend)
    assert friend.id in app.whitelist
    await invoke(app, "auth", owner, user=friend, level=2)
    assert app.permissions.level(friend.id) == 2


async def test_auth_level_without_user_is_rejected(app, owner):
    interaction = await invoke(app, "auth", owner, level=3)
    assert interaction.texts == [texts.MISSING_USER]
    assert app.permissions.level(3) == 0


async def test_long_outputs_are_split_into_follow_ups(app, owner):
    for user_id in range(10**17, 10**17 + 200):
        app.whitelist.add(user_id)
    interaction = await invoke(app, "whitelist", owner)
    kinds = [kind for kind, _, _ in interaction.sent]
    assert kinds[0] == "response" and set(kinds[1:]) == {"followup"}
    assert all(len(content) <= 2000 for content in interaction.texts)


async def test_help_and_token(app, owner):
    assert "**/relation**" in (await invoke(app, "help", owner, command="/relation")).texts[0]
    assert "**Commandes disponibles**" in (await invoke(app, "help", owner)).texts[0]
    assert "Total (logs)" in (await invoke(app, "token", owner, everyone=True)).texts[0]


async def test_quit_answers_before_stopping(app, owner, monkeypatch):
    events = []

    async def fake_stop():
        events.append("stopped")

    monkeypatch.setattr(app, "stop", fake_stop)
    interaction = await invoke(app, "quit", owner)
    assert interaction.texts == [texts.STOPPING]
    assert events == ["stopped"]
