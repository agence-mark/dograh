"""[.mark] Chantier Partie 1, lot 19 bis, étape D : installation et futurs clients (note d'audit 3 de Pierre, § S, et S10 trouvé au déploiement de l'étape A).

Un test vu rouge par ligne (S1 à S10), sur la vraie porte, la vraie diffusion et la vraie installation (aucun appel à un modèle ni à un tiers).
"""

from __future__ import annotations

import pytest

from api.db.bases_clients.restauration_formulaire import horaires_en_texte
from api.services.pipecat.etat_ouverture import vers_expression_osm


# --------------------------------------------------------------------------- S10


def test_horaires_du_formulaire_jour_ferme_ecrit():
    """S10 : un jour fermé du formulaire s'écrit « dimanche : fermé » (source : ``horaires_en_texte`` n'écrivait que les jours ouverts, le lecteur
    exige les sept jours : « jours sans ligne : dimanche », un restaurant refusé au démarrage) ; le texte écrit est relu sans erreur ; un jour sans plage
    (liste vide) est un jour fermé aussi."""
    texte = horaires_en_texte({str(j): [["11:00", "14:00"], ["18:00", "22:30"]] for j in range(1, 7)})
    lignes = texte.splitlines()
    assert len(lignes) == 7 and lignes[6] == "dimanche : fermé", texte
    vers_expression_osm(texte)  # le lecteur du moteur accepte les sept jours
    avec_vide = horaires_en_texte({"1": [["09:00", "12:00"]], "2": []})
    assert avec_vide.splitlines()[1] == "mardi : fermé" and len(avec_vide.splitlines()) == 7
    vers_expression_osm(avec_vide)


# --------------------------------------------------------------------------- S9

from api.db import db_client  # noqa: E402
from api.db.bases_clients import connexion as schema  # noqa: E402
from api.services.gabarits import installation as I  # noqa: E402
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: E402,F401
from api.tests.mark.partie_1.test_l17_gabarit import FORMULAIRE_COMPLET, installe  # noqa: E402,F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402,F401


async def test_deux_restaurants_du_meme_nom(installe):
    """S9 : un second restaurant de même nom (donc de même clé) dans l'organisation est REFUSÉ, avec l'agent qui tient la clé ; le premier garde son
    adresse, ses zones et ses agents (source : ``ecrire_le_formulaire`` réécrivait l'établissement par ``ON CONFLICT (cle)``, le premier groupe servait
    l'autre adresse). Une clé libre n'est tenue par personne ; la reprise de la même installation (clé déjà notée au progrès) saute le contrôle."""
    autre_adresse = {**FORMULAIRE_COMPLET, "adresse": {"voie": "1 rue Autre", "code_postal": "60100", "commune": "Creil", "insee": "60175"}}
    with pytest.raises(I.ErreurInstallation) as refus:
        await I.installer(installe.user, installe.org, autre_adresse)
    assert refus.value.code == "gabarit_restaurant_deja_installe"
    assert refus.value.precisions == [str(installe.application["workflow_id"])]
    c = await schema.connecter(installe.base)
    try:
        assert await c.fetchval("SELECT adresse_commune FROM mark.site WHERE cle = $1", installe.application["formulaire"]["cle"]) == "Pont-Sainte-Maxence"
    finally:
        await c.close()
    cle = installe.application["formulaire"]["cle"]
    assert await I.application_qui_tient_la_cle(installe.org, "restauration", cle) == installe.application["workflow_id"]
    assert await I.application_qui_tient_la_cle(installe.org, "restauration", "autre-cle") is None


# --------------------------------------------------------------------------- S7

from api.services.gabarits import formulaire as F  # noqa: E402
from api.services.gabarits import tests_generes as TG  # noqa: E402


async def _client_installe_sans(base_essai, db_session, *manquants: str):
    from api.tests.mark.partie_1.test_l17_gabarit import _client_avec_sa_base

    cas = await _client_avec_sa_base(db_session, base_essai)
    formulaire = {k: v for k, v in FORMULAIRE_COMPLET.items() if k not in manquants}
    resultat = await I.installer_un_restaurant(cas.user, cas.org, formulaire, nom_base=base_essai)
    assert resultat["echec"] is None, resultat["echec"]
    cas.application = resultat["application"]
    return cas


async def test_donnee_b_saisie_apres_installation_passe_au_vert(db_session, base_essai):  # noqa: F811
    """S7 : installé sans temps de préparation ni capacité de réservation (permis, D10), le test « Donnée à renseigner » est rouge ; saisis à l'écran (dans
    la BASE), il passe au vert (source : ``faits_de_l_etablissement`` ne lisait que la carte et les horaires, le contrôle relisait le formulaire figé) ;
    à l'inverse une donnée du formulaire vidée en base redevient manquante."""
    from api.db.bases_clients.restauration_formulaire import faits_de_l_etablissement

    cas = await _client_installe_sans(base_essai, db_session, "temps_de_preparation", "reservation")
    etab = cas.application["formulaire"]["etablissement_id"]

    def rouges(bilan):
        return {r["slug"] for r in bilan["rouges"]}

    avant = rouges(await TG.jouer_les_tests_du_code(cas.org, cas.application))
    assert {"genere-donnee-temps-de-preparation", "genere-donnee-reservation-capacite", "genere-donnee-reservation-duree",
            "genere-donnee-reservation-creneaux"} <= {s.replace("_", "-").replace(".", "-") for s in avant}, avant
    c = await schema.connecter_proprietaire(base_essai)
    try:
        await c.execute("UPDATE mark.resto_reglage_type SET delai_annonce = 20 WHERE site_id = $1 AND type IN ('emporter', 'livraison')", etab)
        await c.execute("INSERT INTO mark.resto_regle_reservation (site_id, couverts_simultanes) VALUES ($1, 20) ON CONFLICT (site_id) DO UPDATE SET couverts_simultanes = 20", etab)
        await c.execute("INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 20, 90)", etab)
        await c.execute("INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, 'Soir', '{1,2,3}', '19:00', '22:00', 30)", etab)
    finally:
        await c.close()
    apres = {s.replace("_", "-").replace(".", "-") for s in rouges(await TG.jouer_les_tests_du_code(cas.org, cas.application))}
    assert not {s for s in apres if s.startswith("genere-donnee-temps") or s.startswith("genere-donnee-reservation")}, apres
    # à l'inverse : les horaires du formulaire vidés en base redeviennent manquants
    c = await schema.connecter_proprietaire(base_essai)
    try:
        await c.execute("DELETE FROM mark.horaire WHERE site_id = $1", etab)
        faits = await faits_de_l_etablissement(c, etab)
    finally:
        await c.close()
    assert "horaires" in F.controler(cas.application["formulaire"], faits).b_manquer
