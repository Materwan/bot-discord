import json

from prompt_toolkit.document import Document

from clara.console.app import Console
from clara.console.completer import CommandCompleter
from clara.console.dashboard import Dashboard
from clara.tracking import Phase, RequestTracker, summarize


def completions(app, text: str) -> list[str]:
    return [c.text for c in CommandCompleter(app).get_completions(Document(text), None)]


def test_command_names_complete_with_or_without_slash(app):
    assert completions(app, "/wh") == ["/whitelist"]
    assert completions(app, "he") == ["/help"]
    assert len(completions(app, "")) == len(app.commands.names)


def test_arguments_complete_with_actions_names_and_ids(app, settings):
    settings.known_users_file.write_text(json.dumps({"Paul": 2000}), encoding="utf-8")
    app.whitelist.add(42)
    assert completions(app, "/whitelist ") == ["add", "remove", "list"]
    assert completions(app, "/whitelist add ") == ["Paul", "42"]
    assert completions(app, "/relation -a ") == ["0", "50", "100"]
    assert completions(app, "/auth Paul ") == ["0", "1", "2", "3", "4", "5"]
    assert completions(app, "/help /t") == ["/token"]
    assert completions(app, "/nope ") == []


def test_tracker_summaries_and_versions():
    tracker = RequestTracker()
    tracker.start(1, "Erwan", "ligne\n" + "x" * 60)
    assert tracker.active()[0].summary.startswith("ligne x") and tracker.active()[0].summary.endswith("...")
    version = tracker.version
    tracker.set_phase(1, Phase.PROCESSING)  # no change
    assert tracker.version == version
    tracker.set_phase(1, Phase.TOOL_CALLING)
    tracker.finish(1)
    tracker.finish(1)
    assert tracker.version == version + 2
    assert summarize("court") == "court"


def test_dashboard_renders_only_on_change():
    tracker = RequestTracker()
    dashboard = Dashboard(tracker)
    empty = dashboard.render(80)
    assert "Aucune requête active" in empty
    assert dashboard.render(80) is empty  # cached

    tracker.start(1, "Erwan", "question")
    rendered = dashboard.render(80)
    assert "Erwan" in rendered and "Processing" in rendered


async def test_console_runs_lines_as_the_owner(app):
    console = Console(app)
    await console.run_line("/whitelist add 42")
    assert 42 in app.whitelist
    await console.run_line("/remember note du propriétaire")
    assert app.user_notes.notes(app.settings.owner_id) == ["note du propriétaire"]
    assert any("ajouté" in line for line in console._output_lines)
