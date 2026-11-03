"""[.mark] U12 (E104, point 5) : la mise à jour en direct. Chaque écriture publie une modification ; l'écran ouvert sur l'élément la
reçoit et se rafraîchit seul, avec la ligne « Modifié par Claude Code (Evan) · à l'instant ».

Même principe que le chat (``mark_evenements``) : **la table fait foi** (``mark_modifications``), Redis ne porte qu'un réveil par organisation.
Les écrans lisent par SSE, depuis le dernier identifiant reçu (``Last-Event-ID``).

Un « objet » est un mot court qui dit ce qui a changé : ``agent:<id>`` (graphe, brouillon, réglages, fiche, tests de cet agent),
``bibliotheque``, ``a_ameliorer`` (file de tri et « À juger »), ``conversation:<id>``. Une écriture ne dit jamais son contenu : ni
secret ni donnée personnelle ne passent ici, seulement l'objet, le nom de l'action, la source et l'auteur.

⛔ ``noter`` ne lève jamais : une panne d'affichage en direct n'abîme pas l'écriture qu'elle accompagne.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from loguru import logger

from api.db import db_client
from api.services.mark_evenements import publier

Source = Literal["claude_code", "ecran", "collegue"]
OBJET_VALIDE = re.compile(r"^[a-z_]{2,30}(:\d{1,12})?$")


def canal(organisation: int) -> str:
    return f"mark:modifications:{organisation}"


def auteur_de(user: Any) -> str | None:
    """Le prénom affiché : la partie de l'adresse avant le premier point ou le chiffre, première lettre en majuscule."""
    mail = str(getattr(user, "email", "") or "")
    brut = re.split(r"[.\-_+@\d]", mail, maxsplit=1)[0] if mail else ""
    return brut.capitalize()[:40] or None


async def noter(organisation: int, objet: str, action: str, *, source: str, auteur: str | None = None) -> int | None:
    if not OBJET_VALIDE.match(objet):
        return None
    try:
        identifiant = await db_client.ajouter_modification(organisation, objet, action, source, auteur)
        await publier(canal(organisation))
        return identifiant
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[live] modification non publiée ({objet}): {type(erreur).__name__}")
        return None


async def lire_apres(organisation: int, apres: int, objet: str | None = None) -> list[tuple[int, dict[str, Any]]]:
    return [
        (
            int(m.id),
            {
                "type": "modification",
                "objet": m.objet,
                "action": m.action,
                "source": m.source,
                "auteur": m.auteur,
                "le": m.cree_le.isoformat() if m.cree_le else None,
            },
        )
        for m in await db_client.modifications_apres(organisation, apres, objet)
    ]


def objet_d_une_action(nom: str, groupe: str, arguments: dict[str, Any], workflow_id: int | None) -> str:
    """Ce qu'une action du registre modifie : l'agent de ses arguments (ou de la conversation), sinon son groupe."""
    cible = arguments.get("workflow_id")
    identifiant = cible if isinstance(cible, int) and not isinstance(cible, bool) else workflow_id
    if groupe in ("bibliotheque",) and identifiant is None:
        return "bibliotheque"
    if groupe == "juge":
        return "a_ameliorer"
    return f"agent:{identifiant}" if identifiant is not None else (groupe if OBJET_VALIDE.match(groupe) else "general")
