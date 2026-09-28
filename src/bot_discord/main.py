import asyncio
import os
import sys

from .bot import Bot
from .config import TOKEN
from .console import Console


async def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN manquant (voir .env.example)")

    bot = Bot()

    async def cmd_token() -> None:
        print(bot.stats.summary())

    async def cmd_quit() -> None:
        print("Arrêt du bot...")
        await bot.close()  # fait sortir bot.start()

    Console({"/token": cmd_token, "/quit": cmd_quit}).start(asyncio.get_running_loop())

    try:
        async with bot:
            await bot.start(TOKEN)
    finally:  # /quit, Ctrl-C ou crash : on passe toujours ici
        bot.shutdown()


def run() -> None:
    try:
        asyncio.run(
            main()
        )  # 1er Ctrl-C : annule main() proprement, puis lève KeyboardInterrupt
    except KeyboardInterrupt:
        print("\nCtrl-C reçu, bot arrêté.")
    # Le thread console peut rester bloqué sur input() : on quitte sans attendre
    # (tout est déjà sauvegardé dans bot.shutdown()).
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    run()
