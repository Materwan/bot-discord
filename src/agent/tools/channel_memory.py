"""Outil de mémoire de salon pour l'agent."""

from .base import BaseTool, ToolLevel
from core import Memory


class SaveSalonMemoryTool(BaseTool):
    """Enregistre un fait important concernant le salon actuel."""

    name = "save_salon_memory"
    description = "Enregistre un fait important concernant le salon actuel pour s'en souvenir plus tard. Args: fact (str): Le fait ou l'information à mémoriser pour le salon. channel_id (int): L'ID du salon concerné."
    level = ToolLevel.WRITE

    def __init__(self, memory: Memory):
        self.memory = memory

    async def execute(self, fact: str, channel_id: int) -> str:
        self.memory.add_memory(channel_id, fact)
        return f"Information mémorisée pour le salon {channel_id} : {fact}"