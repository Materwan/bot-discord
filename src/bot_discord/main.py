import asyncio
import os
import sys

from .bot import Bot
from .config import TOKEN
from .console import Console
from .stats import SessionStats


def build_console(bot: Bot) -> Console:
    async def cmd_token(args: list[str]) -> None:
        if not args:
            print(bot.stats.summary())
        elif args == ["-a"]:
            # Lecture du fichier hors de la boucle asyncio (peut être gros)
            entries = await asyncio.to_thread(lambda: list(bot.logger.read("message")))
            print(SessionStats.from_log(entries).summary())
        else:
            print("Usage : /token (session en cours) | /token -a (total depuis les logs)")

    async def cmd_quit(args: list[str]) -> None:
        print("Arrêt du bot...")
        await bot.close()  # fait sortir bot.start()

    async def cmd_whitelist(args: list[str]) -> None:
        # Même logique que la commande Discord, sans contrôle du propriétaire
        print(bot.whitelist_reply(args, markdown=False))

    return Console(
        {"/token": cmd_token, "/quit": cmd_quit, "/whitelist": cmd_whitelist}
    )


async def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN manquant (voir .env.example)")

    bot = Bot()
    build_console(bot).start(asyncio.get_running_loop())

    try:
        async with bot:
            await bot.start(TOKEN)
    finally:  # /quit, Ctrl-C ou crash : on passe toujours ici
        bot.shutdown()


def run() -> None:
    try:
        asyncio.run(main())  # 1er Ctrl-C : annule main() proprement
    except KeyboardInterrupt:
        print("\nCtrl-C reçu, bot arrêté.")
    # Le thread console peut rester bloqué sur input() : on quitte sans attendre
    # (tout est déjà sauvegardé dans bot.shutdown()).
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    run()
