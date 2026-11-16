"""[.mark] Module Restauration, lot 17 (refonte de Casa Italia) : un panier en livraison SOUS le minimum de sa zone se remplit quand même.

Trouvé en essayant les outils de Casa Italia sans modèle (16/11) : en zone « Proches » (minimum 15 €), le premier article (une Regina à
12,90 €) était REFUSÉ par ``ajouter`` (``MINIMUM_NON_ATTEINT``) et n'entrait pas au panier ; aucun panier ne pouvait donc jamais atteindre
le minimum article par article. Le minimum se juge à la fin (``finaliser`` et l'enregistrement le refusent toujours), jamais à l'ajout.

| Test | Ce qu'il prouve |
|---|---|
| ajout sous le minimum | l'article entre au panier ; le retour dit le minimum et ce qui manque (rien n'est caché au modèle) |
| modifier sous le minimum | une quantité baissée sous le minimum est posée |
| la fin le refuse toujours | ``finaliser`` rend ``MINIMUM_NON_ATTEINT`` tant que le minimum n'est pas atteint, puis avance une fois atteint |
"""

from __future__ import annotations

import pytest

from api.db.bases_clients import horloge
from api.services.commande import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_panier import Appel


@pytest.fixture
async def en_livraison_proches(commerce):
    """Un appel en livraison, zone « Proches » (minimum 15 €), à jeudi midi."""
    with horloge.remplacer(commerce.base, JEUDI_MIDI):
        a = Appel(commerce)
        assert (await a.mode("livraison")).statut == "OK"
        a.p["zone"] = {"id": commerce.zones["Proches"], "nom": "Proches"}
        yield a


async def test_un_article_sous_le_minimum_de_la_zone_entre_au_panier(en_livraison_proches):
    a = en_livraison_proches
    r = await a.ajouter(articles="une regina normale")  # 12,90 € < 15 €
    assert r.statut == "OK", r
    assert a.lignes() == [("Regina Normale", 1)]
    assert r.faits["minimum_non_atteint"] == {"minimum": 1500, "manque": 1500 - 1290}
    r = await a.ajouter(articles="un coca")  # 14,90 € : toujours sous le minimum, et rien n'est perdu
    assert r.statut == "OK" and a.lignes() == [("Regina Normale", 1), ("Coca-Cola", 1)]
    assert r.faits["minimum_non_atteint"]["manque"] == 10


async def test_une_quantite_baissee_sous_le_minimum_est_posee(en_livraison_proches):
    a = en_livraison_proches
    assert (await a.ajouter(articles="deux regina normale")).statut == "OK"  # 25,80 € : au-dessus
    r = await a.modifier(ligne="regina", quantite=1)
    assert r.statut == "OK", r
    assert a.lignes() == [("Regina Normale", 1)]


async def test_la_fin_de_commande_refuse_toujours_sous_le_minimum(en_livraison_proches):
    a = en_livraison_proches
    await a.ajouter(articles="une regina normale")
    appelant = moteur.Appelant(telephone_affiche="+33612345678", appel_id="lot17-minimum")
    r = await moteur.finaliser(a.source, a.p, a.regles, appelant)
    assert r.statut == "MINIMUM_NON_ATTEINT", r
    await a.ajouter(articles="une regina normale")
    r = await moteur.finaliser(a.source, a.p, a.regles, appelant)
    assert r.statut != "MINIMUM_NON_ATTEINT", r
