"""[.mark] Non-regression test of the connectors of the catalogue, first half (U3 sexies, point 8, F2).

HubSpot, Pipedrive, Sellsy, Salesforce, Teamleader, noCRM, folk, Google Agenda (unchanged, covered
by ``test_connecteurs.py``), Outlook (agenda actions), Calendly, Acuity, Setmore, Twilio SMS, Gmail.

The questions this file answers:

    Does each action send the request its software's documentation describes (method, path,
    body, query) from what the caller said and the client's settings? Does it return the USEFUL
    result only (an identifier, a name, a slot), never the software's raw answer (D8)? Does a
    channel that can reach anyone (SMS, e-mail) go only to the caller's own number and address?
    Does a value put in a query (SOQL) never break out of it? Does one organization ever reach
    another's connection through these connectors (D6)? Do the translators « dossier » of the
    CRMs give identity and phone numbers and nothing else?

Why it exists
-------------
Every connector is « À essayer »: coded from the public documentation, never called for real
(no account opened, no call to a vendor). The answers below are RECORDED IN FILES
(``reponses_enregistrees_connecteurs/``), written from each vendor's documented shapes: they prove
our reading and our bodies, not the vendor. The real trial is done with Evan on a test account (D3).
"""

from __future__ import annotations

import base64
import json
from email import message_from_bytes
from email.policy import default
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from api.services.hub.traducteurs import operer
from api.services.integrations.connectors import execution, nango
from api.services.integrations.connectors.catalogue import connecteur, connecteurs

ENREGISTREES = Path(__file__).parent / "reponses_enregistrees_connecteurs"
NUMERO = "+33612345678"
INTEGRATIONS = (
    "hubspot", "pipedrive", "sellsy", "salesforce", "teamleader-focus", "nocrm", "folk",
    "outlook", "calendly", "acuity-scheduling", "setmore", "twilio", "google-mail",
)  # fmt: skip
FICHE = {
    "extracted_variables": {
        "prenom": "Jeanne",
        "nom": "Martin",
        "mail": "j@exemple.fr",
        "motif": "devis",
    }
}


def enregistree(nom: str):
    return json.loads((ENREGISTREES / f"{nom}.json").read_text(encoding="utf-8"))


class Relais:
    """A Nango whose relay answers with the recorded files, by (method, path)."""

    def __init__(self, routes: dict[tuple[str, str], str] | None = None):
        self.routes = routes or {}
        self.vus: list[httpx.Request] = []

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        chemin = requete.url.path
        if chemin == "/connections":
            tag = requete.url.params.get("tags[organization_id]")
            gardees = (
                [
                    {
                        "connection_id": f"cx-{i}",
                        "provider_config_key": i,
                        "tags": {"organization_id": "1"},
                    }
                    for i in INTEGRATIONS
                ]
                if tag == "1"
                else []
            )
            return httpx.Response(200, json={"connections": gardees})
        if chemin.startswith("/proxy"):
            self.vus.append(requete)
            nom = self.routes.get((requete.method, chemin[len("/proxy"):]))
            if nom is None:
                return httpx.Response(404, json={"error": "pas de réponse enregistrée"})
            return httpx.Response(200, json=enregistree(nom))
        return httpx.Response(404)

    def corps(self, rang: int = -1):
        return json.loads(self.vus[rang].content)

    def appels(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path[len("/proxy"):]) for r in self.vus]


@pytest.fixture
def relais(monkeypatch):
    r = Relais()
    monkeypatch.setenv(nango.VARIABLE_URL, "http://nango.local")
    monkeypatch.setenv(nango.VARIABLE_CLE, "cle-secrete-nango-0123")
    monkeypatch.setattr(
        nango,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(r), **o),
    )
    return r


async def jouer(relais, nom, action, arguments=None, reglages=None, fiche=FICHE, organisation=1):
    return await execution.executer(
        organisation,
        {"connecteur": nom, "action": action, "reglages": reglages or {}, "delai_ms": 4000},
        arguments or {},
        fiche,
        NUMERO,
    )


# --------------------------------------------------------------------------- #
# 1. The catalogue: what each software offers
# --------------------------------------------------------------------------- #

ATTENDU = {
    "hubspot": {"find_contact", "create_contact", "add_call_note", "create_deal"},
    "pipedrive": {"find_contact", "create_contact", "add_call_note", "create_deal"},
    "sellsy": {"find_contact", "create_contact", "add_call_note", "create_deal"},
    "salesforce": {"find_contact", "create_contact", "add_call_note", "create_deal"},
    "teamleader": {"find_contact", "create_contact", "create_deal"},
    "nocrm": {"find_contact", "create_lead", "add_call_note"},
    "folk": {"find_contact", "create_contact", "add_call_note"},
    "outlook_agenda": {"find_free_slots", "book_appointment"},
    "calendly": {"find_free_slots", "book_appointment"},
    "acuity": {"find_free_slots", "book_appointment"},
    "setmore": {"find_free_slots", "book_appointment"},
    "twilio_sms": {"send_sms"},
    "gmail": {"send_email"},
}


def test_chaque_logiciel_declare_ses_actions_et_aucune_ecriture_n_est_anticipee():
    for nom, actions in ATTENDU.items():
        c = connecteur(nom)
        assert c is not None, nom
        assert {a.nom for a in c.actions} == actions, nom
        for a in c.actions:
            if a.ecrit:
                assert not a.anticipable_permis, f"{nom}.{a.nom}"
            else:
                assert a.anticipable_permis, f"{nom}.{a.nom}"
            assert "organization_id" not in {p.nom for p in a.parametres}
    assert len({c.nom for c in connecteurs()}) == len(connecteurs())


# --------------------------------------------------------------------------- #
# 2. The CRMs: search, create, note, deal
# --------------------------------------------------------------------------- #


async def test_hubspot_cherche_par_chaque_ecriture_du_numero_et_ne_rend_que_l_utile(relais):
    relais.routes[("POST", "/crm/v3/objects/contacts/search")] = "hubspot__recherche"
    r = await jouer(relais, "hubspot", "find_contact")
    assert r.statut == "ok"
    assert r.donnees == {"contacts": [{"identifiant": "501", "nom": "Jeanne Martin"}]}
    assert "j@exemple.fr" not in json.dumps(r.donnees)  # D8: never the record
    filtres = [g["filters"][0] for g in relais.corps()["filterGroups"]]
    assert {(f["propertyName"], f["value"]) for f in filtres} == {
        ("phone", NUMERO), ("phone", "0612345678"), ("mobilephone", NUMERO), ("mobilephone", "0612345678"),
    }  # fmt: skip
    assert relais.vus[0].headers["Connection-Id"] == "cx-hubspot"


async def test_hubspot_rien_trouve_dit_aucun(relais):
    relais.routes[("POST", "/crm/v3/objects/contacts/search")] = "hubspot__vide"
    r = await jouer(relais, "hubspot", "find_contact", {"mail": "x@y.fr"})
    assert r.donnees == {"contacts": [], "aucun": True}
    assert relais.corps()["filterGroups"][-1]["filters"][0]["propertyName"] == "email"


async def test_hubspot_cree_le_contact_son_proprietaire_et_note_l_appel(relais):
    relais.routes[("POST", "/crm/v3/objects/contacts")] = "hubspot__creation"
    relais.routes[("POST", "/crm/v3/objects/notes")] = "hubspot__creation"
    relais.routes[("POST", "/crm/v3/objects/deals")] = "hubspot__creation"
    reglages = {"proprietaire": "9001", "pipeline": "ventes", "etape": "qualif"}
    r = await jouer(relais, "hubspot", "create_contact", {}, reglages)
    assert r.donnees == {"cree": True, "identifiant": "777"}
    assert relais.corps()["properties"] == {
        "firstname": "Jeanne", "lastname": "Martin", "email": "j@exemple.fr", "phone": NUMERO,
        "hubspot_owner_id": "9001",
    }  # fmt: skip
    r = await jouer(relais, "hubspot", "add_call_note", {"identifiant": "777", "resume": "Veut un devis."}, reglages)
    assert r.donnees == {"note": True}
    note = relais.corps()
    assert "Veut un devis." in note["properties"]["hs_note_body"] and "devis" in note["properties"]["hs_note_body"]
    assert note["associations"][0]["to"] == {"id": "777"}
    assert note["associations"][0]["types"][0]["associationTypeId"] == 202
    r = await jouer(relais, "hubspot", "create_deal", {"identifiant": "777"}, reglages)
    deal = relais.corps()
    assert deal["properties"] == {
        "dealname": "devis", "pipeline": "ventes", "dealstage": "qualif", "hubspot_owner_id": "9001",
    }  # fmt: skip
    assert deal["associations"][0]["types"][0]["associationTypeId"] == 3


async def test_pipedrive(relais):
    relais.routes[("GET", "/api/v2/persons/search")] = "pipedrive__recherche"
    relais.routes[("POST", "/api/v2/persons")] = "pipedrive__creation"
    relais.routes[("POST", "/api/v1/notes")] = "pipedrive__note"
    relais.routes[("POST", "/api/v2/deals")] = "pipedrive__creation"
    r = await jouer(relais, "pipedrive", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "42", "nom": "Jeanne Martin"}]}
    p = relais.vus[0].url.params
    assert (p["term"], p["fields"]) == ("612345678", "phone")  # the two typings both contain it
    r = await jouer(relais, "pipedrive", "create_contact", {}, {"proprietaire": "12"})
    assert r.donnees == {"cree": True, "identifiant": "43"}
    assert relais.corps() == {
        "name": "Jeanne Martin",
        "emails": [{"value": "j@exemple.fr", "primary": True, "label": "work"}],
        "phones": [{"value": NUMERO, "primary": True, "label": "mobile"}],
        "owner_id": 12,
    }
    await jouer(relais, "pipedrive", "add_call_note", {"identifiant": "43", "resume": "Rappel demandé."})
    assert relais.corps()["person_id"] == 43 and "Rappel demandé." in relais.corps()["content"]
    r = await jouer(relais, "pipedrive", "create_deal", {"identifiant": "43", "titre": "Pose"}, {"pipeline": "2", "etape": "7"})
    assert relais.corps() == {"title": "Pose", "person_id": 43, "pipeline_id": 2, "stage_id": 7}


async def test_folk(relais):
    relais.routes[("GET", "/v1/people")] = "folk__recherche"
    relais.routes[("POST", "/v1/people")] = "folk__creation"
    relais.routes[("POST", "/v1/notes")] = "folk__note"
    r = await jouer(relais, "folk", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "per_aaaa", "nom": "Jeanne Martin"}]}
    assert relais.vus[0].url.params["filter[phones][eq]"] == NUMERO
    r = await jouer(relais, "folk", "create_contact", {}, {"groupe": "grp_1"})
    assert r.donnees == {"cree": True, "identifiant": "per_bbbb"}
    assert relais.corps() == {
        "firstName": "Jeanne", "lastName": "Martin", "emails": ["j@exemple.fr"], "phones": [NUMERO],
        "groups": [{"id": "grp_1"}],
    }  # fmt: skip
    r = await jouer(relais, "folk", "add_call_note", {"identifiant": "per_bbbb", "resume": "Merci."})
    body = relais.corps()
    assert body["entity"] == {"id": "per_bbbb"} and body["visibility"] == "public"
    assert set(body) == {"entity", "visibility", "content"}  # folk refuses any other key


async def test_sellsy(relais):
    relais.routes[("POST", "/contacts/search")] = "sellsy__recherche"
    relais.routes[("POST", "/individuals")] = "sellsy__creation"
    relais.routes[("POST", "/comments")] = "sellsy__creation"
    relais.routes[("POST", "/opportunities")] = "sellsy__creation"
    r = await jouer(relais, "sellsy", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "9", "nom": "Jeanne Martin"}]}
    assert relais.corps() == {"filters": {"phone_number": NUMERO}}
    r = await jouer(relais, "sellsy", "create_contact")
    assert relais.corps() == {
        "first_name": "Jeanne", "last_name": "Martin", "email": "j@exemple.fr", "mobile_number": NUMERO,
    }  # fmt: skip
    await jouer(relais, "sellsy", "add_call_note", {"identifiant": "10", "resume": "RAS"})
    assert relais.corps()["related"] == [{"id": 10, "type": "individual"}]
    await jouer(relais, "sellsy", "create_deal", {"identifiant": "10"}, {"pipeline": "3", "etape": "8"})
    assert relais.corps() == {
        "name": "devis", "related": [{"id": 10, "type": "individual"}], "pipeline": 3, "step": 8,
    }  # fmt: skip


async def test_salesforce(relais):
    relais.routes[("GET", "/services/data/v60.0/query")] = "salesforce__recherche"
    relais.routes[("POST", "/services/data/v60.0/sobjects/Contact")] = "salesforce__creation"
    relais.routes[("POST", "/services/data/v60.0/sobjects/Task")] = "salesforce__creation"
    relais.routes[("POST", "/services/data/v60.0/sobjects/Opportunity")] = "salesforce__opportunite"
    relais.routes[("POST", "/services/data/v60.0/sobjects/OpportunityContactRole")] = "salesforce__creation"
    r = await jouer(relais, "salesforce", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "003A", "nom": "Jeanne Martin"}]}
    soql = relais.vus[0].url.params["q"]
    assert "Phone IN ('+33612345678', '0612345678')" in soql and "MobilePhone IN" in soql
    assert soql.endswith("LIMIT 3")
    r = await jouer(relais, "salesforce", "create_contact", {}, {"proprietaire": "005X"})
    assert relais.corps() == {
        "FirstName": "Jeanne", "LastName": "Martin", "Email": "j@exemple.fr", "Phone": NUMERO, "OwnerId": "005X",
    }  # fmt: skip
    await jouer(relais, "salesforce", "add_call_note", {"identifiant": "003B", "resume": "Rappeler."})
    tache = relais.corps()
    assert (tache["WhoId"], tache["Status"], tache["TaskSubtype"]) == ("003B", "Completed", "Call")
    relais.vus.clear()
    r = await jouer(relais, "salesforce", "create_deal", {"identifiant": "003B"}, {"etape": "Qualification"})
    assert r.donnees == {"cree": True, "identifiant": "006C"}
    # The opportunity, then the contact's role on it, on the same connection.
    assert [c for _m, c in relais.appels()] == [
        "/services/data/v60.0/sobjects/Opportunity",
        "/services/data/v60.0/sobjects/OpportunityContactRole",
    ]
    assert relais.corps() == {"OpportunityId": "006C", "ContactId": "003B", "IsPrimary": True}
    assert relais.corps(0)["StageName"] == "Qualification" and "CloseDate" in relais.corps(0)


async def test_salesforce_une_valeur_ne_sort_jamais_de_la_requete(relais):
    relais.routes[("GET", "/services/data/v60.0/query")] = "salesforce__recherche"
    await jouer(relais, "salesforce", "find_contact", {"mail": "x' OR Name != '", "telephone": "pas un numero"}, fiche={})
    soql = relais.vus[0].url.params["q"]
    assert "x\\' OR Name != \\'" in soql  # the quotes are escaped: one literal, not a second clause
    assert "Phone IN" not in soql and "pas un" not in soql


async def test_teamleader(relais):
    relais.routes[("POST", "/contacts.list")] = "teamleader__recherche"
    relais.routes[("POST", "/contacts.add")] = "teamleader__creation"
    relais.routes[("POST", "/deals.create")] = "teamleader__creation"
    r = await jouer(relais, "teamleader", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "uuid-1", "nom": "Jeanne Martin"}]}
    assert relais.corps()["filter"] == {"term": NUMERO}
    r = await jouer(relais, "teamleader", "create_contact")
    assert relais.corps() == {
        "first_name": "Jeanne", "last_name": "Martin",
        "emails": [{"type": "primary", "email": "j@exemple.fr"}],
        "telephones": [{"type": "mobile", "number": NUMERO}],
    }  # fmt: skip
    await jouer(relais, "teamleader", "create_deal", {"identifiant": "uuid-2"}, {"proprietaire": "u-1", "phase": "p-1"})
    assert relais.corps() == {
        "lead": {"customer": {"type": "contact", "id": "uuid-2"}}, "title": "devis",
        "responsible_user_id": "u-1", "phase_id": "p-1",
    }  # fmt: skip


async def test_nocrm_le_prospect_porte_le_telephone_dans_sa_description(relais):
    relais.routes[("GET", "/leads")] = "nocrm__recherche"
    relais.routes[("POST", "/leads")] = "nocrm__creation"
    relais.routes[("POST", "/leads/32/comments")] = "nocrm__commentaire"
    r = await jouer(relais, "nocrm", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "31", "nom": "Jeanne Martin"}]}
    assert relais.vus[0].url.params["query"] == "612345678"
    r = await jouer(relais, "nocrm", "create_lead", {"resume": "Veut un devis haie."}, {"pipeline": "Ventes", "etiquettes": ["voix"]})
    assert r.donnees == {"cree": True, "identifiant": "32"}
    lead = relais.corps()
    assert lead["title"] == "Jeanne Martin" and lead["pipeline"] == "Ventes" and lead["tags"] == ["voix"]
    assert NUMERO in lead["description"] and "Veut un devis haie." in lead["description"]
    r = await jouer(relais, "nocrm", "add_call_note", {"identifiant": "32", "resume": "Rappel."})
    assert r.statut == "ok" and "Rappel." in relais.corps()["content"]


# --------------------------------------------------------------------------- #
# 3. The booking software and the agenda
# --------------------------------------------------------------------------- #


async def test_calendly_creneaux_tries_disponibles_seulement_en_heure_locale(relais):
    relais.routes[("GET", "/event_type_available_times")] = "calendly__disponibilites"
    uri = "https://api.calendly.com/event_types/ABC"
    r = await jouer(relais, "calendly", "find_free_slots", {}, {"type_evenement": uri})
    assert [c["debut"] for c in r.donnees["creneaux"]] == [
        "2030-01-08T10:00:00+01:00", "2030-01-08T11:00:00+01:00", "2030-01-09T15:00:00+01:00",
    ]  # fmt: skip
    p = relais.vus[0].url.params
    assert p["event_type"] == uri and p["start_time"].endswith("Z") and p["end_time"].endswith("Z")


async def test_calendly_sans_type_d_evenement_ne_part_pas(relais):
    r = await jouer(relais, "calendly", "find_free_slots", {}, {})
    assert r.statut == "repli" and relais.vus == []


async def test_calendly_reserve_en_utc_avec_le_mail_de_l_appelant(relais):
    relais.routes[("POST", "/invitees")] = "calendly__invite"
    uri = "https://api.calendly.com/event_types/ABC"
    absent = await jouer(relais, "calendly", "book_appointment", {"debut": "2030-01-08T10:00:00+01:00"}, {"type_evenement": uri})
    assert absent.statut == "erreur" and absent.donnees == {"manque": ["mail"]} and relais.vus == []
    r = await jouer(
        relais, "calendly", "book_appointment", {"debut": "2030-01-08T10:00:00+01:00", "mail": "j@exemple.fr"},
        {"type_evenement": uri},
    )  # fmt: skip
    assert r.donnees["pose"] is True and r.donnees["identifiant"].endswith("/invitees/I1")
    assert relais.corps() == {
        "event_type": uri,
        "start_time": "2030-01-08T09:00:00Z",
        "invitee": {
            "email": "j@exemple.fr", "timezone": "Europe/Paris", "name": "Jeanne Martin",
            "first_name": "Jeanne", "last_name": "Martin", "text_reminder_number": NUMERO,
        },
    }  # fmt: skip


async def test_acuity_les_jours_puis_les_heures_du_premier_jour(relais):
    relais.routes[("GET", "/availability/dates")] = "acuity__jours"
    relais.routes[("GET", "/availability/times")] = "acuity__heures"
    r = await jouer(relais, "acuity", "find_free_slots", {}, {"type_rendez_vous": "55", "agenda": "7"})
    assert [m for m, _c in relais.appels()] == ["GET", "GET"]
    assert [c for _m, c in relais.appels()] == ["/availability/dates", "/availability/times"]
    heures = relais.vus[1].url.params
    assert (heures["date"], heures["appointmentTypeID"], heures["calendarID"]) == ("2030-01-08", "55", "7")
    assert [c["debut"] for c in r.donnees["creneaux"]] == [
        "2030-01-08T10:00:00+01:00", "2030-01-08T11:00:00+01:00", "2030-01-08T15:30:00+01:00",
    ]  # fmt: skip


async def test_acuity_un_jour_demande_n_appelle_qu_une_fois(relais):
    relais.routes[("GET", "/availability/times")] = "acuity__heures"
    r = await jouer(relais, "acuity", "find_free_slots", {"date": "2030-01-08"}, {"type_rendez_vous": "55"})
    assert relais.appels() == [("GET", "/availability/times")] and r.donnees["creneaux"]
    sans_type = await jouer(relais, "acuity", "find_free_slots", {}, {})
    assert sans_type.statut == "repli"


async def test_acuity_reserve_comme_proprietaire(relais):
    relais.routes[("POST", "/appointments")] = "acuity__rendez_vous"
    r = await jouer(relais, "acuity", "book_appointment", {"debut": "2030-01-08T10:00:00+01:00"}, {"type_rendez_vous": "55"})
    assert r.donnees["identifiant"] == "31991639"
    assert relais.vus[0].url.params["admin"] == "true"
    corps = relais.corps()
    assert (corps["appointmentTypeID"], corps["firstName"], corps["lastName"], corps["email"], corps["phone"]) == (
        55, "Jeanne", "Martin", "j@exemple.fr", NUMERO,
    )  # fmt: skip
    assert corps["datetime"] == "2030-01-08T10:00:00+01:00"


async def test_setmore_creneaux_puis_client_puis_rendez_vous(relais):
    relais.routes[("POST", "/bookingapi/slots")] = "setmore__creneaux"
    relais.routes[("POST", "/bookingapi/customer/create")] = "setmore__client"
    relais.routes[("POST", "/bookingapi/appointment/create")] = "setmore__rendez_vous"
    reglages = {"personnel": "st1", "service": "sv1"}
    r = await jouer(relais, "setmore", "find_free_slots", {"date": "2030-01-08"}, reglages)
    assert relais.corps() == {"staff_key": "st1", "service_key": "sv1", "selected_date": "08/01/2030"}
    assert [c["libelle"] for c in r.donnees["creneaux"]] == [
        "mardi 8 janvier à 9 h", "mardi 8 janvier à 9 h 30", "mardi 8 janvier à 10 h",
    ]  # fmt: skip
    relais.vus.clear()
    r = await jouer(relais, "setmore", "book_appointment", {"debut": "2030-01-08T09:30:00+01:00"}, reglages)
    assert r.donnees["identifiant"] == "a1"
    assert [c for _m, c in relais.appels()] == ["/bookingapi/customer/create", "/bookingapi/appointment/create"]
    assert relais.corps(0)["first_name"] == "Jeanne" and relais.corps(0)["cell_phone"] == NUMERO
    rdv = relais.corps(1)
    assert (rdv["customer_key"], rdv["start_time"], rdv["end_time"]) == ("c1", "2030-01-08T09:30Z", "2030-01-08T10:00Z")
    sans = await jouer(relais, "setmore", "find_free_slots", {}, {})
    assert sans.statut == "repli"


async def test_outlook_creneaux_hors_des_occupations_et_rendez_vous(relais):
    relais.routes[("POST", "/v1.0/me/calendar/getSchedule")] = "outlook__horaire"
    relais.routes[("POST", "/v1.0/users/agenda@exemple.fr/calendar/events")] = "outlook__evenement"
    reglages = {"agenda": "agenda@exemple.fr"}
    r = await jouer(relais, "outlook_agenda", "find_free_slots", {"date": "2030-01-08"}, reglages)
    # busy 08:00-09:00 UTC = 09:00-10:00 in Paris: the first free hour is 10:00.
    assert r.donnees["creneaux"][0]["debut"] == "2030-01-08T10:00:00+01:00"
    assert relais.corps()["schedules"] == ["agenda@exemple.fr"]
    r = await jouer(relais, "outlook_agenda", "book_appointment", {"debut": "2030-01-08T10:00:00+01:00"}, reglages)
    assert r.donnees["identifiant"] == "AAMkAD1"
    ev = relais.corps()
    assert ev["start"] == {"dateTime": "2030-01-08T09:00:00", "timeZone": "UTC"}
    assert ev["end"] == {"dateTime": "2030-01-08T10:00:00", "timeZone": "UTC"}
    assert "devis" in ev["subject"] and "Posé par l'assistant vocal." in ev["body"]["content"]


async def test_outlook_une_boite_inconnue_n_est_jamais_libre(relais):
    relais.routes[("POST", "/v1.0/me/calendar/getSchedule")] = "outlook__inconnu"
    r = await jouer(relais, "outlook_agenda", "find_free_slots", {"date": "2030-01-08"}, {"agenda": "agenda@exemple.fr"})
    assert r.donnees == {"creneaux": [], "aucun": True}
    sans = await jouer(relais, "outlook_agenda", "find_free_slots", {}, {})
    assert sans.statut == "repli"


# --------------------------------------------------------------------------- #
# 4. The channels that reach a person: only the caller
# --------------------------------------------------------------------------- #


async def test_twilio_ecrit_au_numero_de_l_appelant_en_formulaire(relais):
    relais.routes[("POST", "/2010-04-01/Accounts/AC1234/Messages.json")] = "twilio__message"
    reglages = {"sid_compte": "AC1234", "expediteur": "+33700000000", "signature": "Cabinet Martin"}
    # The model tries to choose the destination: the undeclared keys are dropped.
    r = await jouer(relais, "twilio_sms", "send_sms", {"message": "RDV mardi 10 h.", "to": "+33699999999", "numero": "+33699999999"}, reglages)
    assert r.donnees == {"envoye": True, "statut": "queued"}
    requete = relais.vus[0]
    assert requete.headers["content-type"].startswith("application/x-www-form-urlencoded")
    form = parse_qs(requete.content.decode())
    assert form == {"To": [NUMERO], "From": ["+33700000000"], "Body": ["RDV mardi 10 h.\nCabinet Martin"]}


async def test_twilio_sans_compte_ou_expediteur_ne_part_pas(relais):
    for reglages in ({}, {"sid_compte": "AC1234"}, {"sid_compte": "../../x", "expediteur": "+33700000000"}):
        r = await jouer(relais, "twilio_sms", "send_sms", {"message": "x"}, reglages)
        assert r.statut == "repli"
    assert relais.vus == []


async def test_twilio_service_de_messagerie_remplace_le_numero(relais):
    relais.routes[("POST", "/2010-04-01/Accounts/AC1234/Messages.json")] = "twilio__message"
    await jouer(relais, "twilio_sms", "send_sms", {"message": "x"}, {"sid_compte": "AC1234", "expediteur": "+33700000000", "service_messagerie": "MG42"})
    form = parse_qs(relais.vus[0].content.decode())
    assert form["MessagingServiceSid"] == ["MG42"] and "From" not in form


async def test_gmail_ecrit_a_l_adresse_de_l_appelant_seulement(relais):
    relais.routes[("POST", "/gmail/v1/users/me/messages/send")] = "gmail__envoi"
    r = await jouer(
        relais, "gmail", "send_email",
        {"objet": "Votre rendez-vous", "message": "Mardi 10 h, à bientôt.", "destinataire": "autre@ailleurs.fr", "to": "autre@ailleurs.fr"},
        {"prefixe_objet": "[Cabinet]", "signature": "Cabinet Martin"},
    )  # fmt: skip
    assert r.donnees == {"envoye": True}
    brut = relais.corps()["raw"]
    assert "=" not in brut  # base64url without padding
    message = message_from_bytes(base64.urlsafe_b64decode(brut + "=" * (-len(brut) % 4)), policy=default)
    assert message["To"] == "j@exemple.fr"
    assert message["Subject"] == "[Cabinet] Votre rendez-vous"
    assert "Mardi 10 h, à bientôt." in message.get_content() and "Cabinet Martin" in message.get_content()


async def test_gmail_sans_adresse_connue_ne_part_pas(relais):
    r = await jouer(relais, "gmail", "send_email", {"objet": "x", "message": "y"}, fiche={"extracted_variables": {"nom": "Martin"}})
    assert r.statut == "repli" and relais.vus == []


# --------------------------------------------------------------------------- #
# 5. Cloisonnement (D6): another organization has no connection to reach
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("nom", "action", "arguments"),
    [
        ("hubspot", "find_contact", {}),
        ("pipedrive", "create_contact", {}),
        ("salesforce", "add_call_note", {"identifiant": "1", "resume": "x"}),
        ("calendly", "find_free_slots", {}),
        ("twilio_sms", "send_sms", {"message": "x"}),
        ("gmail", "send_email", {"objet": "x", "message": "y"}),
    ],
)
async def test_une_autre_organisation_n_atteint_pas_la_connexion(relais, nom, action, arguments):
    reglages = {"type_evenement": "https://api.calendly.com/event_types/ABC", "sid_compte": "AC1", "expediteur": "+33700000000"}
    r = await jouer(relais, nom, action, {**arguments, "organization_id": 1}, reglages, organisation=2)
    assert r.statut == "repli" and relais.vus == []  # organization 2 owns no connection; the model's id counts for nothing


# --------------------------------------------------------------------------- #
# 6. The translators « dossier » of the CRMs
# --------------------------------------------------------------------------- #

PERMIS = {"id_externe", "telephones", "nom", "prenom", "mail", "code_postal", "commune"}


@pytest.mark.parametrize(
    ("systeme", "route", "fichier"),
    [
        ("hubspot", ("POST", "/crm/v3/objects/contacts/search"), "hubspot__recherche"),
        ("pipedrive", ("GET", "/api/v2/persons/search"), "pipedrive__recherche"),
        ("folk", ("GET", "/v1/people"), "folk__recherche"),
        ("salesforce", ("GET", "/services/data/v60.0/query"), "salesforce__recherche"),
        ("sellsy", ("POST", "/contacts/search"), "sellsy__recherche"),
        ("teamleader", ("POST", "/contacts.list"), "teamleader__recherche"),
    ],
)
async def test_le_dossier_d_un_crm_ne_donne_que_l_identite(relais, systeme, route, fichier):
    relais.routes[route] = fichier
    trouves = await operer(1, systeme, "dossier", "chercher", {"telephone": NUMERO}, delai=3)
    assert len(trouves) == 1 and trouves[0]["id_externe"]
    assert set(trouves[0]) <= PERMIS
    # The record of another organization is out of reach: it owns no connection.
    from api.services.integrations.connectors.nango import ConnexionAbsente

    with pytest.raises(ConnexionAbsente):
        await operer(2, systeme, "dossier", "chercher", {"telephone": NUMERO}, delai=3)


async def test_le_dossier_hubspot_lu_par_identifiant(relais):
    relais.routes[("GET", "/crm/v3/objects/contacts/501")] = "hubspot__lecture"
    lu = await operer(1, "hubspot", "dossier", "lire", {"id_externe": "501"}, delai=3)
    assert lu == {
        "id_externe": "501", "nom": "Martin", "prenom": "Jeanne", "mail": "j@exemple.fr",
        "code_postal": "60000", "commune": "Beauvais", "telephones": [NUMERO],
    }  # fmt: skip
