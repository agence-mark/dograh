"""[.mark] Moteur de la commande : le message demandé par l'appelant.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.commande.moteur.socle import Reglages, avec_le_panier, _r
from api.services.commande.moteur.socle import Appelant


# --------------------------------------------------------------------------- #
# envoyer_un_message : un message demandé par l'appelant (lot 7, E-18)
# --------------------------------------------------------------------------- #


async def envoyer_un_message(source: Source, p: dict[str, Any], regles: Reglages, appelant: "Appelant", quoi: str | None, organisation: int | None) -> Resultat:
    """Envoie à l'appelant le message qu'il demande (par le numéro qui s'affiche, jamais un numéro dicté) : le TEXTE est celui que l'établissement a écrit, le
    modèle n'écrit rien. Éteint par défaut : ``INDISPONIBLE``, rien ne part. Une seule fois par appel et par sorte de message."""
    if not quoi:
        return _r("ARGUMENT_INVALIDE", {}, "", "quoi")  # C7 B5 (Evan 25/11 8 h 45) : le modèle demande quel message d'après le manque
    quoi = quoi.strip().casefold()
    cle = f"{appelant.appel_id or 'sans-appel'}:{quoi}:{appelant.telephone_affiche or ''}"
    return avec_le_panier(await source.envoyer(quoi, appelant.telephone_affiche, cle, organisation), p)
