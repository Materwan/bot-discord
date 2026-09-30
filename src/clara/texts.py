"""French texts shown to users (Discord replies, command outputs, console).

Templates use `str.format` placeholders. Command descriptions live next to
their declarations in `commands/handlers.py`, and model-facing prompt text
lives in `llm/prompt_builder.py` and `llm/insights.py`.
"""

# ----------------------------------------------------------------------
# Permission levels and relationship scores
# ----------------------------------------------------------------------
LEVEL_NAMES = {0: "visiteur", 1: "confiance", 2: "admin", 5: "propriétaire"}


def level_name(level: int) -> str | None:
    """Name of a permission level, None for levels without a name."""
    return LEVEL_NAMES.get(level)


def level_suffix(level: int) -> str:
    """" (admin)" for a named level, "" otherwise."""
    name = level_name(level)
    return f" ({name})" if name else ""


def relationship_label(score: int) -> str:
    if score >= 80:
        return "excellente, vous êtes très proches"
    if score >= 60:
        return "bonne"
    if score >= 40:
        return "neutre"
    if score >= 20:
        return "mauvaise, il te parle mal"
    if score > 0:
        return "très mauvaise, il te fuit"
    return "inexistante ou très récente"


# ----------------------------------------------------------------------
# Command framework
# ----------------------------------------------------------------------
UNKNOWN_COMMAND_NAMED = "**Commande inconnue** : `{name}` — tape `help` pour la liste."
UNKNOWN_COMMAND_HELP = "**Commande inconnue** : `{name}`."
ACCESS_DENIED = (
    "**Accès refusé** : `{command}` demande le niveau **{required}**{required_suffix}, "
    "vous avez le niveau **{level}**{level_suffix}."
)
USAGE = "Usage : {usage}"
ERROR = "**Erreur** : {detail}"
SYNTAX_ERROR = "**Erreur de syntaxe** : `{error}`"
INTERNAL_ERROR = "**Erreur** : `{kind} : {error}`"
USER_NOT_FOUND = (
    "**Utilisateur introuvable** : `{reference}` — donne son ID Discord, une mention "
    "ou son nom exact (voir `data/known_users.json`)."
)
DISCORD_ONLY = "**Erreur** : commande réservée à Discord (il faut un auteur)."

# argparse error messages (English) -> French
ARGPARSE_TRANSLATIONS = (
    ("the following arguments are required:", "argument(s) obligatoire(s) manquant(s) :"),
    ("expected one argument", "argument attendu après"),
    ("expected at least one argument", "au moins un argument attendu"),
    ("unrecognized arguments:", "argument(s) inconnu(s) :"),
    ("invalid choice:", "choix invalide :"),
    ("invalid int value:", "nombre entier invalide :"),
    ("ambiguous option:", "option ambiguë :"),
    ("not allowed with argument", "incompatible avec l'argument"),
)

# ----------------------------------------------------------------------
# /help
# ----------------------------------------------------------------------
HELP_HEADER = "**Commandes disponibles**, avec le niveau minimum requis :"
HELP_FOOTER = (
    "Dans Discord, tape `/` pour choisir une commande de Clara ; "
    "dans le terminal, mêmes noms (`/relation 70 Erwan`)."
)
HELP_OWNER_ONLY = " *(propriétaire)*"
HELP_LEVEL = " *(niveau {level})*"
HELP_NAMED_LEVEL = " *(niveau {level} — {name})*"

# ----------------------------------------------------------------------
# /whitelist
# ----------------------------------------------------------------------
WHITELIST_EMPTY = "Whitelist vide : seul le propriétaire est autorisé."
WHITELIST_TITLE = "**Whitelist ({count})** :"
WHITELIST_ADDED = "{user} ajouté à la whitelist."
WHITELIST_ALREADY_PRESENT = "{user} est déjà dans la whitelist."
WHITELIST_REMOVED = "{user} retiré de la whitelist."
WHITELIST_NOT_PRESENT = "{user} n'était pas dans la whitelist."
WHITELIST_MISSING_USER = "**Erreur** : il manque l'utilisateur à ajouter ou retirer."

# ----------------------------------------------------------------------
# /auth
# ----------------------------------------------------------------------
AUTH_TITLE = "**Niveaux de droit** ({count}) :"
AUTH_OWNER_LINE = "- {user} — **{level}** (propriétaire), immuable"
AUTH_LINE = "- {user} — **{level}**{suffix}"
AUTH_SHOW = "{user} : niveau **{level}**{suffix}{immutable}."
AUTH_IMMUTABLE = ", **immuable**"
AUTH_OWNER_LOCKED = (
    "**Impossible de modifier {user}** : le propriétaire a toujours le niveau maximum "
    "**{level}** (propriétaire)."
)
AUTH_CHANGED = "{user} : niveau {previous} → **{level}**{suffix}."

# ----------------------------------------------------------------------
# /relation
# ----------------------------------------------------------------------
RELATION_SHOW = "Relation avec {user} : **{value}/{max}** — {label}."
RELATION_CHANGED = "Relation avec {user} : **{previous} → {value}** sur {max} — {label}."
RELATION_ALL_TITLE = "**Relations ({count})** :"
RELATION_ALL_LINE = "- {user} : **{value}/{max}** — {label}"
RELATION_ALL_SET = "Relation avec **{count} utilisateur(s)** : **{value}/{max}** — {label}."
RELATION_NOT_A_NUMBER = "**Erreur** : `{value}` n'est pas un nombre."
RELATION_OUT_OF_RANGE = "**Erreur** : `{value}` est hors bornes ({min}-{max})."
MISSING_USER = "**Erreur** : il manque l'utilisateur."
RELATION_ALL_WITH_USER = (
    "**Erreur** : avec `-a`, la cible est **tous** les utilisateurs — donne seulement "
    "le niveau (ou retire `-a` pour une seule personne)."
)
NO_KNOWN_USERS = (
    "**Aucun utilisateur connu** : ajoute des noms dans `data/known_users.json`, "
    "des IDs à la whitelist ou des notes via `/remember`."
)

# ----------------------------------------------------------------------
# /remember, /forget, /token, /quit
# ----------------------------------------------------------------------
REMEMBERED = "C'est noté !"
FORGOTTEN = "J'ai tout oublié te concernant."
TOKENS_SESSION = "Session : {minutes:.1f} min"
TOKENS_ALL_LOGS = "Total (logs)"
TOKENS_SUMMARY = (
    "{head} | {requests} requête(s) | tokens : {total} "
    "(prompt {prompt} + réponse {completion})"
)
STOPPING = "Arrêt du bot en cours…"

# ----------------------------------------------------------------------
# Discord
# ----------------------------------------------------------------------
ANSWER_FAILED = "Désolé, je n'ai pas réussi à générer une réponse."
NOT_ALLOWED = "Tu n'es pas autorisé à utiliser Clara."
USE_SLASH_COMMANDS = (
    "Les commandes se lancent maintenant directement : tape `/` dans Discord "
    "et choisis une commande de Clara (ex. `/relation`)."
)

# ----------------------------------------------------------------------
# Console
# ----------------------------------------------------------------------
CONSOLE_READY = "**Terminal prêt** — tape `help` pour les commandes, `Ctrl+D` pour quitter."
CONSOLE_UNAVAILABLE = "[terminal] interface indisponible : {error}"
CONSOLE_STATUS = " modèle : {model} · requêtes : {count} · Ctrl+C vide · Ctrl+D quitte "
DASHBOARD_TITLE = "Requêtes actives"
DASHBOARD_USER = "Utilisateur"
DASHBOARD_REQUEST = "Demande"
DASHBOARD_PHASE = "Phase"
DASHBOARD_EMPTY = "Aucune requête active"
CONNECTED = "Connecté en tant que **{user}** (modèle : {model})"
SLASH_SYNC_FAILED = "**Commandes Discord non publiées** : `{error}`"
LLM_ERROR = "**Erreur LLM** : `{error}`"
UNHANDLED_EXCEPTION = "**Exception** (`{event}`) :\n```\n{trace}\n```"
INTERRUPTED = "\nCtrl-C reçu, bot arrêté."
