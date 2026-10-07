"""[.mark] Non-regression test for the journeys from the previous appointment (chantier
l-agent-collegue, R-6, retouche du planificateur).

The questions this file answers (R-6, R1, R7):

    On situations posed by hand, does a person's journey start from the address of the PREVIOUS
    appointment of her agenda that day, and go to the NEXT one, otherwise from the establishment?
    The known red case: THE SAME SLOT, a different journey according to the previous appointment
    (a person coming from the caller's own street needs no journey, one coming from an address that
    cannot be read needs the establishment's 85 minutes). Through the engine's REAL dispatcher and
    a real client database: do the slots offered follow, does the stamp say for each slot where each
    journey started from and why, does the booking check the free time with THAT slot's journeys?
    When the agendas' events cannot be read, when an address is not found or not placed in time,
    are the journeys from the establishment (never an error)?

Why it exists
-------------
🔴 R7: a planner that counts the wrong journey offers a slot nobody can reach in time, or hides one
that was possible. Only a corpus whose truth is posed by hand catches it.

The agendas are a stand-in behind the REAL relay (Google's documented answers) and the Base Adresse
Nationale is a stand-in too. No request leaves the machine; no SMS, no call.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from api.enums import OrganizationConfigurationKey
from api.services.planificateur import action as module_action
from api.services.planificateur import trajets
from api.services.planificateur.action import Etape, trajets_du_creneau
from api.services.planificateur.calcul import Candidat, Regles, calculer
from api.services.planificateur.souhaits import lire_souhait

# The fixtures and helpers of the planner's own test.
from api.tests.mark import test_planificateur as _planificateur
from api.tests.mark.test_planificateur import (  # noqa: F401
    CAMILLE,
    MAINTENANT,
    SACHA,
    Agendas,
    _appeler,
    _moteur,
    _outil,
    _regles,
    base_essai,
    base_prete,
    base_v4,
    h,
    modele,
    smtp,
)

installe = _planificateur.installe  # the planner's fixture (the world of the real-route tests)

PARIS = ZoneInfo("Europe/Paris")
SANS = lire_souhait(None, MAINTENANT)
BEAUVAIS = (49.4300, 2.0810)  # the establishment
COMPIEGNE = (49.4179, 2.8261)  # the caller
# 54 km as the crow flies × 1.3 at 50 km/h = 84.3 -> 85 minutes, the establishment's journey.
DEPUIS_L_ETABLISSEMENT = 85
JOURNEE = [(h(8, 9), h(8, 18))]  # Thursday 8 October, 9:00 to 18:00 (no lunch closing)


def trajets_de(etapes: list[Etape]):
    return trajets_du_creneau(
        etapes, appelant=COMPIEGNE, base_min=DEPUIS_L_ETABLISSEMENT, coefficient=1.3, vitesse_kmh=50
    )


def candidat(cle: str, etapes: list[Etape]) -> Candidat:
    return Candidat(
        cle,
        occupe=[(e.debut, e.fin) for e in etapes],
        trajet_min=DEPUIS_L_ETABLISSEMENT,
        trajets=trajets_de(etapes),
    )


def sorties(creneaux):
    return [c.debut.strftime("%H:%M") for c in creneaux]


# --------------------------------------------------------------------------- #
# 1. The journey of a slot, truth posed by hand (R-6, R7)
# --------------------------------------------------------------------------- #


def test_cas_rouge_connu_meme_creneau_trajet_different_selon_le_rendez_vous_precedent():
    """Both people are busy 12:00-13:00. Camille's appointment is in the caller's own place (0 min);
    Sacha's address cannot be read (the establishment's 85 min). The earliest slot after 13:00 is
    therefore not the same, and a planner that ignored the previous appointment would give both 14:30."""
    midi = (h(8, 12), h(8, 13))
    camille = candidat("camille", [Etape(*midi, position=COMPIEGNE, code_insee="60159")])
    sacha = candidat("sacha", [Etape(*midi, sans_position="no readable address on the appointment")])
    regles = Regles(duree_min=60, nombre=1)
    apres_midi = (h(8, 13), h(8, 18))
    [pour_camille] = calculer([camille], [apres_midi], regles, SANS, h(8, 12), h(9, 0))
    [pour_sacha] = calculer([sacha], [apres_midi], regles, SANS, h(8, 12), h(9, 0))
    assert pour_camille.debut == h(8, 13, 0)  # no journey: she is where the caller is
    assert pour_sacha.debut == h(8, 14, 30)  # 13:00 + 85 min = 14:25, on the 30-minute grid
    avant = pour_camille.trajets.avant
    assert (pour_camille.trajets.avant_min, avant["origine"], avant["libelle"]) == (
        0, "previous_appointment", "depuis le rendez-vous précédent")
    assert avant["code_insee"] == "60159" and "ends at 13:00" in avant["pourquoi"]
    assert pour_camille.trajets.apres["origine"] == "establishment"  # nothing later that day
    assert pour_camille.trajets.apres["pourquoi"] == "no next appointment that day"
    assert (pour_sacha.trajets.avant_min, pour_sacha.trajets.avant["origine"]) == (85, "establishment")
    assert pour_sacha.trajets.avant["pourquoi"] == "the previous appointment: no readable address on the appointment"
    assert pour_sacha.trajets.avant["libelle"] == "depuis l'établissement"


def test_le_trajet_vers_le_rendez_vous_suivant_suit_la_meme_regle():
    """Camille's next appointment (15:00) is in the caller's place: a slot may end at 15:00 sharp.
    Sacha's next appointment has no address: 85 minutes must remain, the slot has to end earlier."""
    suite = (h(8, 15), h(8, 16))
    camille = candidat("camille", [Etape(*suite, position=COMPIEGNE)])
    sacha = candidat("sacha", [Etape(*suite, sans_position="address not found by the Base Adresse Nationale (or unreachable)")])
    regles = Regles(duree_min=60, nombre=40)
    toute_la_matinee_et_l_apres_midi = [(h(8, 9), h(8, 15))]
    pour_camille = calculer([camille], toute_la_matinee_et_l_apres_midi, regles, SANS, h(8, 8), h(9, 0))
    pour_sacha = calculer([sacha], toute_la_matinee_et_l_apres_midi, regles, SANS, h(8, 8), h(9, 0))
    assert sorties(pour_camille)[-1] == "14:00"  # 14:00-15:00, nothing to cross before 15:00
    # Sacha: 12:00 + 60 + 85 min = 14:25 <= 15:00 holds; 12:30 + 145 min = 15:35 does not.
    assert sorties(pour_sacha)[-1] == "12:00" and "12:30" not in sorties(pour_sacha)


def test_la_regle_ne_regarde_que_le_meme_jour_et_le_dernier_rendez_vous():
    """Yesterday's appointment is not « the previous one »; of two appointments before the slot, the
    one that ENDS last counts, readable or not (the person is at the last one)."""
    hier = Etape(h(7, 16), h(7, 17), position=COMPIEGNE)
    matin = Etape(h(8, 9), h(8, 10), position=COMPIEGNE)
    midi_illisible = Etape(h(8, 11), h(8, 12), sans_position="no readable address on the appointment")
    calcul = trajets_de([hier, matin, midi_illisible])
    assert calcul(h(8, 14), h(8, 15)).avant["origine"] == "establishment"
    assert calcul(h(8, 14), h(8, 15)).avant["pourquoi"].startswith("the previous appointment: no readable")
    # Before 11:00 the last one ended is the morning's (readable): 0 min.
    t = trajets_de([hier, matin]).__call__(h(8, 10, 30), h(8, 11, 30))
    assert (t.avant_min, t.avant["origine"]) == (0, "previous_appointment")
    # Only yesterday's: the establishment, « no previous appointment that day ».
    seul = trajets_de([hier])(h(8, 9), h(8, 10))
    assert (seul.avant_min, seul.avant["pourquoi"]) == (85, "no previous appointment that day")


def test_sans_agenda_lu_le_trajet_est_celui_de_l_etablissement_comme_avant():
    """No events at all (or the function not given): both sides at the establishment's journey,
    exactly what the planner counted before R-6."""
    sans_fonction = Candidat("a", occupe=[(h(8, 12), h(8, 13))], trajet_min=30)
    [creneau] = calculer([sans_fonction], JOURNEE, Regles(duree_min=60, nombre=1), SANS, h(8, 12), h(9, 0))
    assert creneau.debut == h(8, 13, 30) and creneau.trajets is None  # unchanged; nothing stamped
    vide = candidat("b", [])
    [creneau] = calculer([vide], JOURNEE, Regles(duree_min=60, nombre=1), SANS, h(8, 9), h(9, 0))
    assert creneau.debut == h(8, 9)  # nothing in the agenda: the journeys cross nothing
    assert creneau.trajets.avant_min == creneau.trajets.apres_min == 85


# --------------------------------------------------------------------------- #
# 2. The reading of the agendas' places: never an error
# --------------------------------------------------------------------------- #


def test_un_lieu_n_est_lisible_que_s_il_peut_etre_une_adresse():
    lisible = module_action.lieu_lisible
    assert lisible("  3 place de l'Hôtel de Ville,  60200 Compiègne ") == "3 place de l'Hôtel de Ville, 60200 Compiègne"
    for non in (None, "", "Zoom", "https://meet.example.org/abc-defg", "12345", "x" * 201):
        assert lisible(non) is None, non


async def test_une_adresse_non_placee_a_temps_ou_trop_nombreuse_est_dite_pas_inventee(monkeypatch):
    from api.services.hub import agenda as hub_agenda

    evenements = [
        {"debut": h(8, 9), "fin": h(8, 10), "lieu": "1 rue Première, 60200 Compiègne"},
        {"debut": h(8, 11), "fin": h(8, 12), "lieu": "2 rue Seconde, 60200 Compiègne"},
        {"debut": h(8, 13), "fin": h(8, 14), "lieu": "Visio"},
        {"debut": h(8, 15), "fin": h(8, 16), "lieu": "https://visio.example.org/x"},
    ]

    async def lus(*args, **kwargs):
        return evenements

    async def lent(texte, code_insee=None):
        await asyncio.sleep(5)

    monkeypatch.setattr(hub_agenda, "evenements", lus)
    monkeypatch.setattr(trajets, "geocoder", lent)
    ctx = type("C", (), {"organization_id": 1})()
    debut = horloge = datetime.now(PARIS)
    del horloge
    etapes, bilan = await asyncio.wait_for(
        module_action.etapes_des_agendas(ctx, "google_agenda", ["a"], debut, debut + timedelta(days=3), 0.1), 3)
    raisons = [e.sans_position for e in etapes["a"]]
    # « Visio » is short but could be a place name: it goes to the map; the link never does.
    assert raisons[:3] == ["address not placed in time"] * 3
    assert raisons[3] == "no readable address on the appointment"
    assert bilan == {"agendas_lus": 1, "agendas_non_lus": 0, "evenements": 4, "adresses_placees": 0}
    # The cap: only the first addresses are placed.
    monkeypatch.setattr(module_action, "MAX_LIEUX", 1)

    async def trouve(texte, code_insee=None):
        return {"latitude": 49.4, "longitude": 2.8, "label": texte, "score": 0.9, "code_insee": "60159"}

    monkeypatch.setattr(trajets, "geocoder", trouve)
    etapes, bilan = await module_action.etapes_des_agendas(ctx, "google_agenda", ["a"], debut, debut + timedelta(days=3), 1)
    assert [e.sans_position for e in etapes["a"]] == [
        None, "too many addresses to place", "too many addresses to place", "no readable address on the appointment"]
    assert bilan["adresses_placees"] == 1


async def test_un_agenda_illisible_est_absent_de_la_reponse_jamais_une_erreur(monkeypatch):
    from api.services.hub import agenda as hub_agenda

    async def casse(organization_id, systeme, agenda, *args, **kwargs):
        if agenda == "a":
            raise RuntimeError("down")
        return []

    monkeypatch.setattr(hub_agenda, "evenements", casse)
    ctx = type("C", (), {"organization_id": 1})()
    debut = datetime.now(PARIS)
    etapes, bilan = await module_action.etapes_des_agendas(
        ctx, "google_agenda", ["a", "b"], debut, debut + timedelta(days=3), 1)
    assert list(etapes) == ["b"] and (bilan["agendas_lus"], bilan["agendas_non_lus"]) == (1, 1)


# --------------------------------------------------------------------------- #
# 3. Through the engine's real dispatcher and a real client database (R1)
# --------------------------------------------------------------------------- #

CHEZ_LE_CLIENT = "3 place de l'Hôtel de Ville, 60200 Compiègne"


class AgendasAvecLieux(Agendas):
    """Google Agenda behind the relay, with the events of each agenda (GET .../events)."""

    def __init__(self, organization_id: int):
        super().__init__(organization_id)
        self.evenements: dict[str, list[tuple[str, str, str | None]]] = {}
        self.lectures_evenements: list[httpx.Request] = []
        self.en_panne_evenements = False

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        chemin = requete.url.raw_path.decode().split("?")[0]
        if requete.method == "GET" and chemin.startswith("/proxy/calendar/v3/calendars/") and chemin.endswith("/events"):
            self.lectures_evenements.append(requete)
            if self.en_panne_evenements:
                return httpx.Response(500, json={})
            agenda = chemin.split("/calendars/")[1].removesuffix("/events").replace("%40", "@")
            return httpx.Response(200, json={"items": [
                {"id": f"e{i}", "status": "confirmed", "start": {"dateTime": a}, "end": {"dateTime": b},
                 **({"location": lieu} if lieu else {})}
                for i, (a, b, lieu) in enumerate(self.evenements.get(agenda, []))]})
        return await super().__call__(requete)


@pytest.fixture
async def avec_lieux(installe, monkeypatch, db_session):
    """The planner's world with journeys counted: the caller in Compiègne, the establishment in
    Beauvais, the Base Adresse Nationale a stand-in that knows two addresses; the whole day open."""
    positions = {"60159": COMPIEGNE, "60057": BEAUVAIS}
    adresses = {CHEZ_LE_CLIENT: COMPIEGNE}

    async def geocoder(texte, code_insee=None):
        p = adresses.get(texte) or positions.get(code_insee)
        return {"latitude": p[0], "longitude": p[1], "label": texte, "score": 0.9, "code_insee": code_insee} if p else None

    monkeypatch.setattr(trajets, "geocoder", geocoder)
    # The same agendas, now with events.
    ancien = installe.agendas
    nouveau = AgendasAvecLieux(installe.org.organisation.id)
    nouveau.occupe = ancien.occupe
    monkeypatch.setattr("api.services.integrations.connectors.nango.nouveau_client",
                        lambda **o: httpx.AsyncClient(transport=httpx.MockTransport(nouveau), **o))
    installe.agendas = nouveau
    await db_session.upsert_configuration(
        installe.org.organisation.id, OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
        {"adresses_notification": ["alerte@example.org"],
         "adresse_etablissement": {"code_postal": "60000", "code_insee": "60057", "commune": "Beauvais",
                                   "voie": "1 rue de l'Exemple"}})
    installe.adresses = adresses
    return installe


JOURNEE_ENTIERE = "\n".join(f"{j} : 9h-18h" for j in ("lundi", "mardi", "mercredi", "jeudi", "vendredi")) + "\nsamedi : fermé\ndimanche : fermé"
MIDI = ("2026-10-08T10:00:00Z", "2026-10-08T11:00:00Z")  # Thursday 12:00-13:00 in Paris


async def _proposer(installe, monkeypatch, **regles):
    await _regles(installe, trajets_comptes=True, plages=JOURNEE_ENTIERE, **regles)
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux"),
                                                               _outil("poser_rendez_vous", "Poser")])
    engine._gathered_context["extracted_variables"].update(
        {"voie": "2 rue de l'Essai", "code_postal": "60200", "commune": "Compiègne"})
    await mgr.register_handlers(["uuid-Creneaux", "uuid-Poser"])
    reponse = await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"})
    return reponse, engine, enregistres


async def test_le_meme_creneau_change_de_trajet_selon_le_rendez_vous_precedent_par_le_vrai_repartiteur(
    avec_lieux, monkeypatch
):
    installe = avec_lieux
    # Both busy Thursday 12:00-13:00; Camille's appointment is in the caller's town, Sacha's has no place.
    installe.agendas.occupe = {CAMILLE: [MIDI], SACHA: [MIDI]}
    installe.agendas.evenements = {CAMILLE: [(*MIDI, CHEZ_LE_CLIENT)], SACHA: [(*MIDI, None)]}
    reponse, engine, _ = await _proposer(installe, monkeypatch)
    # Camille (first in the team's order) needs no journey from her appointment: 10:00 and 11:00 end
    # sharp at 12:00 (the next appointment is in the same place) and 13:00 follows it. Before R-6 the
    # establishment's 85 minutes pushed everything to 14:30.
    assert [c["debut"][11:16] for c in reponse["creneaux"]] == ["10:00", "11:00", "13:00"]
    [estampille] = engine._gathered_context["planificateur"]
    assert estampille["trajets"] == {"comptes": True, "minutes": 85, "raison": None}  # the establishment's, as before
    assert estampille["lieux_des_agendas"] == {"agendas_lus": 2, "agendas_non_lus": 0, "evenements": 2,
                                               "adresses_placees": 1}
    premier, deuxieme, troisieme = estampille["creneaux"]
    # 10:00: nothing earlier that day -> the establishment before, the NEXT appointment (placed) after.
    assert premier["trajets"]["avant"]["origine"] == "establishment"
    assert premier["trajets"]["avant"]["libelle"] == "depuis l'établissement"
    assert premier["trajets"]["avant"]["pourquoi"] == "no previous appointment that day"
    assert (premier["trajets"]["apres_min"], premier["trajets"]["apres"]["origine"]) == (0, "previous_appointment")
    # 13:00: the previous appointment (placed) before, nothing later that day after.
    assert (troisieme["trajets"]["avant_min"], troisieme["trajets"]["avant"]["origine"]) == (0, "previous_appointment")
    assert troisieme["trajets"]["avant"]["libelle"] == "depuis le rendez-vous précédent"
    assert troisieme["trajets"]["apres"]["pourquoi"] == "no next appointment that day"
    assert deuxieme["personne"] == troisieme["personne"] == "camille"
    # Sacha alone (Camille busy for the whole period): the establishment's 85 minutes after 13:00.
    installe.agendas.occupe = {CAMILLE: [("2026-10-01T00:00:00Z", "2026-11-30T00:00:00Z")], SACHA: [MIDI]}
    reponse, engine, _ = await _proposer(installe, monkeypatch)
    assert [c["debut"][11:16] for c in reponse["creneaux"]] == ["14:30", "15:30", "16:30"]
    sacha = engine._gathered_context["planificateur"][0]["creneaux"][0]
    assert sacha["personne"] == "sacha" and sacha["trajets"]["avant"]["origine"] == "establishment"
    assert sacha["trajets"]["avant"]["pourquoi"] == "the previous appointment: no readable address on the appointment"


async def test_poser_verifie_le_temps_libre_avec_les_trajets_de_ce_creneau(avec_lieux, monkeypatch):
    """The 13:00 slot only exists because Camille comes from her appointment in the caller's town: the
    booking checks 13:00 against ITS journeys (0 min), not the establishment's 85."""
    installe = avec_lieux
    installe.agendas.occupe = {CAMILLE: [MIDI], SACHA: [MIDI]}
    installe.agendas.evenements = {CAMILLE: [(*MIDI, CHEZ_LE_CLIENT)], SACHA: [(*MIDI, None)]}
    reponse, _, enregistres = await _proposer(installe, monkeypatch)
    treize = next(c["debut"] for c in reponse["creneaux"] if c["debut"][11:16] == "13:00")
    pose = await _appeler(enregistres["poser"][0], {"debut": treize})
    assert pose["pose"] is True and len(installe.agendas.poses) == 1
    assert installe.agendas.poses[0][0] == "/proxy/calendar/v3/calendars/camille%40example.org/events"


async def test_evenements_illisibles_les_trajets_restent_ceux_de_l_etablissement(avec_lieux, monkeypatch):
    """The software refuses the events (HTTP 500): the same slots as before R-6 (14:30, 15:30, 16:30),
    the stamp says no agenda was read, the call goes on."""
    installe = avec_lieux
    installe.agendas.occupe = {CAMILLE: [MIDI], SACHA: [MIDI]}
    installe.agendas.evenements = {CAMILLE: [(*MIDI, CHEZ_LE_CLIENT)]}
    installe.agendas.en_panne_evenements = True
    reponse, engine, _ = await _proposer(installe, monkeypatch)
    assert [c["debut"][11:16] for c in reponse["creneaux"]] == ["14:30", "15:30", "16:30"]
    [estampille] = engine._gathered_context["planificateur"]
    assert estampille["lieux_des_agendas"]["agendas_non_lus"] == 2 and estampille["lieux_des_agendas"]["evenements"] == 0
    assert "trajets" not in estampille["creneaux"][0]  # nothing to say: the establishment's journey, as always
    assert estampille["trajets"]["comptes"] is True


async def test_adresse_introuvable_la_raison_est_dite_et_le_trajet_est_celui_de_l_etablissement(avec_lieux, monkeypatch):
    installe = avec_lieux
    installe.agendas.occupe = {CAMILLE: [MIDI], SACHA: [MIDI]}
    installe.agendas.evenements = {CAMILLE: [(*MIDI, "Chez Paul, derrière la gare")]}
    reponse, engine, _ = await _proposer(installe, monkeypatch)
    assert [c["debut"][11:16] for c in reponse["creneaux"]] == ["14:30", "15:30", "16:30"]
    [estampille] = engine._gathered_context["planificateur"]
    assert estampille["lieux_des_agendas"]["adresses_placees"] == 0
    premier = estampille["creneaux"][0]["trajets"]["avant"]
    assert premier["origine"] == "establishment"
    assert premier["pourquoi"] == "the previous appointment: address not found by the Base Adresse Nationale (or unreachable)"


async def test_sans_trajets_comptes_les_agendas_ne_sont_pas_lus_pour_leurs_lieux(avec_lieux, monkeypatch):
    """X2: journeys not counted (the default), no event is read: nothing changes."""
    installe = avec_lieux
    installe.agendas.evenements = {CAMILLE: [(*MIDI, CHEZ_LE_CLIENT)]}
    await _regles(installe)
    engine, mgr, enregistres = _moteur(installe, monkeypatch, [_outil("proposer_creneaux", "Creneaux")])
    await mgr.register_handlers(["uuid-Creneaux"])
    await _appeler(enregistres["creneaux"][0], {"souhait": "jeudi"})
    assert installe.agendas.lectures_evenements == []
    [estampille] = engine._gathered_context["planificateur"]
    assert "lieux_des_agendas" not in estampille and all("trajets" not in c for c in estampille["creneaux"])


def test_le_calcul_des_trajets_par_creneau_reste_loin_sous_le_delai():
    """20 people with 60 appointments each over 30 days, a grid of 5 minutes: the lookup is a
    bisection, the computation stays far under the action's deadline (5 s)."""
    import time as horloge

    jours = [h(8, 0) + timedelta(days=k) for k in range(30)]
    gens = []
    for i in range(20):
        etapes = [Etape(j.replace(hour=10), j.replace(hour=11), position=COMPIEGNE) for j in jours]
        etapes += [Etape(j.replace(hour=15), j.replace(hour=16), sans_position="x") for j in jours]
        gens.append(candidat(f"p{i}", etapes))
    ouvertures = [(j.replace(hour=9), j.replace(hour=18)) for j in jours]
    debut = horloge.perf_counter()
    creneaux = calculer(gens, ouvertures, Regles(duree_min=60, nombre=3, pas_min=5, repartition="charge"),
                        lire_souhait("le soir après 19h", MAINTENANT), h(8, 8), h(8, 8) + timedelta(days=30))
    assert creneaux == [] and horloge.perf_counter() - debut < 2.0
    # And the row of the stamp is JSON.
    assert json.dumps(trajets_de([])(h(8, 9), h(8, 10)).avant)
