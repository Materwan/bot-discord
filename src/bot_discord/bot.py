import asyncio
import re
import time
import traceback
from pathlib import Path

import discord

from .config import (
    ALLOWED_BOT_IDS,
    LOG_FILE,
    MEMORY_FILE,
    NOTES_FILE,
    UPLOADS_DIR,
    ALLOWED_EXTENSIONS,
    BOT_OWNER_ID,
    MODEL,
)
from .logger import JsonlLogger
from .stats import SessionStats
from .console import Console
from .dashboard import TerminalDashboard
from .views import ToolAuthView

from core import Memory, UserNotes, BotState, RequestTracker
from agent import create_agent, build_system_prompt, find_related_users, extract_prompt, resolve_mentions, ajouter_pings

REMEMBER_PREFIX = "/remember"
FORGET_CMD = "/forget"
MAX_NOTE_LENGTH = 300
MAX_MESSAGE_LENGTH = 2000  # limite Discord

INFERIOR_BOT_ID = 1550112364592898048
INFERIOR_BOT_REPLY = "Je ne répond pas au IA inférieur à moi."

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

        # Création automatique du dossier uploads pour éviter les FileNotFoundError
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # Core services
        self.memory = Memory(MEMORY_FILE)
        self.user_notes = UserNotes(NOTES_FILE)
        self.logger = JsonlLogger(LOG_FILE)
        self.stats = SessionStats()
        self.logger.log("start", model=MODEL)

        # Dashboard et Tracker
        self.tracker = RequestTracker()
        self.dashboard = TerminalDashboard(self.tracker)

        # État et Autorisation
        self.state = BotState()

        # Initialisation de l'Agent Agno
        self.agent = create_agent(
            bot=self,
            memory=self.memory,
            user_notes=self.user_notes,
            state=self.state,
            tracker=self.tracker,
        )

        # (channel_id, user_id) -> dernier "typing" ; message_id -> dernière modification
        self._typing: dict[tuple[int, int], float] = {}
        self._edited: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Construction du prompt (délégué à agent.prompts)
    # ------------------------------------------------------------------
    def build_prompt_context(self, message: discord.Message, prompt: str, uploaded_files: list[str] = None) -> str:
        """Construit le contexte complet pour l'agent."""
        channel_id = message.channel.id
        author = message.author

        # Mémoires du salon
        memories = self.memory.get(channel_id)

        # Utilisateurs liés
        others = find_related_users(message, prompt, self.user, self.user_notes)

        # Construction du prompt système via agent.prompts
        system_prompt = build_system_prompt(author, others, memories, self.user_notes)

        # Fichiers uploadés
        if uploaded_files:
            files_list = ", ".join(uploaded_files)
            system_prompt += f"\n\n[Système : L'utilisateur a envoyé les fichiers suivants : {files_list}. Tu peux utiliser l'outil `read_file` pour lire leur contenu.]"

        user_content = f"{author.display_name} : {prompt}"
        full_prompt = f"CONTEXTE ACTUEL :\n{system_prompt}\n\nMESSAGE :\n{user_content}"

        return full_prompt

    # ------------------------------------------------------------------
    # Texte : extraction et pions
    # ------------------------------------------------------------------
    def extract_prompt(self, message: discord.Message) -> str:
        return extract_prompt(message, self.user)

    def resolve_mentions(self, message: discord.Message, prompt: str) -> str:
        return resolve_mentions(message, prompt, self.user)

    def ajouter_pings(self, texte: str) -> str:
        from agent import find_user_id
        return ajouter_pings(texte, self.user, find_user_id)

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

        # Lancement du dashboard dans une tâche de fond
        self.loop.create_task(self.dashboard.run())

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

        # Gestion des pièces jointes
        uploaded_files = []
        if message.attachments:
            for attachment in message.attachments:
                ext = Path(attachment.filename).suffix.lower()
                if ext in ALLOWED_EXTENSIONS:
                    # On utilise l'ID du message pour éviter les collisions de noms
                    safe_filename = f"{message.id}_{attachment.filename}"
                    await attachment.save(UPLOADS_DIR / safe_filename)
                    uploaded_files.append(safe_filename)

        prompt = self.extract_prompt(message)
        if not prompt:
            return
        self._typing.pop((message.channel.id, message.author.id), None)

        if await self.handle_command(message, prompt):
            return
        await self.answer(message, self.resolve_mentions(message, prompt), uploaded_files)

    # ------------------------------------------------------------------
    # Commandes /remember et /forget
    # ------------------------------------------------------------------
    async def handle_command(self, message: discord.Message, prompt: str) -> bool:
        """Exécute une commande utilisateur. Renvoie True si le message en était une."""
        low = prompt.lower()

        # Commande /set_auth (Admin seulement)
        if low.startswith("/set_auth"):
            if message.author.id != BOT_OWNER_ID:
                return False  # On ignore si ce n'est pas le propriétaire

            parts = low.split()
            if len(parts) == 2 and parts[1].isdigit():
                level = int(parts[1])
                if 0 <= level <= 2:
                    self.state.set_auth_level(level)
                    await message.reply(f"Le niveau d'autorisation automatique a été fixé à {level}.")
                    return True

            await message.reply("Usage : `/set_auth <0|1|2>`")
            return True

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
    # Génération de la réponse via l'agent
    # ------------------------------------------------------------------
    async def answer(self, message: discord.Message, prompt: str, uploaded_files: list[str] = None) -> None:
        channel_id = message.channel.id

        # Lancement du tracking de la requête
        self.tracker.start_request(message.id, message.author.display_name, prompt)

        # Construction du prompt complet
        full_prompt = self.build_prompt_context(message, prompt, uploaded_files)

        start = time.perf_counter()
        try:
            async with message.channel.typing():
                # Phase : Processing
                self.tracker.update_phase(message.id, "Processing")

                # Utilisation de arun() pour l'exécution asynchrone de l'Agent Agno
                resp = await self.agent.arun(full_prompt)

                # Phase : Answering (juste avant l'envoi)
                self.tracker.update_phase(message.id, "Answering")
                reponse = resp.content or "..."
        except Exception as e:
            print(f"Erreur Agno : {e}")
            self.logger.log("error", channel_id=channel_id, error=repr(e))
            await message.reply("Désolé, je n'ai pas réussi à générer une réponse.")
            return
        finally:
            # Suppression de la requête du dashboard une fois terminée
            self.tracker.complete_request(message.id)

        # On ne peut pas facilement récupérer les tokens exacts depuis arun()
        # sans accéder aux détails du modèle, on met 0 par défaut pour les stats
        prompt_tokens = 0
        completion_tokens = 0
        self.stats.add(prompt_tokens, completion_tokens)

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
        self.logger.log("exception", event_method=event_method, trace=traceback.format_exc())
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