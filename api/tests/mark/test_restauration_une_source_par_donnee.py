"""[.mark] Module Restauration, M53 : UNE SEULE SOURCE PAR DONNÉE entre la caisse de démo et le module (décision d'Evan, 16/11).

La caisse de démo simule une caisse : carte, prix, ruptures, état, temps de préparation, horaires. Zones de livraison, minimums, délais par zone, types de
commande, moyens de paiement et réservations vivent dans le module ; c'est l'agent, par le module, qui vérifie la livraison.

| Test | Ce qu'il prouve |
|---|---|
| inventaire sans recouvrement | ``DONNEES_DE_LA_CAISSE`` et ``DONNEES_DU_MODULE`` n'ont aucune donnée commune ; les réglages d'une caisse neuve sont exactement ceux de la caisse |
| réglage refusé | poser zones, types ou moyens de paiement sur la caisse est refusé (avec la raison), jamais ignoré en silence |
| ancienne ligne | des réglages posés avant M53 ne rendent plus ces clés, et la prochaine écriture les efface |
| catalogue | les zones ne deviennent plus des « frais de livraison » du catalogue ; seuls les frais écrits par la caisse restent |
| aucun contrôle de zone | une commande de livraison hors de toute zone est reçue comme par une vraie caisse |
| code de la caisse | rien dans ``caisse_demo/`` ne lit ni n'écrit une donnée du module |
| script de pose | ``poser_le_restaurant.py`` n'écrit plus zones, types ni paiements chez la caisse |
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.db import db_client
from api.services.restauration.caisse_demo import catalogue, restaurants
from api.services.restauration.caisse_demo.moteur import empreinte_du_jeton, moteur
from api.tests.mark.equipe_commun import creer_organisation
from api.tests.mark.test_restauration_caisse_demo_imprevus import CARTE

RACINE = Path(__file__).resolve().parents[2]
CAISSE = RACINE / "services" / "restauration" / "caisse_demo"
SCRIPT = RACINE.parent.parent.parent / "Labo-agent-vocal" / "agents" / "casa-italia-restauration" / "outils" / "poser_le_restaurant.py"


def test_une_donnee_n_a_qu_une_source():
    assert not restaurants.DONNEES_DE_LA_CAISSE & restaurants.DONNEES_DU_MODULE
    assert set(restaurants._reglages_par_defaut()) == set(restaurants.DONNEES_DE_LA_CAISSE)


@pytest.mark.parametrize("cle", ["zones", "types_de_commande", "paiements", "minimum"])
async def test_la_caisse_refuse_une_donnee_du_module(db_session, cle):
    organisation = await creer_organisation(db_client, f"m53-refus-{cle}")
    r = await restaurants.creer(organisation, "Caisse")
    with pytest.raises(restaurants.RestaurantDeTestRefuse, match="module"):
        await restaurants.regler(organisation, r["id"], {"reglages": {cle: []}})
    with pytest.raises(restaurants.RestaurantDeTestRefuse):
        await restaurants.regler(organisation, r["id"], {"reglages": {"inconnu": 1}})


async def test_une_ancienne_ligne_ne_rend_plus_les_donnees_du_module(db_session):
    organisation = await creer_organisation(db_client, "m53-ancienne")
    r = await restaurants.creer(organisation, "Ancienne")
    ancien = {**r["reglages"], "zones": [{"nom": "Z", "communes": "Senlis", "frais": 250, "minimum": 1500, "delai": 30}], "types_de_commande": ["livraison"], "paiements": ["carte"]}
    r2 = await db_client.modifier_restaurant_de_demo(organisation, r["id"], {"reglages": ancien}, r["maj_le"])
    assert not {"zones", "types_de_commande", "paiements"} & set(r2["reglages"])
    r3 = await restaurants.regler(organisation, r["id"], {"reglages": {"delai": 25}})
    assert r3["reglages"]["delai"] == 25 and not {"zones", "types_de_commande", "paiements"} & set(r3["reglages"])


def test_les_zones_ne_font_plus_de_frais_de_livraison_dans_le_catalogue():
    lecture = catalogue.catalogue_de_lecture(catalogue_id="c", compte_id="a", nom="X", carte=catalogue.carte_vide(), remises=[], cree_le=__import__("datetime").datetime(2026, 1, 1),
                                            frais=[{"ref": "F1", "name": "Frais caisse", "type": "delivery", "price": "2.00 EUR"}])
    assert [c["ref"] for c in lecture["data"]["charges"]] == ["F1"]
    with pytest.raises(TypeError):
        catalogue.catalogue_de_lecture(catalogue_id="c", compte_id="a", nom="X", carte=catalogue.carte_vide(), remises=[], cree_le=None, zones=[{"nom": "Z"}])  # type: ignore[call-arg]


async def test_la_caisse_recoit_une_livraison_sans_aucun_controle_de_zone(db_session):
    organisation = await creer_organisation(db_client, "m53-livraison")
    r = await restaurants.creer(organisation, "Caisse", carte=CARTE, comportement={"reponse": "accepte", "acceptation": "auto"})
    await db_client.modifier_restaurant_de_demo(organisation, r["id"], {"jeton_empreinte": empreinte_du_jeton("jeton")}, restaurants.horloge(organisation).maintenant())
    commande = {"status": "new", "service_type": "delivery", "private_ref": "liv-1", "items": [{"product_name": "X", "sku_ref": "REINE-S", "price": "12.50 EUR", "quantity": "1"}],
                "customer": {"address_1": "1 rue de Nulle Part", "city": "Lointain", "postal_code": "99999"}}
    rep = await moteur.servir("jeton", "POST", "/location/orders", corps=commande)  # aucune zone, aucun minimum (12,50 EUR) : une vraie caisse reçoit
    assert rep.code == 200
    assert [c["statut"] for c in await db_client.lister_commandes_de_demo(r["id"])] == ["accepted"]


def test_le_code_de_la_caisse_ne_touche_a_aucune_donnee_du_module():
    motif = re.compile(r"""["'](zones|types_de_commande|paiements|minimum|delai_de_zone)["']""")
    fautes = []
    for fichier in CAISSE.glob("*.py"):
        for n, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if motif.search(ligne) and fichier.name != "restaurants.py":
                fautes.append(f"{fichier.name}:{n}")
    assert not fautes, fautes


def test_le_script_de_pose_n_ecrit_rien_en_double():
    if not SCRIPT.exists():
        pytest.skip("script du labo absent de ce dépôt")
    texte = SCRIPT.read_text(encoding="utf-8")
    blocs = re.split(r"\n    (?=appel\(|#|for )", texte)  # une instruction « appel(...) » de la fonction principale, avec ses lignes de suite
    appels = [b for b in blocs if "caisse-demo/restaurants" in b]
    assert appels
    for a in appels:
        assert not re.search(r'"(zones|types_de_commande|paiements)"', a), a
    assert "ZONES_CAISSE" not in texte and "TYPES_DE_TEST" not in texte
