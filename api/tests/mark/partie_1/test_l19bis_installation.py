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


# --------------------------------------------------------------------------- S2


async def test_test_genere_ni_supprime_ni_relache(installe):
    """S2 : un test généré (la porte d'acceptation) ne se supprime ni ne se modifie (obligatoire retiré, critères réécrits) hors ``regenerer`` ; et la position
    « éteint » du contrôle « Tests obligatoires » ne vide pas la porte d'un agent installé (source : ``DELETE``, ``PATCH`` et la position ne regardaient
    jamais l'origine du test ; plus aucun test rouge, ``forcage_permis`` rendait vrai pour tous)."""
    from fastapi import HTTPException

    from api.routes.builder_tests import supprimer_un_test
    from api.services.builder.tests_agent import creation, stockage
    from api.services.builder.tests_agent import publication as garde

    wid = installe.application["agents"]["commande"]
    slug = "genere-mode-emporter"
    with pytest.raises(HTTPException) as refus:
        await supprimer_un_test(wid, slug, user=installe.user)
    assert refus.value.status_code == 409
    with pytest.raises(stockage.ErreurTest):
        await creation.modifier(installe.org, wid, slug, obligatoire=False)
    with pytest.raises(stockage.ErreurTest):
        await creation.modifier(installe.org, wid, slug, criteres=[{"type": "issue", "attendue": "n'importe quoi"}])
    assert (await stockage.lire(installe.org, wid, slug))["obligatoire"] is True
    # la position « éteint » : la porte reste fermée tant qu'un test généré est rouge, jamais joué
    brouillon = await db_client.get_draft_version(wid)
    reglages = {**(brouillon.workflow_configurations or {}), "publication": {"controles": {"tests_obligatoires": "eteint"}}}
    await db_client.update_workflow(workflow_id=wid, name=None, workflow_definition=None, template_context_variables=None, workflow_configurations=reglages,
                                    organization_id=installe.org)
    agent = await db_client.get_workflow(wid, organization_id=installe.org)
    brouillon = await db_client.get_draft_version(wid)
    refus = await garde.verifier_avant_publication(agent, brouillon, installe.org, installe.user.id)
    assert refus is not None and any(t["slug"] == slug for t in refus["tests_obligatoires"]), refus


# --------------------------------------------------------------------------- S1


async def _tests_marques(cas, wid: int, statut: str) -> None:
    """Les tests de l'agent marqués joués sur son brouillon COURANT (celui de la branche ouverte), avec ce statut (aucune requête au modèle)."""
    from api.services.builder.tests_agent import boucle, stockage

    b = await db_client.get_draft_version(wid)
    emp = boucle.empreinte_du_brouillon(b.workflow_json, b.workflow_configurations)
    for t in await stockage.lister(cas.org, wid):
        await stockage.ajouter_un_resultat(cas.org, wid, t["slug"], {"le": stockage.maintenant(), "version": b.version_number, "empreinte": emp,
                                                                     "statut": statut, "reussis": 1 if statut == "ok" else 0, "total": 1})


async def test_publier_une_branche_passe_par_la_porte(installe):
    """S1 : la publication d'une branche et la fusion dans la principale passent par la porte (tests obligatoires, rejoués sur CE brouillon) comme la
    publication directe (source : ``verifier_avant_publication`` n'avait qu'un appelant ; une branche rouge se publiait et se fusionnait sans test). Le
    forçage d'une porte aux tests générés rouges reste à l'équipe .mark."""
    import json

    from api.db import branche_ouverte
    from api.db.branches_client import ErreurDeBranche
    from api.services.branches import fusion, service
    from api.services.gabarits import diffusion as D

    wid = installe.application["agents"]["commande"]
    agent = await db_client.get_workflow(wid, organization_id=installe.org)
    definition = json.loads(json.dumps((await db_client.get_draft_version(wid)).workflow_json))
    await db_client.publish_workflow_draft(wid)  # une version en ligne sur la principale (la fusion en a besoin)
    branche = await D._ecrire_sur_une_branche(installe.org, wid, installe.user.id, "Essai de la porte", definition)
    assert branche["etat"] == "branche_prete"
    # 1. publication : tests jamais rejoués sur le brouillon de la branche : refusée
    with pytest.raises(ErreurDeBranche) as refus:
        await service.publier(installe.org, agent, branche["branche_id"], installe.user.id, user=installe.user)
    assert refus.value.code == "porte" and "[Required test]" in str(refus.value)
    # 2. tests verts sur le brouillon de la branche : il ne reste plus de test rouge ; ce que la porte dit encore (les modèles de l'organisation de test) se force avec une raison
    #    écrite, journalisée
    branche_ouverte.ouvrir(branche["branche_id"], installe.user.id)
    try:
        await _tests_marques(installe, wid, "ok")
    finally:
        branche_ouverte.ouvrir(None, None)
    with pytest.raises(ErreurDeBranche) as encore:
        await service.publier(installe.org, agent, branche["branche_id"], installe.user.id, user=installe.user)
    assert "[Required test]" not in str(encore.value)
    version = await service.publier(installe.org, agent, branche["branche_id"], installe.user.id, user=installe.user, forcer=True, raison="modèles de l'organisation de test")
    assert version["version_number"]
    gestes, _ = await db_client.lister_journal(limit=20, offset=0, organization_id=installe.org, actions=["agents.publier_force"])
    assert gestes and gestes[0]["detail"]["geste"] == "branch publication"
    # 3. fusion : un test redevenu rouge la refuse (rien n'est écrit)
    from api.services.builder.tests_agent import boucle, stockage

    tete = (await db_client.lire_pour_la_fusion(installe.org, wid, branche["branche_id"], None))["tete_branche"]
    emp = boucle.empreinte_du_brouillon(tete["graphe"], tete["reglages"])
    for t in await stockage.lister(installe.org, wid):
        await stockage.ajouter_un_resultat(installe.org, wid, t["slug"], {"le": stockage.maintenant(), "version": tete["numero"], "empreinte": emp, "statut": "echec",
                                                                          "reussis": 0, "total": 1})
    apercu = await fusion.apercu_de_la_fusion(installe.org, agent, branche["branche_id"])
    with pytest.raises(ErreurDeBranche) as refus:
        await fusion.fusionner(installe.org, agent, branche["branche_id"], choix={}, relue=True, version_branche=apercu["branche"]["id_version"],
                               version_cible=apercu["cible"]["id_version"], user=installe.user)
    assert refus.value.code == "porte" and "[Required test]" in str(refus.value), refus.value


# --------------------------------------------------------------------------- S3, S4, S5 (la diffusion)

import json  # noqa: E402

from api.services.gabarits import diffusion as D  # noqa: E402
from api.services.gabarits import gabarit as G  # noqa: E402
from api.tests.mark.partie_1.test_l17_gabarit import _porte_verte  # noqa: E402,F401


def _gabarit_suivant(monkeypatch, *, version=None, textes=None, definition=None, reglages=None):
    """Une version suivante du gabarit en mémoire (les versions figées en base ne changent pas)."""
    g = G.charger()
    n = version or g.version + 1
    t, d, r = dict(textes or g.textes), definition or g.definition, reglages or g.reglages
    suivant = G.Gabarit(g.nom, n, d, t, r, G._empreinte(d, t, r, n))
    monkeypatch.setattr(G, "charger", lambda nom=G.RESTAURATION: suivant)
    return suivant


async def test_deux_diffusions_successives_sans_faux_conflit(installe, monkeypatch):
    """S3 : installé en v1, v2 diffusée puis mise en ligne (branche publiée, fusionnée), puis v3 qui change encore le même texte : AUCUN conflit (source : la
    diffusion n'écrivait ni ``gabarit_version`` ni ``retouches.base``, la base restée v1 faisait passer le texte de v2 pour une retouche du client). Ni la
    version ni la base ne bougent tant que la branche n'est pas en ligne ; à la fusion, elles suivent et les tests générés sont réécrits pour la version."""
    from api.db import branche_ouverte
    from api.services.builder.tests_agent import stockage
    from api.services.branches import fusion, service

    org, user = installe.org, installe.user
    wid = installe.agents["commande"]
    agent = await db_client.get_workflow(wid, organization_id=org)
    await _porte_verte(installe)
    v1 = G.charger().version
    texte1 = G.charger().textes["commande"]
    v2 = _gabarit_suivant(monkeypatch, textes={**G.charger().textes, "commande": texte1.replace("# Ce que tu ne fais pas ici", "# Ce que tu ne fais pas ici ZZV2")})
    ligne = await D.diffuser(user, nom="restauration", version=v2.version, portee="organisation", organization_id=org)
    r = ligne["resultat"]["agents"][str(installe.application["workflow_id"])]["commande"]
    assert r["etat"] == "branche_prete", r
    en_attente = await db_client.application_de(org, wid)
    assert en_attente["gabarit_version"] == v1 and "ZZV2" not in json.dumps(en_attente["retouches"]["base"]["commande"])  # pas en ligne : rien ne bouge
    branche_ouverte.ouvrir(r["branche_id"], user.id)
    try:
        await _tests_marques(installe, wid, "ok")
    finally:
        branche_ouverte.ouvrir(None, None)
    await service.publier(org, agent, r["branche_id"], user.id, user=user, forcer=True, raison="modèles de l'organisation de test")
    await db_client.publish_workflow_draft(wid)
    apercu = await fusion.apercu_de_la_fusion(org, agent, r["branche_id"])
    choix = {c["cle"]: "source" for c in apercu["champs"] if c["statut"] == "conflit"}  # la branche de diffusion l'emporte
    await fusion.fusionner(org, agent, r["branche_id"], choix=choix, relue=True, version_branche=apercu["branche"]["id_version"],
                           version_cible=apercu["cible"]["id_version"], user=user, forcer=True, raison="modèles de l'organisation de test")
    apres = await db_client.application_de(org, wid)
    assert apres["gabarit_version"] == v2.version and "ZZV2" in json.dumps(apres["retouches"]["base"]["commande"])
    assert {t["genere"]["gabarit"] for t in await stockage.lister(org, wid) if t.get("genere")} == {f"restauration@{v2.version}"}
    # la principale est en ligne : un brouillon repart de la version en ligne, la porte est verte, puis v3 change le même texte
    en_ligne = (await db_client.get_workflow_versions(wid, limit=1, status="published"))[0]
    await db_client.save_workflow_draft(wid, workflow_definition=en_ligne.workflow_json)
    await _porte_verte(installe)
    v3 = _gabarit_suivant(monkeypatch, version=v2.version + 1, textes={**v2.textes, "commande": v2.textes["commande"].replace("ZZV2", "ZZV3")})
    suite = await D.diffuser(user, nom="restauration", version=v3.version, portee="organisation", organization_id=org)
    r3 = suite["resultat"]["agents"][str(installe.application["workflow_id"])]["commande"]
    assert r3["etat"] == "branche_prete", r3  # avant : « conflit », le texte de v2 passait pour une retouche


async def test_diffusion_d_une_version_de_reglages(installe, monkeypatch):
    """S4 : une version qui ne change QUE les réglages du gabarit est diffusée (une branche par agent concerné, jamais « inchangé ») et ne touche pas la
    principale (source : la diffusion ne lisait jamais les réglages) ; un réglage retouché par le client que la version change aussi est un conflit."""
    from api.db import branche_ouverte

    g = G.charger()
    assert g.reglages["modele"]["relecture_des_numeros"] is False
    await _porte_verte(installe)
    nouveaux = json.loads(json.dumps(g.reglages))
    nouveaux["modele"]["relecture_des_numeros"] = True
    _gabarit_suivant(monkeypatch, reglages=nouveaux)
    ligne = await D.diffuser(installe.user, nom="restauration", version=g.version + 1, portee="organisation", organization_id=installe.org)
    r = ligne["resultat"]["agents"][str(installe.application["workflow_id"])]["accueil"]
    assert r["etat"] == "branche_prete" and "reglages:relecture_des_numeros" in r["pris"], r
    wid = installe.agents["accueil"]
    branche_ouverte.ouvrir(r["branche_id"], installe.user.id)
    try:
        sur_la_branche = (await db_client.get_draft_version(wid)).workflow_configurations
    finally:
        branche_ouverte.ouvrir(None, None)
    assert sur_la_branche["relecture_des_numeros"] is True and sur_la_branche["etablissement_id"] == installe.application["formulaire"]["cle"]
    assert (await db_client.get_draft_version(wid)).workflow_configurations["relecture_des_numeros"] is False  # la principale ne bouge pas
    # un client qui a retouché ce réglage (que la version change aussi) : conflit
    commande = installe.agents["commande"]
    brouillon = await db_client.get_draft_version(commande)
    await db_client.update_workflow(workflow_id=commande, name=None, workflow_definition=None, template_context_variables=None, organization_id=installe.org,
                                    workflow_configurations={**brouillon.workflow_configurations, "relecture_des_numeros": "retouche"})
    await _porte_verte(installe)
    nouveaux2 = json.loads(json.dumps(nouveaux))
    nouveaux2["modele"]["relecture_des_numeros"] = "deux"
    _gabarit_suivant(monkeypatch, version=g.version + 2, reglages=nouveaux2)
    suite = await D.diffuser(installe.user, nom="restauration", version=g.version + 2, portee="organisation", organization_id=installe.org)
    c = suite["resultat"]["agents"][str(installe.application["workflow_id"])]["commande"]
    assert c["etat"] == "conflit" and "reglages:relecture_des_numeros" in c["morceaux"], c


async def test_diffusion_avec_un_trou_nouveau(installe, monkeypatch):
    """S5 : une version qui ajoute un trou que le formulaire de l'application ne porte pas : la diffusion de cette application est REFUSÉE proprement (état
    « refusee », le trou nommé, la ligne du journal écrite, rien n'est écrit sur une branche), jamais un plantage au milieu (source : les trous étaient ceux
    figés à l'installation, ``TrouManquant`` n'était attrapé nulle part)."""
    await _porte_verte(installe)
    g = G.charger()
    definition = {**g.definition, "trous": {**g.trous, "pourboire": {"donnee": "pourboire_du_formulaire"}}}
    v2 = _gabarit_suivant(monkeypatch, definition=definition, textes={**g.textes, "commande": g.textes["commande"] + "\nPourboire : {{pourboire}}."})
    ligne = await D.diffuser(installe.user, nom="restauration", version=v2.version, portee="organisation", organization_id=installe.org)
    assert ligne["statut"] == "partielle"
    assert ligne["resultat"]["agents"][str(installe.application["workflow_id"])]["application"] == {"etat": "refusee", "raison": "trou_manquant", "trou": "pourboire"}
    journal = await db_client.diffusions_de("restauration", organization_id=installe.org)
    assert journal[0]["id"] == ligne["id"]
    assert not [b for b in await db_client.lister_les_branches(installe.org, installe.agents["commande"]) if b.nom.startswith("Gabarit")]


async def test_zone_sans_frais_saisis_reste_a_renseigner_apres_installation(db_session, base_essai):  # noqa: F811
    """Pierre A6 (23/11) : une zone installée sans ``frais`` (permis) écrit 0 dans une colonne NOT NULL ; la base ne distingue pas « 0 » de « non saisi » et
    ``faits_de_l_etablissement`` disait la donnée présente : la livraison devenait gratuite sans alerte. Source : la base ne peut pas dire « zones.frais_et_delai » quand
    des zones existent ; le formulaire figé fait foi (frais absents = rouge), un 0 EXPLICITE reste vert."""
    from api.tests.mark.partie_1.test_l17_gabarit import _client_avec_sa_base

    def rouges(bilan):
        return {r["slug"] for r in bilan["rouges"]}

    cas = await _client_avec_sa_base(db_session, base_essai)
    sans_frais = {**FORMULAIRE_COMPLET, "zones": [{"nom": "Pont", "communes": ["60509"], "minimum": 1500, "delai": 30}]}
    r = await I.installer_un_restaurant(cas.user, cas.org, sans_frais, nom_base=base_essai)
    assert r["echec"] is None, r["echec"]
    assert "genere-donnee-zones-frais-et-delai" in {s.replace("_", "-").replace(".", "-") for s in rouges(await TG.jouer_les_tests_du_code(cas.org, r["application"]))}
