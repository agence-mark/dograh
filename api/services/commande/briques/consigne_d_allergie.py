"""[.mark] Brique INF6 : la consigne d'allergie du restaurant, en texte (inventaire, famille 9 ; A41 : « je suis allergique aux noix »).

La consigne est un FAIT du retour (le restaurant l'a écrite : « la cuisine ne peut pas garantir l'absence de traces ») : l'agent la répète. L'allergie dite par la personne part toujours
en note de la commande (E22, lot 6 : ``note.ENTETES["allergie"]``), que la donnée du produit soit connue ou non.
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer
from api.services.commande.note import ENTETES


def brique_inf6_repeter_et_noter(consigne: str | None, allergie_dite: str | None) -> dict[str, str | None]:
    """``{"consigne": texte à répéter ou None, "note": « Allergie : ... » ou None}`` ; rien n'est inventé quand une des deux manque."""
    consigne = " ".join((consigne or "").split()) or None
    dite = " ".join((allergie_dite or "").split())
    return {"consigne": consigne, "note": f"{ENTETES['allergie']}{dite}" if dite else None}


enregistrer(Brique(
    "INF6", "informations", "C", (), brique_inf6_repeter_et_noter,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/INF6",
    phrase="la consigne d'allergie du restaurant est un fait à répéter ; l'allergie dite part en note",
))
