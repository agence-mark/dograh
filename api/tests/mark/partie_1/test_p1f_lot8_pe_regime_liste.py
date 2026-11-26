"""[.mark] Lot 8, PE-3, reprise R1 (Q8 sur la lecture d'un régime) : « Vous avez du végétarien ? » liste des articles étiquetés ; la consigne « quelques noms, puis propose d'en dire plus » accompagne la liste complète.

Décision de Pierre (27/11) : Q8 s'applique aux lectures de liste. La consigne n'est posée que si la liste a plus d'un nom (règle de structure, aucun chiffre du métier).
Client « Vous avez du végétarien ? » / avant : le modèle recevait toute la liste, sans consigne / après : « On a la Margherita, la Veggie et la Reine, entre autres : je vous en dis plus ? ».
"""

from __future__ import annotations

from api.services.actions_communes import phrases_d_information as INFO
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as A_
from api.tests.mark.partie_1.aides_signal import SourceAllergie


async def _regime(noms: list[str]):
    class Source(SourceAllergie):
        async def catalogue(self, _mode):
            return {"articles": [{"nom": n, "regimes": ["vegetarien"]} for n in noms]}

        async def regles_d_information(self):
            return {"halal_restaurant": False}
    return await A_._regime_du_catalogue(Source(), {"mode": "emporter"}, "végétarien")


async def test_plusieurs_articles_vegetariens_portent_la_consigne_et_la_liste_complete():
    r = await _regime(["Margherita", "Veggie", "Reine"])
    assert r.faits["articles"] == ["Margherita", "Veggie", "Reine"], r
    assert r.faits.get("a_faire") == INFO.CONSIGNE_QUELQUES_NOMS, r
    assert r.faits["autres_a_confirmer"] is True, r


async def test_voisin_un_seul_article_vegetarien_n_a_pas_de_consigne():
    r = await _regime(["Veggie"])
    assert r.faits["articles"] == ["Veggie"] and "a_faire" not in r.faits, r
    assert r.faits["autres_a_confirmer"] is True, r
