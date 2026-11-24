"""[.mark] Chantier Partie 1, lot 6 (étape 6.11, L06-43) : les passages d'une étape vers ses collègues montrés en UN outil, ``passer_a(cible, demande)``.

B8 point 2 (lot 2, L02-24) a écrit l'outil, B13 point 2 (D62, prouvé 16/16) l'a mis en tête de la liste de l'accueil. Ici, le vrai moteur :
une étape qui porte plusieurs outils de passage (``transfer_agent``) les montre au modèle en un seul outil à liste fermée de cibles, en tête ;
l'appel est remis au gestionnaire de passage de la cible choisie, tel quel (refus, plafond, note, demande : rien ne change derrière).

Réglage de l'agent ``passage_unique`` : éteint par défaut (un agent d'avant garde ses outils, à l'octet). La cible d'un outil est sa case
``cible`` (posée par le gabarit), sinon son nom sans le préfixe des passages. Le texte de la cible est la description de l'outil. Les mots de
l'outil viennent du rendu de la version finale (``outils.json``), le test les compare. Aucun mot de métier ici.
"""

from __future__ import annotations

from typing import Any, Mapping

NOM = "passer_a"
REGLAGE = "passage_unique"
PREFIXE = "passer_a_l_agent_"
EN_TETE = "Confie la personne au collègue de sa demande, sans un mot de plus."
DESCRIPTION_CIBLE = "Le collègue de sa demande."
# Lot 5 (n° 123) : le texte propre à un métier (ce qu'on recopie tel quel) est écrit par le gabarit dans la config de l'outil de passage (``CLE_DESCRIPTION_DEMANDE``) ;
# sans lui, ce texte sans mot de métier.
CLE_DESCRIPTION_DEMANDE = "description_demande"
DESCRIPTION_DEMANDE = "Sa demande en une phrase, avec ses mots, recopiée telle qu'elle l'a dite, jamais corrigée."
REFUS_CIBLE = "cible_inconnue"


def actif(reglages: Any) -> bool:
    return bool(isinstance(reglages, Mapping) and reglages.get(REGLAGE))


def cible_de(outil: Any) -> str:
    config = ((getattr(outil, "definition", None) or {}).get("config")) or {}
    cible = config.get("cible") if isinstance(config, Mapping) else None
    if isinstance(cible, str) and cible.strip():
        return cible.strip()
    nom = str(getattr(outil, "name", "") or "")
    return nom[len(PREFIXE):] if nom.startswith(PREFIXE) else nom


def description_de_la_demande(outils: list[Any]) -> str:
    """Le texte de la case ``demande`` : celui que le gabarit a posé dans la config du premier outil de passage qui en porte un, sinon le texte commun."""
    for o in outils:
        config = ((getattr(o, "definition", None) or {}).get("config")) or {}
        texte = config.get(CLE_DESCRIPTION_DEMANDE) if isinstance(config, Mapping) else None
        if isinstance(texte, str) and texte.strip():
            return texte.strip()
    return DESCRIPTION_DEMANDE


def _phrase(texte: Any) -> str:
    t = " ".join(str(texte or "").split())
    return t if not t or t.endswith((".", "!", "?")) else t + "."


def schema(outils: list[Any]) -> dict:
    """L'outil unique (format OpenAI), cibles dans l'ordre des outils de l'étape."""
    cibles = [cible_de(o) for o in outils]
    description = " ".join([EN_TETE] + [f"cible {c} : {_phrase(getattr(o, 'description', ''))}" for c, o in zip(cibles, outils)])
    return {
        "type": "function",
        "function": {
            "name": NOM,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "cible": {"type": "string", "enum": cibles, "description": DESCRIPTION_CIBLE},
                    "demande": {"type": "string", "description": description_de_la_demande(outils)},
                },
                "required": ["cible", "demande"],
            },
        },
    }


def outil_de_la_cible(outils: list[Any], arguments: Any) -> Any | None:
    cible = arguments.get("cible") if isinstance(arguments, Mapping) else None
    return next((o for o in outils if cible_de(o) == cible), None)


def refus_de_cible(outils: list[Any]) -> dict:
    return {"status": "transfer_failed", "reason": REFUS_CIBLE, "message": "Cible inconnue : " + ", ".join(cible_de(o) for o in outils) + "."}
