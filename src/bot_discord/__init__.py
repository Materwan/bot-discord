"""Paquet principal du bot Discord.

Les sous-modules sont importés paresseusement (voir __getattr__) : un import
en eager provoquait des cycles (bot_discord -> main -> bot -> agent ->
bot_discord.config), selon l'ordre dans lequel on importe les paquets.
"""

__all__ = [
    "main",
    "bot",
    "config",
    "console",
    "logger",
    "stats",
    "views",
    "dashboard",
]


def __getattr__(name: str):
    if name in __all__:
        import importlib

        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
