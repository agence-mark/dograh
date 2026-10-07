"""[.mark] Non-regression test for the connectors (chantier l-agent-travaille, L5; plan connecteurs-agent).

The questions this file answers:

    Does an organization ever reach another's connection (list, relay, link)? Does an
    ``organization_id`` sent by the model ever travel? Through the REAL dispatcher of the
    engine (``CustomToolManager``), does an ``integration`` tool give the model the useful
    result only, say the waiting phrase, and on a deadline or a dead Nango SAY the fallback
    phrase (never a blank) and put a writing action aside for the after-call, which does it?
    Is an action that writes refused as anticipable? Does an anticipated read land before the
    model asks, get used with the same parameters, thrown away with others, and stamped?
    Do the Google Agenda slots respect the client's rules?

Why it exists
-------------
🔴 R1: the dispatcher of the upstream (``pipecat_engine_custom_tools.py``) sends every
unknown category to the HTTP tool; an integration tool that silently became an HTTP call, or
an error swallowed, is an agent that promises an appointment nobody booked.

Nango is a stand-in (``httpx.MockTransport``) that keeps connections by tag like the real one
(checked on the real one in L0 and in this lot, journal). No request leaves the machine.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import httpx
import pytest

from api.enums import ToolCategory
from api.schemas.tool import CreateToolRequest
from api.services.integrations.connectors import anticipation, execution, nango
from api.services.integrations.connectors.actions import google_agenda
from api.services.integrations.connectors.catalogue import (
    Action,
    CatalogueInvalide,
    Connecteur,
    Parametre,
    declarer,
)
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.pipecat_test_utils import stub_agent_runtime

PARIS = ZoneInfo("Europe/Paris")


class FauxNango:
    """Connections by tag, the relay, the connect session; what each request carried."""

    def __init__(self, lent_s: float = 0.0, en_panne: bool = False):
        self.connexions = [
            {
                "connection_id": "cx-a",
                "provider_config_key": "google-calendar",
                "tags": {"organization_id": "1"},
            },
            {
                "connection_id": "cx-b",
                "provider_config_key": "google-calendar",
                "tags": {"organization_id": "2"},
            },
        ]
        self.relais: list[httpx.Request] = []
        self.lent_s = lent_s
        self.en_panne = en_panne
        self.reponse_relais: dict = {"calendars": {"primary": {"busy": []}}}

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.en_panne:
            raise httpx.ConnectError("down")
        chemin = requete.url.path
        if chemin == "/connections":
            tag = requete.url.params.get("tags[organization_id]")
            # Like the real one; the test « listing not trusted » sends both back.
            gardees = (
                [c for c in self.connexions if c["tags"]["organization_id"] == tag]
                if not getattr(self, "tout", False)
                else self.connexions
            )
            return httpx.Response(200, json={"connections": gardees})
        if chemin == "/connect/sessions":
            corps = json.loads(requete.content)
            return httpx.Response(
                201,
                json={
                    "data": {
                        "connect_link": f"https://connect/{corps['tags']['organization_id']}",
                        "expires_at": "x",
                    }
                },
            )
        if chemin.startswith("/proxy/"):
            self.relais.append(requete)
            if self.lent_s:
                await asyncio.sleep(self.lent_s)
            return httpx.Response(200, json=self.reponse_relais)
        return httpx.Response(404)


@pytest.fixture
def faux_nango(monkeypatch):
    faux = FauxNango()
    monkeypatch.setenv(nango.VARIABLE_URL, "http://nango.local")
    monkeypatch.setenv(nango.VARIABLE_CLE, "cle-secrete-nango-0123")
    monkeypatch.setattr(
        nango,
        "nouveau_client",
        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(faux), **o),
    )
    return faux


CONFIG_CRENEAUX = {
    "connecteur": "google_agenda",
    "action": "find_free_slots",
    "delai_ms": 2000,
    "phrase_attente": "Je regarde l'agenda.",
}
CONFIG_RDV = {
    "connecteur": "google_agenda",
    "action": "book_appointment",
    "delai_ms": 600,
    "phrase_repli": "Je transmets, on vous rappelle.",
}


# --------------------------------------------------------------------------- #
# 1. Tenant isolation (D6)
# --------------------------------------------------------------------------- #


async def test_une_organisation_n_atteint_jamais_la_connexion_d_une_autre(faux_nango):
    assert [c.connection_id for c in await nango.connexions(1)] == ["cx-a"]
    assert [c.connection_id for c in await nango.connexions(2)] == ["cx-b"]
    # A Nango that would send every connection back: the tag is checked again.
    faux_nango.tout = True
    assert [c.connection_id for c in await nango.connexions(1)] == ["cx-a"]
    with pytest.raises(nango.ConnexionAbsente):
        await nango.connexion_de(3, "google-calendar")
    await nango.relayer(
        1,
        "google-calendar",
        nango.Requete("POST", "/calendar/v3/freeBusy", json={}),
        delai=2,
    )
    assert faux_nango.relais[-1].headers["Connection-Id"] == "cx-a"
    assert (
        faux_nango.relais[-1].headers["Authorization"]
        == "Bearer cle-secrete-nango-0123"
    )
    lien = await nango.lien_d_autorisation(2, ["google-calendar"])
    assert lien["lien"] == "https://connect/2"
    with pytest.raises(ValueError):
        await nango.relayer(
            1, "google-calendar", nango.Requete("GET", "https://ailleurs/x"), delai=1
        )
    with pytest.raises(ValueError):
        await nango.connexions("1")  # never a value read from a request


async def test_l_organisation_envoyee_par_le_modele_ne_voyage_jamais(faux_nango):
    resultat = await execution.executer(
        1, CONFIG_CRENEAUX, {"motif": "entretien", "organization_id": 2}
    )
    assert resultat.statut == "ok"
    envoye = faux_nango.relais[-1]
    assert envoye.headers["Connection-Id"] == "cx-a"
    assert "organization_id" not in envoye.content.decode()


def test_le_catalogue_refuse_une_ecriture_anticipable_et_l_organisation_en_parametre():
    def rien(*a, **k):
        return {}

    with pytest.raises(CatalogueInvalide):
        declarer(
            Connecteur(
                "essai_x",
                "X",
                "x",
                (Action("ecrire", "", (), True, rien, rien, anticipable_permis=True),),
            )
        )
    with pytest.raises(CatalogueInvalide):
        declarer(
            Connecteur(
                "essai_y",
                "Y",
                "y",
                (
                    Action(
                        "lire", "", (Parametre("organization_id"),), False, rien, rien
                    ),
                ),
            )
        )
    with pytest.raises(ValueError, match="never anticipated"):
        CreateToolRequest(
            name="Poser",
            definition={
                "type": "integration",
                "config": {
                    **CONFIG_RDV,
                    "anticipable": True,
                    "declencheurs": {"debut": "x"},
                },
            },
        )
    with pytest.raises(ValueError, match="Unknown action"):
        CreateToolRequest(
            name="X",
            definition={
                "type": "integration",
                "config": {"connecteur": "google_agenda", "action": "inconnue"},
            },
        )


# --------------------------------------------------------------------------- #
# 2. Through the real dispatcher of the engine (R1)
# --------------------------------------------------------------------------- #


def _outil(config, nom="Agenda"):
    t = MagicMock()
    t.tool_uuid = f"uuid-{nom}"
    t.name = nom
    t.description = None
    t.category = ToolCategory.INTEGRATION.value
    t.definition = {"type": "integration", "config": config}
    return t


def _moteur(monkeypatch, outils):
    engine = MagicMock()
    engine.active_agent = stub_agent_runtime(llm=MagicMock())
    engine._gathered_context = {
        "extracted_variables": {"nom": "Martin", "motif": "entretien"}
    }
    engine._call_context_vars = {"caller_number": "+33612345678"}
    engine.queue_text_message = AsyncMock()
    enregistres = {}
    engine.active_agent.llm.register_function = lambda nom, fn, **kw: (
        enregistres.__setitem__(nom, (fn, kw))
    )
    from api.db import db_client

    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(return_value=outils))
    mgr = CustomToolManager(engine)
    mgr.get_organization_id = AsyncMock(return_value=1)
    return engine, mgr, enregistres


async def _appeler(fn, arguments):
    capte = {}

    class P:
        function_name = "x"

        def __init__(self):
            self.arguments = arguments

        async def result_callback(self, r, *, properties=None):
            capte["r"] = r

    await fn(P())
    return capte["r"]


async def test_outil_integration_par_le_vrai_repartiteur(faux_nango, monkeypatch):
    faux_nango.reponse_relais = {
        "calendars": {
            "primary": {
                "busy": [
                    {"start": "2030-01-07T08:00:00Z", "end": "2030-01-07T09:00:00Z"}
                ]
            }
        },
        "secret_d_un_autre_rendez_vous": "Dr X",
    }
    engine, mgr, enregistres = _moteur(monkeypatch, [_outil(CONFIG_CRENEAUX)])
    schemas = await mgr.get_tool_schemas(["uuid-Agenda"])
    assert [s.name for s in schemas] == ["agenda"]
    assert set(schemas[0].properties) == {"motif", "date"}  # never the organization
    await mgr.register_handlers(["uuid-Agenda"])
    fn, kw = enregistres["agenda"]
    assert kw["timeout_secs"] == pytest.approx(7.0)
    r = await _appeler(fn, {"motif": "entretien", "date": "2030-01-07"})
    assert (
        set(r) == {"creneaux"} and len(r["creneaux"]) == 3
    )  # D8: the useful result only
    engine.queue_text_message.assert_awaited_with(
        "Je regarde l'agenda.", mute_user=True
    )
    trace = engine._gathered_context["connecteurs"][-1]
    assert trace["statut"] == "ok" and trace["duree_ms"] is not None


async def test_delai_depasse_phrase_de_repli_dite_et_ecriture_mise_de_cote(
    faux_nango, monkeypatch
):
    faux_nango.lent_s = 2.0
    engine, mgr, enregistres = _moteur(monkeypatch, [_outil(CONFIG_RDV, "Poser")])
    await mgr.register_handlers(["uuid-Poser"])
    r = await _appeler(
        enregistres["poser"][0],
        {"debut": "2030-01-07T09:00:00+01:00", "organization_id": 2},
    )
    assert r["status"] == "passed_on"
    engine.queue_text_message.assert_awaited_with(
        "Je transmets, on vous rappelle.", mute_user=True
    )
    differe = engine._gathered_context["connecteurs_differes"]
    assert differe == [
        {
            "connecteur": "google_agenda",
            "action": "book_appointment",
            "reglages": {},
            "arguments": {"debut": "2030-01-07T09:00:00+01:00"},
        }
    ]
    assert engine._gathered_context["connecteurs"][-1]["statut"] == "repli"

    # Nango dead: the same fallback, the call goes on.
    faux_nango.lent_s, faux_nango.en_panne = 0, True
    r = await _appeler(enregistres["poser"][0], {"debut": "2030-01-07T10:00:00+01:00"})
    assert r["status"] == "passed_on"

    # The after-call module does what was put aside, once, with the run's organization.
    from api.db import db_client
    from api.schemas.apres_appel import ApresAppelAgent, ReglagesApresAppel
    from api.services.apres_appel.modules import MODULES, ContexteModule

    faux_nango.en_panne = False
    etat: dict = {}
    monkeypatch.setattr(
        db_client, "lire_apres_appel", AsyncMock(side_effect=lambda _id: etat)
    )

    async def fusionner(_id, etape=None, valeur=None, racine=None):
        etat.setdefault("etapes", {}).setdefault(etape, {}).update(valeur or {})
        return etat

    monkeypatch.setattr(db_client, "fusionner_apres_appel", fusionner)
    run = SimpleNamespace(id=9, gathered_context=engine._gathered_context)
    ctx = ContexteModule(
        organization_id=1,
        run=run,
        reglages=ReglagesApresAppel(),
        agent=ApresAppelAgent(),
        envoi={"numero_appelant": "+33612345678"},
    )
    avant = len(faux_nango.relais)
    resultat = await MODULES["connecteurs"](ctx)
    assert len(resultat.envois) == 2 and len(faux_nango.relais) == avant + 2
    assert all(r.headers["Connection-Id"] == "cx-a" for r in faux_nango.relais[avant:])
    corps = json.loads(faux_nango.relais[-1].content)
    assert (
        corps["summary"] == "entretien · Martin"
        and "+33612345678" in corps["description"]
    )
    await MODULES["connecteurs"](ctx)  # retried: nothing done twice
    assert len(faux_nango.relais) == avant + 2


async def test_action_anticipee_lancee_utilisee_ou_jetee(faux_nango, monkeypatch):
    config = {
        **CONFIG_CRENEAUX,
        "anticipable": True,
        "declencheurs": {"motif": "motif"},
    }
    faux_nango.lent_s = 0.3
    engine, mgr, enregistres = _moteur(monkeypatch, [_outil(config)])
    await mgr.register_handlers(["uuid-Agenda"])
    fiche = engine._gathered_context
    anticipation.apres_une_note(fiche)  # the record already holds the reason
    assert fiche["connecteurs"][-1]["anticipee"] == "lancee"
    await asyncio.sleep(0.5)
    relais = len(faux_nango.relais)
    r = await _appeler(enregistres["agenda"][0], {"motif": "entretien"})
    assert "creneaux" in r and len(faux_nango.relais) == relais  # no second request
    utilisee = [t for t in fiche["connecteurs"] if t.get("anticipee") == "utilisee"][-1]
    assert utilisee["prete"] is True and utilisee["gain_ms"] >= 250
    # Other parameters: thrown away, the normal call runs.
    fiche["extracted_variables"]["motif"] = "ramonage"
    anticipation.apres_une_note(fiche)
    r = await _appeler(enregistres["agenda"][0], {"motif": "installation"})
    assert "creneaux" in r and any(
        t.get("anticipee") == "jetee" for t in fiche["connecteurs"]
    )


async def test_une_note_lance_l_anticipation_par_le_point_d_ecriture_unique(
    faux_nango, monkeypatch
):
    """The hook is in ``noter`` (tool, postscript, clerk): a note that writes the trigger launches."""
    from api.services.workflow import fiche_au_fil_de_leau as module_fiche

    config = {
        **CONFIG_CRENEAUX,
        "anticipable": True,
        "declencheurs": {"motif": "motif"},
    }
    engine, mgr, _ = _moteur(monkeypatch, [_outil(config)])
    engine._gathered_context = {"extracted_variables": {}}
    await mgr.register_handlers(["uuid-Agenda"])
    appels = []
    monkeypatch.setattr(
        anticipation.Anticipateur, "sur_note", lambda self, fiche: appels.append(fiche)
    )
    reglages = module_fiche.ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [{"nom": "motif", "origine": "deduit"}],
        },
        is_realtime=False,
    )
    await module_fiche.noter(
        lambda: engine._gathered_context,
        reglages,
        {"motif": "entretien"},
        paroles=["c'est pour un entretien"],
        question=None,
    )
    assert appels and appels[0] is engine._gathered_context


# --------------------------------------------------------------------------- #
# 3. Google Agenda: the client's rules (D9)
# --------------------------------------------------------------------------- #


def test_creneaux_respectent_les_regles_du_client():
    maintenant = datetime(2030, 1, 4, 10, 0, tzinfo=PARIS)  # a Friday
    reglages = {
        "duree_par_motif": {"installation|pose": 120},
        "delai_minimal_h": 24,
        "nombre": 3,
    }
    occupe = [
        (
            datetime(2030, 1, 7, 9, 0, tzinfo=PARIS),
            datetime(2030, 1, 7, 10, 0, tzinfo=PARIS),
        )
    ]
    libres = google_agenda.creneaux_libres(
        occupe, {"motif": "pose d'un poêle"}, reglages, maintenant
    )
    # No weekend, not before the notice, not over the busy hour, 2 h for an installation.
    assert [m.isoformat() for m in libres] == [
        "2030-01-07T10:00:00+01:00",
        "2030-01-07T14:00:00+01:00",
        "2030-01-07T16:00:00+01:00",
    ]
    assert google_agenda.libelle(libres[0]) == "lundi 7 janvier à 10 h"
    assert google_agenda.duree(reglages, "entretien") == 60
