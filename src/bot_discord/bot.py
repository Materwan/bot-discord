import asyncio
import re
import time
import traceback

import discord
from ollama import AsyncClient

from .config import (
    ALLOWED_BOT_IDS,
    LOG_FILE,
    MEMORY_FILE,
    MEMORY_SIZE,
    MODEL,
    NOTES_FILE,
    find_user_id,
    load_prompt,
    load_user_instructions,
)
from .logger import JsonlLogger
from .memory import Memory
from .stats import SessionStats
from .users import UserNotes

REMEMBER_PREFIX = "/remember"
FORGET_CMD = "/forget"
MAX_NOTE_LENGTH = 300
MAX_OTHERS = 3  # nombre max d'autres personnes injectées dans le prompt
MAX_MESSAGE_LENGTH = 2000  # limite Discord
MIN_NAME_LENGTH = 3  # évite les faux positifs sur les pseudos très courts

INFERIOR_BOT_ID = 1550112364592898048
INFERIOR_BOT_REPLY = "Je ne répond pas au IA inférieur à moi."

MENTION_RE = re.compile(r"(?<![<\w])@(\w[\w'-]*(?: \w[\w'-]*){0,2})")

TYPING_TIMEOUT = 2  # secondes sans événement "typing" => la personne a arrêté
MAX_TYPING_WAIT = 60  # on ne bloque jamais plus longtemps
EDIT_GRACE = 2  # secondes sans modification avant de considérer le message comme final


def decouper(texte: str, taille: int = MAX_MESSAGE_LENGTH) -> list[str]:
    return [texte[i : i + taille] for i in range(0, len(texte), taille)]


class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        allowed = discord.AllowedMentions(
            users=True,  # pings d'utilisateurs autorisés
            roles=False,  # pas de @role
            everyone=False,  # pas de @everyone / @here
            replied_user=True,  # la réponse (message.reply) ping l'auteur
        )
        super().__init__(intents=intents, allowed_mentions=allowed)

        self.ai = AsyncClient()  # http://localhost:11434 par défaut
        self.memory = Memory(MEMORY_FILE, MEMORY_SIZE)
        self.user_notes = UserNotes(NOTES_FILE)
        self.logger = JsonlLogger(LOG_FILE)
        self.stats = SessionStats()
        self.logger.log("start", model=MODEL)

        # (channel_id, user_id) -> dernier "typing" ; message_id -> dernière modification
        self._typing: dict[tuple[int, int], float] = {}
        self._edited: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Construction du prompt
    # ------------------------------------------------------------------
    def describe_user(self, user: discord.abc.User, role: str) -> str:
        instructions = load_user_instructions(user.id)
        notes = self.user_notes.get(user.id)
        if not instructions and not notes:
            return ""
        lines = [f"Informations sur {user.display_name} ({role}) :"]
        if instructions:
            lines.append(instructions)
        if notes:
            lines.append(
                "Ce qu'on t'a demandé de retenir :\n"
                + "\n".join(f"- {n}" for n in notes)
            )
        return "\n".join(lines)

    def has_info(self, user: discord.abc.User) -> bool:
        return bool(load_user_instructions(user.id) or self.user_notes.get(user.id))

    def find_related_users(self, message: discord.Message, text: str) -> list:
        """Personnes mentionnées ou citées par leur nom, autres que l'auteur et le bot."""
        found: dict[int, discord.abc.User] = {}

        # 1. Mentions explicites (@Paul)
        for u in message.mentions:
            if u not in (self.user, message.author) and not u.bot:
                found[u.id] = u

        # 2. Noms écrits sans mention (« que penses-tu de Paul ? »)
        if message.guild:
            for m in message.guild.members:
                if m.bot or m == message.author or m.id in found:
                    continue
                name = m.display_name
                if len(name) < MIN_NAME_LENGTH:
                    continue
                if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
                    found[m.id] = m

        # On ne garde que ceux pour qui on a quelque chose à dire, puis on limite
        return [u for u in found.values() if self.has_info(u)][:MAX_OTHERS]

    def build_system(self, author: discord.abc.User, others=()) -> str:
        parts = [
            load_prompt(),
            self.describe_user(author, "la personne qui te parle"),
            *(
                self.describe_user(u, "une autre personne, qui ne te parle pas")
                for u in others
            ),
        ]
        return "\n\n".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # Texte : extraction et pings
    # ------------------------------------------------------------------
    def extract_prompt(self, message: discord.Message) -> str:
        return (
            message.content.replace(f"<@{self.user.id}>", "")
            .replace(f"<@!{self.user.id}>", "")
            .strip()
        )

    def resolve_mentions(self, message: discord.Message, prompt: str) -> str:
        """Remplace les mentions <@id> des autres personnes par leur nom."""
        for u in message.mentions:
            if u != self.user:
                prompt = prompt.replace(f"<@{u.id}>", u.display_name).replace(
                    f"<@!{u.id}>", u.display_name
                )
        return prompt

    def ajouter_pings(self, texte: str) -> str:
        """Transforme « @Paul » en <@id> grâce à find_user_id."""

        def remplacer(mo: re.Match) -> str:
            mots = mo.group(1).split(" ")
            # On essaie d'abord le nom le plus long, puis on raccourcit
            for n in range(len(mots), 0, -1):
                user_id = find_user_id(" ".join(mots[:n]))
                if user_id and user_id != self.user.id:
                    reste = " ".join(mots[n:])
                    return f"<@{user_id}>" + (f" {reste}" if reste else "")
            return mo.group(0)  # nom inconnu : on laisse le texte tel quel

        return MENTION_RE.sub(remplacer, texte)

    # ------------------------------------------------------------------
    # Attente que l'auteur ait fini d'écrire / modifier
    # ------------------------------------------------------------------
    async def wait_until_not_typing(self, channel, user) -> None:
        key = (channel.id, user.id)
        deadline = time.monotonic() + MAX_TYPING_WAIT
        while time.monotonic() < deadline:
            last = self._typing.get(key)
            if last is None or time.monotonic() - last > TYPING_TIMEOUT:
                return
            await asyncio.sleep(1)

    async def settle(self, message: discord.Message) -> discord.Message | None:
        """Attend que l'auteur ait fini d'écrire et de modifier, puis renvoie
        la version à jour du message (None s'il a été supprimé)."""
        # Message vide : on laisse un délai pour qu'il soit complété
        if not self.extract_prompt(message):
            self._edited.setdefault(message.id, time.monotonic())

        await self.wait_until_not_typing(message.channel, message.author)
        while True:
            last = self._edited.get(message.id)
            if last is None or time.monotonic() - last > EDIT_GRACE:
                break
            await asyncio.sleep(1)

        self._edited.pop(message.id, None)
        try:
            return await message.channel.fetch_message(message.id)
        except discord.NotFound:
            return None

    # ------------------------------------------------------------------
    # Événements Discord
    # ------------------------------------------------------------------
    async def on_ready(self):
        print(f"Connecté en tant que {self.user} (modèle : {MODEL})")
        self.logger.log("ready", user=str(self.user))

    async def on_typing(self, channel, user, when):
        self._typing[(channel.id, user.id)] = time.monotonic()

    async def on_message_edit(self, before, after):
        self._edited[after.id] = time.monotonic()
        # Cas : le message n'avait pas la mention du bot, il l'a maintenant
        if self.user in after.mentions and self.user not in before.mentions:
            await self.on_message(after)

    async def on_message(self, message: discord.Message):
        if self.user not in message.mentions or message.author == self.user:
            return
        if message.author.bot and message.author.id not in ALLOWED_BOT_IDS:
            return
        if message.author.id == INFERIOR_BOT_ID:
            await message.reply(INFERIOR_BOT_REPLY)
            return

        message = await self.settle(message)
        if message is None or self.user not in message.mentions:
            return

        prompt = self.extract_prompt(message)
        if not prompt:
            return
        self._typing.pop((message.channel.id, message.author.id), None)

        if await self.handle_command(message, prompt):
            return
        await self.answer(message, self.resolve_mentions(message, prompt))

    # ------------------------------------------------------------------
    # Commandes /remember et /forget
    # ------------------------------------------------------------------
    async def handle_command(self, message: discord.Message, prompt: str) -> bool:
        """Exécute une commande utilisateur. Renvoie True si le message en était une."""
        low = prompt.lower()
        if low.startswith(REMEMBER_PREFIX):
            note = prompt[len(REMEMBER_PREFIX) :].strip()[:MAX_NOTE_LENGTH]
            self.user_notes.add(message.author.id, note)
            await message.reply("C'est noté !")
            return True
        if low == FORGET_CMD:
            self.user_notes.clear(message.author.id)
            await message.reply("J'ai tout oublié te concernant.")
            return True
        return False

    # ------------------------------------------------------------------
    # Génération de la réponse
    # ------------------------------------------------------------------
    async def answer(self, message: discord.Message, prompt: str) -> None:
        channel_id = message.channel.id
        user_content = f"{message.author.display_name} : {prompt}"
        others = self.find_related_users(message, prompt)
        messages = [
            {"role": "system", "content": self.build_system(message.author, others)},
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

        await self.send_reply(message, reponse)

    async def send_reply(self, message: discord.Message, reponse: str) -> None:
        morceaux = [self.ajouter_pings(m) for m in decouper(reponse)]
        await self.wait_until_not_typing(message.channel, message.author)
        await message.reply(morceaux[0])
        for morceau in morceaux[1:]:
            await message.channel.send(morceau)

    # ------------------------------------------------------------------
    # Erreurs et arrêt
    # ------------------------------------------------------------------
    async def on_error(self, event_method, *args, **kwargs):
        self.logger.log("exception", event=event_method, trace=traceback.format_exc())
        traceback.print_exc()

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
