"""[.mark] Non-regression test for the hub and its translators (chantier l-agent-collegue, L4).

The questions this file answers (H1 to H9, R1, R7):

    Does a translator keep the common format (a field the hub does not know, an operation
    that does not exist, are refused at load)? Do Google Agenda (MULTI-agenda) and Microsoft
    Outlook turn the APIs' documented answers into the hub's format, and the hub's format into
    the bodies those APIs expect -- and is an agenda the software does not know left OUT
    (unknown is never free)? Does a NEW software plug in by a declaration alone, without one
    line of the hub changed? Does an organization ever reach another's connection through a
    translator? Is the token of a connection asked on demand and never kept? Through the
    engine's REAL dispatcher, does a booking leave its note for the hub, and after the call
    does the client's database get the ``rendez_vous``, its ``lien_externe`` and the certain
    mention of the person -- once, even on a replay? Are each person's agendas kept in
    ``lien_externe`` from the « Team » screen?

Why it exists
-------------
🔴 H6: until this chantier no code wrote ``rendez_vous`` nor ``lien_externe``: a booking was
visible in the client's agenda and nowhere else. And a translator that read an unknown agenda
as « free » would offer slots in an agenda nobody looks at.

The APIs are stand-ins (``httpx.MockTransport`` behind the real relay): no request leaves the
machine. The answers are the documented shapes of each API (Q7: no Google nor Microsoft
application exists yet).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from api.schemas.base_client import Equipe, Personne
from api.services.hub import agenda as hub_agenda
from api.services.hub.traducteurs import (
    Champ,
    ObjetTraduit,
    Operation,
    Traducteur,
    TraducteurInconnu,
    TraducteurInvalide,
    declarer_traducteur,
    depuis_logiciel,
    retirer_traducteur,
    traducteur,
    traducteurs,
    vers_logiciel,
)
from api.services.integrations.connectors import nango
from api.services.integrations.connectors.nango import Requete
from api.tests.mark.test_connecteurs import (
    CONFIG_RDV,
    _appeler,
    _moteur,
    _outil,
    faux_nango,  # noqa: F401 -- a fixture, found by its name
)

DEBUT = "2030-01-07T00:00:00+01:00"
FIN = "2030-01-08T00:00:00+01:00"


@pytest.fixture
def nango_hub(faux_nango):
    faux_nango.connexions.append(
        {"connection_id": "cx-a-outlook", "provider_config_key": "outlook",
         "tags": {"organization_id": "1"}}
    )
    return faux_nango


def _corps(requete) -> dict:
    return json.loads(requete.content) if requete.content else {}


# --------------------------------------------------------------------------- #
# 1. The common format is kept (H1, H2)
# --------------------------------------------------------------------------- #


def test_la_correspondance_va_et_revient_sans_rien_perdre():
    correspondance = (
        Champ("titre", "summary"),
        Champ("debut", "start.dateTime"),
        Champ("fuseau", "start.timeZone"),
        Champ("fuseau", "end.timeZone"),
        Champ("lieu", "where", vers=str.upper, depuis=str.lower),
    )
    corps = vers_logiciel(
        correspondance,
        {"titre": "Visite", "debut": DEBUT, "fuseau": "Europe/Paris", "lieu": "ici", "description": ""},
    )
    assert corps == {
        "summary": "Visite",
        "start": {"dateTime": DEBUT, "timeZone": "Europe/Paris"},
        "end": {"timeZone": "Europe/Paris"},
        "where": "ICI",
    }
    assert depuis_logiciel(correspondance, corps) == {
        "titre": "Visite", "debut": DEBUT, "fuseau": "Europe/Paris", "lieu": "ici",
    }


def test_un_traducteur_hors_du_format_commun_est_refuse_au_chargement():
    rien = Operation(lambda a, o: Requete("GET", "/x"), lambda r, a, o: r)
    with pytest.raises(TraducteurInvalide, match="not a field of the hub"):
        declarer_traducteur(Traducteur("essai_x", "X", "x", "agenda", (
            ObjetTraduit("rendez_vous", (Champ("couleur", "color"),), {}),)))
    with pytest.raises(TraducteurInvalide, match="not an object of the hub"):
        declarer_traducteur(Traducteur("essai_x", "X", "x", "agenda", (
            ObjetTraduit("facture", (), {}),)))
    with pytest.raises(TraducteurInvalide, match="not an operation"):
        declarer_traducteur(Traducteur("essai_x", "X", "x", "agenda", (
            ObjetTraduit("rendez_vous", (), {"supprimer": rien}),)))
    with pytest.raises(TraducteurInvalide, match="lower case"):
        declarer_traducteur(Traducteur("Essai X", "X", "x", "agenda", ()))
    assert traducteur("essai_x") is None


def test_les_traducteurs_livres_sont_declares_et_eteints():
    """H8: Google Agenda and Outlook declared; nothing chooses them by default (X2)."""
    from api.schemas.traducteurs import ChoixTraducteurs

    assert {t.systeme for t in traducteurs("agenda")} >= {"google_agenda", "outlook_agenda"}
    assert ChoixTraducteurs().agenda is None
    for systeme in ("google_agenda", "outlook_agenda"):
        t = traducteur(systeme)
        assert set(t.objet("rendez_vous").operations) == {"creer", "chercher", "lire", "modifier"}
        assert set(t.objet("disponibilites").operations) == {"chercher"}


# --------------------------------------------------------------------------- #
# 2. Google Agenda, multi-agenda (H8), from the API's documented answers
# --------------------------------------------------------------------------- #


async def test_google_agenda_lit_plusieurs_agendas_et_ecarte_l_inconnu(nango_hub):
    nango_hub.reponse_relais = {
        "kind": "calendar#freeBusy",
        "calendars": {
            "camille@example.org": {"busy": [
                {"start": "2030-01-07T08:00:00Z", "end": "2030-01-07T09:30:00Z"}]},
            "sacha@example.org": {"busy": []},
            "inconnu@example.org": {"errors": [{"domain": "global", "reason": "notFound"}],
                                    "busy": []},
        },
    }
    occupe = await hub_agenda.occupations(
        1, "google_agenda",
        ["camille@example.org", "sacha@example.org", "inconnu@example.org", "absent@example.org"],
        datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2,
    )
    assert occupe == {
        "camille@example.org": [(datetime(2030, 1, 7, 8, tzinfo=UTC), datetime(2030, 1, 7, 9, 30, tzinfo=UTC))],
        "sacha@example.org": [],
    }  # unknown or absent: OUT, never free
    [requete] = nango_hub.relais
    assert requete.url.path == "/proxy/calendar/v3/freeBusy"
    assert requete.headers["Provider-Config-Key"] == "google-calendar"
    assert requete.headers["Connection-Id"] == "cx-a"
    assert [i["id"] for i in _corps(requete)["items"]] == [
        "camille@example.org", "sacha@example.org", "inconnu@example.org", "absent@example.org"]


async def test_google_agenda_pose_un_rendez_vous_dans_l_agenda_de_la_personne(nango_hub):
    nango_hub.reponse_relais = {"kind": "calendar#event", "id": "evt-123", "status": "confirmed",
                                "summary": "Visite · Martin"}
    identifiant = await hub_agenda.poser(
        1, "google_agenda",
        {"agenda": "camille@example.org", "debut": "2030-01-07T10:00:00+01:00",
         "fin": "2030-01-07T11:00:00+01:00", "fuseau": "Europe/Paris",
         "titre": "Visite · Martin", "description": "Posé par l'assistant vocal.", "lieu": ""},
        delai=2,
    )
    assert identifiant == "evt-123"
    [requete] = nango_hub.relais
    assert requete.url.raw_path.decode() == "/proxy/calendar/v3/calendars/camille%40example.org/events"
    assert _corps(requete) == {
        "summary": "Visite · Martin",
        "description": "Posé par l'assistant vocal.",
        "start": {"dateTime": "2030-01-07T10:00:00+01:00", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2030-01-07T11:00:00+01:00", "timeZone": "Europe/Paris"},
    }


# --------------------------------------------------------------------------- #
# 3. Microsoft Outlook (H8, Q2), from Graph's documented answers
# --------------------------------------------------------------------------- #


async def test_outlook_lit_les_agendas_en_utc_et_ecarte_le_libre_et_l_inconnu(nango_hub):
    nango_hub.reponse_relais = {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#Collection(microsoft.graph.scheduleInformation)",
        "value": [
            {"scheduleId": "Camille@Example.org", "availabilityView": "0220",
             "scheduleItems": [
                 {"isPrivate": False, "status": "busy",
                  "start": {"dateTime": "2030-01-07T08:00:00.0000000", "timeZone": "UTC"},
                  "end": {"dateTime": "2030-01-07T09:00:00.0000000", "timeZone": "UTC"}},
                 {"status": "free",
                  "start": {"dateTime": "2030-01-07T12:00:00.0000000", "timeZone": "UTC"},
                  "end": {"dateTime": "2030-01-07T13:00:00.0000000", "timeZone": "UTC"}},
                 {"status": "oof",
                  "start": {"dateTime": "2030-01-07T15:00:00.0000000", "timeZone": "UTC"},
                  "end": {"dateTime": "2030-01-07T16:00:00.0000000", "timeZone": "UTC"}}]},
            {"scheduleId": "inconnu@example.org", "error": {"message": "not found", "responseCode": "Error"}},
        ],
    }
    occupe = await hub_agenda.occupations(
        1, "outlook_agenda", ["camille@example.org", "inconnu@example.org"],
        datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2,
    )
    assert occupe == {"camille@example.org": [
        (datetime(2030, 1, 7, 8, tzinfo=UTC), datetime(2030, 1, 7, 9, tzinfo=UTC)),
        (datetime(2030, 1, 7, 15, tzinfo=UTC), datetime(2030, 1, 7, 16, tzinfo=UTC)),
    ]}
    [requete] = nango_hub.relais
    assert requete.url.path == "/proxy/v1.0/me/calendar/getSchedule"
    assert requete.headers["Provider-Config-Key"] == "outlook"
    assert requete.headers["Connection-Id"] == "cx-a-outlook"
    assert _corps(requete)["startTime"] == {"dateTime": "2030-01-06T23:00:00", "timeZone": "UTC"}


async def test_outlook_pose_le_rendez_vous_en_utc(nango_hub):
    nango_hub.reponse_relais = {"id": "AAMkAG-1", "subject": "Visite",
                                "start": {"dateTime": "2030-01-07T09:00:00.0000000", "timeZone": "UTC"}}
    identifiant = await hub_agenda.poser(
        1, "outlook_agenda",
        {"agenda": "camille@example.org", "debut": "2030-01-07T10:00:00+01:00",
         "fin": "2030-01-07T11:00:00+01:00", "fuseau": "Europe/Paris", "titre": "Visite",
         "description": "Posé par l'assistant vocal.", "lieu": "1 rue de l'Exemple, 60000 Ville"},
        delai=2,
    )
    assert identifiant == "AAMkAG-1"
    [requete] = nango_hub.relais
    assert requete.url.path == "/proxy/v1.0/users/camille@example.org/calendar/events"
    assert _corps(requete) == {
        "subject": "Visite",
        "body": {"content": "Posé par l'assistant vocal.", "contentType": "text"},
        "location": {"displayName": "1 rue de l'Exemple, 60000 Ville"},
        "start": {"dateTime": "2030-01-07T09:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2030-01-07T10:00:00", "timeZone": "UTC"},
    }
    lu = traducteur("outlook_agenda").objet("rendez_vous").depuis_logiciel(nango_hub.reponse_relais)
    assert lu["debut"] == "2030-01-07T09:00:00+00:00" and lu["id_externe"] == "AAMkAG-1"


async def test_google_lit_le_lieu_des_rendez_vous_sans_titre_ni_invite(nango_hub):
    """R-6: events of one agenda with their place; cancelled, « free » and all-day left out; only
    the times, the place and the state are asked (never a title or a guest)."""
    nango_hub.reponse_relais = {"items": [
        {"id": "a", "status": "confirmed", "location": "1 rue de l'Exemple, 60000 Beauvais",
         "start": {"dateTime": "2030-01-07T09:00:00+01:00"}, "end": {"dateTime": "2030-01-07T10:00:00+01:00"}},
        {"id": "b", "status": "confirmed", "start": {"dateTime": "2030-01-07T11:00:00+01:00"},
         "end": {"dateTime": "2030-01-07T12:00:00+01:00"}},
        {"id": "c", "status": "cancelled", "location": "x", "start": {"dateTime": "2030-01-07T13:00:00+01:00"},
         "end": {"dateTime": "2030-01-07T14:00:00+01:00"}},
        {"id": "d", "transparency": "transparent", "location": "x",
         "start": {"dateTime": "2030-01-07T15:00:00+01:00"}, "end": {"dateTime": "2030-01-07T16:00:00+01:00"}},
        {"id": "e", "location": "x", "start": {"date": "2030-01-07"}, "end": {"date": "2030-01-08"}},
    ]}
    vus = await hub_agenda.evenements(
        1, "google_agenda", "camille@example.org",
        datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2,
    )
    assert [(e["debut"].hour, e["lieu"]) for e in vus] == [(9, "1 rue de l'Exemple, 60000 Beauvais"), (11, None)]
    [requete] = nango_hub.relais
    assert requete.method == "GET"
    assert requete.url.raw_path.decode().split("?")[0] == "/proxy/calendar/v3/calendars/camille%40example.org/events"
    assert requete.url.params["fields"] == "items(id,status,transparency,start,end,location)"
    assert requete.url.params["singleEvents"] == "true"


async def test_outlook_lit_le_lieu_des_rendez_vous_en_utc(nango_hub):
    nango_hub.reponse_relais = {"value": [
        {"id": "a", "showAs": "busy", "isCancelled": False, "isAllDay": False,
         "location": {"displayName": "2 rue de l'Essai, 60200 Compiègne"},
         "start": {"dateTime": "2030-01-07T08:00:00.0000000", "timeZone": "UTC"},
         "end": {"dateTime": "2030-01-07T09:00:00.0000000", "timeZone": "UTC"}},
        {"id": "b", "showAs": "free", "location": {"displayName": "x"},
         "start": {"dateTime": "2030-01-07T10:00:00.0000000", "timeZone": "UTC"},
         "end": {"dateTime": "2030-01-07T11:00:00.0000000", "timeZone": "UTC"}},
        {"id": "c", "showAs": "busy", "isAllDay": True, "location": {"displayName": "x"},
         "start": {"dateTime": "2030-01-07T00:00:00.0000000", "timeZone": "UTC"},
         "end": {"dateTime": "2030-01-08T00:00:00.0000000", "timeZone": "UTC"}},
        {"id": "d", "showAs": "oof", "isCancelled": True, "location": {"displayName": "x"},
         "start": {"dateTime": "2030-01-07T12:00:00.0000000", "timeZone": "UTC"},
         "end": {"dateTime": "2030-01-07T13:00:00.0000000", "timeZone": "UTC"}},
        {"id": "e", "showAs": "tentative", "location": {"displayName": ""},
         "start": {"dateTime": "2030-01-07T14:00:00.0000000", "timeZone": "UTC"},
         "end": {"dateTime": "2030-01-07T15:00:00.0000000", "timeZone": "UTC"}},
    ]}
    vus = await hub_agenda.evenements(
        1, "outlook_agenda", "camille@example.org",
        datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2,
    )
    assert [(e["debut"], e["lieu"]) for e in vus] == [
        (datetime(2030, 1, 7, 8, tzinfo=UTC), "2 rue de l'Essai, 60200 Compiègne"),
        (datetime(2030, 1, 7, 14, tzinfo=UTC), None),
    ]
    [requete] = nango_hub.relais
    assert requete.url.path == "/proxy/v1.0/users/camille@example.org/calendarView"
    assert requete.url.params["startDateTime"] == "2030-01-06T23:00:00+00:00"
    assert requete.url.params["$select"] == "id,start,end,location,isCancelled,isAllDay,showAs"


async def test_un_traducteur_sans_recherche_d_evenements_fait_lever_et_le_planificateur_se_replie(faux_nango):
    """R-6: a translator that does not search events raises ``TraducteurInconnu``; the planner's
    reader catches every failure (see test_planificateur)."""
    faux_nango.connexions.append(
        {"connection_id": "cx-essai", "provider_config_key": "agenda-essai", "tags": {"organization_id": "1"}})
    essai = Operation(lambda a, o: Requete("POST", "/c", json=a), lambda r, a, o: r)
    declarer_traducteur(Traducteur("essai_sans_lieu", "Essai", "agenda-essai", "agenda",
                                   (ObjetTraduit("rendez_vous", (), {"creer": essai}),)))
    try:
        with pytest.raises(TraducteurInconnu):
            await hub_agenda.evenements(1, "essai_sans_lieu", "a", datetime.fromisoformat(DEBUT),
                                        datetime.fromisoformat(FIN), delai=2)
    finally:
        retirer_traducteur("essai_sans_lieu")


# --------------------------------------------------------------------------- #
# 4. A new software by a declaration alone (H2, H9), and tenant isolation (D6)
# --------------------------------------------------------------------------- #


async def test_un_logiciel_de_test_s_ajoute_sans_toucher_au_hub(faux_nango):
    """The test connector of the plan: an agenda software the hub has never seen, declared
    here, used by the hub's own functions unchanged."""
    faux_nango.connexions.append(
        {"connection_id": "cx-essai", "provider_config_key": "agenda-essai",
         "tags": {"organization_id": "1"}}
    )
    o = (Champ("debut", "quand.debut"), Champ("fin", "quand.fin"), Champ("titre", "objet"),
         Champ("id_externe", "ref"))
    t = declarer_traducteur(Traducteur(
        systeme="agenda_essai", libelle="Agenda d'essai", integration="agenda-essai",
        domaine="agenda", base_url="http://agenda-essai.local",
        objets=(
            ObjetTraduit("disponibilites", (), {"chercher": Operation(
                lambda a, _o: Requete("GET", "/occupe", params={"qui": ",".join(a["agendas"])}),
                lambda r, a, _o: {x["qui"]: [(datetime.fromisoformat(x["de"]), datetime.fromisoformat(x["a"]))]
                                  for x in r["occupe"]})}),
            ObjetTraduit("rendez_vous", o, {"creer": Operation(
                lambda a, ob: Requete("POST", f"/agendas/{a['agenda']}/rdv", json=ob.vers_logiciel(a)),
                lambda r, a, ob: ob.depuis_logiciel(r))}),
        ),
    ))
    try:
        faux_nango.reponse_relais = {"occupe": [{"qui": "p1", "de": "2030-01-07T08:00:00+00:00",
                                                 "a": "2030-01-07T09:00:00+00:00"}], "ref": "r-9"}
        occupe = await hub_agenda.occupations(1, "agenda_essai", ["p1"],
                                              datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2)
        assert list(occupe) == ["p1"]
        assert await hub_agenda.poser(1, "agenda_essai", {"agenda": "p1", "debut": DEBUT, "fin": FIN,
                                                          "titre": "Essai"}, delai=2) == "r-9"
        lecture, ecriture = faux_nango.relais
        assert lecture.headers["Base-Url-Override"] == "http://agenda-essai.local"
        assert _corps(ecriture) == {"quand": {"debut": DEBUT, "fin": FIN}, "objet": "Essai"}
        assert t in traducteurs("agenda")
    finally:
        retirer_traducteur("agenda_essai")


async def test_une_organisation_n_atteint_jamais_l_agenda_d_une_autre(nango_hub):
    # Organization 2 has Google (its own connection) and no Outlook.
    await hub_agenda.occupations(2, "google_agenda", ["x@example.org"],
                                 datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2)
    assert nango_hub.relais[-1].headers["Connection-Id"] == "cx-b"
    with pytest.raises(nango.ConnexionAbsente):
        await hub_agenda.occupations(2, "outlook_agenda", ["x@example.org"],
                                     datetime.fromisoformat(DEBUT), datetime.fromisoformat(FIN), delai=2)
    with pytest.raises(nango.ConnexionAbsente):
        await hub_agenda.poser(3, "google_agenda", {"agenda": "x", "debut": DEBUT, "fin": FIN}, delai=2)
    with pytest.raises(TraducteurInconnu):
        await hub_agenda.poser(1, "inexistant", {"agenda": "x"}, delai=2)
    assert [r.headers["Connection-Id"] for r in nango_hub.relais] == ["cx-b"]


async def test_le_jeton_est_demande_a_la_demande_et_jamais_garde(nango_hub, monkeypatch):
    """H3: an official library gets the token at the moment of the call, from Nango."""
    vus = []
    reel = nango._requete

    async def espion(methode, chemin, **options):
        vus.append(chemin)
        if chemin.startswith("/connection/"):
            import httpx

            return httpx.Response(200, json={"credentials": {"access_token": "jeton-court"}})
        return await reel(methode, chemin, **options)

    monkeypatch.setattr(nango, "_requete", espion)
    assert await nango.jeton_a_la_demande(1, "outlook") == "jeton-court"
    assert vus[-1] == "/connection/cx-a-outlook"
    with pytest.raises(nango.ConnexionAbsente):
        await nango.jeton_a_la_demande(2, "outlook")
    # Nothing kept: a second call asks again.
    await nango.jeton_a_la_demande(1, "outlook")
    assert vus.count("/connection/cx-a-outlook") == 2


# --------------------------------------------------------------------------- #
# 5. Through the real dispatcher: the booking leaves its note for the hub (H6, R1)
# --------------------------------------------------------------------------- #


async def test_une_reservation_par_le_vrai_repartiteur_laisse_sa_note_pour_le_hub(faux_nango, monkeypatch):
    faux_nango.reponse_relais = {"id": "evt-42"}
    engine, mgr, enregistres = _moteur(monkeypatch, [_outil({**CONFIG_RDV, "delai_ms": 2000}, nom="Poser")])
    await mgr.register_handlers(["uuid-Poser"])
    r = await _appeler(enregistres["poser"][0], {"debut": "2030-01-07T10:00:00+01:00"})
    assert r["pose"] is True and r["identifiant"] == "evt-42"
    [note] = engine._gathered_context["hub_rendez_vous"]
    assert note == {
        "systeme": "google_agenda", "agenda": "primary", "id_externe": "evt-42",
        "debut": "2030-01-07T10:00:00+01:00", "fin": "2030-01-07T11:00:00+01:00",
        "motif": "entretien",
    }
    # A booking that fell back leaves no note (nothing was booked).
    faux_nango.en_panne = True
    await _appeler(enregistres["poser"][0], {"debut": "2030-01-08T10:00:00+01:00"})
    assert len(engine._gathered_context["hub_rendez_vous"]) == 1


def test_l_envoi_sans_reservation_reste_celui_d_avant():
    from types import SimpleNamespace

    from api.schemas.apres_appel import ApresAppelAgent
    from api.services.apres_appel.envoi import construire_envoi

    def run(contexte):
        return SimpleNamespace(
            id=1, workflow_id=1, definition_id=1, mode="twilio", call_type="inbound",
            initial_context={"caller_number": "+33612345678"}, gathered_context=contexte,
            usage_info={}, created_at=None, definition=None, workflow=None,
        )

    avant = construire_envoi(run({}), {}, ApresAppelAgent(), [])
    assert "hub" not in avant and avant["demande"] is None
    avec = construire_envoi(
        run({"hub_rendez_vous": [{"systeme": "google_agenda", "id_externe": "e"}]}), {}, ApresAppelAgent(), []
    )
    assert avec["hub"]["rendez_vous"][0]["id_externe"] == "e"
    assert avec["demande"]["type"] == "autre"  # an appointment always has its request


# --------------------------------------------------------------------------- #
# 6. The client's database: agendas of the team, and the booking after the call (H6, H7)
# --------------------------------------------------------------------------- #


async def test_les_agendas_de_l_equipe_vivent_dans_lien_externe(base_prete):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe, lire_equipe
    from api.db.bases_clients.hub import agendas_des_personnes

    connexion = await schema.connecter(base_prete)
    try:
        await ecrire_equipe(connexion, Equipe(personnes=[
            Personne(cle="camille", prenom="Camille", agendas={"google_agenda": "camille@example.org",
                                                               "outlook_agenda": " "}),
            Personne(cle="sacha", prenom="Sacha"),
        ]), "test")
        equipe = await lire_equipe(connexion)
        assert {p.cle: p.agendas for p in equipe.personnes} == {
            "camille": {"google_agenda": "camille@example.org"}, "sacha": None}
        assert await agendas_des_personnes(connexion, "google_agenda") == {"camille": "camille@example.org"}
        # A save without agendas (None) leaves them; an empty map removes them.
        await ecrire_equipe(connexion, Equipe(personnes=[Personne(cle="camille", prenom="Camille")]), "test")
        assert await agendas_des_personnes(connexion, "google_agenda") == {"camille": "camille@example.org"}
        await ecrire_equipe(connexion, Equipe(personnes=[Personne(cle="camille", prenom="Camille", agendas={})]), "test")
        assert await agendas_des_personnes(connexion, "google_agenda") == {}
    finally:
        await connexion.close()
    with pytest.raises(ValueError, match="share the same agenda"):
        Equipe(personnes=[Personne(cle="a", prenom="A", agendas={"google_agenda": "x@example.org"}),
                          Personne(cle="b", prenom="B", agendas={"google_agenda": "X@example.org"})])


async def test_apres_l_appel_le_rendez_vous_entre_dans_le_hub_une_seule_fois(
    base_v4, smtp, modele, db_session, async_session
):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe
    from api.db.bases_clients.hub import ecrire_rendez_vous
    from api.tasks.workflow_completion import process_workflow_completion
    from api.tests.mark import test_apres_appel as t

    org = await t._organisation(async_session, db_session)
    await t._regler(db_session, org, base_v4, smtp)
    await t._equipe(base_v4)
    connexion = await schema.connecter(base_v4)
    try:
        await ecrire_equipe(connexion, Equipe(personnes=[
            Personne(cle="camille", prenom="Camille", mail="camille@example.org",
                     agendas={"google_agenda": "camille@example.org"})]), "test")
    finally:
        await connexion.close()
    run = await t._run(db_session, org)
    poses = [{
        "systeme": "google_agenda", "agenda": "camille@example.org", "id_externe": "evt-1",
        "debut": "2030-01-07T10:00:00+01:00", "fin": "2030-01-07T11:00:00+01:00", "motif": "visite",
        "adresse": {"voie": "rue de l'Exemple", "numero": "1", "code_postal": "60000",
                    "commune": "Ville", "code_insee": "60001", "latitude": 49.4, "longitude": 2.08,
                    "verifiee": True},
    }]
    await db_session.update_workflow_run(
        run.id, gathered_context={**run.gathered_context, "hub_rendez_vous": poses})
    file: list[dict] = []
    with patch("api.tasks.arq.enqueue_job", await t._executer_tout_de_suite(file)):
        await process_workflow_completion(None, run.id)

    connexion = await schema.connecter(base_v4)
    try:
        rdv = await connexion.fetchrow(
            "SELECT r.*, p.cle FROM mark.rendez_vous r JOIN mark.personne p ON p.id = r.intervenant_id")
        assert rdv["cle"] == "camille" and rdv["origine"] == "agent" and rdv["statut"] == "pose"
        assert rdv["debut"] == datetime(2030, 1, 7, 9, tzinfo=UTC)
        lien = await connexion.fetchrow(
            "SELECT * FROM mark.lien_externe WHERE objet_type = 'rendez_vous'")
        assert (lien["systeme"], lien["id_externe"], lien["objet_id"]) == ("google_agenda", "evt-1", rdv["id"])
        adresse = await connexion.fetchrow("SELECT * FROM mark.adresse WHERE id = $1", rdv["adresse_id"])
        assert float(adresse["latitude"]) == 49.4 and adresse["code_insee"] == "60001" and adresse["verifiee"]
        mention = await connexion.fetchrow(
            "SELECT m.source, m.certitude, p.cle FROM mark.mention m JOIN mark.personne p ON p.id = m.personne_id")
        assert dict(mention) == {"source": "rendez_vous", "certitude": "certaine", "cle": "camille"}
        # A replay writes nothing twice.
        appel_id, demande_id, contact_id = await connexion.fetchrow(
            "SELECT id, demande_id, contact_id FROM mark.appel")
        bilan = await ecrire_rendez_vous(connexion, appel_id, demande_id, contact_id, poses)
        assert bilan["rendez_vous"] == 0 and bilan["deja"] == 1
        assert await connexion.fetchval("SELECT count(*) FROM mark.rendez_vous") == 1
        assert await connexion.fetchval("SELECT count(*) FROM mark.adresse") == 1
    finally:
        await connexion.close()


# Fixtures of the client database's and the after-call's tests.
from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402, F401
