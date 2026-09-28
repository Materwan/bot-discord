"""Outil de lecture de fichiers pour l'agent."""

import os
from pathlib import Path
from pypdf import PdfReader

from .base import BaseTool, ToolLevel
from bot_discord.config import UPLOADS_DIR, ALLOWED_EXTENSIONS


class ReadFileTool(BaseTool):
    """Lit le contenu d'un fichier précédemment envoyé par l'utilisateur."""

    name = "read_file"
    description = "Lit le contenu d'un fichier précédemment envoyé par l'utilisateur. Args: filename (str): Le nom du fichier à lire."
    level = ToolLevel.READ

    async def execute(self, filename: str) -> str:
        # Sécurité : on ne garde que le nom du fichier pour éviter le path traversal
        safe_name = os.path.basename(filename)
        file_path = UPLOADS_DIR / safe_name

        if not file_path.exists():
            return f"Erreur : Le fichier '{filename}' est introuvable."

        ext = file_path.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return f"Erreur : L'extension {ext} n'est pas autorisée."

        try:
            if ext == ".pdf":
                reader = PdfReader(file_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text if text.strip() else "Le PDF est vide ou ne contient pas de texte extractible."
            else:
                # Fichiers texte (.md, .py, .c, .h)
                return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Erreur lors de la lecture du fichier : {str(e)}"