import time

import discord
from ollama import AsyncClient

from .config import LOG_FILE, MEMORY_FILE, MEMORY_SIZE, MODEL, load_prompt
from .logger import JsonlLogger
from .memory import Memory
from .stats import SessionStats


def decouper(texte: str, taille: int = 2000) -> list[str]:
    return [texte[i : i + taille] for i in range(0, len(texte), taille)]


class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.ai = AsyncClient()  # http://localhost:11434 par défaut
        self.memory = Memory(MEMORY_FILE, MEMORY_SIZE)
        self.logger = JsonlLogger(LOG_FILE)
        self.stats = SessionStats()
        self.logger.log("start", model=MODEL)

    async def on_ready(self):
        print(f"Connecté en tant que {self.user} (modèle : {MODEL})")
        self.logger.log("ready", user=str(self.user))

    async def on_message(self, message: discord.Message):
        if message.author.bot or self.user not in message.mentions:
            return

        prompt = (
            message.content.replace(f"<@{self.user.id}>", "")
            .replace(f"<@!{self.user.id}>", "")
            .strip()
        )
        if not prompt:
            return

        channel_id = message.channel.id
        user_content = f"{message.author.display_name} : {prompt}"
        messages = [
            {"role": "system", "content": load_prompt()},
            *self.memory.get(channel_id),
            {"role": "user", "content": user_content},
        ]

        start = time.perf_counter()
        try:
            async with message.channel.typing():
                resp = await self.ai.chat(model=MODEL, messages=messages)
        except Exception as e:
            print(f"Erreur Ollama : {e}")
            self.logger.log("error", channel_id=channel_id, error=repr(e))
            await message.reply("Désolé, je n'ai pas réussi à générer une réponse.")
            return

        reponse = resp.message.content or "..."
        prompt_tokens = resp.prompt_eval_count or 0
        completion_tokens = resp.eval_count or 0

        self.stats.add(prompt_tokens, completion_tokens)
        self.memory.add_exchange(channel_id, user_content, reponse)
        self.logger.log(
            "message",
            channel_id=channel_id,
            guild_id=message.guild.id if message.guild else None,
            author_id=message.author.id,
            author=message.author.display_name,
            model=MODEL,
            prompt=prompt,
            response=reponse,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_s=round(time.perf_counter() - start, 2),
        )

        morceaux = decouper(reponse)
        await message.reply(morceaux[0])
        for morceau in morceaux[1:]:
            await message.channel.send(morceau)

    def shutdown(self) -> None:
        """Sauvegarde finale + résumé de session (appelé quel que soit le mode d'arrêt)."""
        self.memory.save()
        self.logger.log(
            "stop",
            requests=self.stats.requests,
            prompt_tokens=self.stats.prompt_tokens,
            completion_tokens=self.stats.completion_tokens,
        )
        print(self.stats.summary())
