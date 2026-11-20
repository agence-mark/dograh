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


# --------------------------------------------------------------------------- S8


async def _problemes_de_la_commande(cas) -> dict[str, str]:
    from api.services.builder.tests_agent import publication as garde

    wid = cas.application["agents"]["commande"]
    brouillon = await db_client.get_draft_version(wid)
    problemes = await garde.problemes_des_tests_obligatoires(cas.org, wid, brouillon.version_number, garde.empreinte_du_brouillon_publie(brouillon))
    return {p["slug"]: p["code"] for p in problemes}


async def test_article_change_rend_son_test_a_rejouer(installe):
    """S8 : la carte change (un article ajouté à l'écran, qui monte la version de la carte) : le nouvel article a SON test, et les tests d'articles déjà verts
    sont à rejouer (source : ``carte_version`` écrit dans chaque test, lu nulle part ; la porte restait verte sans test du nouvel article)."""
    from api.services.builder.tests_agent import stockage

    await TG.jouer_les_tests_du_code(installe.org, installe.application)
    wid = installe.application["agents"]["commande"]
    articles = sorted(t["slug"] for t in await stockage.lister(installe.org, wid) if (t.get("genere") or {}).get("genre") == "article")
    assert articles and not [s for s in await _problemes_de_la_commande(installe) if s in articles]  # verts avant
    c = await schema.connecter_proprietaire(installe.base)
    try:
        etab = installe.application["formulaire"]["etablissement_id"]
        await c.execute("INSERT INTO mark.resto_produit (site_id, portee, ref, nom) VALUES ($1, 'etablissement', 'S8-NEUF', 'Calzone du jour')", etab)
    finally:
        await c.close()
    apres = await _problemes_de_la_commande(installe)
    assert apres.get("genere-article-s8-neuf") == "test_jamais_rejoue", apres  # le nouvel article a son test, jamais joué
    assert all(apres.get(s) == "test_jamais_rejoue" for s in articles), apres  # les anciens sont à rejouer


# --------------------------------------------------------------------------- S6


async def test_reprise_avec_un_autre_formulaire_repart_de_zero(db_session, base_essai, monkeypatch):  # noqa: F811
    """S6 : une installation coupée après la création du groupe du restaurant A, reprise avec le formulaire du restaurant B : elle repart de zéro (l'empreinte
    du formulaire noté au progrès a changé) au lieu de garder la clé et les agents de A sous le formulaire de B (source : la reprise lisait ``etablissement_id``
    et ``etapes_ecrites`` du progrès sans jamais se demander s'il était du même formulaire)."""
    import asyncio

    from api.services.installation_client import moteur
    from api.tests.mark.partie_1.test_l17_gabarit import _client_avec_sa_base

    cas = await _client_avec_sa_base(db_session, base_essai)
    vraie = I.appliquer_les_reglages

    async def coupee(*a, **k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(I, "appliquer_les_reglages", coupee)
    with pytest.raises(asyncio.CancelledError):
        await I.installer_un_restaurant(cas.user, cas.org, FORMULAIRE_COMPLET, nom_base=base_essai)
    monkeypatch.setattr(I, "appliquer_les_reglages", vraie)
    monkeypatch.setattr(moteur, "BAIL_S", 0)
    b = {**FORMULAIRE_COMPLET, "nom_etablissement": "Chez Autre", "adresse": {"voie": "1 rue Autre", "code_postal": "60100", "commune": "Creil", "insee": "60175"}}
    resultat = await I.installer_un_restaurant(cas.user, cas.org, b, nom_base=base_essai)
    assert resultat["echec"] is None, resultat["echec"]
    application = resultat["application"]
    assert application["formulaire"]["cle"] == "chez-autre"
    principal = await db_client.get_workflow(application["workflow_id"], organization_id=cas.org)
    assert principal.name == "Chez Autre · accueil"
    c = await schema.connecter(base_essai)
    try:
        assert await c.fetchval("SELECT adresse_commune FROM mark.site WHERE cle = 'chez-autre'") == "Creil"
    finally:
        await c.close()
