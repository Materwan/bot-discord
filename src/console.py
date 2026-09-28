import asyncio
import threading
from typing import Awaitable, Callable

Handler = Callable[[], Awaitable[None]]


class Console:
    """Lit les commandes tapées dans le terminal (thread daemon, n'empêche pas l'arrêt)."""

    def __init__(self, commands: dict[str, Handler]):
        self.commands = commands

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        threading.Thread(target=self._run, args=(loop,), daemon=True).start()

    def _run(self, loop: asyncio.AbstractEventLoop) -> None:
        print("Commandes : " + ", ".join(self.commands))
        while True:
            try:
                line = input()
            except EOFError:  # stdin fermé (ex. lancé en service) : on arrête juste la console
                return
            cmd = line.strip().lower()
            if not cmd:
                continue
            handler = self.commands.get(cmd)
            if handler is None:
                print(f"Commande inconnue. Disponibles : {', '.join(self.commands)}")
                continue
            asyncio.run_coroutine_threadsafe(handler(), loop)
