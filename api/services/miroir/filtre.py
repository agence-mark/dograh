"""[.mark] U12 (D7 du 03/11) : le filtre du miroir. Rien de secret ne sort d'une conversation Claude Code vers le fork.

Les hooks (``scripts/claude-code/filtre.mjs``) filtrent AVANT l'envoi ; le serveur refiltre TOUT ce qu'il reçoit (une seconde barrière : un
hook modifié, une clé mal posée, une autre source). Les deux filtres suivent les mêmes règles, et les mêmes cas d'essai
(``scripts/claude-code/tests/vecteurs-filtre.json``) les contrôlent côté Node et côté Python.

Ce qui est retiré, sans jamais l'afficher ni le journaliser :
* les clés et jetons des fournisseurs (``sk-ant-``, ``sk-``, ``sk_``/``rk_``/``pk_``, ``AKIA``, ``ghp_``, ``github_pat_``, ``AIza``, ``xox*-``, ``dgr_``), les JWT, les
  ``Bearer``, les blocs de clé privée, les mots de passe dans une adresse ;
* toute valeur affectée à un nom qui dit un secret (``api_key``, ``token``, ``password``, ``secret``...) et toute ligne ``NOM=valeur``
  d'un fichier d'environnement (``.env``) : la valeur est retirée, un bloc de trois lignes ou plus l'est en entier ;
* un bloc de code long (30 lignes ou plus) : c'est le contenu d'un fichier, il ne se recopie pas.
"""

from __future__ import annotations

import re

RETIRE = "[retiré]"
BLOC_ENV = "[contenu d'un fichier d'environnement retiré]"
LIGNES_DE_CODE_MAX = 30

_SECRETS = (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
    r"sk-ant-[A-Za-z0-9_\-]{8,}",
    r"sk-[A-Za-z0-9_\-]{16,}",
    # Revue serveur M3 : les clés « préfixe_… » (Stripe sk_live_/rk_live_/pk_live_/sk_org_, Cartesia, ElevenLabs...).
    r"(?<![A-Za-z0-9])(?:sk|rk|pk)_[A-Za-z0-9_]{16,}",
    # Règle d'entropie : une suite de 32 caractères alphanumériques ou plus, avec au moins un chiffre ET une lettre, est une clé
    # (fournisseurs sans préfixe : Deepgram, Mistral, Soniox...). Au prix de retirer aussi quelques empreintes (sha, uuid sans tirets).
    r"(?<![A-Za-z0-9_\-])(?=[A-Za-z0-9]*[0-9])(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{32,}(?![A-Za-z0-9_\-])",
    # Revue de contrôle, point 9 : un jeton base64url (``-`` et ``_``) de 32 caractères ou plus, avec un chiffre, une minuscule ET une
    # majuscule. Le mélange de casse laisse passer les noms de fichier et les identifiants en minuscules (``2026-11-04-revue-...``).
    r"(?<![A-Za-z0-9_\-])(?=[A-Za-z0-9_\-]*[0-9])(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*[A-Z])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9_\-])",
    r"AKIA[0-9A-Z]{12,}",
    r"gh[pousr]_[A-Za-z0-9]{16,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"AIza[0-9A-Za-z_\-]{20,}",
    r"xox[abprs]-[A-Za-z0-9\-]{8,}",
    r"dgr_[A-Za-z0-9_\-]{8,}",
    r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}",
)
_RE_SECRETS = re.compile("|".join(_SECRETS))
_RE_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{12,}")
_RE_URL = re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:)[^\s/@]+(@)")
_RE_NOM_SECRET = re.compile(
    r"(?i)\b([A-Za-z0-9_\-]*(?:api[_\-]?key|apikey|secret|token|passwd|password|mot[_\-]?de[_\-]?passe|credential|private[_\-]?key)[A-Za-z0-9_\-]*)"
    r"(\s*[:=]\s*)(?!\[retiré\])(\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)"
)
_RE_ENV = re.compile(r"^\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}\s*=\s*\S.*$")
_RE_BLOC_DE_CODE = re.compile(r"```[^\n]*\n([\s\S]*?)```")


def _blocs_de_code(texte: str) -> str:
    def remplacer(m: re.Match[str]) -> str:
        corps = m.group(1)
        lignes = corps.count("\n") + (0 if corps.endswith("\n") else 1)
        return f"[bloc de code de {lignes} lignes non recopié]" if lignes >= LIGNES_DE_CODE_MAX else m.group(0)

    return _RE_BLOC_DE_CODE.sub(remplacer, texte)


def _lignes_d_environnement(texte: str) -> str:
    """Une ligne ``NOM=valeur`` perd sa valeur ; trois lignes de suite ou plus : le bloc entier est retiré."""
    sortie: list[str] = []
    suite: list[str] = []

    def vider() -> None:
        if len(suite) >= 3:
            sortie.append(BLOC_ENV)
        else:
            sortie.extend(f"{ligne.split('=', 1)[0]}={RETIRE}" for ligne in suite)
        suite.clear()

    for ligne in texte.split("\n"):
        if _RE_ENV.match(ligne) and RETIRE not in ligne:
            suite.append(ligne)
            continue
        vider()
        sortie.append(ligne)
    vider()
    return "\n".join(sortie)


def filtrer(texte: str | None) -> tuple[str, bool]:
    """Le texte sans secret, et vrai si quelque chose a été retiré. Le secret n'est jamais renvoyé ni journalisé."""
    if not texte:
        return "", False
    avant = str(texte)
    t = _blocs_de_code(avant)
    t = _RE_SECRETS.sub(RETIRE, t)
    t = _RE_BEARER.sub(lambda m: f"{m.group(1)} {RETIRE}", t)
    t = _RE_URL.sub(lambda m: f"{m.group(1)}{RETIRE}{m.group(2)}", t)
    t = _RE_NOM_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{RETIRE}", t)
    t = _lignes_d_environnement(t)
    return t, t != avant


def borner(texte: str, maxi: int) -> str:
    return texte if len(texte) <= maxi else texte[: maxi - 1].rstrip() + "…"
