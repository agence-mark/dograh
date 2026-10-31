"""[.mark] Builder, revue R6 et N4 : des écritures simultanées ne se perdent pas ; la conversation est bornée en octets.

Chaque test ENTRELACE les écritures (la lecture rend la main à la boucle avant de répondre) : sans la condition d'écriture, la
seconde écraserait la première. Le « vrai » test de la base vérifie la condition elle-même sur PostgreSQL.

| Test | Ce qu'il prouve |
|---|---|
| stock.modifier | cinq ajouts simultanés sur une même ligne : cinq ajouts gardés |
| base | ``compare_and_set_configuration`` : écrit si la valeur est celle lue, sinon refuse ; création concurrente détectée |
| verrou | deux demandes simultanées : une seule obtient le verrou de la conversation |
| révision | une conversation lue avant l'écriture d'un autre est refusée proprement, rien n'est écrasé |
| fiche, dépôts, usage, propositions | deux écritures simultanées : les deux sont là |
| N4 | la conversation enregistrée ne dépasse jamais 1 Mo, les plus vieux messages passent au résumé |
"""

from __future__ import annotations

import asyncio
import json

import pytest

from api.services.builder import contexte, fiche, stock
from api.services.builder.constantes import CONVERSATION_OCTETS_MAX
from api.services.builder.dossiers import base as base_de_connaissances
from api.services.builder.dossiers import depot
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT


@pytest.fixture
def entrelace(monde, monkeypatch):
    """Le monde simulé, où chaque lecture d'une ligne rend la main avant de répondre : les écritures s'entrelacent vraiment."""
    vrai = monde.get_configuration

    async def lecture_lente(organization_id, key):
        ligne = await vrai(organization_id, key)
        await asyncio.sleep(0)
        return ligne

    monkeypatch.setattr(monde, "get_configuration", lecture_lente)
    return monde


async def test_cinq_ajouts_simultanes_sur_une_meme_ligne_sont_tous_gardes(entrelace):
    def ajouter(n):
        return lambda courant: {"n": [*(courant or {}).get("n", []), n]}

    await asyncio.gather(*(stock.modifier(ORG_CLIENT, "MARK_T:x", ajouter(i)) for i in range(5)))
    assert sorted((await stock.lire(ORG_CLIENT, "MARK_T:x"))["n"]) == list(range(5))


async def test_une_ligne_qui_bouge_sans_cesse_est_dite_pas_perdue_en_silence(entrelace, monkeypatch):
    async def toujours_refuse(*a, **k):
        return False

    monkeypatch.setattr(entrelace, "compare_and_set_configuration", toujours_refuse)
    with pytest.raises(stock.ConflitDEcriture):
        await stock.modifier(ORG_CLIENT, "MARK_T:y", lambda courant: {"v": 1})


async def test_la_condition_d_ecriture_de_la_vraie_base(db_session):
    user, _ = await db_session.get_or_create_user_by_provider_id("concurrence_user")
    org, _ = await db_session.get_or_create_organization_by_provider_id("concurrence_org", user.id)
    cas = db_session.compare_and_set_configuration
    assert await cas(org.id, "MARK_C:1", None, {"v": 1}) is True  # création
    assert await cas(org.id, "MARK_C:1", None, {"v": 2}) is False  # quelqu'un l'a déjà créée : refusé, pas écrasé
    assert (await db_session.get_configuration(org.id, "MARK_C:1")).value == {"v": 1}
    assert await cas(org.id, "MARK_C:1", {"v": 0}, {"v": 3}) is False  # lue sur une valeur périmée
    assert await cas(org.id, "MARK_C:1", {"v": 1}, {"v": 4}) is True
    assert (await db_session.get_configuration(org.id, "MARK_C:1")).value == {"v": 4}
    assert await cas(org.id, "MARK_C:absente", {"v": 1}, {"v": 5}) is False  # attendait une ligne qui n'existe pas


async def test_deux_demandes_simultanees_une_seule_obtient_le_verrou(entrelace):
    resultats = await asyncio.gather(*(contexte.prendre_le_verrou(ORG_CLIENT, AGENT, 600.0) for _ in range(5)))
    prises = [r for r in resultats if r is not None]
    assert len(prises) == 1 and prises[0]["en_cours_depuis"]
    # un verrou périmé se reprend
    reprise = await contexte.prendre_le_verrou(ORG_CLIENT, AGENT, 600.0, maintenant=prises[0]["en_cours_depuis"] + 601)
    assert reprise is not None


async def test_une_conversation_lue_avant_l_ecriture_d_un_autre_est_refusee_sans_rien_ecraser(entrelace):
    a = await contexte.charger(ORG_CLIENT, AGENT)
    b = await contexte.charger(ORG_CLIENT, AGENT)
    a["messages"].append({"role": "user", "content": "de A"})
    await contexte.enregistrer(ORG_CLIENT, AGENT, a)
    b["messages"].append({"role": "user", "content": "de B"})
    with pytest.raises(contexte.ConflitDeRevision):
        await contexte.enregistrer(ORG_CLIENT, AGENT, b)
    garde = await contexte.charger(ORG_CLIENT, AGENT)
    assert [m["content"] for m in garde["messages"]] == ["de A"]
    # et celle de A, relue, s'écrit de nouveau
    garde["messages"].append({"role": "user", "content": "suite"})
    await contexte.enregistrer(ORG_CLIENT, AGENT, garde)
    assert len((await contexte.charger(ORG_CLIENT, AGENT))["messages"]) == 2


async def test_deux_ecritures_simultanees_de_la_fiche_sont_toutes_les_deux_la(entrelace):
    ligne = lambda valeur: fiche.ChampFiche(valeur=valeur, source="audit.pdf, p. 1", classement="objet")  # noqa: E731
    await asyncio.gather(
        fiche.ecrire(ORG_CLIENT, AGENT, {"horaires": ligne("9h-18h")}),
        fiche.ecrire(ORG_CLIENT, AGENT, {"adresse": ligne("1 rue de l'Essai")}),
    )
    assert set((await fiche.lire(ORG_CLIENT, AGENT)).champs) == {"horaires", "adresse"}


async def test_deux_depots_simultanes_sont_tous_les_deux_dans_l_index(entrelace):
    def un(nom):
        return {"id": nom, "nom": nom, "genre": "fichier"}

    await asyncio.gather(depot._ajouter_a_l_index(ORG_CLIENT, AGENT, un("a.pdf")), depot._ajouter_a_l_index(ORG_CLIENT, AGENT, un("b.pdf")))
    assert {d["nom"] for d in await depot.lister(ORG_CLIENT, AGENT)} == {"a.pdf", "b.pdf"}
    # le même nom déposé deux fois en même temps : un seul passe, l'autre est refusé
    resultats = await asyncio.gather(
        depot._ajouter_a_l_index(ORG_CLIENT, AGENT, un("c.pdf")), depot._ajouter_a_l_index(ORG_CLIENT, AGENT, {**un("C.PDF"), "id": "x"}), return_exceptions=True
    )
    assert sum(isinstance(r, depot.ErreurDepot) for r in resultats) == 1
    assert len(await depot.lister(ORG_CLIENT, AGENT)) == 3


async def test_deux_agents_qui_appliquent_le_meme_element_s_ajoutent_tous_les_deux(entrelace, monkeypatch):
    from api.services.builder.bibliotheque import service

    await asyncio.gather(
        service.enregistrer_utilisation("regles", "x", 1, ORG_CLIENT, 11), service.enregistrer_utilisation("regles", "x", 1, ORG_CLIENT, 12)
    )
    assert sorted(u["agent"] for u in await service.utilisation("regles", "x")) == [11, 12]


async def test_deux_propositions_de_base_simultanees_sont_toutes_les_deux_la(entrelace, monkeypatch):
    monkeypatch.setattr(base_de_connaissances, "verifier", lambda *a, **k: None)

    async def aucun_texte(*a, **k):
        return {}

    monkeypatch.setattr(base_de_connaissances, "textes_deposes", aucun_texte)
    source = base_de_connaissances.SourceCitee(document="audit.pdf", page=1, extrait="Question de la FAQ ?")
    await asyncio.gather(
        base_de_connaissances.proposer(ORG_CLIENT, AGENT, "FAQ", "Question ?", [source], "evan"),
        base_de_connaissances.proposer(ORG_CLIENT, AGENT, "Conditions", "Texte.", [source], "evan"),
    )
    assert {d.titre for d in await base_de_connaissances.lister(ORG_CLIENT, AGENT)} == {"FAQ", "Conditions"}


# --- N4 : la conversation enregistrée est bornée en octets ------------------------------------------------------------------------------


def _conversation_lourde(tours: int, taille: int) -> dict:
    messages = []
    for i in range(tours):
        messages.append({"role": "user", "content": f"demande {i} " + "x" * taille})
        messages.append({"role": "assistant", "content": f"réponse {i} " + "y" * taille})
    return {**contexte.conversation_vide(), "messages": messages}


def test_la_conversation_depassant_un_mega_octet_est_ramenee_dessous_les_plus_vieux_au_resume():
    conv = _conversation_lourde(60, 30_000)  # ~3,6 Mo pour 120 messages (sous le plafond de lignes)
    assert len(json.dumps(conv).encode()) > CONVERSATION_OCTETS_MAX
    contexte.borner(conv)
    assert len(json.dumps(conv, ensure_ascii=False).encode()) <= CONVERSATION_OCTETS_MAX
    assert conv["messages"][0]["role"] == "user"  # on coupe à une frontière de tour
    assert conv["messages"][-1]["content"].startswith("réponse 59")  # les plus récents restent
    assert "Demande :" in conv["resume"]  # les plus vieux sont passés au résumé


def test_un_message_seul_plus_gros_que_le_plafond_est_raccourci():
    conv = {**contexte.conversation_vide(), "messages": [{"role": "user", "content": "z" * 2_000_000}]}
    contexte.borner(conv)
    assert len(json.dumps(conv).encode()) <= CONVERSATION_OCTETS_MAX


def test_une_conversation_sous_le_plafond_n_est_pas_touchee():
    conv = _conversation_lourde(3, 100)
    avant = json.dumps(conv, sort_keys=True)
    contexte.borner(conv)
    assert json.dumps(conv, sort_keys=True) == avant


async def test_l_enregistrement_applique_le_plafond_en_octets(entrelace):
    conv = _conversation_lourde(60, 30_000)
    await contexte.enregistrer(ORG_CLIENT, AGENT, conv)
    brut = entrelace.configs[(ORG_CLIENT, f"MARK_BUILDER:{AGENT}:conversation")]
    assert len(json.dumps(brut, ensure_ascii=False).encode()) <= CONVERSATION_OCTETS_MAX


# --- les dernières familles de stockage (revue R6, suite) ----------------------------------------------------------


async def test_deux_candidats_notes_en_meme_temps_sont_tous_deux_gardes(entrelace):
    await asyncio.gather(
        contexte.noter_un_candidat(ORG_CLIENT, AGENT, "etape", "a", 1),
        contexte.noter_un_candidat(ORG_CLIENT, AGENT, "etape", "b", 1),
        contexte.ecrire_notes(ORG_CLIENT, AGENT, "des notes"),
    )
    ligne = await contexte.lire_contexte_agent(ORG_CLIENT, AGENT)
    assert sorted(c["slug"] for c in ligne["candidats"]) == ["a", "b"]
    assert ligne["notes"] == "des notes"


async def test_des_resultats_et_des_notes_de_test_simultanes_ne_se_perdent_pas(entrelace):
    from api.services.builder.tests_agent import juge, stockage

    await asyncio.gather(*(stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, "t", {"n": i}) for i in range(3)))
    assert sorted(e["n"] for e in await stockage.resultats(ORG_CLIENT, AGENT, "t")) == [0, 1, 2]

    await asyncio.gather(*(juge.noter(ORG_CLIENT, AGENT, f"id{i}", True) for i in range(4)))
    assert sorted(n["id"] for n in await juge.notes(ORG_CLIENT, AGENT)) == ["id0", "id1", "id2", "id3"]


async def test_deux_versions_testees_en_meme_temps_prennent_deux_numeros_de_correction(entrelace):
    from api.services.builder.tests_agent import boucle

    graphes = [{"nodes": [{"id": str(i)}], "edges": []} for i in range(3)]
    await asyncio.gather(*(boucle.noter_la_version_testee(ORG_CLIENT, AGENT, g, i + 1, True) for i, g in enumerate(graphes)))
    ids = sorted(e["id"] for e in await boucle.lire_les_corrections(ORG_CLIENT, AGENT))
    assert ids == ["c1", "c2", "c3"]


async def test_la_conception_decidee_pendant_une_ecriture_garde_une_revision_coherente(entrelace):
    from api.services.builder import conception

    doc = conception.Conception(objectif="o", reussite="r")
    await conception.ecrire(ORG_CLIENT, AGENT, doc)
    await asyncio.gather(
        conception.ecrire(ORG_CLIENT, AGENT, doc),
        conception.ecrire(ORG_CLIENT, AGENT, doc),
        conception.ecrire(ORG_CLIENT, AGENT, doc),
    )
    assert (await conception.lire(ORG_CLIENT, AGENT)).revision == 4


async def test_deux_lots_d_operations_simultanes_sont_tous_deux_en_attente(entrelace):
    from api.services.builder import brouillon

    def ajouter(op):
        return lambda etat: {"operations": [*etat["operations"], op], "base_version": 3}

    await asyncio.gather(*(brouillon.modifier_en_attente(ORG_CLIENT, AGENT, ajouter({"op": f"o{i}"})) for i in range(4)))
    etat = await brouillon.lire_en_attente(ORG_CLIENT, AGENT)
    assert sorted(o["op"] for o in etat["operations"]) == ["o0", "o1", "o2", "o3"]


async def test_deux_ajouts_de_version_simultanes_gardent_chacun_leur_numero(entrelace):
    from api.services.builder.bibliotheque import service

    await service.creer("moules-etape", "x", "X", {"texte": "v1"}, "moi")
    await asyncio.gather(*(service.ajouter_version("moules-etape", "x", {"texte": f"v{i}"}, "moi") for i in (2, 3)))
    element = await service.lire_element("moules-etape", "x")
    assert sorted(v.numero for v in element.versions) == [1, 2, 3]


async def test_deux_acceptations_simultanees_d_une_proposition_ajoutent_une_seule_version(entrelace):
    from api.services.builder.bibliotheque import propositions, service
    from api.services.builder.bibliotheque.service import ErreurBibliotheque

    await service.creer("moules-etape", "p", "P", {"texte": "v1"}, "moi")
    proposition = await propositions.creer("version", "moules-etape", "p", "mieux", "builder", contenu={"texte": "v2"})
    resultats = await asyncio.gather(
        propositions.accepter(proposition.id, "alice"), propositions.accepter(proposition.id, "bob"), return_exceptions=True
    )
    assert sum(isinstance(r, ErreurBibliotheque) and r.statut == 409 for r in resultats) == 1
    assert [v.numero for v in (await service.lire_element("moules-etape", "p")).versions] == [1, 2]
    assert (await propositions.lire(proposition.id)).etat == "acceptee"


async def test_une_acceptation_dont_l_effet_echoue_remet_la_proposition_en_attente(entrelace, monkeypatch):
    from api.services.builder.bibliotheque import propositions, service

    await service.creer("moules-etape", "q", "Q", {"texte": "v1"}, "moi")
    proposition = await propositions.creer("version", "moules-etape", "q", "mieux", "builder", contenu={"texte": "v2"})

    async def casse(*a, **k):
        raise RuntimeError("panne")

    with monkeypatch.context() as m:
        m.setattr(service, "ajouter_version", casse)
        with pytest.raises(RuntimeError):
            await propositions.accepter(proposition.id, "alice")
    assert (await propositions.lire(proposition.id)).etat == "en_attente"
    assert (await propositions.accepter(proposition.id, "alice")).etat == "acceptee"
