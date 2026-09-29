import asyncio
import logging
import os
import sys

from .bot import Bot
from .config import TOKEN
from .console import Console


def build_console(bot: Bot) -> Console:
    """Interface terminal du bot (tableau des requêtes + ligne de commande)."""
    return Console(bot)


async def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN manquant (voir .env.example)")

    # Les logs INFO de discord.py passeraient au travers de l'interface
    # plein écran : on ne garde que les avertissements et les erreurs.
    logging.getLogger("discord").setLevel(logging.WARNING)

    bot = Bot()
    console = build_console(bot)
    bot.console = console  # bot.note() écrit dans le panneau des sorties
    console.start(asyncio.get_running_loop())

    try:
        async with bot:
            await bot.start(TOKEN)
    finally:  # /quit, Ctrl-C ou crash : on passe toujours ici
        await console.stop()  # rend le terminal avant le résumé de session
        bot.shutdown()


def run() -> None:
    try:
        asyncio.run(main())  # 1er Ctrl-C : annule main() proprement
    except KeyboardInterrupt:
        print("\nCtrl-C reçu, bot arrêté.")
    # L'interface a quitté l'écran alterné : on ferme sans attendre.
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    run()
