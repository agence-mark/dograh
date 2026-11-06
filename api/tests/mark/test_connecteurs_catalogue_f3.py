"""[.mark] Non-regression test of the connectors of the catalogue, second half, and of the proposals (U3 sexies, F3).

Slack, WhatsApp Business, Google Sheets, Airtable, Notion, Zendesk, Freshdesk, Crisp, Pennylane,
Doctolib, the cards « À activer ». Then point 9 (E77): the proposals to a client, the account's name
and « Autorisé par » carried by the connection, several accounts of one software per organization.

The questions this file answers:

    Does each action send the request its vendor's documentation describes, and return the USEFUL
    result only (D8)? Does a channel that can reach anyone (SMS, WhatsApp) go only to the caller's
    own number? Does a value put in a formula (Airtable) never break out of it? Does one
    organization ever reach another's connection, proposal or link (D6)? Does a tool keep the
    account it was given when the organization has two?

Why it exists
-------------
Like the first half (``test_connecteurs_catalogue_f2.py``), every connector is « À essayer »: coded from
the vendor's public documentation, never called for real. The answers are RECORDED IN FILES
(``reponses_enregistrees_connecteurs/``), written from the documented shapes: they prove our reading
and our bodies, not the vendor. The trial on a test account is done with Evan (D3).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services.auth.depends import get_user_with_selected_organization
from api.services.integrations.connectors import execution, nango, propositions
from api.services.integrations.connectors.catalogue import connecteur, connecteurs
from api.services.integrations.connectors.routes import router

ENREGISTREES = Path(__file__).parent / "reponses_enregistrees_connecteurs"
NUMERO = "+33612345678"
FICHE = {
    "extracted_variables": {"prenom": "Jeanne", "nom": "Martin", "mail": "j@exemple.fr", "motif": "panne"}
}
INTEGRATIONS = (
    "slack", "whatsapp-business", "google-sheet", "airtable", "notion", "zendesk", "freshdesk",
    "crisp", "pennylane", "twilio",
)  # fmt: skip


def enregistree(nom: str):
    return json.loads((ENREGISTREES / f"{nom}.json").read_text(encoding="utf-8"))


class Relais:
    """A Nango whose relay answers with the recorded files, by (method, path). Organization 1 is
    connected to every software; ``comptes`` adds named accounts (tags ``compte``, ``autorise_par``)."""

    def __init__(self):
        self.routes: dict[tuple[str, str], str] = {}
        self.vus: list[httpx.Request] = []
        self.sessions: list[dict] = []
        self.comptes: list[tuple[str, str, str]] = []  # (integration, compte, connection_id)

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        chemin = requete.url.path
        if chemin == "/connections":
            if requete.url.params.get("tags[organization_id]") != "1":
                return httpx.Response(200, json={"connections": []})
            liste = [
                {"connection_id": f"cx-{i}", "provider_config_key": i, "tags": {"organization_id": "1"}}
                for i in INTEGRATIONS
                if not any(i == c[0] for c in self.comptes)
            ]
            liste += [
                {
                    "connection_id": cid,
                    "provider_config_key": i,
                    "tags": {"organization_id": "1", "compte": compte, "autorise_par": "Paul Durand"},
                }
                for i, compte, cid in self.comptes
            ]
            return httpx.Response(200, json={"connections": liste})
        if chemin == "/connect/sessions":
            self.sessions.append(json.loads(requete.content))
            return httpx.Response(201, json={"data": {"connect_link": "https://connect.test/x", "expires_at": "z"}})
        if chemin.startswith("/proxy"):
            self.vus.append(requete)
            nom = self.routes.get((requete.method, chemin[len("/proxy"):]))
            if nom is None:
                return httpx.Response(404, json={"error": "pas de réponse enregistrée"})
            return httpx.Response(200, json=enregistree(nom))
        return httpx.Response(404)

    def corps(self, rang: int = -1):
        return json.loads(self.vus[rang].content)


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


async def jouer(nom, action, arguments=None, reglages=None, fiche=FICHE, organisation=1, compte=None):
    config = {"connecteur": nom, "action": action, "reglages": reglages or {}, "delai_ms": 4000}
    if compte:
        config["compte"] = compte
    return await execution.executer(organisation, config, arguments or {}, fiche, NUMERO)


# --------------------------------------------------------------------------- #
# 1. The catalogue
# --------------------------------------------------------------------------- #

ATTENDU = {
    "slack": {"post_message"},
    "whatsapp_business": {"send_template"},
    "google_sheets": {"append_row", "find_row"},
    "airtable": {"find_record", "create_record"},
    "notion": {"create_page"},
    "zendesk": {"find_contact", "create_contact", "create_ticket"},
    "freshdesk": {"create_ticket"},
    "crisp": {"create_conversation"},
    "pennylane": {"read_invoice"},
    "doctolib": {"send_booking_link"},
}
CARTES = ("hektor", "apimo", "cosium", "vetstoria", "praxedo")


def test_chaque_logiciel_declare_ses_actions_et_aucune_ecriture_n_est_anticipee():
    for nom, actions in ATTENDU.items():
        c = connecteur(nom)
        assert c is not None, nom
        assert c.etat == "a_essayer", nom
        assert {a.nom for a in c.actions} == actions, nom
        for a in c.actions:
            assert a.anticipable_permis == (not a.ecrit), f"{nom}.{a.nom}"
            assert "organization_id" not in {p.nom for p in a.parametres}
    assert len({c.nom for c in connecteurs()}) == len(connecteurs())


def test_les_cartes_a_activer_n_ont_aucune_action_et_ne_se_branchent_pas():
    for nom in CARTES:
        c = connecteur(nom)
        assert c is not None and c.etat == "a_activer" and not c.actions and c.editeur, nom
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, email="e@x.fr", selected_organization_id=1
    )
    client = TestClient(app)
    assert client.post("/connecteurs/lien", json={"connecteurs": ["hektor"]}).status_code == 422
    vue = {c["nom"]: c for c in client.get("/connecteurs/catalogue").json()}
    assert vue["hektor"]["etat"] == "a_activer" and vue["hektor"]["editeur"] == "La Boîte Immo"
    assert vue["slack"]["etat"] == "a_essayer" and vue["equipe"]["etat"] == "interne"


# --------------------------------------------------------------------------- #
# 2. Messages
# --------------------------------------------------------------------------- #


async def test_slack_publie_dans_le_canal_du_client_jamais_dans_un_autre(relais):
    relais.routes[("POST", "/api/chat.postMessage")] = "slack__publie"
    r = await jouer("slack", "post_message", {"message": "Rappel demandé.", "channel": "C-AUTRE"}, {"canal": "C0123"})
    assert r.statut == "ok" and r.donnees == {"publie": True}
    corps = relais.corps()
    assert corps["channel"] == "C0123" and corps["text"].startswith("Rappel demandé.")
    assert "Motif : panne" in corps["text"]


async def test_slack_qui_refuse_en_200_est_un_echec_pas_un_succes(relais):
    relais.routes[("POST", "/api/chat.postMessage")] = "slack__refus"
    r = await jouer("slack", "post_message", {"message": "x"}, {"canal": "C0123"})
    assert r.statut == "repli"


async def test_slack_sans_canal_ne_part_pas(relais):
    r = await jouer("slack", "post_message", {"message": "x"})
    assert r.statut == "repli" and relais.vus == []


async def test_whatsapp_envoie_le_modele_au_numero_de_l_appelant_seulement(relais):
    relais.routes[("POST", "/v21.0/1055/messages")] = "whatsapp__envoi"
    reglages = {"identifiant_numero": "1055", "modele": "confirmation_rdv", "langue": "fr"}
    r = await jouer(
        "whatsapp_business", "send_template", {"variable_1": "jeudi 14 h", "to": "+33700000000"}, reglages
    )
    assert r.donnees == {"envoye": True, "statut": "accepted"}
    corps = relais.corps()
    assert corps["to"] == "33612345678" and corps["type"] == "template"
    assert corps["template"]["name"] == "confirmation_rdv" and corps["template"]["language"] == {"code": "fr"}
    assert corps["template"]["components"][0]["parameters"] == [{"type": "text", "text": "jeudi 14 h"}]
    assert "33700000000" not in json.dumps(corps)  # a number the model says is ignored


async def test_whatsapp_sans_modele_ne_part_pas(relais):
    r = await jouer("whatsapp_business", "send_template", {}, {"identifiant_numero": "1055"})
    assert r.statut == "repli" and relais.vus == []


async def test_doctolib_envoie_la_page_du_praticien_par_sms_a_l_appelant(relais):
    relais.routes[("POST", "/2010-04-01/Accounts/AC123/Messages.json")] = "twilio__message"
    reglages = {"page": "https://www.doctolib.fr/medecin/senlis/dr-x", "sid_compte": "AC123", "expediteur": "+33700000001"}
    r = await jouer("doctolib", "send_booking_link", {}, reglages)
    assert r.statut == "ok" and r.donnees["envoye"] is True
    from urllib.parse import parse_qs

    envoye = parse_qs(relais.vus[0].content.decode())
    assert envoye["To"] == [NUMERO]
    assert "https://www.doctolib.fr/medecin/senlis/dr-x" in envoye["Body"][0]


@pytest.mark.parametrize(
    "page",
    ["https://evil.example/doctolib.fr", "http://www.doctolib.fr/x", "https://www.doctolib.fr.evil.io/x", "https://u@www.doctolib.fr/x", ""],
)
async def test_doctolib_n_envoie_jamais_un_lien_qui_n_est_pas_doctolib(relais, page):
    reglages = {"page": page, "sid_compte": "AC123", "expediteur": "+33700000001"}
    r = await jouer("doctolib", "send_booking_link", {}, reglages)
    assert r.statut == "repli" and relais.vus == []


# --------------------------------------------------------------------------- #
# 3. Data
# --------------------------------------------------------------------------- #

FEUILLE = {"classeur": "s1", "feuille": "Appels", "colonne_telephone": "C", "colonnes_lues": "B"}


async def test_google_sheets_ajoute_une_ligne_et_rend_ajoute(relais):
    relais.routes[("POST", "/v4/spreadsheets/s1/values/Appels:append")] = "sheets__ajout"
    r = await jouer("google_sheets", "append_row", {"note": "Veut un devis."}, FEUILLE)
    assert r.donnees == {"ajoute": True}
    requete = relais.vus[0]
    assert requete.url.params["valueInputOption"] == "RAW" and requete.url.params["insertDataOption"] == "INSERT_ROWS"
    ligne = relais.corps()["values"][0]
    assert ligne[1:] == ["Jeanne Martin", NUMERO, "j@exemple.fr", "panne", "Veut un devis."]


async def test_google_sheets_retrouve_la_ligne_par_n_importe_quelle_ecriture_du_numero_et_ne_rend_que_les_colonnes_choisies(relais):
    relais.routes[("GET", "/v4/spreadsheets/s1/values/Appels")] = "sheets__lecture"
    r = await jouer("google_sheets", "find_row", {}, FEUILLE)
    assert r.donnees == {"ligne": ["Jeanne Martin"]}
    assert "interne" not in json.dumps(r.donnees)  # the column « Secret » was not chosen (D8)


async def test_google_sheets_une_colonne_qui_n_est_pas_une_lettre_est_refusee(relais):
    relais.routes[("GET", "/v4/spreadsheets/s1/values/Appels")] = "sheets__lecture"
    r = await jouer("google_sheets", "find_row", {}, {**FEUILLE, "colonne_telephone": "C1; DROP"})
    assert r.statut == "repli"


AIRTABLE = {"base": "appXYZ", "table": "Clients"}


async def test_airtable_cherche_par_formule_ne_rend_que_les_champs_lus(relais):
    relais.routes[("GET", "/v0/appXYZ/Clients")] = "airtable__recherche"
    r = await jouer("airtable", "find_record", {}, AIRTABLE)
    assert r.donnees == {"enregistrement": {"identifiant": "rec123", "champs": {"Nom": "Jeanne Martin"}}}
    formule = relais.vus[0].url.params["filterByFormula"]
    assert formule == f'OR({{Téléphone}}="{NUMERO}",{{Téléphone}}="0612345678")'
    assert "ne pas lire" not in json.dumps(r.donnees)


async def test_airtable_rien_trouve_dit_aucun(relais):
    relais.routes[("GET", "/v0/appXYZ/Clients")] = "airtable__vide"
    r = await jouer("airtable", "find_record", {}, AIRTABLE)
    assert r.donnees == {"enregistrement": None, "aucun": True}


async def test_airtable_un_champ_avec_une_accolade_ne_sort_pas_de_la_formule(relais):
    relais.routes[("GET", "/v0/appXYZ/Clients")] = "airtable__vide"
    r = await jouer("airtable", "find_record", {}, {**AIRTABLE, "champ_telephone": 'T"x'})
    assert r.statut == "ok"  # quotes inside a field name are inside braces: harmless
    r = await jouer("airtable", "find_record", {}, {**AIRTABLE, "champ_telephone": "T}x"})
    assert r.statut == "repli"


async def test_airtable_cree_l_enregistrement_dans_les_champs_nommes(relais):
    relais.routes[("POST", "/v0/appXYZ/Clients")] = "airtable__creation"
    r = await jouer("airtable", "create_record", {}, {**AIRTABLE, "champ_motif": "Motif"})
    assert r.donnees == {"cree": True, "identifiant": "recNEW1"}
    assert relais.corps()["fields"] == {
        "Nom": "Jeanne Martin", "Téléphone": NUMERO, "Email": "j@exemple.fr", "Motif": "panne",
    }  # fmt: skip


async def test_airtable_une_base_qui_n_est_pas_une_base_est_refusee(relais):
    r = await jouer("airtable", "create_record", {}, {"base": "../../autre", "table": "Clients"})
    assert r.statut == "repli" and relais.vus == []


async def test_notion_cree_la_page_dans_la_source_de_donnees_du_client(relais):
    relais.routes[("POST", "/v1/pages")] = "notion__page"
    r = await jouer("notion", "create_page", {"resume": "Veut un devis."}, {"parent": "ds-1", "propriete_titre": "Nom"})
    assert r.donnees == {"cree": True, "identifiant": "page-0001"}
    corps = relais.corps()
    assert corps["parent"] == {"data_source_id": "ds-1"}
    assert corps["properties"]["Nom"]["title"][0]["text"]["content"] == "panne"
    assert len(corps["children"]) == 2


async def test_notion_refuse_un_type_de_parent_inconnu(relais):
    r = await jouer("notion", "create_page", {"resume": "x"}, {"parent": "p", "type_parent": "workspace"})
    assert r.statut == "repli" and relais.vus == []


# --------------------------------------------------------------------------- #
# 4. Support, books
# --------------------------------------------------------------------------- #


async def test_zendesk_cherche_cree_et_ouvre_un_ticket(relais):
    relais.routes[("GET", "/api/v2/search")] = "zendesk__recherche"
    relais.routes[("POST", "/api/v2/users")] = "zendesk__utilisateur"
    relais.routes[("POST", "/api/v2/tickets")] = "zendesk__ticket"
    r = await jouer("zendesk", "find_contact")
    assert r.donnees == {"contacts": [{"identifiant": "55", "nom": "Jeanne Martin"}]}
    assert "j@exemple.fr" not in json.dumps(r.donnees)
    assert relais.vus[0].url.params["query"] == f"type:user phone:{NUMERO}"
    r = await jouer("zendesk", "create_contact")
    assert r.donnees == {"cree": True, "identifiant": "99"}
    assert relais.corps() == {"user": {"name": "Jeanne Martin", "email": "j@exemple.fr", "phone": NUMERO}}
    r = await jouer("zendesk", "create_ticket", {"sujet": "Panne", "description": "Plus de chauffage.", "identifiant": "55"}, {"priorite": "high"})
    assert r.donnees == {"cree": True, "identifiant": "35436"}
    ticket = relais.corps()["ticket"]
    assert ticket["requester_id"] == 55 and ticket["priority"] == "high"
    assert ticket["comment"]["body"].endswith(NUMERO)


async def test_zendesk_une_priorite_inconnue_est_refusee(relais):
    r = await jouer("zendesk", "create_ticket", {"sujet": "x", "description": "y"}, {"priorite": "critique"})
    assert r.statut == "repli" and relais.vus == []


async def test_freshdesk_ouvre_le_ticket_au_nom_de_l_appelant(relais):
    relais.routes[("POST", "/api/v2/tickets")] = "freshdesk__ticket"
    r = await jouer("freshdesk", "create_ticket", {"sujet": "Panne", "description": "Ligne 1\nLigne 2"})
    assert r.donnees == {"cree": True, "identifiant": "4242"}
    corps = relais.corps()
    assert (corps["email"], corps["phone"], corps["status"], corps["priority"]) == ("j@exemple.fr", NUMERO, 2, 1)
    assert corps["description"] == "Ligne 1<br>Ligne 2"


async def test_crisp_ouvre_la_conversation_puis_y_pose_la_demande(relais):
    relais.routes[("POST", "/v1/website/site-1/conversation")] = "crisp__conversation"
    relais.routes[("POST", "/v1/website/site-1/conversation/session_abc/message")] = "crisp__message"
    r = await jouer("crisp", "create_conversation", {"message": "Panne de chaudière."}, {"site": "site-1"})
    assert r.donnees == {"cree": True, "identifiant": "session_abc"}
    assert [v.url.path for v in relais.vus] == [
        "/proxy/v1/website/site-1/conversation",
        "/proxy/v1/website/site-1/conversation/session_abc/message",
    ]
    message = relais.corps()
    assert message["from"] == "user" and message["type"] == "text" and NUMERO in message["content"]


async def test_pennylane_lit_l_etat_d_une_facture_et_rien_d_autre(relais):
    relais.routes[("GET", "/api/external/v2/customer_invoices")] = "pennylane__facture"
    r = await jouer("pennylane", "read_invoice", {"numero": "F20230001"})
    assert r.donnees == {
        "facture": {"numero": "F20230001", "etat": "late", "payee": False, "reste_a_payer": "120.00", "echeance": "2026-10-01"}
    }
    assert "Ne pas lire" not in json.dumps(r.donnees) and "customers/5" not in json.dumps(r.donnees)
    assert json.loads(relais.vus[0].url.params["filter"]) == [
        {"field": "invoice_number", "operator": "eq", "value": "F20230001"}
    ]


async def test_pennylane_facture_inconnue_dit_aucune(relais):
    relais.routes[("GET", "/api/external/v2/customer_invoices")] = "pennylane__vide"
    r = await jouer("pennylane", "read_invoice", {"numero": "X"})
    assert r.donnees == {"facture": None, "aucune": True}


# --------------------------------------------------------------------------- #
# 5. Cloisonnement et plusieurs comptes (D6, E77)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nom,action,args,reglages", [
    ("slack", "post_message", {"message": "x"}, {"canal": "C1"}),
    ("zendesk", "find_contact", {}, {}),
    ("pennylane", "read_invoice", {"numero": "F1"}, {}),
    ("airtable", "find_record", {}, AIRTABLE),
])  # fmt: skip
async def test_une_organisation_sans_connexion_n_atteint_pas_celle_d_une_autre(relais, nom, action, args, reglages):
    r = await jouer(nom, action, args, reglages, organisation=2)
    assert r.statut == "repli" and relais.vus == []


async def test_deux_comptes_d_un_meme_logiciel_chaque_outil_garde_le_sien(relais):
    relais.comptes = [("slack", "equipe vente", "cx-vente"), ("slack", "equipe sav", "cx-sav")]
    relais.routes[("POST", "/api/chat.postMessage")] = "slack__publie"
    await jouer("slack", "post_message", {"message": "a"}, {"canal": "C1"}, compte="equipe sav")
    await jouer("slack", "post_message", {"message": "b"}, {"canal": "C1"}, compte="equipe vente")
    assert [v.headers["Connection-Id"] for v in relais.vus] == ["cx-sav", "cx-vente"]
    r = await jouer("slack", "post_message", {"message": "c"}, {"canal": "C1"}, compte="compte inconnu")
    assert r.statut == "repli" and len(relais.vus) == 2


async def test_le_compte_suit_une_action_mise_de_cote_pour_l_apres_appel():
    fiche: dict = {}
    execution.mettre_de_cote(fiche, {"connecteur": "slack", "action": "post_message", "compte": "equipe sav"}, {})
    assert fiche[execution.CLE_DIFFERES][0]["compte"] == "equipe sav"


# --------------------------------------------------------------------------- #
# 6. Point 9: proposals, links, who authorized
# --------------------------------------------------------------------------- #


class BaseEnMemoire:
    def __init__(self):
        self.lignes: dict[tuple[int, str], object] = {}

    async def get_configuration(self, organization_id, key):
        v = self.lignes.get((organization_id, key))
        return None if v is None else SimpleNamespace(value=v)

    async def upsert_configuration(self, organization_id, key, value, last_validated_at=None):
        self.lignes[(organization_id, key)] = value
        return SimpleNamespace(value=value)


@pytest.fixture
def base():
    memoire = BaseEnMemoire()
    # [.mark] « Utilisé par » des logiciels (lot F6) lit les outils dans la vraie base : depuis le TestClient (une autre boucle)
    # il tombait sur les connexions d'un test antérieur (« attached to a different loop »), dans la suite entière seulement.
    # Couvert par ``test_connexion_portail_et_logiciels.py`` ; ici, aucun outil.
    from unittest.mock import AsyncMock

    from api.services.integrations.connectors import utilisation

    with patch.object(propositions, "db_client", memoire), patch.object(
        utilisation, "outils_par_logiciel", AsyncMock(return_value={})
    ):
        yield memoire


def client_de(organisation: int) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=organisation, email=f"dirigeant{organisation}@client.fr", selected_organization_id=organisation
    )
    return TestClient(app)


def test_proposer_lister_relancer_retirer(base, relais):
    c = client_de(1)
    cree = c.post("/connecteurs/propositions", json={"connecteur": "google_agenda", "compte": "agenda des techniciens", "message": "Pour poser les rendez-vous."})
    assert cree.status_code == 201, cree.text
    p = cree.json()
    assert (p["etat"], p["propose_par"], p["relances"]) == ("a_autoriser", "dirigeant1@client.fr", 0)
    assert c.post("/connecteurs/propositions", json={"connecteur": "google_agenda", "compte": "agenda des techniciens"}).status_code == 409
    assert [x["identifiant"] for x in c.get("/connecteurs/propositions").json()] == [p["identifiant"]]
    relance = c.post(f"/connecteurs/propositions/{p['identifiant']}/relancer").json()
    assert relance["relances"] == 1 and relance["relance_le"]
    assert c.delete(f"/connecteurs/propositions/{p['identifiant']}").status_code == 200
    assert c.get("/connecteurs/propositions").json() == []


@pytest.mark.parametrize("connecteur_nom", ["hektor", "equipe", "n_existe_pas"])
def test_on_ne_propose_ni_une_carte_a_activer_ni_un_connecteur_interne_ni_un_inconnu(base, relais, connecteur_nom):
    r = client_de(1).post("/connecteurs/propositions", json={"connecteur": connecteur_nom, "compte": "x"})
    assert r.status_code == 422


def test_le_lien_porte_l_organisation_le_compte_et_qui_autorise(base, relais):
    c = client_de(1)
    p = c.post("/connecteurs/propositions", json={"connecteur": "slack", "compte": "equipe sav"}).json()
    r = c.post(f"/connecteurs/propositions/{p['identifiant']}/lien", json={"autorise_par": "  Martine   Leroy "})
    assert r.status_code == 200 and r.json()["lien"] == "https://connect.test/x"
    session = relais.sessions[-1]
    assert session["tags"] == {"organization_id": "1", "compte": "equipe sav", "autorise_par": "Martine Leroy"}
    assert session["allowed_integrations"] == ["slack"]
    c.post(f"/connecteurs/propositions/{p['identifiant']}/lien")  # nobody named: the signed-in person
    assert relais.sessions[-1]["tags"]["autorise_par"] == "dirigeant1@client.fr"


def test_la_proposition_d_une_organisation_est_inconnue_d_une_autre(base, relais):
    p = client_de(1).post("/connecteurs/propositions", json={"connecteur": "slack", "compte": "equipe sav"}).json()
    autre = client_de(2)
    assert autre.get("/connecteurs/propositions").json() == []
    for appel in (
        lambda: autre.post(f"/connecteurs/propositions/{p['identifiant']}/lien"),
        lambda: autre.post(f"/connecteurs/propositions/{p['identifiant']}/relancer"),
        lambda: autre.delete(f"/connecteurs/propositions/{p['identifiant']}"),
    ):
        assert appel().status_code == 404
    assert relais.sessions == []  # no link was ever made for the other organization
    assert len(client_de(1).get("/connecteurs/propositions").json()) == 1  # and hers is intact


def test_la_proposition_devient_autorisee_quand_le_compte_est_branche_et_dit_qui_a_autorise(base, relais):
    c = client_de(1)
    c.post("/connecteurs/propositions", json={"connecteur": "slack", "compte": "equipe sav"})
    assert c.get("/connecteurs/propositions").json()[0]["etat"] == "a_autoriser"
    relais.comptes = [("slack", "equipe sav", "cx-sav")]
    p = c.get("/connecteurs/propositions").json()[0]
    assert (p["etat"], p["autorise_par"]) == ("autorisee", "Paul Durand")
    connexions = c.get("/connecteurs/connexions").json()["connexions"]
    assert {(x["compte"], x["autorise_par"]) for x in connexions if x["integration"] == "slack"} == {("equipe sav", "Paul Durand")}


def test_le_lien_du_labo_porte_le_compte_et_qui_a_branche(relais):
    r = client_de(1).post("/connecteurs/lien", json={"connecteurs": ["slack"], "compte": "compte de test .mark"})
    assert r.status_code == 200
    assert relais.sessions[-1]["tags"] == {
        "organization_id": "1", "compte": "compte de test .mark", "autorise_par": "dirigeant1@client.fr",
    }  # fmt: skip


async def test_la_suppression_vise_le_compte_nomme(relais):
    relais.comptes = [("slack", "equipe vente", "cx-vente"), ("slack", "equipe sav", "cx-sav")]
    supprimes = []
    base_requete = relais.__call__

    async def espion(requete: httpx.Request) -> httpx.Response:
        if requete.method == "DELETE":
            supprimes.append(requete.url.path)
            return httpx.Response(200)
        return await base_requete(requete)

    with patch.object(nango, "nouveau_client", lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(espion), **o)):
        await nango.supprimer_connexion(1, "slack", "equipe sav")
    assert supprimes == ["/connection/cx-sav"]
