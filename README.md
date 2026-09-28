# 🤖 AI Discord Bot (Agno + Ollama)

Ce projet est un bot Discord intelligent propulsé par l'agent **Agno** et le modèle LLM **Ollama**. Il est conçu pour être un assistant personnel capable de mémoriser des informations sur les utilisateurs, de gérer une mémoire contextuelle par salon et d'interagir avec des outils externes.

## ✨ Fonctionnalités

- **🧠 Mémoire Personnalisée** : Le bot peut retenir des informations spécifiques sur chaque utilisateur (préférences, faits) via des commandes dédiées.
- **📁 Lecture de Fichiers** : Capacité d'analyser des pièces jointes envoyées dans les messages (`.md`, `.pdf`, `.py`, `.c`, `.h`).
- **💬 Mémoire de Salon** : Le bot peut mémoriser des faits importants propres à un salon spécifique pour maintenir le contexte.
- **🛠️ Système d'Outils (Tool Use)** : L'agent peut décider d'appeler des outils (météo, lecture de fichiers, mémoire) pour répondre précisément aux requêtes.
- **🛡️ Système d'Autorisation** : Un niveau de sécurité configurable (`AUTO_AUTHORISATION`) permet au propriétaire du bot de valider via DM les actions sensibles avant qu'elles ne soient exécutées.
- **📊 Dashboard Terminal** : Un moniteur en temps réel dans la console affiche les requêtes actives et leur phase de traitement (Processing, Tool Calling, Answering).

## 🚀 Installation

### Prérequis
- **Python 3.10+**
- **Ollama** installé et configuré avec le modèle souhaité (par défaut `gemma4:31b-cloud`).
- Un **Token de Bot Discord** (créé via le [Discord Developer Portal](https://discord.com/developers/applications)).

### Mise en place
1. Clonez le dépôt :
   ```bash
   git clone <url-du-depot>
   cd bot-discord
   ```

2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

3. Configurez les variables d'environnement dans un fichier `.env` à la racine :
   ```env
   DISCORD_BOT_TOKEN=votre_token_ici
   MODEL=gemma4:31b-cloud
   ```

4. Lancez le bot :
   ```bash
   python -m src.bot_discord.bot
   ```

## 🛠️ Utilisation

### Commandes Utilisateurs
- `/remember <info>` : Demande au bot de retenir une information sur vous.
- `/forget` : Demande au bot d'effacer tout ce qu'il sait sur vous.

### Commandes Administrateur (Propriétaire uniquement)
- `/set_auth <0|1|2>` : Modifie le niveau d'autorisation automatique des outils.
    - **0** : Toutes les actions sensibles demandent une confirmation par DM.
    - **1** : Les outils de base (comme la lecture de fichiers) sont automatiques.
    - **2** : Presque tous les outils sont automatiques.

## 🔒 Sécurité et Autorisations

Le bot utilise un système de niveaux pour protéger les données :
- **Niveau 0 (Sûr)** : Exécution immédiate (ex: Météo).
- **Niveau 1 (Données)** : Lecture de fichiers.
- **Niveau 2 (Système)** : Modification de la mémoire utilisateur ou du salon.

Si l'outil demandé a un niveau supérieur à `AUTO_AUTHORISATION`, le propriétaire reçoit un DM avec des boutons **Accepter** ou **Refuser**.

## 📂 Structure du Projet
- `src/bot_discord/` : Code source principal.
    - `bot.py` : Orchestration Discord et agent.
    - `tools.py` : Définition des outils de l'IA.
    - `memory.py` : Gestion de la mémoire persistante.
    - `state.py` : Gestion de l'état du bot (auth level).
    - `views.py` : Interfaces UI Discord (boutons de confirmation).
- `config/` : Fichiers de configuration et instructions du prompt.
- `tests/` : Suite de tests unitaires.
