"""[.mark] Non-regression test for the appointment planner (chantier l-agent-collegue, L5).

The questions this file answers (P1 to P10, R1, R7):

    Is the caller's wish read right on a corpus whose truth is posed BY HAND -- including the
    known red case « pas le lundi » (read as « lundi » by a naive reader) -- and is what is not
    on the closed list « not understood » rather than guessed? Are the public holidays right,
    in metropolitan France and in Alsace-Moselle? On situations posed by hand (agendas, length,
    margins, journeys, holidays, wish), are the slots EXACTLY the expected ones? Does the turn
    stay fair over a series, the one skipped keeping his priority? Does the computation stay far
    under the action's deadline on a big team and a long horizon? Through the engine's REAL
    dispatcher and a real client database: does the agent get the slots only, book one of THEM
    only, in the right person's agenda, and does the hub get the appointment, its attribution and
    the mention after the call? With no slot, is the fallback played in BOTH modes (the
    call-back SAID by the code; the human handoff told to the model), and does the after-call
    make the call-back request? Is the anticipated read used?

Why it exists
-------------
🔴 R7: a planner that lies offers an appointment nobody can honour, or gives every appointment
to the same person. Only a corpus posed by hand catches it.

The agendas are a stand-in behind the REAL relay (Google's documented answers). No request
leaves the machine; no SMS, no call.
"""

from __future__ import annotations

import asyncio
import json
import time as horloge
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api.services.planificateur.calcul import Candidat, Regles, calculer
from api.services.planificateur.feries import jours_feries, paques
from api.services.planificateur.souhaits import lire_souhait

PARIS = ZoneInfo("Europe/Paris")
# Wednesday 7 October 2026, 10:00 in Paris.
MAINTENANT = datetime(2026, 10, 7, 10, 0, tzinfo=PARIS)


def d(jour: int, mois: int = 10) -> str:
    return date(2026, mois, jour).isoformat()


# --------------------------------------------------------------------------- #
# 1. The caller's wish (P4), truth posed by hand
# --------------------------------------------------------------------------- #

# (words, jours, jours_exclus, des_le, heure_min, heure_max); None = no constraint.
CORPUS_SOUHAITS = [
    ("plutôt mardi matin", [d(13)], [], None, None, "12:00"),
    # Revue du 10/10 : « des » article et « où » ne sont pas des bornes.
    ("je voudrais des disponibilités jeudi", [d(8)], [], None, None, None),
    ("des créneaux le matin", None, [], None, None, "12:00"),
    ("où vous voulez mardi", [d(13)], [], None, None, None),
    ("après 17 heures", None, [], None, "17:00", None),
    ("après dix-sept heures", None, [], None, "17:00", None),
    ("la semaine prochaine", [d(k) for k in range(12, 19)], [], None, None, None),
    ("demain après-midi", [d(8)], [], None, "12:00", None),
    ("après-demain vers 15h", [d(9)], [], None, "14:00", "16:01"),
    ("jeudi entre 14h et 16h", [d(8)], [], None, "14:00", "16:00"),
    ("pas le lundi", None, [0], None, None, None),
    ("pas mardi ni mercredi", None, [1, 2], None, None, None),
    ("le 20 octobre", [d(20)], [], None, None, None),
    ("le 3", [d(3, 11)], [], None, None, None),
    ("le 12/10", [d(12)], [], None, None, None),
    ("en fin de journée", None, [], None, "16:30", None),
    ("avant midi", None, [], None, None, "12:00"),
    ("mercredi", [d(14)], [], None, None, None),  # today is a Wednesday: the NEXT one
    ("vendredi en huit", [d(16)], [], None, None, None),
    ("ce week-end", [d(10), d(11)], [], None, None, None),
    ("pas le matin", None, [], None, "12:00", None),
    ("dans quinze jours", None, [], d(21), None, None),
    ("cette semaine le soir", [d(k) for k in range(7, 12)], [], None, "17:00", None),
    ("en début d'après-midi", None, [], None, "12:00", "15:00"),
    ("Demain, à 9 h 30", [d(8)], [], None, "08:30", "10:31"),
    ("le plus tôt possible", None, [], None, None, None),
]

PAS_COMPRIS = ["n'importe quoi", "quand mon mari rentre", "le matin après 14h", "dès que la neige fond",
               # L1 prudence rule: a negation or a bound word nobody consumed = not understood.
               "pas à 10h", "sauf le week-end", "demain ou après-demain", "pas mardi sauf le matin ou jamais"]

# L1 (reparation-globale): the 8 phrasings added, truth posed by hand. Today: Wednesday 7 October 2026.
# (words, expected fields of the stamp; the fields not listed must be the "nothing" value).
CORPUS_SOUHAITS_L1 = [
    ("pas avant 10h", {"heure_min": "10:00"}),
    ("pas cette semaine", {"dates_exclues": [d(k) for k in range(7, 12)]}),
    ("pas la semaine prochaine", {"dates_exclues": [d(k) for k in range(12, 19)]}),
    ("à partir de mardi", {"des_le": d(13)}),
    ("après le 20", {"des_le": d(21)}),
    ("avant vendredi", {"jusqu_au": d(8)}),
    ("lundi ou mardi", {"jours": [d(12), d(13)]}),
    ("mardi ou jeudi après-midi", {"jours": [d(8), d(13)], "heure_min": "12:00"}),
    # Around the new rules: still read as before, and the bounds combine with the rest.
    ("jusqu'à vendredi", {"jusqu_au": d(9)}),
    ("pas après 17h", {"heure_max": "17:00"}),
    ("à partir de mardi après 14h", {"des_le": d(13), "heure_min": "14:00"}),
]
RIEN = {"jours": None, "jours_exclus": [], "dates_exclues": [], "des_le": None, "jusqu_au": None,
        "heure_min": None, "heure_max": None}


@pytest.mark.parametrize("texte,attendu", CORPUS_SOUHAITS_L1)
def test_le_souhait_des_bornes_negations_et_unions(texte, attendu):
    s = lire_souhait(texte, MAINTENANT)
    e = s.estampille()
    assert s.compris, texte
    assert {cle: e[cle] for cle in RIEN} == {**RIEN, **attendu}, texte


def test_les_bornes_et_les_semaines_exclues_filtrent_les_creneaux():
    s = lire_souhait("avant vendredi", MAINTENANT)
    assert s.accepte(h(8, 10)) and not s.accepte(h(9, 10))
    s = lire_souhait("pas la semaine prochaine", MAINTENANT)
    assert s.accepte(h(9, 10)) and not s.accepte(h(13, 10)) and s.accepte(h(19, 10))
    s = lire_souhait("lundi ou mardi", MAINTENANT)
    assert s.accepte(h(12, 10)) and s.accepte(h(13, 10)) and not s.accepte(h(14, 10))


def test_preuve_par_un_autre_metier_un_garage_et_un_type_de_rendez_vous():
    """The reader knows no trade: a garage booking an « entretien » (a person called « mecano »)."""
    from api.services.planificateur.calcul import Candidat, Regles, calculer

    mecano = Candidat("mecano")
    regles = Regles(duree_min=60, nombre=4)
    s = lire_souhait("pas avant 10h, lundi ou mardi", MAINTENANT)
    pris = calculer([mecano], ouvert(12, 13, 14), regles, s, h(7, 11), h(16, 0))
    assert [c.debut.strftime("%d %H:%M") for c in pris] == ["12 10:00", "12 11:00", "12 14:00", "12 15:00"]


@pytest.mark.parametrize("texte,jours,exclus,des_le,hmin,hmax", CORPUS_SOUHAITS)
def test_le_souhait_est_lu_comme_pose_a_la_main(texte, jours, exclus, des_le, hmin, hmax):
    s = lire_souhait(texte, MAINTENANT)
    e = s.estampille()
    assert s.compris, texte
    assert (e["jours"], e["jours_exclus"], e["des_le"], e["heure_min"], e["heure_max"]) == (
        jours, exclus, des_le, hmin, hmax
    ), texte


@pytest.mark.parametrize("texte", PAS_COMPRIS)
def test_ce_qui_n_est_pas_sur_la_liste_n_est_pas_devine(texte):
    s = lire_souhait(texte, MAINTENANT)
    assert not s.compris
    assert s.accepte(MAINTENANT + timedelta(days=1))  # nothing constrained


def test_cas_rouge_connu_pas_le_lundi_n_est_jamais_lundi():
    s = lire_souhait("pas le lundi, plutôt l'après-midi", MAINTENANT)
    assert not s.accepte(datetime(2026, 10, 12, 14, 0, tzinfo=PARIS))  # a Monday afternoon
    assert s.accepte(datetime(2026, 10, 13, 14, 0, tzinfo=PARIS))
    assert not s.accepte(datetime(2026, 10, 13, 10, 0, tzinfo=PARIS))


# sha256 of ``dates_relatives.py`` as of 03adc42a (line ends normalised); works without git history.
EMPREINTE_DATES_RELATIVES = "9d6d9558ec3df156ddf92f78c32279bd203cf1a1286da1f5efc0aee12e7ca642"


def _empreinte(octets: bytes) -> str:
    import hashlib

    return hashlib.sha256(octets.replace(b"\r\n", b"\n")).hexdigest()


def test_le_lecteur_des_dates_passees_n_a_pas_change():
    """Repli 6: the planner's reader is a function of its own; dates_relatives untouched (a
    fingerprint, so that the guard also runs in the CI, which has no history)."""
    from pathlib import Path

    fichier = Path(__file__).resolve().parents[3] / "api" / "services" / "workflow" / "dates_relatives.py"
    assert _empreinte(fichier.read_bytes()) == EMPREINTE_DATES_RELATIVES


def test_l_empreinte_change_au_moindre_caractere():
    from pathlib import Path

    fichier = Path(__file__).resolve().parents[3] / "api" / "services" / "workflow" / "dates_relatives.py"
    octets = fichier.read_bytes()
    assert _empreinte(octets + b" ") != EMPREINTE_DATES_RELATIVES
    assert _empreinte(octets.replace(b"a", b"b", 1)) != EMPREINTE_DATES_RELATIVES


# --------------------------------------------------------------------------- #
# 2. Public holidays (P10)
# --------------------------------------------------------------------------- #


def test_jours_feries_metropole_et_alsace_moselle():
    assert paques(2026) == date(2026, 4, 5) and paques(2027) == date(2027, 3, 28)
    metropole = jours_feries(2026)
    assert len(metropole) == 11
    assert {date(2026, 4, 6), date(2026, 5, 14), date(2026, 5, 25), date(2026, 11, 11)} <= metropole
    alsace = jours_feries(2026, "alsace_moselle")
    assert alsace - metropole == {date(2026, 4, 3), date(2026, 12, 26)}


# --------------------------------------------------------------------------- #
# 3. The slots, on situations posed by hand (P3, P5, P7, P10)
# --------------------------------------------------------------------------- #


def h(jour: int, heure: int, minute: int = 0, mois: int = 10) -> datetime:
    return datetime(2026, mois, jour, heure, minute, tzinfo=PARIS)


def ouvert(*jours: int, mois: int = 10) -> list:
    """9:00-12:00 and 14:00-18:00 on these days."""
    return [r for j in jours for r in ((h(j, 9, mois=mois), h(j, 12, mois=mois)), (h(j, 14, mois=mois), h(j, 18, mois=mois)))]


SANS = lire_souhait(None, MAINTENANT)


def debuts(creneaux):
    return [(c.debut.strftime("%d %H:%M"), c.cle) for c in creneaux]


def test_premier_libre_respecte_agenda_duree_et_marges():
    a = Candidat("a", occupe=[(h(8, 9), h(8, 10, 30))])
    b = Candidat("b", occupe=[(h(8, 9), h(8, 12))])
    regles = Regles(duree_min=60, marge_avant_min=15, marge_apres_min=15, nombre=3)
    creneaux = calculer([a, b], ouvert(8, 9), regles, SANS, h(8, 8), h(10, 0))
    # 10:30 busy end + 15 min margin -> 11:00 is the first start for a ; 11:00-12:00 holds.
    # Then the next start for anyone is 12:00 -> closed until 14:00.
    assert debuts(creneaux) == [("08 11:00", "a"), ("08 14:00", "a"), ("08 15:00", "a")]


def test_les_trajets_comptent_de_chaque_cote():
    a = Candidat("a", occupe=[(h(8, 14), h(8, 15))], trajet_min=30)
    creneaux = calculer([a], ouvert(8), Regles(duree_min=60, nombre=2), SANS, h(8, 8), h(9, 0))
    # Morning: 9:00 holds (8:30-10:30 free). Afternoon: after 15:00 + 30 min -> 15:30.
    assert debuts(creneaux) == [("08 09:00", "a"), ("08 10:00", "a")]
    creneaux = calculer([a], ouvert(8), Regles(duree_min=60, nombre=5), SANS, h(8, 12), h(9, 0))
    assert debuts(creneaux) == [("08 15:30", "a"), ("08 16:30", "a")]


def test_le_delai_minimal_et_le_jour_ferie():
    a = Candidat("a")
    # 11 November 2026 is a Wednesday and a public holiday.
    creneaux = calculer([a], ouvert(10, 11, 12, mois=11), Regles(duree_min=120, nombre=3, pas_min=30), SANS,
                        h(10, 15, 10, mois=11), h(13, 0, mois=11))
    assert debuts(creneaux) == [("10 15:30", "a"), ("12 09:00", "a"), ("12 14:00", "a")]


def test_le_souhait_filtre_les_creneaux():
    a = Candidat("a")
    s = lire_souhait("jeudi après 15h", MAINTENANT)
    creneaux = calculer([a], ouvert(8, 9), Regles(duree_min=60, nombre=3), s, h(8, 8), h(10, 0))
    # 14:00-18:00 open, one hour each: 15:00, 16:00 and 17:00 (ends at 18:00) hold.
    assert debuts(creneaux) == [("08 15:00", "a"), ("08 16:00", "a"), ("08 17:00", "a")]


def test_charge_et_zone_ordonnent_les_personnes():
    a = Candidat("a", charge_min=300, distance_km=40)
    b = Candidat("b", charge_min=60, distance_km=5)
    c = Candidat("c", charge_min=120, distance_km=None)
    r = Regles(duree_min=60, nombre=1, repartition="charge")
    assert debuts(calculer([a, b, c], ouvert(8), r, SANS, h(8, 8), h(9, 0))) == [("08 09:00", "b")]
    r.repartition = "zone"
    assert debuts(calculer([c, a, b], ouvert(8), r, SANS, h(8, 8), h(9, 0))) == [("08 09:00", "b")]


def test_tour_de_role_equitable_sur_une_serie_et_priorite_gardee():
    """Nine bookings for three people always free: 3 each, in turn. Then A has nothing on a
    round: B takes it, and A is still first at the next one."""
    compte = {"a": 0, "b": 0, "c": 0}
    serie = []
    for _ in range(9):
        candidats = [Candidat(k, attributions=n) for k, n in compte.items()]
        [premier] = calculer(candidats, ouvert(8), Regles(duree_min=60, nombre=1, repartition="tour_de_role"),
                             SANS, h(8, 8), h(9, 0))
        compte[premier.cle] += 1
        serie.append(premier.cle)
    assert serie == ["a", "b", "c"] * 3 and compte == {"a": 3, "b": 3, "c": 3}
    occupe_toute_la_journee = [(h(8, 0), h(9, 0))]
    candidats = [Candidat("a", attributions=3, occupe=occupe_toute_la_journee), Candidat("b", attributions=3),
                 Candidat("c", attributions=3)]
    [pris] = calculer(candidats, ouvert(8), Regles(duree_min=60, nombre=1, repartition="tour_de_role"),
                      SANS, h(8, 8), h(9, 0))
    assert pris.cle == "b" and pris.rang == 2
    candidats = [Candidat("a", attributions=3), Candidat("b", attributions=4), Candidat("c", attributions=3)]
    [suivant] = calculer(candidats, ouvert(8), Regles(duree_min=60, nombre=1, repartition="tour_de_role"),
                         SANS, h(8, 8), h(9, 0))
    assert suivant.cle == "a"  # A kept his priority


def test_tour_de_role_le_premier_donne_ses_creneaux_puis_le_suivant_complete():
    a = Candidat("a", occupe=[(h(8, 10), h(8, 18))])
    b = Candidat("b")
    creneaux = calculer([a, b], ouvert(8), Regles(duree_min=60, nombre=3, repartition="tour_de_role"),
                        SANS, h(8, 8), h(9, 0))
    assert debuts(creneaux) == [("08 09:00", "a"), ("08 10:00", "b"), ("08 11:00", "b")]
    assert [c.rang for c in creneaux] == [1, 2, 2]


def test_le_calcul_reste_loin_sous_le_delai_de_l_action():
    """20 people with busy agendas, 90 days, a grid of 5 minutes, a wish nobody can meet."""
    candidats = [
        Candidat(f"p{i}", occupe=[(h(8, 9) + timedelta(days=k), h(8, 17) + timedelta(days=k)) for k in range(90)])
        for i in range(20)
    ]
    jours = [h(8, 0) + timedelta(days=k) for k in range(90)]
    ouvertures = [(j.replace(hour=9), j.replace(hour=18)) for j in jours]
    debut = horloge.perf_counter()
    creneaux = calculer(candidats, ouvertures, Regles(duree_min=60, nombre=3, pas_min=5), lire_souhait("le soir après 19h", MAINTENANT),
                        h(8, 8), h(8, 8) + timedelta(days=90))
    duree = horloge.perf_counter() - debut
    assert creneaux == [] and duree < 1.0, duree  # the action's deadline is 5 s by default


# --------------------------------------------------------------------------- #
# 4. Through the engine's real dispatcher and a real client database (R1, P1, P8, P9, H6)
# --------------------------------------------------------------------------- #

from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import httpx  # noqa: E402
from pipecat.services.llm_service import FunctionCallParams  # noqa: E402

from api.enums import OrganizationConfigurationKey, ToolCategory  # noqa: E402
from api.schemas.base_client import Equipe, Personne, Sujet  # noqa: E402
from api.schemas.planificateur import Planificateur, ReglagesPlanificateur, TypeRendezVous  # noqa: E402
from api.services.integrations.connectors import anticipation, nango  # noqa: E402
from api.services.planificateur import action as module_action  # noqa: E402
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager  # noqa: E402
from api.tests.mark.test_connecteurs import FauxNango, stub_agent_runtime  # noqa: E402

CAMILLE, SACHA = "camille@example.org", "sacha@example.org"


class Agendas(FauxNango):
    """Google Agenda behind the relay: freeBusy from ``occupe``, an event created per booking."""

    def __init__(self, organization_id: int):
        super().__init__()
        self.connexions.append({"connection_id": "cx-plan", "provider_config_key": "google-calendar",
                                "tags": {"organization_id": str(organization_id)}})
        self.occupe: dict[str, list[tuple[str, str]]] = {}
        self.lectures = 0
        self.poses: list[tuple[str, dict]] = []
        # Faults and behaviours of a real software, off by default (revue du 07/10).
        self.lenteur_lecture = 0.0  # seconds before freeBusy answers
        self.occupe_par_pose = False  # an event created makes its slot busy
        self.reponse_perdue = 0  # truthy: the event is created, the line is cut before the answer
        self.refus_pose = 0  # the next N creations are refused (HTTP 500), nothing created
        self.lecture_des_evenements = False  # GET .../events lists what was created
        self.evenements_visibles: list | None = None  # None: what was created

    def _occupe_de(self, agenda: str) -> list[dict]:
        occupe = [{"start": a, "end": b} for a, b in self.occupe.get(agenda, [])]
        if self.occupe_par_pose:
            occupe += [{"start": c["start"]["dateTime"], "end": c["end"]["dateTime"]}
                       for ch, c in self.poses if ch.endswith(agenda.replace("@", "%40") + "/events")]
        return occupe

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        chemin = requete.url.raw_path.decode().split("?")[0]
        if chemin == "/proxy/calendar/v3/freeBusy":
            self.lectures += 1
            corps = json.loads(requete.content)
            lu = {i["id"]: {"busy": self._occupe_de(i["id"])} for i in corps["items"]}  # as of the request
            if self.lenteur_lecture:
                await asyncio.sleep(self.lenteur_lecture)
            return httpx.Response(200, json={"calendars": lu})
        if requete.method == "GET" and chemin.startswith("/proxy/calendar/v3/calendars/") and self.lecture_des_evenements:
            if self.evenements_visibles is not None:
                return httpx.Response(200, json={"items": self.evenements_visibles})
            return httpx.Response(200, json={"items": [
                {"id": f"evt-{i + 1}", "status": "confirmed", "start": c["start"], "end": c["end"],
                 "description": c.get("description", "")}
                for i, (ch, c) in enumerate(self.poses) if ch == chemin]})
        if chemin.startswith("/proxy/calendar/v3/calendars/"):
            if self.refus_pose:
                self.refus_pose -= 1
                return httpx.Response(500, json={})
            self.poses.append((chemin, json.loads(requete.content)))
            if self.reponse_perdue:
                # The event exists, the line is cut before the answer (the lock now waits for the
                # protected write, so a slow answer would simply be waited for).
                raise httpx.ReadTimeout("answer lost", request=requete)
            return httpx.Response(200, json={"id": f"evt-{len(self.poses)}"})
        return await super().__call__(requete)


@pytest.fixture
async def installe(base_v4, smtp, modele, db_session, async_session, monkeypatch):
    """An organization with its client database, Google Agenda chosen, two people who do
    « visite » with their agendas, the planner's rules; the clock at Wednesday 7/10 10:00."""
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe
    from api.db.bases_clients.planificateur import ecrire_planificateur
    from api.tests.mark import test_apres_appel as t

    org = await t._organisation(async_session, db_session)
    await t._regler(db_session, org, base_v4, smtp)
    await t._equipe(base_v4)
    await db_session.upsert_configuration(
        org.organisation.id, OrganizationConfigurationKey.TRADUCTEURS.value, {"agenda": "google_agenda"})
    connexion = await schema.connecter(base_v4)
    try:
        await ecrire_equipe(connexion, Equipe(
            personnes=[
                Personne(cle="camille", prenom="Camille", agendas={"google_agenda": CAMILLE}),
                Personne(cle="sacha", prenom="Sacha", agendas={"google_agenda": SACHA}),
                Personne(cle="noa", prenom="Noa"),  # no agenda: never booked
            ],
            sujets=[Sujet(code="visite", libelle="Visite", destinataires=["camille", "sacha", "noa"])],
        ), "test")
        await ecrire_planificateur(connexion, Planificateur(
            types=[TypeRendezVous(code="visite", libelle="Visite", duree_min=60, sujet="visite")]), "test")
    finally:
        await connexion.close()
    agendas = Agendas(org.organisation.id)
    monkeypatch.setenv(nango.VARIABLE_URL, "http://nango.local")
    monkeypatch.setenv(nango.VARIABLE_CLE, "cle-secrete-nango-0123")
    monkeypatch.setattr(nango, "nouveau_client",
                        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(agendas), **o))
    monkeypatch.setattr(module_action, "maintenant", lambda: MAINTENANT)
    run = await t._run(db_session, org)
    return SimpleNamespace(org=org, base=base_v4, agendas=agendas, run=run, t=t, smtp=smtp, db=db_session)


async def _regles(installe, **reglages) -> None:
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.planificateur import ecrire_planificateur, lire_planificateur

    connexion = await schema.connecter(installe.base)
    try:
        actuel = await lire_planificateur(connexion)
        actuel.reglages = ReglagesPlanificateur(**reglages)
        await ecrire_planificateur(connexion, actuel, "test")
    finally:
        await connexion.close()


def _outil(action, nom, **config):
    t = MagicMock()
    t.tool_uuid = f"uuid-{nom}"
    t.name = nom
    t.description = None
    t.category = ToolCategory.INTEGRATION.value
    t.definition = {"type": "integration", "config": {"connecteur": "planificateur", "action": action,
                                                      "delai_ms": 5000, **config}}
    return t


def _moteur(installe, monkeypatch, outils, contexte=None):
    engine = MagicMock()
    engine.active_agent = stub_agent_runtime(llm=MagicMock())
    engine._gathered_context = {"extracted_variables": {"nom": "Dupont", "motif": "visite du logement"}}
    engine._call_context_vars = {"caller_number": "+33612345678", **(contexte or {})}
    engine._workflow_run_id = installe.run.id
    engine.queue_text_message = AsyncMock()
    enregistres = {}
    engine.active_agent.llm.register_function = lambda nom, fn, **kw: enregistres.__setitem__(nom, (fn, kw))
    from api.db import db_client

    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(return_value=outils))
    mgr = CustomToolManager(engine)
    mgr.get_organization_id = AsyncMock(return_value=installe.org.organisation.id)
    return engine, mgr, enregistres


async def _appeler(fn, arguments):
    capte = []

    async def rappel(resultat, *args, properties=None, **kwargs):
        capte.append(resultat)

    await fn(FunctionCallParams(function_name="x", tool_call_id="t1", arguments=arguments, llm=MagicMock(),
                                pipeline_worker=MagicMock(), context=MagicMock(), result_callback=rappel))
    assert len(capte) == 1
    return capte[0]


TOUTE_LA_PERIODE = [("2026-10-01T00:00:00Z", "2026-11-30T00:00:00Z")]


async def test_proposer_puis_poser_par_le_vrai_repartiteur_et_le_hub_apres_l_appel(installe, monkeypatch, db_session):
    from api.db.bases_clients import connexion as schema
    from api.tasks.workflow_completion import process_workflow_completion

    # Camille is busy Thursday 10:00-12:00 (Paris); Sacha is free.
    installe.agendas.occupe = {CAMILLE: [("2026-10-08T08:00:00Z", "2026-10-08T10:00:00Z")]}
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [
        _outil("proposer_creneaux", "Creneaux"), _outil("poser_rendez_vous", "Poser")])
    schemas = {s.name: s for s in await mgr.get_tool_schemas(["uuid-Creneaux", "uuid-Poser"])}
    assert set(schemas["creneaux"].properties) == {"type", "souhait"}
    assert set(schemas["poser"].properties) == {"debut"}  # never a person, never an agenda
    await mgr.register_handlers(["uuid-Creneaux", "uuid-Poser"])
    assert enregistres["creneaux"][1]["is_node_transition"] is False  # never a door of the record

    r = await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"})
    # P9: the slots only (first name hidden by default), never an agenda.
    assert r == {"type": "Visite", "creneaux": [
        {"debut": "2026-10-08T10:00:00+02:00", "libelle": "jeudi 8 octobre à 10 h"},
        {"debut": "2026-10-08T11:00:00+02:00", "libelle": "jeudi 8 octobre à 11 h"},
        {"debut": "2026-10-08T14:00:00+02:00", "libelle": "jeudi 8 octobre à 14 h"},
    ]}
    [estampille] = engine._gathered_context["planificateur"]
    assert [(c["personne"], c["rang"]) for c in estampille["creneaux"]] == [("sacha", 2), ("sacha", 2), ("camille", 1)]
    assert estampille["ordre"] == ["camille", "sacha"] and estampille["souhait"]["compris"] is True
    assert estampille["trajets"]["comptes"] is False and isinstance(estampille["duree_calcul_ms"], int)

    refus = await _appeler(enregistres["poser"][0], {"debut": "2026-10-09T09:00:00+02:00"})
    assert refus["status"] == "refused" and refus["reason"] == "not_proposed" and len(refus["creneaux"]) == 3
    assert installe.agendas.poses == []

    pose = await _appeler(enregistres["poser"][0], {"debut": "2026-10-08T14:00:00+02:00"})
    assert pose == {"pose": True, "libelle": "jeudi 8 octobre à 14 h"}
    [(chemin, corps)] = installe.agendas.poses
    assert chemin == "/proxy/calendar/v3/calendars/camille%40example.org/events"  # HER agenda
    assert corps["summary"] == "Visite · Dupont" and corps["start"]["dateTime"] == "2026-10-08T14:00:00+02:00"
    [note] = engine._gathered_context["hub_rendez_vous"]
    assert note["personne"] == "camille" and note["type"] == "visite"
    assert note["attribution"]["mode"] == "premier_libre" and note["attribution"]["rang"] == 1

    # After the call: the hub gets the appointment, its link, its attribution and the mention.
    await db_session.update_workflow_run(installe.run.id, gathered_context=json.loads(json.dumps(engine._gathered_context)))
    with patch("api.tasks.arq.enqueue_job", await installe.t._executer_tout_de_suite([])):
        await process_workflow_completion(None, installe.run.id)
    connexion = await schema.connecter(installe.base)
    try:
        rdv = await connexion.fetchrow(
            "SELECT r.type_code, p.cle FROM mark.rendez_vous r JOIN mark.personne p ON p.id = r.intervenant_id")
        assert dict(rdv) == {"type_code": "visite", "cle": "camille"}
        attribution = await connexion.fetchrow(
            "SELECT a.mode, a.rang, a.type_code, p.cle FROM mark.attribution a JOIN mark.personne p ON p.id = a.personne_id")
        assert dict(attribution) == {"mode": "premier_libre", "rang": 1, "type_code": "visite", "cle": "camille"}
        assert await connexion.fetchval(
            "SELECT id_externe FROM mark.lien_externe WHERE objet_type = 'rendez_vous'") == "evt-1"
        assert await connexion.fetchval("SELECT count(*) FROM mark.mention WHERE source = 'rendez_vous'") == 1
    finally:
        await connexion.close()


async def test_un_creneau_pris_entre_temps_n_est_jamais_pose(installe, monkeypatch):
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [
        _outil("proposer_creneaux", "Creneaux"), _outil("poser_rendez_vous", "Poser")])
    await mgr.register_handlers(["uuid-Creneaux", "uuid-Poser"])
    r = await _appeler(enregistres["creneaux"][0], {})
    premier = r["creneaux"][0]["debut"]
    installe.agendas.occupe = {CAMILLE: TOUTE_LA_PERIODE}
    pris = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert pris["status"] == "slot_taken" and installe.agendas.poses == []


# --------------------------------------------------------------------------- #
# Revue du 07/10 : un seul rendez-vous par appel, jamais deux en parallèle, jamais un doublon
# --------------------------------------------------------------------------- #


async def _deux_creneaux(installe, monkeypatch, delai_poser=5000):
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [
        _outil("proposer_creneaux", "Creneaux"), _outil("poser_rendez_vous", "Poser", delai_ms=delai_poser)])
    await mgr.register_handlers(["uuid-Creneaux", "uuid-Poser"])
    r = await _appeler(enregistres["creneaux"][0], {})
    return engine, enregistres, [c["debut"] for c in r["creneaux"]]


async def test_un_second_rendez_vous_dans_le_meme_appel_est_refuse_le_meme_creneau_ne_cree_rien_de_plus(installe, monkeypatch):
    engine, enregistres, [premier, second, *_] = await _deux_creneaux(installe, monkeypatch)
    assert (await _appeler(enregistres["poser"][0], {"debut": premier}))["pose"] is True
    # « Finalement… » : another slot is refused, a call-back to change it is noted, nothing is created.
    r = await _appeler(enregistres["poser"][0], {"debut": second})
    assert r["status"] == "already_booked" and "colleague" in r["instruction"]
    assert [x["raison"] for x in engine._gathered_context["planificateur_rappel"]] == [
        "change of the appointment booked in this call"]
    # The same slot again: the same answer, not a second event.
    assert (await _appeler(enregistres["poser"][0], {"debut": premier}))["pose"] is True
    assert len(installe.agendas.poses) == 1
    assert len(engine._gathered_context["hub_rendez_vous"]) == 1


async def test_deux_poses_en_parallele_ne_creent_qu_un_evenement(installe, monkeypatch):
    import asyncio

    installe.agendas.lenteur_lecture = 0.15  # both read the agenda before either writes
    _engine, enregistres, [premier, second, *_] = await _deux_creneaux(installe, monkeypatch)
    r = await asyncio.gather(_appeler(enregistres["poser"][0], {"debut": premier}),
                             _appeler(enregistres["poser"][0], {"debut": second}))
    assert sorted(x.get("status") or "pose" for x in r) == ["already_booked", "pose"]
    assert len(installe.agendas.poses) == 1
    r = await asyncio.gather(_appeler(enregistres["poser"][0], {"debut": premier}),
                             _appeler(enregistres["poser"][0], {"debut": premier}))
    assert all(x.get("pose") is True or x.get("status") == "already_booked" for x in r)
    assert len(installe.agendas.poses) == 1


async def test_deux_appels_ne_prennent_pas_le_meme_creneau_de_la_meme_agenda(installe, monkeypatch):
    """Two different calls, one slot, one agenda: the second finds it taken (the agenda lock)."""
    import asyncio

    installe.agendas.lenteur_lecture = 0.4
    installe.agendas.occupe_par_pose = True  # an event created makes its slot busy, like a real agenda
    engine, enregistres, [premier, *_] = await _deux_creneaux(installe, monkeypatch)
    autre_run = await installe.t._run(installe.db, installe.org)
    engine2, mgr2, enregistres2 = _moteur(installe, monkeypatch, [
        _outil("proposer_creneaux", "Creneaux"), _outil("poser_rendez_vous", "Poser")])
    engine2._workflow_run_id = autre_run.id
    await mgr2.register_handlers(["uuid-Creneaux", "uuid-Poser"])
    r2 = await _appeler(enregistres2["creneaux"][0], {})
    assert r2["creneaux"][0]["debut"] == premier
    r = await asyncio.gather(_appeler(enregistres["poser"][0], {"debut": premier}),
                             _appeler(enregistres2["poser"][0], {"debut": premier}))
    assert sorted(x.get("status") or "pose" for x in r) == ["pose", "slot_taken"]
    assert len(installe.agendas.poses) == 1


async def test_un_evenement_cree_dont_la_reponse_est_perdue_est_retrouve_sans_doublon(installe, monkeypatch):
    installe.agendas.reponse_perdue = 3  # created, then the answer never comes back in time
    engine, enregistres, [premier, *_] = await _deux_creneaux(installe, monkeypatch, delai_poser=900)
    perdu = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert perdu.get("pose") is not True and len(installe.agendas.poses) == 1
    # The next try of the call finds the event in the agenda and gives it as booked: no second one.
    installe.agendas.reponse_perdue = 0
    installe.agendas.lecture_des_evenements = True
    r = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert r["pose"] is True and len(installe.agendas.poses) == 1
    [note] = engine._gathered_context["hub_rendez_vous"]
    assert note["id_externe"] == "evt-1"


async def test_un_evenement_cree_introuvable_n_en_cree_pas_un_autre(installe, monkeypatch):
    installe.agendas.reponse_perdue = 3
    engine, enregistres, [premier, *_] = await _deux_creneaux(installe, monkeypatch, delai_poser=900)
    await _appeler(enregistres["poser"][0], {"debut": premier})
    installe.agendas.reponse_perdue = 0
    installe.agendas.lecture_des_evenements = True
    installe.agendas.evenements_visibles = []  # the agenda does not show it (yet)
    r = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert r["status"] == "booking_uncertain" and len(installe.agendas.poses) == 1
    assert "previous booking unconfirmed" in [x["raison"] for x in engine._gathered_context["planificateur_rappel"]]


async def test_un_rendez_vous_pose_a_la_main_au_meme_creneau_n_est_pas_adopte(installe, monkeypatch):
    """Same start, same end, but no marker of the planner: put by a person, it is not ours."""
    installe.agendas.reponse_perdue = 1
    engine, enregistres, [premier, *_] = await _deux_creneaux(installe, monkeypatch, delai_poser=900)
    await _appeler(enregistres["poser"][0], {"debut": premier})
    [(_chemin, cree)] = installe.agendas.poses
    installe.agendas.reponse_perdue = 0
    installe.agendas.lecture_des_evenements = True
    installe.agendas.evenements_visibles = [  # by hand: same slot, same hours, another description
        {"id": "evt-main", "status": "confirmed", "start": cree["start"], "end": cree["end"],
         "description": "Rendez-vous noté par un collègue"}]
    r = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert r["status"] == "booking_uncertain" and len(installe.agendas.poses) == 1
    assert "hub_rendez_vous" not in engine._gathered_context
    # The planner's own event (marker first in its description) is still found.
    installe.agendas.evenements_visibles = [{**installe.agendas.evenements_visibles[0], "id": "evt-1",
                                             "description": cree["description"]}]
    r = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert r["pose"] is True and len(installe.agendas.poses) == 1
    assert cree["description"].startswith("Réf. assistant : ")


async def test_un_refus_net_du_logiciel_permet_de_reessayer(installe, monkeypatch):
    installe.agendas.refus_pose = 1
    engine, enregistres, [premier, *_] = await _deux_creneaux(installe, monkeypatch)
    echec = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert echec["status"] == "no_slot" and installe.agendas.poses == []
    r = await _appeler(enregistres["poser"][0], {"debut": premier})
    assert r["pose"] is True and len(installe.agendas.poses) == 1


@pytest.mark.parametrize("mode", ["toujours_rappel", "humain_puis_rappel"])
async def test_aucun_creneau_le_rappel_est_dit_par_le_code_et_la_demande_creee(installe, monkeypatch, db_session, mode):
    from api.db.bases_clients import connexion as schema
    from api.tasks.workflow_completion import process_workflow_completion

    await _regles(installe, repli=mode)
    installe.agendas.occupe = {CAMILLE: TOUTE_LA_PERIODE, SACHA: TOUTE_LA_PERIODE}
    # Closed business: the human handoff is impossible in both modes, the call-back is said.
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")],
                                       {"etat_ouverture": "FERME", "numero_transfert": "+33300000000"})
    await mgr.register_handlers(["uuid-Creneaux"])
    r = await _appeler(enregistres["creneaux"][0], {"souhait": "mardi matin"})
    assert r["status"] == "no_slot" and r["fallback"] == "callback"
    assert r["said_to_caller"] == module_action.PHRASE_RAPPEL_DEFAUT
    engine.queue_text_message.assert_awaited_with(module_action.PHRASE_RAPPEL_DEFAUT, mute_user=True)
    [rappel] = engine._gathered_context["planificateur_rappel"]
    assert rappel["mode"] == "rappel" and rappel["souhait"] == "mardi matin" and rappel["raison"] == "no slot fits"

    await db_session.update_workflow_run(installe.run.id, gathered_context=json.loads(json.dumps(engine._gathered_context)))
    with patch("api.tasks.arq.enqueue_job", await installe.t._executer_tout_de_suite([])):
        await process_workflow_completion(None, installe.run.id)
    connexion = await schema.connecter(installe.base)
    try:
        resume = await connexion.fetchval("SELECT resume FROM mark.demande")
        assert resume.startswith("Rendez-vous à rappeler pour le fixer") and "mardi matin" in resume
    finally:
        await connexion.close()


@pytest.mark.parametrize("mode,attendu", [("humain_puis_rappel", "human"), ("toujours_rappel", "callback")])
async def test_aucun_creneau_etablissement_ouvert(installe, monkeypatch, mode, attendu):
    await _regles(installe, repli=mode)
    installe.agendas.occupe = {CAMILLE: TOUTE_LA_PERIODE, SACHA: TOUTE_LA_PERIODE}
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")],
                                       {"etat_ouverture": "OUVERT", "numero_transfert": "+33300000000"})
    await mgr.register_handlers(["uuid-Creneaux"])
    r = await _appeler(enregistres["creneaux"][0], {})
    assert r["fallback"] == attendu
    if attendu == "human":
        assert "said_to_caller" not in r
        engine.queue_text_message.assert_not_awaited()  # the code says nothing over the handoff
        assert engine._gathered_context["planificateur_rappel"][0]["mode"] == "humain"  # safety net
    else:
        engine.queue_text_message.assert_awaited()


async def test_sans_logiciel_d_agenda_le_repli_jamais_le_silence(installe, monkeypatch, db_session):
    await db_session.upsert_configuration(
        installe.org.organisation.id, OrganizationConfigurationKey.TRADUCTEURS.value, {"agenda": None})
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")])
    await mgr.register_handlers(["uuid-Creneaux"])
    r = await _appeler(enregistres["creneaux"][0], {})
    assert r["fallback"] == "callback" and installe.agendas.lectures == 0
    assert engine._gathered_context["planificateur"][0]["raison"] == "no calendar software chosen (« Integrations »)"


async def test_plusieurs_types_le_modele_demande_lequel(installe, monkeypatch):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.planificateur import ecrire_planificateur, lire_planificateur

    connexion = await schema.connecter(installe.base)
    try:
        p = await lire_planificateur(connexion)
        p.types.append(TypeRendezVous(code="devis", libelle="Devis", duree_min=30))
        await ecrire_planificateur(connexion, p, "test")
    finally:
        await connexion.close()
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")])
    await mgr.register_handlers(["uuid-Creneaux"])
    r = await _appeler(enregistres["creneaux"][0], {})
    assert r["status"] == "choose_type" and [t["code"] for t in r["types"]] == ["visite", "devis"]
    r = await _appeler(enregistres["creneaux"][0], {"type": "devis"})
    assert len(r["creneaux"]) == 3 and r["type"] == "Devis"


async def test_souhait_illisible_les_premiers_creneaux_et_le_modele_prevenu(installe, monkeypatch):
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")])
    await mgr.register_handlers(["uuid-Creneaux"])
    r = await _appeler(enregistres["creneaux"][0], {"souhait": "quand mon mari rentre"})
    assert r["souhait_compris"] is False and "not understood" in r["instruction"]
    assert r["creneaux"][0]["debut"] == "2026-10-08T10:00:00+02:00"


async def test_la_lecture_anticipee_est_utilisee(installe, monkeypatch):
    import asyncio

    engine, mgr, enregistres = _moteur(installe, monkeypatch, [
        _outil("proposer_creneaux", "Creneaux", anticipable=True, declencheurs={"souhait": "souhait_rdv"})])
    await mgr.register_handlers(["uuid-Creneaux"])
    engine._gathered_context["extracted_variables"]["souhait_rdv"] = "jeudi"
    anticipation.apres_une_note(engine._gathered_context)
    for _ in range(100):
        await asyncio.sleep(0.05)
        if installe.agendas.lectures:
            break
    r = await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"})
    assert len(r["creneaux"]) == 3 and installe.agendas.lectures == 1  # read once, before the model asked
    assert any(e.get("anticipee") == "utilisee" for e in engine._gathered_context["connecteurs"])
    # Delivered once: the stamp of the computation is noted when the model takes it.
    assert len(engine._gathered_context["planificateur"]) == 1


async def test_les_regles_a_l_etablissement_heritent_de_l_organisation(base_prete):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.planificateur import ReferenceInconnue, ecrire_planificateur, lire_planificateur
    from api.schemas.planificateur import effectifs

    connexion = await schema.connecter(base_prete)
    try:
        await connexion.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('E')")
        await connexion.execute("INSERT INTO mark.site (entreprise_id, cle, nom) SELECT id, 'nord', 'Nord' FROM mark.entreprise")
        await ecrire_planificateur(connexion, Planificateur(
            reglages=ReglagesPlanificateur(nombre_creneaux=2, repartition="tour_de_role"),
            par_etablissement={"nord": ReglagesPlanificateur(nombre_creneaux=4, jours_feries="alsace_moselle")},
            types=[TypeRendezVous(code="visite", libelle="Visite", duree_min=60),
                   TypeRendezVous(code="visite", etablissement="nord", libelle="Visite longue", duree_min=90)],
        ), "test")
        lu = await lire_planificateur(connexion)
        nord = effectifs(lu.reglages, lu.par_etablissement["nord"])
        assert (nord.nombre_creneaux, nord.repartition, nord.jours_feries, nord.horizon_jours) == (
            4, "tour_de_role", "alsace_moselle", 14)  # its own, the organization's, the default
        assert effectifs(lu.reglages).nombre_creneaux == 2
        assert [t.duree_min for t in module_action.types_de(lu.types, "nord")] == [90]
        assert [t.duree_min for t in module_action.types_de(lu.types, None)] == [60]
        journal = await connexion.fetchval(
            "SELECT count(*) FROM mark.journal_modif WHERE table_nom IN ('reglage_planificateur', 'type_rendez_vous')")
        assert journal >= 4  # written like the rest of the referential
        with pytest.raises(ReferenceInconnue):
            await ecrire_planificateur(connexion, Planificateur(par_etablissement={"sud": ReglagesPlanificateur()}), "test")
    finally:
        await connexion.close()


# Fixtures of the client database's and the after-call's tests.
from api.tests.mark.test_apres_appel import base_v4, modele, smtp  # noqa: E402, F401
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402, F401


async def test_trajets_et_zone_par_la_position_de_l_adresse(installe, monkeypatch, db_session):
    """P5, P6, repli 7: the caller's address read by our modules, positioned by the Base Adresse
    Nationale (a stand-in here), the journey counted both ways; outside the radius, the fallback."""
    from api.services.planificateur import trajets

    positions = {"60159": (49.4179, 2.8261), "60057": (49.4300, 2.0810)}  # Compiègne, Beauvais

    async def geocoder(texte, code_insee=None):
        p = positions.get(code_insee)
        return {"latitude": p[0], "longitude": p[1], "label": texte, "score": 0.9, "code_insee": code_insee} if p else None

    monkeypatch.setattr(trajets, "geocoder", geocoder)
    await db_session.upsert_configuration(
        installe.org.organisation.id, OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
        {"adresses_notification": ["alerte@example.org"],
         "adresse_etablissement": {"code_postal": "60000", "code_insee": "60057", "commune": "Beauvais",
                                   "voie": "1 rue de l'Exemple"}})
    # Both busy Thursday 12:00-13:00 (Paris).
    installe.agendas.occupe = {CAMILLE: [("2026-10-08T10:00:00Z", "2026-10-08T11:00:00Z")],
                               SACHA: [("2026-10-08T10:00:00Z", "2026-10-08T11:00:00Z")]}
    adresse = {"voie": "2 rue de l'Essai", "code_postal": "60200", "commune": "Compiègne"}

    async def proposer(**regles):
        await _regles(installe, **regles)
        engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")])
        engine._gathered_context["extracted_variables"].update(adresse)
        await mgr.register_handlers(["uuid-Creneaux"])
        return await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"}), engine

    sans, _ = await proposer()
    assert [c["debut"][11:16] for c in sans["creneaux"]] == ["10:00", "11:00", "14:00"]
    avec, engine = await proposer(trajets_comptes=True)
    # 54 km as the crow flies × 1.3 at 50 km/h = 84.3 -> 85 min each way: 13:00 + 85 -> 14:30.
    assert [c["debut"][11:16] for c in avec["creneaux"]] == ["14:30", "15:30", "16:30"]
    tampon = engine._gathered_context["planificateur"][0]
    assert tampon["trajets"] == {"comptes": True, "minutes": 85, "raison": None}
    assert tampon["adresse_appelant"]["code_insee"] == "60159" and tampon["adresse_appelant"]["verifiee"]
    hors, engine = await proposer(zone_rayon_km=20)
    assert hors["fallback"] in ("callback", "human")
    assert engine._gathered_context["planificateur"][0]["hors_zone"] is True
    # The Base Adresse Nationale does not know the address: journeys not counted, said in the stamp.
    positions.pop("60159")
    _, engine = await proposer(trajets_comptes=True)
    assert engine._gathered_context["planificateur"][0]["trajets"]["comptes"] is False
    assert "Base Adresse Nationale" in engine._gathered_context["planificateur"][0]["trajets"]["raison"]


async def test_le_geocodeur_ne_garde_qu_une_adresse_sure(monkeypatch):
    from api.services.planificateur import trajets

    trajets.oublier()
    reponses = {
        "sure": {"features": [{"geometry": {"coordinates": [2.08, 49.43]},
                               "properties": {"score": 0.92, "citycode": "60057", "label": "1 rue X 60000 Beauvais"}}]},
        "douteuse": {"features": [{"geometry": {"coordinates": [2.08, 49.43]},
                                   "properties": {"score": 0.31, "citycode": "60057"}}]},
        "ailleurs": {"features": [{"geometry": {"coordinates": [2.0, 49.0]},
                                   "properties": {"score": 0.95, "citycode": "75056"}}]},
    }

    def repondre(requete):
        return httpx.Response(200, json=reponses[requete.url.params["q"]])

    monkeypatch.setattr(trajets, "nouveau_client",
                        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(repondre), **o))
    assert (await trajets.geocoder("sure", "60057"))["latitude"] == 49.43
    assert await trajets.geocoder("douteuse", "60057") is None
    assert await trajets.geocoder("ailleurs", "60057") is None
    monkeypatch.setattr(trajets, "nouveau_client",
                        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))), **o))
    trajets.oublier()
    assert await trajets.geocoder("sure", "60057") is None  # unreachable: None, never raises
    assert trajets.duree_trajet_min((49.43, 2.08), (49.4179, 2.8261), coefficient=1.3, vitesse_kmh=50) == 85


async def test_la_memoire_du_geocodeur_est_par_organisation_et_expire(monkeypatch):
    """Revue du 07/10: an address placed for one client was answered to another from the same memory,
    for ever. Now: per organization, and an hour at most."""
    from api.services.planificateur import trajets

    trajets.oublier()
    demandes = []

    def repondre(requete):
        demandes.append(requete.url.params["q"])
        return httpx.Response(200, json={"features": [{"geometry": {"coordinates": [2.08, 49.43]},
                                                       "properties": {"score": 0.9, "citycode": "60057"}}]})

    monkeypatch.setattr(trajets, "nouveau_client",
                        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(repondre), **o))
    for organisation, attendu in ((1, 1), (1, 1), (2, 2)):
        trajets.ORGANISATION.set(organisation)
        assert (await trajets.geocoder("1 rue X Beauvais", "60057"))["latitude"] == 49.43
        assert len(demandes) == attendu  # the same organization: from memory; another: asked again
    trajets.ORGANISATION.set(1)
    reel = horloge.monotonic
    monkeypatch.setattr(trajets.time, "monotonic", lambda: reel() + trajets.DUREE_MEMOIRE_S + 1)
    await trajets.geocoder("1 rue X Beauvais", "60057")
    assert len(demandes) == 3  # expired: asked again
    trajets.ORGANISATION.set(None)
    trajets.oublier()


def test_la_route_du_planificateur_refuse_des_plages_illisibles(base_prete, monkeypatch):
    """G1, « by hand »: GET/PUT /organizations/planificateur; ranges checked when SAVED."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import base_client as route
    from api.services.auth.depends import get_user_with_selected_organization

    async def nom(_organisation):
        return base_prete

    monkeypatch.setattr(route.rattachement, "nom_de_la_base", nom)
    app = FastAPI()
    app.include_router(route.routeur_planificateur)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=1, email="essai@example.org")
    client = TestClient(app)
    assert client.get("/organizations/planificateur").json()["defauts"]["nombre_creneaux"] == 3
    refus = client.put("/organizations/planificateur", json={"reglages": {"plages": "lundi 9h"}})
    assert refus.status_code == 422 and "Booking ranges" in refus.json()["detail"]
    bon = client.put("/organizations/planificateur", json={
        "reglages": {"nombre_creneaux": 2, "repli": "toujours_rappel"},
        "types": [{"code": "visite", "libelle": "Visite", "duree_min": 45}]})
    assert bon.status_code == 200, bon.text
    assert bon.json()["reglages"]["nombre_creneaux"] == 2 and bon.json()["types"][0]["duree_min"] == 45
