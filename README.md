# 🤖 AI Discord Bot (Agno + Ollama)

Ce projet est un bot Discord intelligent propulsé par l'agent **Agno** et le modèle LLM **Ollama**. Il est conçu pour être un assistant personnel capable de mémoriser des informations sur les utilisateurs, de gérer une mémoire contextuelle par salon et d'interagir avec des outils externes.

## ✨ Fonctionnalités

- **🧠 Mémoire Personnalisée** : Le bot peut retenir des informations spécifiques sur chaque utilisateur (préférences, faits) via des commandes dédiées.
- **📁 Lecture de Fichiers** : Capacité d'analyser des pièces jointes envoyées dans les messages (`.md`, `.pdf`, `.py`, `.c`, `.h`).
- **💬 Mémoire de Salon** : Le bot peut mémoriser des faits importants propres à un salon spécifique pour maintenir le contexte.
- **🛠️ Système d'Outils (Tool Use)** : L'agent peut décider d'appeler des outils (météo, lecture de fichiers, mémoire) pour répondre précisément aux requêtes.
- **🛡️ Système d'Autorisation** : Un niveau de sécurité configurable (`AUTO_AUTHORISATION`) permet au propriétaire du bot de valider via DM les actions sensibles avant qu'elles ne soient exécutées.
- **🔐 Whitelist** : Le bot ne répond qu'aux IDs autorisés, stockés dans `src/bot_discord/data/whitelist.json` (le propriétaire reste toujours autorisé).
- **🧠 Notes Utilisateurs** : À chaque message, le bot analyse l'auteur et les personnes citées, sauvegarde automatiquement les faits utiles et fait évoluer un **niveau de relation (0-100)** — qui baisse quand on lui parle mal. Tout est persisté dans `user_notes.json`.
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
- `/remember <info>` : Demande au bot de retenir une information sur vous (note **immuable**, le modèle ne peut pas l'effacer).
- `/forget` : Demande au bot d'effacer tout ce qu'il sait sur vous (notes et niveau de relation).

### Commandes Administrateur (Propriétaire uniquement)
- `/set_auth <0|1|2>` : Modifie le niveau d'autorisation automatique des outils.
    - **0** : Toutes les actions sensibles demandent une confirmation par DM.
    - **1** : Les outils de base (comme la lecture de fichiers) sont automatiques.
    - **2** : Presque tous les outils sont automatiques.
- `/whitelist [add|remove|list] <user_id>` : Gère la whitelist (IDs autorisés à obtenir une réponse).
    - `add <user_id>` / `remove <user_id>` : ajoute ou retire un ID.
    - `list` (ou sans argument) : affiche les IDs autorisés.

La même commande est disponible dans le **terminal** (`/whitelist add 123456789`), sans contrôle du propriétaire.

## 🔐 Whitelist

Le bot ignore silencieusement les messages de toute personne absente de `src/bot_discord/data/whitelist.json` (format : liste d'IDs, ex. `[123, 456]`).

- Une whitelist **vide** verrouille le bot : seul le propriétaire (`BOT_OWNER_ID`) obtient des réponses.
- Le propriétaire est **toujours** autorisé, même hors whitelist.
- Ajouter / retirer un ID persiste immédiatement dans le JSON.

## 🧠 Notes utilisateurs et niveau de relation

Tout est stocké dans `src/bot_discord/data/user_notes.json`, par utilisateur :

```json
{
  "123456789": {
    "immutable": ["Notes écrites par le propriétaire via /remember"],
    "model_editable": ["Faits découverts automatiquement par le bot"],
    "relationship": 62
  }
}
```

**À chaque message**, après avoir répondu, le bot :

1. détermine **l'auteur** et les **personnes citées** (mentions `<@id>` et noms écrits en clair) ;
2. injecte leurs informations (notes + relation) dans le prompt système de la réponse suivante ;
3. lance une passe d'analyse (agent dédié, sortie JSON) qui :
   - sauvegarde automatiquement les **faits utiles** (`model_editable`), sans doublon ni injection possible sur un ID non cité ;
   - évalue le **ton de l'auteur** : `friendly` (+4), `polite` (+2), `neutral` (0), `rude` (-12), `hostile` (-25) ;
4. applique le delta au **niveau de relation (0-100)** de l'auteur.

**Filet de sécurité** : les insultes (« connard », « ta gueule », etc.) sont aussi détectées localement, donc la relation baisse même si le modèle rate le ton.

- `relationship = 0` : relation inexistante ou très mauvaise — `100` : excellente relation.
- Le niveau de relation est affiché au modèle (`Niveau de relation : 62/100 — bonne`), ce qui module son attitude.
- `/forget` remet la fiche à zéro (notes **et** relation).
- `AUTO_NOTES=0` dans le `.env` désactive l'appel LLM d'extraction (la détection locale des insultes continue de faire évoluer la relation).

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
