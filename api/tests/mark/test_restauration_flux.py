"""[.mark] Module Restauration, lot 22 : le cœur du flux en direct (un seul émetteur, D2 ; transcription finale seulement, D11).

Vrai Redis, vraie base du client, vraie route avec la vraie authentification (clé d'API de l'organisation).

| Test | Ce qu'il prouve |
|---|---|
| le contrat des événements | chaque type du contrat § 3 est accepté avec ses champs, jamais avec un champ en plus ou en moins ; les listes fermées sont fermées ; un numéro de téléphone entier est refusé ; ``appel.tour`` ne passe pas par la voie générale |
| un événement | identifiant croissant, ``{id, type, organisation, etablissement, le, donnees}``, l'heure vient de la source d'heure de l'organisation |
| D11 | un tour provisoire n'entre pas dans le flux ; le final y entre ; le pipeline : seuls les textes finaux et les outils sont traduits |
| cloisonnement | l'événement d'une organisation ou d'un établissement n'arrive JAMAIS chez un autre, même avec le même numéro d'établissement |
| reprise | ``Last-Event-ID`` rejoue exactement ce qui a été manqué, sans perte ni doublon, aussi avec plusieurs établissements |
| bornes | le flux est borné ; une reprise plus vieille que ce qui reste dit ``flux.reprise_impossible`` |
| rôle tablette | ``appel.tour`` ne lui est jamais envoyé, le reste oui ; l'équipe reçoit tout |
| R1 | un Redis en panne ne casse pas l'émetteur ; une lecture en panne le dit au client |
| la route | 401 sans clé ; 404 pour un établissement inconnu de l'organisation (aucun flux ouvert) ; 422 mal formée ; la clé d'une autre organisation ne lit pas ; le rôle et la reprise passent |
| permission | ``conversations.voir`` au registre, ouverte à la clé ; la route est gelée dans le contrat avec le portail |
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime

import pytest
import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db.bases_clients import connexion as schema
from api.db.bases_clients.horloge import remplacer
from api.services.equipe_mark import registre_routes as registre
from api.services.restauration.appel_et_memoire import flux
from api.tests.mark.equipe_commun import client_http, creer_organisation, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_contacts_portail import _cas, _cle, seconde_base  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401

HEURE = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
TEL_MASQUE = flux.masquer_telephone("+33612345678")


@pytest.fixture(autouse=True)
def flux_court(monkeypatch):
    """Une lecture ne bloque que 150 ms et se referme après un battement : une réponse en flux se termine pour le test."""
    monkeypatch.setattr(flux, "BLOCAGE_LECTURE_MS", 150)
    monkeypatch.setattr(flux, "NB_BATTEMENTS_MAX", 1)


@pytest.fixture
async def organisations():
    """Deux numéros d'organisation neufs, leurs clés Redis vidées avant et après."""
    base = int(uuid.uuid4().int % 900_000_000) + 1000
    ids = (base, base + 1)
    r = aioredis.from_url(REDIS_URL, decode_responses=True)

    async def vider():
        for o in ids:
            for cle in await r.keys(f"mark:resto:flux:{o}:*"):
                await r.delete(cle)

    await vider()
    flux._redis = None  # un client neuf sur la boucle de CE test
    yield ids
    await vider()
    await r.aclose()
    flux._redis = None


def _evenements(sse: str) -> list[dict]:
    """Les événements d'un texte ``text/event-stream`` : ``{"curseur", "event", "data"}``."""
    sorties = []
    for bloc in sse.split("\n\n"):
        champs = dict(ligne.split(": ", 1) for ligne in bloc.split("\n") if ": " in ligne and not ligne.startswith(":"))
        if "data" in champs:
            sorties.append({"curseur": champs.get("id"), "event": champs.get("event"), "data": json.loads(champs["data"])})
    return sorties


async def _lire(organisation, etablissements, **options) -> list[dict]:
    texte = "".join([m async for m in flux.ecouter(organisation, etablissements, **options)])
    return _evenements(texte)


def _depuis_le_debut(*etablissements: int) -> str:
    return flux.encoder_curseurs({e: "0-0" for e in etablissements})


# --------------------------------------------------------------------------- le contrat des événements

EXEMPLES = {
    "appel.commence": {"appel_id": "12", "agent_id": 3, "telephone_masque": TEL_MASQUE},
    "appel.outil": {"appel_id": "12", "outil": "chercher_dans_la_liste", "statut": "appele"},
    "appel.fini": {"appel_id": "12", "motif": "Commande"},
    "commande.creee": {"numero": "8f0d6c64", "numero_court": "C12", "mode": "emporter", "heure_annoncee": HEURE, "total": 2380},
    "commande.panier": {"appel_id": "12", "version": 3},
    "commande.statut": {"numero": "8f0d6c64", "de": "nouvelle", "vers": "envoyee", "source": "agent"},
    "commande.heure": {"numero": "8f0d6c64", "heure_annoncee": HEURE},
    "ticket.imprime": {"numero": "8f0d6c64", "code": "ok"},
    "ticket.erreur": {"numero": "8f0d6c64", "code": "papier"},
    "rupture.changee": {"code_caisse": "TIRA-1", "disponible": False},
    "temps.change": {"type": "emporter"},
    "caisse.etat": {"mode": "deborde", "minutes_en_plus": 15},
    "caisse.liaison": {"etat": "ok"},
    "reservation.creee": {"reservation_id": 41},
    "reservation.changee": {"reservation_id": 41},
}


def test_chaque_type_du_contrat_est_accepte_avec_ses_champs_et_refuse_sans_eux():
    assert set(EXEMPLES) | {"appel.tour"} == set(flux.TYPES)  # les 16 types du contrat § 3, ni plus ni moins
    for type_, donnees in EXEMPLES.items():
        propres = flux.verifier(type_, donnees)
        assert set(propres) == set(donnees)
        assert all(not isinstance(v, datetime) for v in propres.values())  # les dates sont écrites en ISO
        # un champ obligatoire manquant, un champ en trop : refusés
        obligatoires, _ = flux.TYPES[type_]
        retire = {k: v for k, v in donnees.items() if k != sorted(obligatoires)[0]}
        with pytest.raises(flux.EvenementRefuse):
            flux.verifier(type_, retire)
        with pytest.raises(flux.EvenementRefuse):
            flux.verifier(type_, {**donnees, "inattendu": 1})
    assert flux.verifier("appel.tour", {"appel_id": "1", "role": "agent", "texte": "  Bonjour  "})["texte"] == "Bonjour"
    with pytest.raises(flux.EvenementRefuse):
        flux.verifier("inconnu.type", {})


def test_les_listes_fermees_et_le_numero_masque_sont_tenus():
    for type_, champ, mauvais in (
        ("appel.fini", "motif", "Autre"), ("appel.outil", "statut", "plante"), ("commande.creee", "mode", "drive"), ("commande.statut", "vers", "cuite"),
        ("commande.statut", "source", "robot"), ("temps.change", "type", "livre"), ("caisse.etat", "mode", "ferme"), ("caisse.liaison", "etat", "morte"),
    ):
        with pytest.raises(flux.EvenementRefuse):
            flux.verifier(type_, {**EXEMPLES[type_], champ: mauvais})
    for en_clair in ("+33612345678", "0612345678", "06 12 34 56 78", ""):
        with pytest.raises(flux.EvenementRefuse):
            flux.verifier("appel.commence", {**EXEMPLES["appel.commence"], "telephone_masque": en_clair})
    assert TEL_MASQUE == "+33 6 ** ** ** 78" and flux.masquer_telephone(None) == flux.NUMERO_INCONNU and flux.verifier("appel.commence", {"appel_id": "1", "agent_id": "2", "telephone_masque": flux.masquer_telephone(None)}) and "12345" not in TEL_MASQUE
    with pytest.raises(flux.EvenementRefuse):
        flux.verifier("commande.creee", {**EXEMPLES["commande.creee"], "total": 23.8})  # des centimes entiers
    with pytest.raises(flux.EvenementRefuse):
        flux.verifier("appel.tour", {"appel_id": "1", "role": "agent", "texte": "   "})
    with pytest.raises(flux.EvenementRefuse):
        flux.verifier("appel.tour", {"appel_id": "1", "role": "client", "texte": "x"})
    long = flux.verifier("appel.tour", {"appel_id": "1", "role": "agent", "texte": "x" * 5000})["texte"]
    assert len(long) == flux.LONGUEUR_TEXTE_MAX
    for faux in (0, -1, "1", None, True):
        with pytest.raises(flux.EvenementRefuse):
            flux.cle_du_flux(faux, 1)
        with pytest.raises(flux.EvenementRefuse):
            flux.cle_du_flux(1, faux)


# --------------------------------------------------------------------------- un événement


async def test_un_evenement_a_son_identifiant_son_heure_et_sa_forme(organisations):
    o, _ = organisations
    with remplacer(o, HEURE):
        un = await flux.emettre(o, 1, "commande.creee", EXEMPLES["commande.creee"])
        deux = await flux.emettre(o, 1, "commande.statut", EXEMPLES["commande.statut"], le=datetime(2026, 11, 15, 12, 5, tzinfo=UTC))
    assert un and deux and tuple(map(int, un.split("-"))) < tuple(map(int, deux.split("-")))
    lus = await _lire(o, [1], reprise=_depuis_le_debut(1))
    assert [e["event"] for e in lus] == ["commande.creee", "commande.statut"]
    premier = lus[0]["data"]
    assert set(premier) == {"id", "type", "organisation", "etablissement", "le", "donnees"}
    assert (premier["id"], premier["organisation"], premier["etablissement"], premier["le"]) == (un, o, 1, HEURE.isoformat())
    assert premier["donnees"]["total"] == 2380 and premier["donnees"]["heure_annoncee"] == HEURE.isoformat()
    assert lus[1]["data"]["le"] == "2026-11-15T12:05:00+00:00"  # l'heure donnée par l'appelant prévaut
    assert lus[1]["curseur"] == f"1:{deux}"  # le curseur de reprise est celui du dernier événement lu


async def test_appel_tour_ne_passe_pas_par_la_voie_generale(organisations):
    o, _ = organisations
    with pytest.raises(flux.EvenementRefuse):
        await flux.emettre(o, 1, "appel.tour", {"appel_id": "1", "role": "agent", "texte": "bonjour"})
    with pytest.raises(flux.EvenementRefuse):
        await flux.emettre(o, 1, "type.inconnu", {})
    assert await _lire(o, [1], reprise=_depuis_le_debut(1)) == []


# --------------------------------------------------------------------------- D11 : transcription finale seulement


async def test_un_tour_provisoire_n_entre_jamais_dans_le_flux_le_final_oui(organisations):
    o, _ = organisations
    assert await flux.emettre_tour_final(o, 1, 12, "appelant", "je voudrais une pi", final=False) is None
    assert await flux.emettre_tour_final(o, 1, 12, "appelant", "je voudrais une pizza", final=True)
    assert await flux.emettre_tour_final(o, 1, 12, "agent", "Très bien, quelle taille ?", final=True)
    assert await flux.emettre_tour_final(o, 1, 12, "appelant", "   ", final=True) is None  # un silence final : rien à montrer
    lus = await _lire(o, [1], reprise=_depuis_le_debut(1))
    assert [(e["event"], e["data"]["donnees"]["role"], e["data"]["donnees"]["texte"]) for e in lus] == [
        ("appel.tour", "appelant", "je voudrais une pizza"), ("appel.tour", "agent", "Très bien, quelle taille ?"),
    ]


def test_le_pipeline_n_est_traduit_que_pour_le_final_et_les_outils():
    traduits = [
        flux.depuis_le_pipeline({"type": "rtf-user-transcription", "payload": {"text": "une pizza", "final": True}}),
        flux.depuis_le_pipeline({"type": "rtf-user-transcription", "payload": {"text": "une pi", "final": False}}),
        flux.depuis_le_pipeline({"type": "rtf-user-transcription", "payload": {"text": "", "final": True}}),
        flux.depuis_le_pipeline({"type": "rtf-bot-text", "payload": {"text": "Quelle taille ?"}}),
        flux.depuis_le_pipeline({"type": "rtf-function-call-start", "payload": {"function_name": "chercher_dans_la_liste"}}),
        flux.depuis_le_pipeline({"type": "rtf-function-call-end", "payload": {"function_name": "chercher_dans_la_liste", "result": "x"}}),
        flux.depuis_le_pipeline({"type": "rtf-ttfb-metric", "payload": {}}),
        flux.depuis_le_pipeline({"type": "rtf-pipeline-error", "payload": {"error": "x"}}),
        flux.depuis_le_pipeline({"type": "rtf-user-mute-started", "payload": {}}),
    ]
    assert traduits == [
        ("appel.tour", {"role": "appelant", "texte": "une pizza"}), None, None,
        ("appel.tour", {"role": "agent", "texte": "Quelle taille ?"}),
        ("appel.outil", {"outil": "chercher_dans_la_liste", "statut": "appele"}),
        ("appel.outil", {"outil": "chercher_dans_la_liste", "statut": "termine"}), None, None, None,
    ]
    # ce qui est traduit est du contrat une fois l'appel ajouté
    for type_, donnees in (t for t in traduits if t):
        flux.verifier(type_, {"appel_id": "12", **donnees})


# --------------------------------------------------------------------------- cloisonnement


async def test_l_evenement_d_une_organisation_ou_d_un_etablissement_n_arrive_jamais_chez_un_autre(organisations):
    o1, o2 = organisations
    await flux.emettre(o1, 1, "temps.change", {"type": "emporter"})
    await flux.emettre(o1, 2, "temps.change", {"type": "livraison"})
    await flux.emettre(o2, 1, "temps.change", {"type": "sur_place"})  # MÊME numéro d'établissement, autre organisation
    tout = _depuis_le_debut(1, 2)
    chez_o1_etab1 = await _lire(o1, [1], reprise=tout)
    chez_o1_etab2 = await _lire(o1, [2], reprise=tout)
    chez_o2_etab1 = await _lire(o2, [1], reprise=tout)
    chez_o2_etab2 = await _lire(o2, [2], reprise=tout)
    assert [(e["data"]["organisation"], e["data"]["etablissement"], e["data"]["donnees"]["type"]) for e in chez_o1_etab1] == [(o1, 1, "emporter")]
    assert [(e["data"]["organisation"], e["data"]["etablissement"], e["data"]["donnees"]["type"]) for e in chez_o1_etab2] == [(o1, 2, "livraison")]
    assert [(e["data"]["organisation"], e["data"]["etablissement"], e["data"]["donnees"]["type"]) for e in chez_o2_etab1] == [(o2, 1, "sur_place")]
    assert chez_o2_etab2 == []
    # plusieurs établissements d'une organisation : les siens, jamais ceux d'une autre
    deux = await _lire(o1, [1, 2], reprise=tout)
    assert sorted(e["data"]["etablissement"] for e in deux) == [1, 2] and {e["data"]["organisation"] for e in deux} == {o1}
    # le flux n'écrit que dans la clé de l'organisation ET de l'établissement
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        assert sorted(await r.keys(f"mark:resto:flux:{o1}:*")) == [f"mark:resto:flux:{o1}:1", f"mark:resto:flux:{o1}:2"]
        assert await r.keys(f"mark:resto:flux:{o2}:*") == [f"mark:resto:flux:{o2}:1"]
    finally:
        await r.aclose()


# --------------------------------------------------------------------------- reprise sans perte ni doublon


async def test_la_reprise_rejoue_ce_qui_a_ete_manque_sans_perte_ni_doublon(organisations):
    o, _ = organisations
    ids = [await flux.emettre(o, 1, "caisse.liaison", {"etat": "ok"}) for _ in range(4)]
    lus = await _lire(o, [1], reprise=_depuis_le_debut(1))
    assert [e["data"]["id"] for e in lus] == ids
    # le client a vu les deux premiers, a perdu la connexion, deux autres sont arrivés pendant ce temps
    curseur = lus[1]["curseur"]
    manques = await _lire(o, [1], reprise=curseur)
    assert [e["data"]["id"] for e in manques] == ids[2:]  # exactement les deux manqués : aucun doublon, aucun trou
    suite = [await flux.emettre(o, 1, "caisse.liaison", {"etat": "erreur"})]
    encore = await _lire(o, [1], reprise=manques[-1]["curseur"])
    assert [e["data"]["id"] for e in encore] == suite
    assert await _lire(o, [1], reprise=encore[-1]["curseur"]) == []  # à jour : rien
    # sans reprise : seulement ce qui arrive après la connexion (le portail a relu la base pour le reste)
    assert await _lire(o, [1]) == []


async def test_un_evenement_arrive_pendant_que_le_flux_est_ouvert(organisations):
    o, _ = organisations

    async def emettre_plus_tard():
        await asyncio.sleep(0.05)
        await flux.emettre(o, 1, "reservation.creee", {"reservation_id": 7})

    tache = asyncio.create_task(emettre_plus_tard())
    lus = await _lire(o, [1])
    await tache
    assert [(e["event"], e["data"]["donnees"]) for e in lus] == [("reservation.creee", {"reservation_id": 7})]


async def test_la_reprise_de_plusieurs_etablissements_garde_un_curseur_par_etablissement(organisations):
    o, _ = organisations
    a1 = await flux.emettre(o, 1, "caisse.liaison", {"etat": "ok"})
    b1 = await flux.emettre(o, 2, "caisse.liaison", {"etat": "ok"})
    a2 = await flux.emettre(o, 1, "caisse.liaison", {"etat": "erreur"})
    lus = await _lire(o, [1, 2], reprise=_depuis_le_debut(1, 2))
    assert sorted(e["data"]["id"] for e in lus) == sorted([a1, b1, a2])
    # un client qui n'a vu que le premier de l'établissement 1 et rien de l'établissement 2
    curseur = flux.encoder_curseurs({1: a1, 2: "0-0"})
    assert sorted(e["data"]["id"] for e in await _lire(o, [1, 2], reprise=curseur)) == sorted([b1, a2])
    # un curseur mal formé est ignoré : le flux repart du présent, il ne plante pas
    for faux in ("n'importe quoi", "1:abc", "1:1-1;2:2-2", "x", ""):
        assert flux.decoder_curseurs(faux) == {}
        assert await _lire(o, [1], reprise=faux) == []


# --------------------------------------------------------------------------- bornes


async def test_le_flux_est_borne_et_une_reprise_trop_ancienne_le_dit(organisations, monkeypatch):
    o, _ = organisations
    monkeypatch.setattr(flux, "MAX_EVENEMENTS", 5)
    ids = [await flux.emettre(o, 1, "caisse.liaison", {"etat": "ok"}) for _ in range(9)]
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        assert await r.xlen(f"mark:resto:flux:{o}:1") == 5  # les plus récents
        assert 0 < await r.ttl(f"mark:resto:flux:{o}:1") <= flux.DUREE_DE_VIE_S
    finally:
        await r.aclose()
    texte = "".join([m async for m in flux.ecouter(o, [1], reprise=flux.encoder_curseurs({1: ids[1]}))])
    assert "event: flux.reprise_impossible" in texte  # le client a manqué des événements retirés : il relit la base
    assert [e["data"]["id"] for e in _evenements(texte) if "id" in e["data"]] == ids[4:]  # ce qui reste est rejoué
    recent = "".join([m async for m in flux.ecouter(o, [1], reprise=flux.encoder_curseurs({1: ids[6]}))])
    assert "reprise_impossible" not in recent and [e["data"]["id"] for e in _evenements(recent)] == ids[7:]


# --------------------------------------------------------------------------- rôle tablette


async def test_la_tablette_ne_recoit_jamais_la_transcription_l_equipe_recoit_tout(organisations):
    o, _ = organisations
    await flux.emettre(o, 1, "appel.commence", EXEMPLES["appel.commence"])
    await flux.emettre_tour_final(o, 1, 12, "appelant", "mon allergie est grave", final=True)
    await flux.emettre(o, 1, "commande.creee", EXEMPLES["commande.creee"])
    await flux.emettre_tour_final(o, 1, 12, "agent", "bien noté", final=True)
    await flux.emettre(o, 1, "appel.fini", EXEMPLES["appel.fini"])
    equipe = await _lire(o, [1], reprise=_depuis_le_debut(1), role="equipe")
    tablette = await _lire(o, [1], reprise=_depuis_le_debut(1), role="tablette")
    assert [e["event"] for e in equipe] == ["appel.commence", "appel.tour", "commande.creee", "appel.tour", "appel.fini"]
    assert [e["event"] for e in tablette] == ["appel.commence", "commande.creee", "appel.fini"]
    assert "allergie" not in json.dumps(tablette) and "bien noté" not in json.dumps(tablette)
    # le curseur de la tablette avance quand même : une reprise ne rejoue pas ce qu'elle a déjà vu
    assert await _lire(o, [1], reprise=tablette[-1]["curseur"], role="tablette") == []
    with pytest.raises(flux.EvenementRefuse):
        await _lire(o, [1], role="admin")


# --------------------------------------------------------------------------- R1


async def test_un_redis_en_panne_ne_casse_pas_l_emetteur_et_une_lecture_en_panne_le_dit(organisations, monkeypatch):
    o, _ = organisations

    async def panne():
        raise ConnectionError("redis injoignable")

    monkeypatch.setattr(flux, "_client", panne)
    assert await flux.emettre(o, 1, "caisse.liaison", {"etat": "ok"}) is None  # l'appelant continue ; le portail relit la base
    assert await flux.emettre_tour_final(o, 1, 1, "agent", "bonjour", final=True) is None

    class Casse:
        async def xrevrange(self, *a, **k):
            return []

        async def xread(self, *a, **k):
            raise ConnectionError("lecture impossible")

    texte = "".join([m async for m in flux.ecouter(o, [1], client=Casse())])
    assert "event: flux.erreur" in texte and "indisponible" in texte


# --------------------------------------------------------------------------- la route, par la vraie authentification


async def _deux_organisations_avec_des_etablissements(db_session, seconde_base):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    sites = {}
    for base in (cas.base_a, cas.base_b):
        c = await schema.connecter(base)
        try:
            await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
            sites[base] = [
                await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle)
                for cle in ("un", "deux")
            ]
        finally:
            await c.close()
    cas.sites_a, cas.sites_b = sites[cas.base_a], sites[cas.base_b]
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    for o in (cas.a, cas.b):
        for cle in await r.keys(f"mark:resto:flux:{o}:*"):
            await r.delete(cle)
    await r.aclose()
    flux._redis = None
    return cas


RACINE = "/api/v1/restauration/flux"


async def test_la_route_ouvre_le_flux_de_l_organisation_de_la_cle_et_d_elle_seule(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab_a = cas.sites_a[0]
    await flux.emettre(cas.a, etab_a, "commande.creee", EXEMPLES["commande.creee"])
    await flux.emettre(cas.b, cas.sites_b[0], "commande.creee", {**EXEMPLES["commande.creee"], "numero": "D-AUTRE-ORGANISATION"})
    async with client_http() as c:
        sans_cle = await c.get(RACINE, params={"etablissements": str(etab_a)})
        ok = await c.get(RACINE, params={"etablissements": str(etab_a)}, headers={**_cle(cas.cle_a), "Last-Event-ID": _depuis_le_debut(etab_a)})
        chez_b = await c.get(RACINE, params={"etablissements": str(cas.sites_b[0])}, headers={**_cle(cas.cle_b), "Last-Event-ID": _depuis_le_debut(cas.sites_b[0])})
    assert sans_cle.status_code == 401
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/event-stream") and ok.headers["cache-control"] == "no-cache"
    lus = _evenements(ok.text)
    assert [(e["event"], e["data"]["organisation"], e["data"]["etablissement"]) for e in lus] == [("commande.creee", cas.a, etab_a)]
    assert "D-AUTRE-ORGANISATION" not in ok.text  # l'événement de l'autre organisation n'arrive pas, même sur un numéro d'établissement identique
    assert [e["data"]["donnees"]["numero"] for e in _evenements(chez_b.text)] == ["D-AUTRE-ORGANISATION"]


async def test_un_etablissement_inconnu_de_l_organisation_est_refuse_sans_rien_ouvrir(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    inconnu = max(cas.sites_a + cas.sites_b) + 1000
    async with client_http() as c:
        for demande in (str(inconnu), f"{cas.sites_a[0]},{inconnu}", "999999999"):
            r = await c.get(RACINE, params={"etablissements": demande}, headers=_cle(cas.cle_a))
            assert r.status_code == 404 and "text/event-stream" not in r.headers["content-type"], demande
            assert str(inconnu) not in r.text  # jamais un moyen de sonder les identifiants
        for mal_forme in ("", "a", "1,,2", "1;2", "-1", "0", ",".join(str(i) for i in range(1, 60))):
            r = await c.get(RACINE, params={"etablissements": mal_forme}, headers=_cle(cas.cle_a))
            assert r.status_code == 422, mal_forme
        assert (await c.get(RACINE, headers=_cle(cas.cle_a))).status_code == 422  # le paramètre est obligatoire
        assert (await c.get(RACINE, params={"etablissements": str(cas.sites_a[0]), "role": "admin"}, headers=_cle(cas.cle_a))).status_code == 422


async def test_un_etablissement_qui_n_existe_que_dans_l_autre_base_est_refuse(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    c_b = await schema.connecter(cas.base_b)
    try:
        en_plus = await c_b.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'trois', 'trois', 'Europe/Paris' FROM mark.entreprise LIMIT 1 RETURNING id")
    finally:
        await c_b.close()
    assert en_plus not in cas.sites_a
    async with client_http() as c:
        r = await c.get(RACINE, params={"etablissements": str(en_plus)}, headers=_cle(cas.cle_a))
        assert r.status_code == 404  # l'établissement de B existe, pas chez A
        assert (await c.get(RACINE, params={"etablissements": str(en_plus)}, headers=_cle(cas.cle_b))).status_code == 200


async def test_la_route_garde_le_role_tablette_et_la_reprise(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    etab = cas.sites_a[0]
    premier = await flux.emettre(cas.a, etab, "appel.commence", EXEMPLES["appel.commence"])
    await flux.emettre_tour_final(cas.a, etab, 12, "appelant", "texte de transcription", final=True)
    dernier = await flux.emettre(cas.a, etab, "appel.fini", EXEMPLES["appel.fini"])
    async with client_http() as c:
        equipe = await c.get(RACINE, params={"etablissements": str(etab)}, headers={**_cle(cas.cle_a), "Last-Event-ID": _depuis_le_debut(etab)})
        tablette = await c.get(RACINE, params={"etablissements": str(etab), "role": "tablette"}, headers={**_cle(cas.cle_a), "Last-Event-ID": _depuis_le_debut(etab)})
        reprise = await c.get(RACINE, params={"etablissements": str(etab)}, headers={**_cle(cas.cle_a), "Last-Event-ID": flux.encoder_curseurs({etab: premier})})
    assert [e["event"] for e in _evenements(equipe.text)] == ["appel.commence", "appel.tour", "appel.fini"]
    assert [e["event"] for e in _evenements(tablette.text)] == ["appel.commence", "appel.fini"] and "transcription" not in tablette.text
    assert [e["event"] for e in _evenements(reprise.text)] == ["appel.tour", "appel.fini"] and _evenements(reprise.text)[-1]["data"]["id"] == dernier


# --------------------------------------------------------------------------- permission et contrat


def test_la_route_a_sa_permission_au_registre_ouverte_a_la_cle():
    from api.services.equipe_mark.permissions import PERMISSIONS_DE_CLE

    decision, _ = registre.decision_de("GET", "/restauration/flux")
    assert isinstance(decision, registre.Permission) and decision.cle == "conversations.voir"
    assert (decision.pour_cle or decision.cle) in PERMISSIONS_DE_CLE
    assert registre.decision_de("POST", "/restauration/flux") is None or not isinstance(registre.decision_de("POST", "/restauration/flux")[0], registre.Permission)  # seule la lecture a une décision


def test_la_route_est_gelee_dans_le_contrat_avec_le_portail():
    from pathlib import Path

    from api.tests.mark.test_contrat_portail_fork import P, ROUTES_DU_PORTAIL

    assert ("GET", f"{P}/restauration/flux") in ROUTES_DU_PORTAIL
    gele = json.loads((Path(__file__).with_name("contrat_portail_fork.json")).read_text(encoding="utf-8"))[f"GET {P}/restauration/flux"]
    assert gele["ouverte_a_la_cle"] is True and gele["permission"] == "conversations.voir"
    assert {(p["nom"], p["dans"]) for p in gele["parametres"]} >= {("etablissements", "query"), ("role", "query"), ("Last-Event-ID", "header")}
    assert next(p for p in gele["parametres"] if p["nom"] == "etablissements")["obligatoire"] is True
    assert "text/event-stream" in gele["reponses"]["200"]
    assert re.fullmatch(r"[a-z.]+", "caisse.etat")
