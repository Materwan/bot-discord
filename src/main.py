import os
import discord
from ollama import AsyncClient

from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("MODEL", "gemma4:31b-cloud")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
ai = AsyncClient()  # http://localhost:11434 par défaut


def decouper(texte, taille=2000):
    return [texte[i : i + taille] for i in range(0, len(texte), taille)]


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")


@bot.event
async def on_message(message):
    if message.author.bot or bot.user not in message.mentions:
        return

    prompt = (
        message.content.replace(f"<@{bot.user.id}>", "")
        .replace(f"<@!{bot.user.id}>", "")
        .strip()
    )
    if not prompt:
        return

    async with message.channel.typing():
        resp = await ai.chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un bot Discord sympa. Réponds en français, de façon concise.",
                },
                {"role": "user", "content": prompt},
            ],
        )

    reponse = resp["message"]["content"]
    morceaux = decouper(reponse)
    await message.reply(morceaux[0])
    for morceau in morceaux[1:]:
        await message.channel.send(morceau)


bot.run(os.environ.get("DISCORD_BOT_TOKEN"))
