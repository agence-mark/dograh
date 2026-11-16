"""[.mark] Module Restauration, lot 26 (SA-15) : la qualité de l'agent de démo (manques M25 à M31 trouvés en construisant Casa Italia, lot 17).

| Test | Manque | Ce qu'il prouve |
|---|---|---|
| voir sous le minimum | M27 | ``voir_commande`` sous le minimum de la zone rend les lignes ET ce qui manque, jamais un refus |
| commune hors zone | M28 | une commune réelle hors de toute zone rend ``HORS_ZONE`` avec les communes livrées, pas « dans quelle commune ? » |
| nom de rue | M28 | un nom de rue qui est aussi une commune n'est jamais pris pour la commune de livraison |
| commune ambiguë | M28 | un nom porté par plusieurs communes reste à confirmer |
"""

from __future__ import annotations

import pytest

from api.db.bases_clients.restauration_zone import verifier_adresse
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_lot17_minimum import en_livraison_proches  # noqa: F401
from api.tests.mark.test_restauration_zones import _regler


async def test_voir_la_commande_sous_le_minimum_rend_les_lignes_et_ce_qui_manque(en_livraison_proches):
    a = en_livraison_proches
    assert (await a.ajouter(articles="une regina normale")).statut == "OK"  # 12,90 € < 15 €
    r = await a.voir()
    assert r.statut == "OK", r
    assert [(l["nom"], l["quantite"], l["prix_unitaire"]) for l in r.faits["lignes"]] == [("Regina Normale", 1, 1290)]
    assert r.faits["minimum_non_atteint"] == {"minimum": 1500, "manque": 210}
    assert r.faits["total"] is None
    assert "il manque deux euros dix" in r.suggestion and "quinze euros" in r.suggestion
    await a.ajouter(articles="un coca")  # 14,90 € : encore 10 centimes
    r = await a.voir()
    assert r.statut == "OK" and r.faits["minimum_non_atteint"]["manque"] == 10 and len(r.faits["lignes"]) == 2


async def test_voir_la_commande_au_dessus_du_minimum_ne_change_pas(en_livraison_proches):
    a = en_livraison_proches
    await a.ajouter(articles="deux regina normale")
    r = await a.voir()
    assert r.statut == "OK" and "minimum_non_atteint" not in r.faits and r.faits["total"] is not None


async def test_une_commune_reelle_hors_de_toute_zone_est_hors_zone_avec_les_communes_livrees(commerce):  # noqa: F811
    await _regler(commerce)
    for adresse in ("3 rue de la Gare, Pont-Sainte-Maxence", "3 rue de la Gare Pont-Sainte-Maxence", "je suis à Pont Sainte Maxence"):
        r = await verifier_adresse(commerce.c, commerce.a, adresse)
        assert r.statut == "HORS_ZONE", (adresse, r)
        assert r.faits["commune"]["nom"] == "Pont-Sainte-Maxence" and "Chantilly" in r.faits["communes_livrees"]
        assert "Nous ne livrons pas à Pont-Sainte-Maxence." in r.suggestion and "Nous livrons" in r.suggestion and "Chantilly" in r.suggestion


async def test_un_nom_de_rue_n_est_jamais_une_commune_de_livraison(commerce):  # noqa: F811
    await _regler(commerce)
    for adresse in ("rue de Creil", "3 avenue de Compiègne", "rue de Paris"):
        assert (await verifier_adresse(commerce.c, commerce.a, adresse)).statut == "INTROUVABLE", adresse


async def test_un_nom_porte_par_plusieurs_communes_reste_a_confirmer(commerce):  # noqa: F811
    await _regler(commerce)
    r = await verifier_adresse(commerce.c, commerce.a, "5 rue de la Mairie, Saint-Just")
    assert r.statut == "AMBIGU" and len(r.faits["candidats"]) >= 2
