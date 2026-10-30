"""[.mark] builder-agent-vocal, lot 2 : la bibliothèque (versions, retour arrière, statuts, import, propositions).

Ce qui doit tenir : une ligne par élément dans l'organisation .mark ; chaque modification est une version (auteur,
date, notes) ; un retour arrière AJOUTE une version et ne perd rien ; Recette exige un banc, Rejeté une raison ;
une recette modifiée n'est plus une recette ; un réimport rend le comparatif de ce qui a changé ; une proposition
attend une personne ; « utilisée par N agents » se lit sans parcourir les clients.
"""

from __future__ import annotations

import pytest

from api.services.builder.bibliotheque import importation, propositions, service
from api.services.builder.bibliotheque.modele import Banc, Origine, Statut
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.tests.mark.builder_commun import ORG_CLIENT, ORG_MARK

FAMILLE = "moules-etape"


async def test_un_element_est_une_ligne_de_l_organisation_mark(monde):
    await service.creer(FAMILLE, "qualifier", "Qualifier", {"texte": "v1"}, "alice")
    assert (ORG_MARK, "MARK_BIBLIO:moules-etape:qualifier") in monde.configs
    # Rien n'est rangé dans l'organisation du client.
    assert not [cle for (org, cle) in monde.configs if org == ORG_CLIENT]


async def test_chaque_modification_est_une_version_avec_auteur_et_date(monde):
    await service.creer(FAMILLE, "qualifier", "Qualifier", {"texte": "v1"}, "alice")
    element = await service.ajouter_version(FAMILLE, "qualifier", {"texte": "v2"}, "bob", notes="plus court")
    assert [v.numero for v in element.versions] == [1, 2]
    assert element.version_courante == 2
    assert (element.courante.auteur, element.courante.notes) == ("bob", "plus court")
    assert element.versions[0].contenu == {"texte": "v1"}


async def test_un_retour_arriere_ajoute_une_version_et_ne_perd_rien(monde):
    await service.creer(FAMILLE, "qualifier", "Qualifier", {"texte": "v1"}, "alice")
    await service.ajouter_version(FAMILLE, "qualifier", {"texte": "v2"}, "bob")
    element = await service.retour_arriere(FAMILLE, "qualifier", 1, "carol")
    assert len(element.versions) == 3
    assert element.courante.contenu == {"texte": "v1"}
    assert element.courante.restaure_de == 1
    assert element.versions[1].contenu == {"texte": "v2"}  # la version écartée reste dans l'historique


async def test_recette_exige_un_banc_et_rejet_une_raison(monde):
    await service.creer(FAMILLE, "qualifier", "Qualifier", {"texte": "v1"}, "alice")
    with pytest.raises(ErreurBibliotheque):
        await service.marquer(FAMILLE, "qualifier", 1, Statut.RECETTE, "alice")
    with pytest.raises(ErreurBibliotheque):
        await service.marquer(FAMILLE, "qualifier", 1, Statut.REJETE, "alice", raison="  ")
    element = await service.marquer(FAMILLE, "qualifier", 1, Statut.RECETTE, "alice", banc=Banc(description="v12, 31 propres sur 39"))
    assert element.statut is Statut.RECETTE and element.courante.banc.description.startswith("v12")
    element = await service.marquer(FAMILLE, "qualifier", 1, Statut.REJETE, "alice", raison="ne tient pas au banc")
    assert element.statut is Statut.REJETE and element.courante.raison_rejet == "ne tient pas au banc"


async def test_une_recette_modifiee_redevient_candidate_et_la_restauration_rend_la_preuve(monde):
    await service.creer(FAMILLE, "qualifier", "Qualifier", {"texte": "v1"}, "alice")
    await service.marquer(FAMILLE, "qualifier", 1, Statut.RECETTE, "alice", banc=Banc(description="banc A"))
    element = await service.ajouter_version(FAMILLE, "qualifier", {"texte": "v2"}, "bob")
    assert element.statut is Statut.CANDIDAT
    restauree = await service.retour_arriere(FAMILLE, "qualifier", 1, "bob")
    assert restauree.statut is Statut.RECETTE and restauree.courante.banc.description == "banc A"


async def test_au_dela_de_vingt_versions_les_plus_anciennes_partent_sauf_la_prouvee(monde):
    await service.creer(FAMILLE, "qualifier", "Qualifier", {"n": 0}, "alice")
    await service.marquer(FAMILLE, "qualifier", 1, Statut.RECETTE, "alice", banc=Banc(description="banc"))
    for n in range(1, 25):
        element = await service.ajouter_version(FAMILLE, "qualifier", {"n": n}, "alice")
    numeros = [v.numero for v in element.versions]
    assert len(numeros) == 20 and 1 in numeros and element.version_courante == 25


async def test_un_contenu_trop_gros_ou_une_famille_inconnue_sont_refuses(monde):
    with pytest.raises(ErreurBibliotheque):
        await service.creer(FAMILLE, "gros", "Gros", {"texte": "x" * 11_000}, "alice")
    with pytest.raises(ErreurBibliotheque) as erreur:
        await service.creer("famille-inconnue", "a", "A", {}, "alice")
    assert erreur.value.statut == 404


async def test_le_builder_ne_modifie_que_des_candidats(monde):
    cree = await service.ecrire_candidat(FAMILLE, "qualifier", "Qualifier", {"texte": "v1"}, "builder")
    assert cree.statut is Statut.CANDIDAT
    await service.ecrire_candidat(FAMILLE, "qualifier", "Qualifier", {"texte": "v2"}, "builder")
    await service.marquer(FAMILLE, "qualifier", 2, Statut.RECETTE, "alice", banc=Banc(description="banc"))
    with pytest.raises(ErreurBibliotheque) as erreur:
        await service.ecrire_candidat(FAMILLE, "qualifier", "Qualifier", {"texte": "v3"}, "builder")
    assert erreur.value.statut == 403


async def test_la_liste_filtre_par_statut_et_compte_les_agents(monde):
    await service.creer(FAMILLE, "a", "A", {"t": 1}, "alice")
    await service.creer(FAMILLE, "b", "B", {"t": 2}, "alice")
    await service.marquer(FAMILLE, "b", 1, Statut.RECETTE, "alice", banc=Banc(description="banc"))
    await service.enregistrer_utilisation(FAMILLE, "b", 1, ORG_CLIENT, 42)
    await service.enregistrer_utilisation(FAMILLE, "b", 1, ORG_CLIENT, 43)
    await service.enregistrer_utilisation(FAMILLE, "b", 1, ORG_CLIENT, 43)  # le même agent ne compte qu'une fois
    recettes = await service.lister(FAMILLE, Statut.RECETTE)
    assert [(r.slug, r.utilisee_par) for r in recettes] == [("b", 2)]
    assert {r.slug for r in await service.lister(FAMILLE)} == {"a", "b"}


async def test_sans_organisation_de_bibliotheque_la_liste_est_vide_et_l_ecriture_refusee(monde, monkeypatch):
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    assert await service.lister() == []
    with pytest.raises(ErreurBibliotheque) as erreur:
        await service.creer(FAMILLE, "a", "A", {}, "alice")
    assert erreur.value.statut == 503


# --- import avec origine, licence, date ; comparatif au réimport -----------------------------------------------------


ORIGINE = Origine(source="https://exemple.test/guide", licence="MIT", date="2026-10-31")


async def test_un_import_garde_son_origine_et_un_reimport_rend_le_comparatif(monde):
    premier = await importation.importer("regles-redaction", "guide", "Guide", {"texte": "a\nb"}, ORIGINE, "alice")
    assert premier["cree"] and premier["element"].courante.origine == ORIGINE
    assert premier["element"].statut is Statut.CANDIDAT

    inchange = await importation.importer("regles-redaction", "guide", "Guide", {"texte": "a\nb"}, ORIGINE, "alice")
    assert inchange["comparatif"]["identique"] and len(inchange["element"].versions) == 1

    change = await importation.importer("regles-redaction", "guide", "Guide", {"texte": "a\nc"}, ORIGINE, "alice")
    assert not change["comparatif"]["identique"]
    assert change["comparatif"]["ajoutees"] >= 1 and change["comparatif"]["retirees"] >= 1
    assert len(change["element"].versions) == 2 and change["element"].courante.origine.licence == "MIT"


async def test_un_reimport_fait_retomber_une_recette_en_candidat(monde):
    await importation.importer("regles-redaction", "guide", "Guide", {"texte": "a"}, ORIGINE, "alice")
    await service.marquer("regles-redaction", "guide", 1, Statut.RECETTE, "alice", banc=Banc(description="banc"))
    resultat = await importation.importer("regles-redaction", "guide", "Guide", {"texte": "b"}, ORIGINE, "alice")
    assert resultat["element"].statut is Statut.CANDIDAT  # le nouveau contenu n'est pas prouvé
    assert resultat["element"].versions[0].statut is Statut.RECETTE  # l'ancienne garde sa preuve


async def test_une_adresse_privee_ou_en_http_n_est_pas_lue(monde):
    for adresse in ("http://exemple.test/x", "https://127.0.0.1/x", "https://localhost/x"):
        with pytest.raises(ErreurBibliotheque):
            await importation.lire_adresse(adresse)


async def test_une_adresse_publique_est_lue_sans_redirection_et_bornee(monde, monkeypatch):
    import httpx

    async def publique(hote):
        return True

    monkeypatch.setattr(importation, "_adresses_publiques", publique)
    transport = httpx.MockTransport(lambda requete: httpx.Response(200, text="contenu de la page"))
    assert await importation.lire_adresse("https://exemple.test/p", transport=transport) == "contenu de la page"
    gros = httpx.MockTransport(lambda requete: httpx.Response(200, content=b"x" * 300_000))
    with pytest.raises(ErreurBibliotheque):
        await importation.lire_adresse("https://exemple.test/p", transport=gros)
    redirige = httpx.MockTransport(lambda requete: httpx.Response(302, headers={"location": "https://10.0.0.1/"}))
    with pytest.raises(ErreurBibliotheque):
        await importation.lire_adresse("https://exemple.test/p", transport=redirige)


# --- propositions ----------------------------------------------------------------------------------------------------


async def test_une_proposition_attend_une_personne_puis_cree_une_version_candidate(monde):
    proposition = await propositions.creer(
        "version", FAMILLE, "nouveau", "Plus clair", "builder pour alice", titre="Nouveau", contenu={"texte": "idée"}
    )
    assert [p.id for p in await propositions.lister()] == [proposition.id]
    assert await service.element_ou_none(FAMILLE, "nouveau") is None  # rien n'est écrit tant que personne n'accepte
    decidee = await propositions.accepter(proposition.id, "alice")
    assert decidee.etat == "acceptee" and decidee.decide_par == "alice"
    element = await service.lire_element(FAMILLE, "nouveau")
    assert element.statut is Statut.CANDIDAT and element.courante.contenu == {"texte": "idée"}
    assert await propositions.lister() == []
    with pytest.raises(ErreurBibliotheque):  # on ne décide pas deux fois
        await propositions.accepter(proposition.id, "alice")


async def test_un_passage_en_recette_propose_exige_un_banc_a_l_acceptation(monde):
    await service.creer(FAMILLE, "a", "A", {"t": 1}, "alice")
    sans_banc = await propositions.creer("passage_recette", FAMILLE, "a", "Tests verts", "builder", version=1)
    with pytest.raises(ErreurBibliotheque):
        await propositions.accepter(sans_banc.id, "alice")
    avec_banc = await propositions.creer("passage_recette", FAMILLE, "a", "Tests verts", "builder", version=1, banc=Banc(description="3 x 3 verts"))
    await propositions.accepter(avec_banc.id, "alice")
    assert (await service.lire_element(FAMILLE, "a")).statut is Statut.RECETTE


async def test_un_refus_garde_sa_raison_et_ne_change_rien(monde):
    await service.creer(FAMILLE, "a", "A", {"t": 1}, "alice")
    proposition = await propositions.creer("rejet", FAMILLE, "a", "Doublon", "builder", version=1)
    with pytest.raises(ErreurBibliotheque):
        await propositions.refuser(proposition.id, "alice", " ")
    refusee = await propositions.refuser(proposition.id, "alice", "Pas un doublon")
    assert refusee.etat == "refusee" and refusee.motif_refus == "Pas un doublon"
    assert (await service.lire_element(FAMILLE, "a")).statut is Statut.CANDIDAT
