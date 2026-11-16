"""[.mark] SA-18, lot A (C2) : le panier de l'appel reste sérialisable après l'enregistrement.

Le panier vit dans la fiche de l'appel, que la session clavier (et tout enregistrement de fiche) écrit en JSON. La source de
commande rend l'heure annoncée en ``datetime`` ; elle ne doit jamais entrer telle quelle dans le panier (erreur 500 après chaque
commande enregistrée aux essais du 17/11 : « Object of type datetime is not JSON serializable »).
"""

from __future__ import annotations

import json

from api.services.commande import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import Appel


async def test_le_panier_enregistre_s_ecrit_en_json(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.finaliser(confirmer=True)
    assert r.statut == "ENREGISTREE", r
    json.dumps(a.p)  # la fiche de l'appel s'écrit
    assert isinstance(a.p["enregistree"]["heure_annoncee"], str)  # ISO, jamais un objet date


async def test_un_second_oui_rend_la_meme_heure_en_texte(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    premier = await a.finaliser(confirmer=True)
    second = await a.finaliser(confirmer=True)
    assert second.statut == "DEJA_FAIT" and second.faits["numero"] == premier.faits["numero"]
    json.dumps(second.faits)
