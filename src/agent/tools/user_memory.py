"""Outils de mémoire utilisateur pour l'agent."""

from .base import BaseTool, ToolLevel
from core import UserNotes


class RememberUserInfoTool(BaseTool):
    """Mémorise une information importante sur un utilisateur."""

    name = "remember_user_info"
    description = "Mémorise une information importante sur un utilisateur. Args: info (str): Le fait ou la préférence à retenir. user_id (int): L'ID de l'utilisateur concerné."
    level = ToolLevel.WRITE

    def __init__(self, user_notes: UserNotes):
        self.user_notes = user_notes

    async def execute(self, info: str, user_id: int) -> str:
        self.user_notes.add(user_id, info)
        return f"C'est noté pour l'utilisateur {user_id} : {info}"


class ForgetUserInfoTool(BaseTool):
    """Efface toutes les informations mémorisées sur un utilisateur."""

    name = "forget_user_info"
    description = "Efface toutes les informations mémorisées sur un utilisateur. Args: user_id (int): L'ID de l'utilisateur concerné."
    level = ToolLevel.WRITE

    def __init__(self, user_notes: UserNotes):
        self.user_notes = user_notes

    async def execute(self, user_id: int) -> str:
        self.user_notes.clear(user_id)
        return f"Toutes les informations concernant l'utilisateur {user_id} ont été effacées."