"""[.mark] Module Restauration, lot 6, étape 5 : les quatre outils de l'agent, par le vrai gestionnaire d'outil (R1).

``etat_ouverture``, ``heure_annoncee``, ``verifier_adresse``, ``resoudre_une_date``. Vraie base du client, vrai établissement, vrai flux ;
la fiche de l'appel porte le panier. Aucun texte de caisse : un statut fermé, des faits, une phrase.

| Test | Ce qu'il prouve |
|---|---|
| ouverture | tous les modes ou un seul ; un mode en pause rend son statut, sa raison et sa reprise ; ne change rien |
| heure annoncée | la durée du type, la durée ajoutée par la puce ; une livraison exige sa zone et annonce celle de la zone |
| adresse | une commune sûre pose la zone et rechiffre le panier ; un doute ne pose rien ; hors zone vide l'ancienne zone ; jamais la zone d'un autre établissement |
| date | « demain à 19 h 30 » donne l'instant exact ; l'heure floue ou la date ambiguë se confirme ; une commande pour plus tard dit son jour |
| module coupé | les quatre outils rendent un refus fermé |
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from api.db.bases_clients.restauration_temps import ecrire_temps
from api.services.commande import panier
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401

SENLIS, CHANTILLY = "60612", "60141"


async def _zones(commerce_):  # noqa: F811
    c, a = commerce_.c, commerce_.a
    await c.execute("UPDATE mark.site SET adresse_insee = $2 WHERE id = $1", a, SENLIS)
    await c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", a)
    ids = {}
    for nom, forme, communes, rayon, minimum, frais, delai, ordre in (
        ("Chantilly", "communes", [CHANTILLY], None, 2500, 400, 45, 0),
        ("Centre", "rayon", [], 8, 1500, 300, 30, 1),
    ):
        ids[nom] = await c.fetchval(
            "INSERT INTO mark.resto_zone (site_id, nom, forme, communes, rayon_km, minimum, frais, delai, ordre) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id",
            a, nom, forme, communes, rayon, minimum, frais, delai, ordre,
        )
    return ids


# --------------------------------------------------------------------------- #
# etat_ouverture
# --------------------------------------------------------------------------- #


async def test_l_etat_d_ouverture_dit_chaque_mode_ou_un_seul_sans_rien_changer(appel_de_test):
    jouer = appel_de_test.jouer
    r = await jouer("etat_ouverture")
    assert r["statut"] == "OK" and [m["mode"] for m in r["faits"]["modes"]] == ["emporter", "livraison", "sur_place"]
    assert all(m["ouvert"] for m in r["faits"]["modes"]) and r["faits"]["ouverts"] == ["à emporter", "en livraison", "sur place"]
    un = await jouer("etat_ouverture", mode="en livraison")
    assert un["statut"] == "OK" and [m["mode"] for m in un["faits"]["modes"]] == ["livraison"]
    assert (await jouer("etat_ouverture", mode="en hélicoptère"))["statut"] == "ARGUMENT_INVALIDE"
    assert panier.CLE not in appel_de_test.fiche or appel_de_test.fiche[panier.CLE]["mode"] is None  # lecture seule


async def test_un_mode_en_pause_rend_son_statut_sa_raison_et_sa_reprise(appel_de_test, commerce):
    await ecrire_temps(commerce.c, commerce.a, "livraison", 0, None, {"jusqu_a": JEUDI_MIDI + timedelta(hours=2)}, source="portail")
    jouer = appel_de_test.jouer
    r = await jouer("etat_ouverture", mode="livraison")
    assert r["statut"] == "PAUSE_TYPE" and r["faits"]["modes"][0]["raison"] == "pause_type" and "pause" in r["suggestion"]
    tous = await jouer("etat_ouverture")
    assert tous["statut"] == "OK" and tous["faits"]["ouverts"] == ["à emporter", "sur place"]  # la livraison n'y est pas


# --------------------------------------------------------------------------- #
# heure_annoncee
# --------------------------------------------------------------------------- #


async def test_l_heure_annoncee_vient_du_code_et_compte_la_duree_ajoutee(appel_de_test, commerce):
    jouer = appel_de_test.jouer
    sans_mode = await jouer("heure_annoncee")
    assert sans_mode["statut"] == "INCOMPLETE" and sans_mode["manque"] == "mode"
    r = await jouer("heure_annoncee", mode="à emporter")
    assert r["statut"] == "OK" and r["faits"]["minutes"] == 20 and r["suggestion"] == "Ce sera prêt dans vingt minutes."
    await ecrire_temps(commerce.c, commerce.a, "emporter", 15, None, None, source="portail")
    assert (await jouer("heure_annoncee", mode="à emporter"))["suggestion"] == "Ce sera prêt dans trente-cinq minutes."
    await jouer("choisir_mode", mode="sur place")
    assert (await jouer("heure_annoncee"))["faits"]["mode"] == "sur_place"  # le mode de la commande par défaut


async def test_une_livraison_exige_sa_zone_et_annonce_celle_de_la_zone(appel_de_test, commerce):
    ids = await _zones(commerce)
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="en livraison")
    sans_zone = await jouer("heure_annoncee")
    assert sans_zone["statut"] == "INCOMPLETE" and sans_zone["manque"] == "zone"
    assert (await jouer("verifier_adresse", adresse="12 rue de la République à Senlis"))["statut"] == "RETENU"
    assert appel_de_test.fiche[panier.CLE]["zone"]["id"] == ids["Centre"]
    assert (await jouer("heure_annoncee"))["faits"]["minutes"] == 30  # le délai de la zone en entier
    await jouer("verifier_adresse", adresse="je suis à Chantilly")
    assert (await jouer("heure_annoncee"))["faits"]["minutes"] == 45


# --------------------------------------------------------------------------- #
# verifier_adresse
# --------------------------------------------------------------------------- #


async def test_une_commune_sure_pose_la_zone_et_le_panier_est_rechiffre_avec_son_minimum(appel_de_test, commerce):
    ids = await _zones(commerce)
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles="un coca")
    assert (await jouer("choisir_mode", mode="en livraison"))["manque"] == "zone"  # les articles sont gardés, la zone est demandée
    r = await jouer("verifier_adresse", adresse="12 rue de la République à Senlis")
    assert r["statut"] == "RETENU" and r["faits"]["zone"]["id"] == ids["Centre"] and r["faits"]["commune"]["insee"] == SENLIS
    assert r["faits"]["a_revoir"]["statut"] == "MINIMUM_NON_ATTEINT"  # le coca ne fait pas les 15 € de cette zone : dit, rien n'est retiré
    p = appel_de_test.fiche[panier.CLE]
    assert p["zone"] == {"id": ids["Centre"], "nom": "Centre"} and p["adresse"] == "12 rue de la République à Senlis" and len(p["lignes"]) == 1
    ajoute = await jouer("ajouter", articles="deux regina normale")
    assert ajoute["statut"] == "OK"
    assert (await jouer("voir_commande"))["faits"]["frais"] == 300


async def test_un_doute_ne_pose_rien_et_hors_zone_vide_l_ancienne_zone(appel_de_test, commerce):
    await _zones(commerce)
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="en livraison")
    flou = await jouer("verifier_adresse", adresse="l'adresse c'est 12 rue des lilas")
    assert flou["statut"] in ("AMBIGU", "INTROUVABLE") and not appel_de_test.fiche[panier.CLE].get("zone")
    sans_commune = await jouer("verifier_adresse", adresse="rue de Paris")
    assert sans_commune["statut"] == "INTROUVABLE" and sans_commune["manque"] == "commune"
    assert (await jouer("verifier_adresse", adresse="12 rue de la République à Senlis"))["statut"] == "RETENU"
    hors = await jouer("verifier_adresse", adresse="7 rue Victor Hugo, Compiègne")
    assert hors["statut"] == "HORS_ZONE" and "Compiègne" in hors["suggestion"]
    p = appel_de_test.fiche[panier.CLE]
    assert p["zone"] is None and p["adresse"] is None  # jamais l'ancienne zone pour une nouvelle adresse
    assert (await jouer("verifier_adresse", adresse="  "))["statut"] == "ARGUMENT_INVALIDE"


async def test_jamais_la_zone_d_un_autre_etablissement(appel_de_test, commerce):
    await _zones(commerce)
    await commerce.c.execute("INSERT INTO mark.resto_zone (site_id, nom, forme, communes) VALUES ($1, 'Chez B', 'communes', ARRAY[$2])", commerce.b, "60159")
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="en livraison")
    r = await jouer("verifier_adresse", adresse="au 5 rue Victor Hugo, Compiègne")  # Compiègne est dans la zone de B, pas dans celles de A
    assert r["statut"] == "HORS_ZONE"


# --------------------------------------------------------------------------- #
# resoudre_une_date
# --------------------------------------------------------------------------- #


async def test_la_date_et_l_heure_dites_donnent_l_instant_exact(appel_de_test):
    jouer = appel_de_test.jouer
    r = await jouer("resoudre_une_date", texte="demain", heure="19 h 30")
    assert r["statut"] == "RETENU" and r["faits"]["heure_voulue"] == "2026-11-13T19:30:00+01:00" and r["suggestion"] == "vendredi treize novembre à dix-neuf heures trente."
    r = await jouer("resoudre_une_date", texte="samedi", heure="sept heures et demie du soir")
    assert r["faits"]["heure_voulue"] == "2026-11-14T19:30:00+01:00"
    sans_heure = await jouer("resoudre_une_date", texte="demain")
    assert sans_heure["statut"] == "INCOMPLETE" and sans_heure["manque"] == "heure" and sans_heure["faits"]["jour"] == "2026-11-13"


async def test_le_doute_se_confirme_et_rien_n_est_choisi(appel_de_test):
    jouer = appel_de_test.jouer
    jour = await jouer("resoudre_une_date", texte="jeudi", heure="19 h")
    assert jour["statut"] == "AMBIGU" and [c["jour"] for c in jour["faits"]["candidats"]] == ["2026-11-12", "2026-11-19"] and "heure_voulue" not in jour["faits"]
    heure = await jouer("resoudre_une_date", texte="demain", heure="sept heures")
    assert heure["statut"] == "AMBIGU" and heure["faits"]["candidats_heure"] == ["sept heures", "dix-neuf heures"] and "heure_voulue" not in heure["faits"]
    assert (await jouer("resoudre_une_date", texte="bientôt"))["statut"] == "INTROUVABLE"
    passee = await jouer("resoudre_une_date", texte="ce soir", heure="9 h du matin")
    assert passee["statut"] == "ARGUMENT_INVALIDE" and passee["manque"] == "heure"  # une heure déjà passée n'est jamais proposée


async def test_une_commande_pour_plus_tard_de_bout_en_bout_dit_son_jour(appel_de_test, commerce):
    await commerce.c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = true, jours_a_l_avance = 3 WHERE site_id = $1 AND type = 'emporter'", commerce.a)
    jouer = appel_de_test.jouer
    quand = await jouer("resoudre_une_date", texte="demain", heure="19 h 30")
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles="une regina normale et un coca")
    r = None
    for _ in range(5):
        r = await jouer("finaliser", prenom="Alice", moyen="carte", heure=quand["faits"]["heure_voulue"])
        if r.get("manque") == "relecture":
            break
    assert r["manque"] == "relecture"
    fin = await jouer("finaliser", prenom="Alice", moyen="carte", heure=quand["faits"]["heure_voulue"], sens="accord", mots="oui c'est bon")  # agent fiable : l'accord passe par le sens
    assert fin["statut"] == "ENREGISTREE", fin
    assert fin["suggestion"] == "Votre commande est enregistrée pour vendredi treize novembre à dix-neuf heures trente. Puis-je faire autre chose pour vous ?"  # M108


# --------------------------------------------------------------------------- #
# Module coupé
# --------------------------------------------------------------------------- #


async def test_un_module_coupe_refuse_les_quatre_outils(appel_de_test):
    appel_de_test.moteur.configurations_des_modules = {"commande_sur_catalogue": False}
    for action, arguments in (("etat_ouverture", {}), ("heure_annoncee", {}), ("verifier_adresse", {"adresse": "Senlis"}), ("resoudre_une_date", {"texte": "demain"})):
        r = await appel_de_test.jouer(action, **arguments)
        assert r["statut"] == "INDISPONIBLE" and r["faits"] == {}, action


_ = pytest


# SA-18 : le mode et les articles dits dans la même phrase partent dans un seul geste (le modèle n'enchaîne pas toujours deux appels).
async def test_le_mode_et_les_articles_dits_ensemble_sont_poses_en_un_geste(appel_de_test):
    jouer = appel_de_test.jouer
    r = await jouer("choisir_mode", mode="à emporter", articles="une regina normale")
    assert r["statut"] == "OK" and r["faits"]["ajoutes"] == ["Regina Normale"], r
    assert appel_de_test.fiche[panier.CLE]["mode"] == "emporter"
    # sans articles : comme avant
    autre = await jouer("choisir_mode", mode="en livraison")
    assert "ajoutes" not in autre["faits"]


async def test_un_verbe_dit_pour_le_mode_est_reconnu(appel_de_test):
    jouer = appel_de_test.jouer
    assert (await jouer("choisir_mode", mode="livrer"))["statut"] == "OK"
    assert appel_de_test.fiche[panier.CLE]["mode"] == "livraison"
    assert (await jouer("choisir_mode", mode="manger sur la lune"))["statut"] == "ARGUMENT_INVALIDE"
