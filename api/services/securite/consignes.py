"""[.mark] Couche 1 : les consignes de sécurité posées par le code après le prompt (U3 quinquies).

Le moteur compose le prompt d'une étape en UN seul endroit, pour le téléphone comme pour le clavier (parité) : le bloc d'ici
y est ajouté, à la fin, après les blocs du code. Aucun bloc quand aucun interrupteur n'est allumé (le défaut).
"""

from __future__ import annotations

from typing import Any

from api.schemas.securite_conversation import SecuriteConversation
from api.services.securite import textes
from api.services.securite.reglages import lire


def bloc_de_consignes(reglages: SecuriteConversation | dict | None) -> str | None:
    """Le bloc de consignes de sécurité, ou ``None`` quand rien n'est allumé. ⛔ Ne lève jamais."""
    try:
        r = reglages if isinstance(reglages, SecuriteConversation) else lire(reglages)
        lignes: list[str] = []
        for nom in ("manipulation", "confidentialite", "role"):
            consigne = getattr(r, nom)
            if consigne.actif:
                lignes.append(f"- {(consigne.phrase or '').strip() or textes.CONSIGNES[nom]}")
        if r.urgence.actif:
            phrase = (r.urgence.phrase or "").strip() or textes.CONSIGNES["urgence"]
            lignes.append(f"- {phrase}{' ' + textes.URGENCE_TRANSFERT if r.urgence.transfert and not r.urgence.phrase.strip() else ''}")
        if not lignes:
            return None
        return "\n".join([textes.ENTETE, *lignes])
    except Exception:  # noqa: BLE001 -- une consigne qui ne se compose pas ne coûte pas l'appel
        return None


def ajouter_au_prompt(texte: str, run_configs: dict[str, Any] | None) -> str:
    """``texte`` suivi du bloc de sécurité de l'agent, s'il y en a un."""
    bloc = bloc_de_consignes((run_configs or {}).get("securite_conversation"))
    return f"{texte}\n\n{bloc}" if bloc else texte
