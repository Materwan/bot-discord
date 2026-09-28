"""Outil météo pour l'agent."""

import asyncio
from .base import BaseTool, ToolLevel


class WeatherTool(BaseTool):
    """Récupère la météo actuelle pour une ville donnée."""

    name = "get_weather"
    description = "Récupère la météo actuelle pour une ville donnée. Args: location (str): La ville pour laquelle obtenir la météo (ex: Paris, Tokyo)."
    level = ToolLevel.FREE

    async def execute(self, location: str) -> str:
        # Simulation d'un appel API
        await asyncio.sleep(5)
        return f"Il fait actuellement 22°C et themed soleil à {location}."