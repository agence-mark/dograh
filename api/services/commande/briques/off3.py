"""[.mark] Brique OFF3 : le code de remise (inventaire, famille 8 ; A13 : « offres exclusives dans l'application » ; prouvé au banc B11 et B12).

Deux cases de la fiche, présentes seulement quand l'établissement a une remise active à code (``objets_de_la_carte``) : ``code_de_remise`` (« Le code lui-même, tel qu'elle le dit ou
l'épelle ») et ``reduction_annoncee`` (« Vrai quand elle dit avoir un code sans le dire »). Le CODE vérifie le code dit contre les codes des remises actives de l'établissement
(``code_lu`` : « pizza cinq » vaut PIZZA5) ; il ne devine jamais : un code faux, expiré, d'une remise brouillon ou d'un autre établissement est le même refus, ``code_inconnu``.
Une remise à code n'est JAMAIS annoncée par l'agent (ni « qu'est-ce que vous avez », ni offre proposée) ; elle ne s'applique qu'avec son code dit.
"""

from __future__ import annotations

from typing import Any

from api.services.actions_communes.barriere_des_chiffres import code_lu
from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "code_inconnu"


def brique_off3_verifier_le_code(dit: Any, codes: list[dict[str, Any]]) -> dict[str, Any]:
    """``{"code", "ref", "nom", "phrase"}`` quand le code dit est celui d'une remise active ; sinon le refus ``{"raison": "code_inconnu", "dit"}`` (jamais de code deviné)."""
    lu = code_lu(dit)
    trouve = next((c for c in codes if lu and c["code"] == lu), None)
    return {"code": trouve["code"], "ref": trouve["ref"], "nom": trouve["nom"], "phrase": trouve.get("phrase")} if trouve else {"raison": RAISON, "dit": str(dit or "")}


enregistrer(Brique(
    "OFF3", "offres", "C", (), brique_off3_verifier_le_code, change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OFF3",
    phrase="un code dit est vérifié par le code ; la remise à code n'est jamais annoncée ; code_inconnu pour tout code que l'établissement n'a pas",
))
