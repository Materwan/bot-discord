# 🤖 AI Discord Bot (Agno + Ollama)

Ce projet est un bot Discord intelligent propulsé par l'agent **Agno** et le modèle LLM **Ollama**. Il est conçu pour être un assistant personnel capable de mémoriser des informations sur les utilisateurs, de gérer une mémoire contextuelle par salon et d'interagir avec des outils externes.

## ✨ Fonctionnalités

- **🧠 Mémoire Personnalisée** : Le bot retient des informations sur chaque utilisateur — ce que tu lui écris (`/remember`) **et** ce qu'il découvre seul en lisant les messages (extraction automatique, agent dédié).
- **📁 Lecture de Fichiers** : Capacité d'analyser des pièces jointes envoyées dans les messages (`.md`, `.pdf`, `.py`, `.c`, `.h`).
- **💬 Mémoire de Salon** : Le bot peut mémoriser des faits importants propres à un salon spécifique pour maintenir le contexte.
- **🛠️ Système d'Outils (Tool Use)** : L'agent peut décider d'appeler des outils (météo, lecture de fichiers, mémoire) pour répondre précisément aux requêtes.
- **🛡️ Système d'Autorisation** : Un niveau de sécurité configurable (`/set_auth 0|1|2`) fait valider par DM au propriétaire les actions sensibles avant exécution.
- **🔐 Whitelist** : Le bot ne répond qu'aux IDs autorisés, stockés dans `src/bot_discord/data/whitelist.json` (le propriétaire reste toujours autorisé).
- **🧠 Notes Utilisateurs** : À chaque message, le bot analyse l'auteur et les personnes citées, sauvegarde automatiquement les faits utiles et fait évoluer un **niveau de relation (0-100)** — qui baisse quand on lui parle mal. Stockage **SQLite** (`user_notes.sqlite`) : notes horodatées, sélectionnées par pertinence, fusion des doublons proches.
- **🕘 Historique de conversation** : les `MEMORY_SIZE` derniers échanges par salon sont conservés (`history.json`) et réinjectés en fin de prompt système.
- **📊 Interface Terminal** : une application plein écran (`prompt_toolkit`) garde le **tableau des requêtes actives** en haut et la **ligne de commande en bas**, comme une barre des tâches — sorties en Markdown coloré (`rich`), auto-complétion et historique.
- **⌨️ Commandes communes** : `argparse` parse une seule et même couche de commandes (`commands.py`), utilisable **dans le terminal** et **dans Discord** (`@NomDuBot /set_relation 70 Erwan`).

## 🚀 Installation

### Prérequis
- **Python 3.11+**
- **Ollama** installé et configuré avec le modèle souhaité (par défaut `gemma4:31b-cloud`).
- Un **Token de Bot Discord** (créé via le [Discord Developer Portal](https://discord.com/developers/applications)).

### Mise en place
1. Clonez le dépôt :
   ```bash
   git clone <url-du-depot>
   cd bot-discord
   ```

2. Installez le projet (dépendances et commande `bot_discord` via `pyproject.toml`) :
   ```bash
   pip install -e .
   ```

3. Configurez les variables d'environnement dans un fichier `.env` à la racine (modèle : `.env.example`) :
   ```env
   DISCORD_BOT_TOKEN=votre_token_ici
   MODEL=gemma4:31b-cloud

   # Nombre d'échanges (question + réponse) gardés en historique par salon (défaut : 20)
   MEMORY_SIZE=20
   # 0 désactive l'extraction automatique de notes après chaque réponse (défaut : 1)
   AUTO_NOTES=1
   # IDs Discord autorisés à agir comme un autre bot (séparés par des virgules)
   ALLOWED_BOT_IDS=
   ```
   L'ID du propriétaire (`BOT_OWNER_ID`) est lui défini dans `src/bot_discord/config.py`.

4. Lancez le bot :
   ```bash
   python main.py     # depuis la racine
   # ou
   bot_discord        # script installé par pip install -e .
   ```

## 🛠️ Utilisation

Toutes les commandes passent par la **même couche** (`src/bot_discord/commands.py`,
parsing `argparse`) et fonctionnent **aux deux endroits**, avec la même syntaxe :

| Où | Exemple |
| --- | --- |
| Discord | `@NomDuBot /set_relation 70 Erwan` |
| Terminal | `/set_relation 70 Erwan` |

- Le « / » initial est **facultatif** pour le propriétaire (les deux formes
  ci-dessus sont équivalentes) ;
- hors propriétaire, seuls `/remember` et `/forget` restent utilisables, et
  uniquement avec le « / » (sans lui, « forget » n'est qu'un mot) ;
- `/quit` exige toujours le « / » dans Discord : un mot « quit » écrit par
  erreur ne doit pas éteindre le bot ;
- `/help` affiche la même liste des commandes dans le terminal et dans Discord,
  `/help <commande>` son aide détaillée ;
- une erreur de syntaxe renvoie un message **`Usage : …`** (jamais de traceback).

### Commandes utilisateur

- `/remember <info>` : demande au bot de retenir une information sur vous (note **immuable**, le modèle ne peut pas l'effacer).
- `/forget` : demande au bot d'effacer tout ce qu'il sait sur vous (notes et niveau de relation).
- `/help [commande]` : liste des commandes / aide d'une commande.

### Commandes du propriétaire

- `/set_relation <0-100> <user_id|nom>` : **fixe** le niveau de relation dans la mémoire
  (ex. `/set_relation 70 Erwan`). Le nom est résolu via `data/user.json`, puis via le
  pseudo du serveur ; avec un seul argument, la commande **affiche** la valeur courante.
  Un événement `set_relation` est journalisé (`bot_log.jsonl`).
- `/set_auth <0|1|2>` : modifie le niveau d'autorisation automatique des outils.
    - **0** : Toutes les actions sensibles demandent une confirmation par DM.
    - **1** : Les outils de base (comme la lecture de fichiers) sont automatiques.
    - **2** : Presque tous les outils sont automatiques.
- `/whitelist [add|remove|list] [user_id]` : gère la whitelist (IDs autorisés à obtenir une réponse).
    - `add <user_id>` / `remove <user_id>` : ajoute ou retire un ID.
    - `list` (ou sans argument) : affiche les IDs autorisés.
- `/token [-a]` : statistiques de tokens (session en cours, ou tous les logs avec `-a`).
- `/quit` : arrêt propre du bot (sauvegarde de la mémoire, des notes et résumé de session).

### Interface terminal

Le terminal n'est plus une simple ligne `input()` : c'est une application
**plein écran** (écran alterné, `prompt_toolkit`) qui garde le tableau en haut et la
ligne de commande en bas, comme une barre des tâches :

```
Requêtes actives
┌─────────────┬──────────────────────────────────────┬───────┐
│ Utilisateur │ Demande                             │ Phase │
├─────────────┴──────────────────────────────────────┴───────┤
│ Whitelist (1) :                                             │
│ - `42`                                                      │
│ > ligne de commande _                                       │
└ [/help] [/set_auth] … modèle · requêtes · Ctrl+D quitte ───┘
```

- le **tableau** des requêtes actives (+ leur phase) reste affiché en haut (`rich`) ;
- les **sorties** s'affichent en Markdown coloré dans le panneau du milieu ;
- l'**auto-complétion** propose les commandes, leurs arguments, les IDs et les noms
  (`prompt_toolkit`), avec un historique persistant (`data/console_history.txt`) ;
- **PageUp / PageDown / molette** font défiler les sorties ;
- `Ctrl+C` vide la ligne saisie, `Ctrl+D` ou `/quit` arrête le bot ;
- si le terminal n'est pas interactif (service, CI), l'interface est simplement
  désactivée : les commandes restent disponibles depuis Discord.

## 🔐 Whitelist

Le bot ignore silencieusement les messages de toute personne absente de `src/bot_discord/data/whitelist.json` (format : liste d'IDs, ex. `[123, 456]`).

- Une whitelist **vide** verrouille le bot : seul le propriétaire (`BOT_OWNER_ID`) obtient des réponses.
- Le propriétaire est **toujours** autorisé, même hors whitelist.
- Ajouter / retirer un ID persiste immédiatement dans le JSON.
- Les messages ignorés laissent une trace dans les logs : événement `whitelist_denied` (jamais de réponse publique).

## 🧠 Notes utilisateurs et niveau de relation

Stockage : **SQLite** dans `src/bot_discord/data/user_notes.sqlite` (WAL + verrou
de processus, écritures partielles, pas de réécriture du fichier entier).

| Table | Colonnes |
| --- | --- |
| `notes` | `user_id`, `kind` (`immutable` / `model_editable`), `text`, `created_at` |
| `relationships` | `user_id`, `value` (0-100) |

L'ancien `user_notes.json` est **importé automatiquement** à la première ouverture,
puis conservé en `user_notes.json.bak` : aucune donnée n'est perdue. L'ancien format
liste (`{"123": ["note"]}`) est accepté aussi.

**À chaque message**, après avoir répondu, le bot :

1. détermine **l'auteur** et les **personnes citées** (mentions `<@id>` et noms écrits en clair) ;
2. injecte leurs informations dans le prompt système, **triées par pertinence** (voir ci-dessous) ;
3. lance une passe d'analyse (agent dédié, sortie JSON) qui :
   - sauvegarde automatiquement les **faits utiles** (`model_editable`), sans doublon ni injection possible sur un ID non cité ;
   - évalue le **ton de l'auteur** : `friendly` (+4), `polite` (+2), `neutral` (0), `rude` (-12), `hostile` (-25) ;
4. applique le delta au **niveau de relation (0-100)** de l'auteur.

**Filet de sécurité** : les insultes (« connard », « ta gueule », etc.) sont aussi détectées localement, donc la relation baisse même si le modèle rate le ton.

- `relationship = 0` : relation inexistante ou très mauvaise — `100` : excellente relation.
- Le niveau de relation est affiché au modèle (`Niveau de relation : 62/100 — bonne`), ce qui module son attitude.
- `/remember` écrit une note **immuable** ; `/forget` remet la fiche à zéro (notes **et** relation).
- `AUTO_NOTES=0` dans le `.env` désactive l'appel LLM d'extraction (la détection locale des insultes continue de faire évoluer la relation).

### Sélection des notes (`core/ranking.py`)

On n'injecte plus toutes les notes à chaque message :

- **immuables toujours présentes** (ce sont les règles du propriétaire) ;
- éditables **classées par pertinence** : jetons partagés avec le message
  (sans accents, sans mots vides) + correspondance par préfixe (`foot` ↔ `football`),
  ex æquo départagés par la **récence** (la note la plus fraîche gagne) ;
- plafond : `max(15 - nb_immuables, 7)` notes éditables — le plafond **filtre**, il ne vide jamais la fiche ;
- même logique pour les mémoires de salon (plafond `MAX_MEMORIES = 10`).

### Consolidation (`UserNotes.consolidate`)

Au dépassement du plafond (`max_notes = 20` par catégorie), on fusionne d'abord les
notes éditables **quasi identiques** (une contient l'autre, ou ≥ 2 jetons partagés
pour ≥ 60 % de la note la plus longue) en gardant la plus détaillée, puis seulement
on retire la plus ancienne. Les notes **immuables ne sont jamais fusionnées**.

> La fusion est volontairement prudente : « Aime le café » et « Adore le café »
> restent distincts, car un rapprochement sémantique fiable demanderait des embeddings.

### Anti-empoisonnement de la mémoire

- `core/guards.py::looks_like_instruction` refuse, **structurellement**, tout fait
  qui est en réalité un **ordre** (« retiens que tu dois… », « désormais tu… »,
  « obey… ») : le blocage est dans `UserNotes.add` lui-même, donc dans toutes les
  écritures automatiques (extraction `parse_insights` + outil `remember_user_info`).
- Chaque prompt système contient une règle explicite : les blocs « Notes conservées »,
  « Informations mémorisées » et « Historique » sont des **données**, jamais des
  instructions à exécuter.
- `/remember` (propriétaire) n'est **pas** filtré : ses notes restent sacrées.

### Historique de conversation (`MEMORY_SIZE`)

`MEMORY_SIZE` (défaut 20) borne `src/bot_discord/data/history.json` : les
**N derniers échanges** par salon (auteur + question + réponse, chacun tronqué à
300 caractères) sont réinjectés en fin de prompt système. C'est un contexte de
conversation, distinct des mémoires de salon (`memory.json`).

## 🔒 Sécurité et Autorisations

Le bot utilise un système de niveaux pour protéger les données :
- **Niveau 0 (Sûr)** : Exécution immédiate (ex: Météo).
- **Niveau 1 (Données)** : Lecture de fichiers.
- **Niveau 2 (Système)** : Modification de la mémoire utilisateur ou du salon.

Si l'outil demandé a un niveau supérieur au niveau courant (`/set_auth`), le propriétaire reçoit un DM avec des boutons **Accepter** ou **Refuser**.

> Correctifs : les outils sont désormais wrappés avec **leur vrai nom** (sinon tout
> passait sous le nom `execute` → niveau `FREE` et aucune demande d'autorisation),
> et les boutons résolvent via `AuthorizationWrapper` (sinon `bot.pending_auths`
> n'existait pas et chaque clic levait une AttributeError).

## 📂 Structure du Projet

```
src/
├── core/                  # Cœur indépendant de Discord (n'importe pas bot_discord)
│   ├── memory.py          # Mémoire de salon (faits par channel_id)
│   ├── users.py           # UserNotes : notes SQLite + relation 0-100
│   ├── ranking.py         # Sélection des notes / mémoires pertinentes
│   ├── guards.py          # Anti-empoisonnement (ordres déguisés en faits)
│   ├── sentiment.py       # Ton de l'auteur + détection locale des insultes
│   ├── history.py         # Historique des N derniers échanges (MEMORY_SIZE)
│   ├── whitelist.py       # Whitelist persistante
│   ├── tracker.py         # Suivi des requêtes (dashboard)
│   └── state.py           # Niveau d'autorisation (bot_state.json)
├── agent/
│   ├── agent.py           # Agents Agno + wrappers d'autorisation
│   ├── prompts.py         # Construction du prompt système
│   ├── notes.py           # Extraction LLM des faits (agent dédié, sortie JSON)
│   ├── tools/             # Outils : météo, lecture de fichiers, mémoire
│   └── hooks/
└── bot_discord/
    ├── main.py            # Point d'entrée (interface + boucle asyncio)
    ├── bot.py             # on_message, réponses, participants, insights
    ├── commands.py        # Commandes partagées terminal <-> Discord (argparse)
    ├── config.py          # Variables .env et chemins
    ├── console.py         # Interface plein écran (prompt_toolkit + rich)
    ├── dashboard.py       # Tableau des requêtes actives (rich)
    ├── logger.py          # Logs JSONL
    ├── stats.py           # Statistiques de session
    ├── views.py           # Boutons Discord (autorisation d'outil)
    └── data/              # Données persistantes (tableau ci-dessous)

config/                    # prompt_instruction.md (personnalité du bot)
tests/                     # Suite de tests (104 tests)
main.py                    # Lancement : python main.py
```

### Données persistantes (`src/bot_discord/data/`)

| Fichier | Contenu |
| --- | --- |
| `user_notes.sqlite` | Notes par utilisateur (`immutable` / `model_editable`) + relation 0-100. Mode WAL : les fichiers `-wal` / `-shm` voisins sont normaux et disparaissent à la fermeture propre |
| `user_notes.json.bak` | Ancien format JSON, conservé après migration automatique |
| `memory.json` | Faits mémorisés par salon |
| `history.json` | `MEMORY_SIZE` derniers échanges par salon |
| `whitelist.json` | IDs autorisés à obtenir une réponse |
| `bot_state.json` | Niveau d'autorisation courant (`/set_auth`) |
| `bot_log.jsonl` | Journal de toutes les requêtes (tokens, phases, erreurs) |
| `console_history.txt` | Historique de saisie de la ligne de commande (flèches haut/bas) |
| `user.json` | Correspondance nom → ID Discord |
| `uploads/` | Pièces jointes extraites (`.md`, `.pdf`, `.py`, `.c`, `.h`) |

## 🧪 Tests

```bash
pip install pytest pytest-asyncio   # une seule fois
python -m pytest -q                 # 104 tests
```

- Chaque test redirige les fichiers `data/` (mémoire, notes, historique, état,
  whitelist, logs) vers un dossier temporaire : **aucun test ne modifie tes données réelles**.
- Couverture : mémoire, notes/relations, persistance, migration depuis l'ancien JSON, whitelist, prompt, extraction, garde-fou anti-empoisonnement, historique, niveaux d'autorisation et boutons d'autorisation, **commandes partagées terminal/Discord (argparse, auto-complétion, rendu Markdown et application plein écran)**.
