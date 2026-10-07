"""[.mark] The planner's two actions (chantier l-agent-collegue, L5, P1, P3 to P9).

Internal actions of the connector ``planificateur`` (``connectors/actions/planificateur.py``),
run like any action of the catalogue (deadline, anticipation, stamps), never by the relay:

- ``proposer_creneaux`` (reads, may be ANTICIPATED, D17): the number of slots set, for a type of
  appointment, as the caller wishes (``souhait``, read by the code, P4), counting the length, the
  margins, the journeys (P5, P6), the zone, the holidays (P10) and the distribution (P7). The
  agent gets the slots only, with the person's first name when the setting allows it (P9),
  never the agendas.
- ``poser_rendez_vous`` (writes, never anticipated): ONE of the slots proposed in this call
  (the model never chooses the person: the slot carries her), checked free again, booked in her
  agenda through the translator (H2), noted for the hub (H6: ``rendez_vous``, ``lien_externe``,
  the attribution P7, the mention C11), written after the call.

Nothing found, or nothing possible (no calendar software, no client database, nobody for this
type, outside the zone): the fallback P8 -- « human then call-back » (default): the business is
open and someone can take the call, the model is told to put the caller through; otherwise, or
« always call-back »: a call-back request is noted with the caller's wish and a sentence of the
catalogue is SAID by the code (``phrase_planificateur_rappel``, default text below). Either way
the after-call makes the request (never a silence, never a lost caller).

Journeys (R-6): a person's journey to the caller starts from the address of the PREVIOUS appointment
of her agenda that day (the last event ending before the slot) when it carries a readable address,
otherwise from the establishment; the journey back to the NEXT appointment follows the same rule.
Always through ``trajets.duree_trajet_min`` (the one function that counts a journey). An address the
Base Adresse Nationale cannot place, an agenda that cannot be read, a lack of time: the establishment,
never an error. The stamp says, for each slot offered, where each journey started from and why.

Every run leaves its stamp in the record (``planificateur``): slots computed, by whom, the time of
the computation, whether journeys were counted and why not, the wish as read.
"""

from __future__ import annotations

import asyncio
import time as horloge
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from api.schemas.planificateur import (
    DEFAUTS,
    ReglagesPlanificateur,
    TypeRendezVous,
    effectifs,
)
from api.services.apres_appel.rappels import CLE_RAPPEL
from api.services.integrations.connectors import nango
from api.services.integrations.connectors.outil import CLE_A_DIRE, CLE_A_NOTER
from api.services.planificateur import pose as etat_pose
from api.services.planificateur import trajets
from api.services.planificateur.calcul import (
    Candidat,
    Creneau,
    Regles,
    Trajets,
    calculer,
)
from api.services.planificateur.souhaits import Souhait, lire_souhait
from api.services.verrou import Occupe, verrou
from api.utils.template_renderer import render_template

FUSEAU = ZoneInfo("Europe/Paris")
CLE_ESTAMPILLE = "planificateur"
CLE_HUB = "hub_rendez_vous"
VARIABLE_PHRASE_RAPPEL = "phrase_planificateur_rappel"
PHRASE_RAPPEL_DEFAUT = (
    "Je n'ai pas de créneau qui convienne pour le moment : je note votre demande, "
    "on vous rappelle pour fixer le rendez-vous."
)
# The default booking ranges when neither the planner nor the establishment has hours.
PLAGES_DEFAUT = "\n".join(
    [f"{j} : 9h-12h, 14h-18h" for j in ("lundi", "mardi", "mercredi", "jeudi", "vendredi")]
    + ["samedi : fermé", "dimanche : fermé"]
)
# R-6: how many agenda places are placed on a map at most per call, how many at once, and the time
# given to read the agendas' events and place their addresses (a slice of the action's deadline).
MAX_LIEUX = 40
PARALLELE_LIEUX = 8
TEMPS_MAX_LIEUX_S = 2.5
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")


def maintenant() -> datetime:
    """The present, in the business's time (a test sets it)."""
    return datetime.now(FUSEAU)


class Indisponible(RuntimeError):
    """The planner cannot run for this call (a setting is missing). Safe to stamp."""


def libelle(moment: datetime) -> str:
    m = moment.astimezone(FUSEAU)
    minutes = f" {m.minute:02d}" if m.minute else ""
    jour = "1er" if m.day == 1 else str(m.day)
    return f"{JOURS[m.weekday()]} {jour} {MOIS[m.month - 1]} à {m.hour} h{minutes}"


# --------------------------------------------------------------------------- #
# What the computation reads
# --------------------------------------------------------------------------- #


@dataclass
class Lecture:
    systeme: str
    etablissement: Any  # schemas.etablissements.Etablissement | None
    reglages: ReglagesPlanificateur
    types: list[TypeRendezVous]
    personnes: list[dict] = field(default_factory=list)
    attributions: dict[str, int] = field(default_factory=dict)


async def _etablissement(ctx) -> Any:
    from api.services.etablissements.appel import etablissement_de_lappel

    workflow_id = None
    if ctx.run_id:
        try:
            from api.db import db_client

            run = await db_client.get_workflow_run_by_id(ctx.run_id)
            workflow_id = getattr(run, "workflow_id", None)
        except Exception:  # noqa: BLE001 -- never raises during a call: stamped and logged
            workflow_id = None
    servi = await etablissement_de_lappel(ctx.organization_id, workflow_id, ctx.appel or {})
    return servi.etablissement if servi else None


def types_de(types: list[TypeRendezVous], etablissement: str | None) -> list[TypeRendezVous]:
    """The ACTIVE types for this establishment: its own replace the organization's of the same code."""
    propres = {t.code: t for t in types if t.etablissement == etablissement and etablissement}
    sortie = [propres.get(t.code, t) for t in types if t.etablissement is None]
    sortie += [t for c, t in propres.items() if c not in {x.code for x in types if x.etablissement is None}]
    return [t for t in sortie if t.actif]


async def lire(ctx, type_code: str | None) -> tuple[Lecture, TypeRendezVous | None, list[TypeRendezVous]]:
    from api.db.bases_clients.connexion import connecter
    from api.db.bases_clients.planificateur import (
        attributions_par_personne,
        lire_planificateur,
        personnes_du_type,
    )
    from api.services.base_client.rattachement import nom_de_la_base
    from api.services.hub.choix import lire_choix

    systeme = (await lire_choix(ctx.organization_id)).agenda
    if not systeme:
        raise Indisponible("no calendar software chosen (« Integrations »)")
    nom = await nom_de_la_base(ctx.organization_id)
    if not nom:
        raise Indisponible("no client database attached")
    etablissement = await _etablissement(ctx)
    site = etablissement.id if etablissement else None
    connexion = await connecter(nom)
    try:
        planificateur = await lire_planificateur(connexion)
        reglages = effectifs(planificateur.reglages, planificateur.par_etablissement.get(site) if site else None)
        types = types_de(planificateur.types, site)
        choisi = next((t for t in types if t.code == type_code), None)
        if choisi is None and not type_code and len(types) == 1:
            choisi = types[0]
        lecture = Lecture(systeme, etablissement, reglages, types)
        if choisi is not None:
            lecture.personnes = await personnes_du_type(connexion, choisi.sujet, site, systeme)
            lecture.attributions = await attributions_par_personne(
                connexion, choisi.code,
                # R-7: the window of the turn's fairness (P7), a setting with its inheritance.
                datetime.now(UTC) - timedelta(days=int(reglages.fenetre_equite_jours or DEFAUTS.fenetre_equite_jours)),
            )
    finally:
        await connexion.close()
    return lecture, choisi, types


def ouvertures(texte: str | None, debut: datetime, fin: datetime) -> list[tuple[datetime, datetime]]:
    """The open ranges between two instants, from the readable hours format."""
    from opening_hours import OpeningHours, State

    from api.services.pipecat.etat_ouverture import vers_expression_osm

    if fin <= debut:
        return []
    expression = vers_expression_osm(texte or PLAGES_DEFAUT)
    horaires = OpeningHours(expression, timezone=FUSEAU, country="FR")
    sortie = []
    for a, b, etat, _commentaire in horaires.intervals(debut.astimezone(FUSEAU), fin.astimezone(FUSEAU)):
        if etat != State.OPEN:
            continue
        a = a.replace(tzinfo=FUSEAU) if a.tzinfo is None else a.astimezone(FUSEAU)
        b = b.replace(tzinfo=FUSEAU) if b.tzinfo is None else b.astimezone(FUSEAU)
        sortie.append((a, b))
    return sortie


async def _commune(code_postal: str | None, commune: str | None):
    """The commune of the caller (INSEE, centre), from our national list. None if unsure."""
    if not commune and not code_postal:
        return None
    from api.services.communes.base import normaliser, obtenir_base

    base = await obtenir_base()
    nom = normaliser(commune or "")
    if code_postal:
        candidates = base.communes_du_code_postal(str(code_postal))
        if nom:
            candidates = [c for c in candidates if normaliser(c.nom) == nom]
        return candidates[0] if len(candidates) == 1 else None
    indices = base.par_nom.get(nom) or []
    return base.communes[indices[0]] if len(indices) == 1 else None


async def position_appelant(ctx) -> dict:
    """``{commune: insee|None, centre, position, adresse, raison}``: the caller's address from our
    modules (P6), its position by the Base Adresse Nationale (repli 7)."""
    adresse = ctx.modele.adresse
    commune = await _commune(adresse.code_postal, adresse.commune)
    sortie: dict = {"commune": None, "centre": None, "position": None, "adresse": None, "raison": None}
    if commune is None:
        sortie["raison"] = "no sure commune for the caller"
        return sortie
    sortie["commune"] = commune.insee
    if commune.lat is not None:
        sortie["centre"] = (commune.lat, commune.lon)
    if not adresse.voie:
        sortie["raison"] = "no street for the caller"
        return sortie
    trouve = await trajets.geocoder(f"{adresse.voie} {commune.cps[0] if commune.cps else ''} {commune.nom}", commune.insee)
    if trouve is None:
        sortie["raison"] = "address not found by the Base Adresse Nationale (or unreachable)"
        return sortie
    sortie["position"] = (trouve["latitude"], trouve["longitude"])
    sortie["adresse"] = {
        "voie": adresse.voie,
        "code_postal": adresse.code_postal or (commune.cps[0] if commune.cps else None),
        "commune": commune.nom,
        "code_insee": commune.insee,
        "latitude": trouve["latitude"],
        "longitude": trouve["longitude"],
        "verifiee": True,
    }
    return sortie


async def position_etablissement(ctx, etablissement) -> tuple[float, float] | None:
    from api.services.communes.adresse import lire_adresse_etablissement, texte_adresse
    from api.services.communes.base import obtenir_base

    adresse = getattr(etablissement, "adresse", None) if etablissement else None
    if adresse is None:
        adresse = await lire_adresse_etablissement(None, ctx.organization_id)
    if adresse is None:
        return None
    if adresse.voie:
        trouve = await trajets.geocoder(texte_adresse(adresse), adresse.code_insee)
        if trouve:
            return (trouve["latitude"], trouve["longitude"])
    centre = (await obtenir_base()).coordonnees(adresse.code_insee)
    return (centre[1], centre[0]) if centre else None


# --------------------------------------------------------------------------- #
# Journeys from the previous appointment (R-6)
# --------------------------------------------------------------------------- #

ORIGINE_RENDEZ_VOUS = "previous_appointment"
ORIGINE_ETABLISSEMENT = "establishment"
LIBELLES_ORIGINE = {
    ORIGINE_RENDEZ_VOUS: "depuis le rendez-vous précédent",
    ORIGINE_ETABLISSEMENT: "depuis l'établissement",
}


@dataclass
class Etape:
    """One appointment of a person's agenda: when, and where when a position was found.
    ``sans_position`` says why not (English, goes into the stamp)."""

    debut: datetime
    fin: datetime
    position: tuple[float, float] | None = None
    code_insee: str | None = None
    sans_position: str | None = None


def lieu_lisible(lieu: str | None) -> str | None:
    """The place of an event when it could be an address; None otherwise (empty, a link of a video
    call, a few characters). The Base Adresse Nationale has the last word."""
    texte = " ".join((lieu or "").split())
    if not 5 <= len(texte) <= 200 or "://" in texte or not any(c.isalpha() for c in texte):
        return None
    return texte


async def _positionner(lieux: list[str], delai: float) -> dict[str, dict | None]:
    """Place the addresses by the Base Adresse Nationale, a few at a time, within ``delai``.
    An address absent from the answer was not placed in time."""
    trouves: dict[str, dict | None] = {}
    feu = asyncio.Semaphore(PARALLELE_LIEUX)

    async def un(lieu: str) -> None:
        async with feu:
            trouves[lieu] = await trajets.geocoder(lieu)

    taches = [asyncio.create_task(un(lieu)) for lieu in lieux]
    if taches:
        _, restantes = await asyncio.wait(taches, timeout=delai)
        for tache in restantes:
            tache.cancel()
        await asyncio.gather(*restantes, return_exceptions=True)
    return trouves


async def etapes_des_agendas(
    ctx, systeme: str, agendas: list[str], debut: datetime, fin: datetime, delai: float
) -> tuple[dict[str, list[Etape]], dict]:
    """For each agenda, its appointments with the position of their address (R-6), and what was
    done, for the stamp. An agenda that cannot be read is absent from the answer (its person
    starts from the establishment). Never raises."""
    from api.services.hub import agenda as hub_agenda

    async def lire_un(agenda: str):
        try:
            return agenda, await hub_agenda.evenements(
                ctx.organization_id, systeme, agenda, debut, fin, delai=delai
            )
        except Exception as erreur:  # noqa: BLE001 -- never raises during a call: stamped and logged
            logger.warning(f"[.mark] Agenda events not read, journeys from the establishment: {erreur!r}")
            return agenda, None

    lus = dict(await asyncio.gather(*(lire_un(a) for a in agendas)))
    bilan = {
        "agendas_lus": sum(1 for v in lus.values() if v is not None),
        "agendas_non_lus": sum(1 for v in lus.values() if v is None),
        "evenements": 0,
        "adresses_placees": 0,
    }
    # The places to place: distinct, in the order of the agendas, within the cap.
    voulus: list[str] = []
    for evenements in lus.values():
        for e in evenements or []:
            lieu = lieu_lisible(e["lieu"])
            if lieu and lieu not in voulus:
                voulus.append(lieu)
    voulus = voulus[:MAX_LIEUX]
    placees = await _positionner(voulus, delai)
    sortie: dict[str, list[Etape]] = {}
    for agenda, evenements in lus.items():
        if evenements is None:
            continue
        etapes = []
        for e in evenements:
            bilan["evenements"] += 1
            lieu = lieu_lisible(e["lieu"])
            etape = Etape(e["debut"], e["fin"])
            if lieu is None:
                etape.sans_position = "no readable address on the appointment"
            elif lieu not in voulus:
                etape.sans_position = "too many addresses to place"
            elif lieu not in placees:
                etape.sans_position = "address not placed in time"
            elif placees[lieu] is None:
                etape.sans_position = "address not found by the Base Adresse Nationale (or unreachable)"
            else:
                etape.position = (placees[lieu]["latitude"], placees[lieu]["longitude"])
                etape.code_insee = placees[lieu].get("code_insee")
                bilan["adresses_placees"] += 1
            etapes.append(etape)
        sortie[agenda] = etapes
    return sortie, bilan


def trajets_du_creneau(
    etapes: list[Etape],
    *,
    appelant: tuple[float, float],
    base_min: int,
    coefficient: float,
    vitesse_kmh: float,
) -> Callable[[datetime, datetime], Trajets]:
    """The journeys around a slot for a person whose agenda holds ``etapes`` (R-6).

    Before: the last appointment ending at or before the start, the same day (business time); after:
    the first one starting at or after the end, the same day. With a position: the journey from (to)
    it, by ``duree_trajet_min``. Otherwise ``base_min``, the establishment's, and the stamp says why."""
    par_fin = sorted(etapes, key=lambda e: e.fin)
    fins = [e.fin for e in par_fin]
    par_debut = sorted(etapes, key=lambda e: e.debut)
    debuts = [e.debut for e in par_debut]

    def de_l_etablissement(pourquoi: str) -> tuple[int, dict]:
        return base_min, {
            "origine": ORIGINE_ETABLISSEMENT,
            "libelle": LIBELLES_ORIGINE[ORIGINE_ETABLISSEMENT],
            "pourquoi": pourquoi,
            "minutes": base_min,
        }

    def un_cote(etape: Etape | None, jour, avant: bool) -> tuple[int, dict]:
        voisin = "previous" if avant else "next"
        if etape is None or etape.fin.astimezone(FUSEAU).date() != jour or etape.debut.astimezone(FUSEAU).date() != jour:
            return de_l_etablissement(f"no {voisin} appointment that day")
        if etape.position is None:
            return de_l_etablissement(f"the {voisin} appointment: {etape.sans_position}")
        a, b = (etape.position, appelant) if avant else (appelant, etape.position)
        minutes = trajets.duree_trajet_min(a, b, coefficient=coefficient, vitesse_kmh=vitesse_kmh)
        repere = (etape.fin if avant else etape.debut).astimezone(FUSEAU).strftime("%H:%M")
        return minutes, {
            "origine": ORIGINE_RENDEZ_VOUS,
            "libelle": LIBELLES_ORIGINE[ORIGINE_RENDEZ_VOUS],
            "pourquoi": f"the {voisin} appointment {'ends' if avant else 'starts'} at {repere}, its address is placed",
            "minutes": minutes,
            **({"code_insee": etape.code_insee} if etape.code_insee else {}),
        }

    def calcul(debut: datetime, fin: datetime) -> Trajets:
        jour = debut.astimezone(FUSEAU).date()
        i = bisect_right(fins, debut) - 1
        j = bisect_left(debuts, fin)
        avant_min, avant = un_cote(par_fin[i] if i >= 0 else None, jour, True)
        apres_min, apres = un_cote(par_debut[j] if j < len(par_debut) else None, jour, False)
        return Trajets(avant_min, apres_min, avant, apres)

    return calcul


# --------------------------------------------------------------------------- #
# The fallback (P8)
# --------------------------------------------------------------------------- #


def _humain_possible(ctx, personnes: list[dict]) -> bool:
    from api.services.annonce.constantes import OUVERT

    appel = ctx.appel or {}
    if appel.get("etat_ouverture") != OUVERT:
        return False
    return bool(appel.get("numero_transfert")) or any(
        p.get("joignable_par_transfert") and p.get("telephone") for p in personnes
    )


def repli(ctx, reglages: ReglagesPlanificateur, raison: str, souhait: Souhait | None,
          personnes: list[dict], estampille: dict, type_code: str | None = None,
          creneau: str | None = None) -> dict:
    mode = reglages.repli or DEFAUTS.repli
    rappel = {
        "raison": raison,
        "souhait": souhait.texte if souhait else None,
        "type": type_code,
        "creneau_choisi": creneau,
        "le": datetime.now(UTC).isoformat(),
    }
    estampille = {**estampille, "repli": None, "raison": raison}
    if mode == "humain_puis_rappel" and _humain_possible(ctx, personnes):
        estampille["repli"] = "humain"
        return {
            "status": "no_slot",
            "fallback": "human",
            "instruction": (
                "No appointment can be booked now. Offer to put the caller through to a colleague right "
                "away (« direct to a person » or the transfer tool). If that fails, tell the caller he will "
                "be called back: a call-back request is noted anyway."
            ),
            CLE_A_NOTER: {CLE_ESTAMPILLE: estampille, CLE_RAPPEL: {**rappel, "mode": "humain"}},
        }
    brut = (ctx.appel or {}).get(VARIABLE_PHRASE_RAPPEL)
    phrase = brut if isinstance(brut, str) and brut.strip() else PHRASE_RAPPEL_DEFAUT
    phrase = " ".join(str(render_template(phrase, {"souhait": souhait.texte if souhait else ""}) or "").split())
    estampille["repli"] = "rappel"
    return {
        "status": "no_slot",
        "fallback": "callback",
        "instruction": "A call-back request was noted and said to the caller; do not repeat it, go on with the call.",
        CLE_A_DIRE: phrase,
        CLE_A_NOTER: {CLE_ESTAMPILLE: estampille, CLE_RAPPEL: {**rappel, "mode": "rappel"}},
    }


# --------------------------------------------------------------------------- #
# proposer_creneaux
# --------------------------------------------------------------------------- #


async def proposer(arguments: dict, ctx, delai_s: float) -> dict:
    trajets.ORGANISATION.set(ctx.organization_id)  # the geocoder's memory is per organization
    from api.services.hub import agenda as hub_agenda

    debut_calcul = horloge.monotonic()
    present = maintenant()
    souhait = lire_souhait(arguments.get("souhait"), present)
    type_code = (str(arguments.get("type") or "").strip() or None)
    estampille: dict = {"action": "proposer_creneaux", "le": datetime.now(UTC).isoformat(),
                        "souhait": souhait.estampille(), "type": type_code}
    try:
        lecture, choisi, types = await lire(ctx, type_code)
    except Indisponible as erreur:
        return repli(ctx, DEFAUTS, str(erreur), souhait, [], estampille, type_code)
    reglages = lecture.reglages
    if choisi is None:
        if not types:
            return repli(ctx, reglages, "no appointment type set", souhait, [], estampille, type_code)
        return {
            "status": "choose_type",
            "types": [{"code": t.code, "libelle": t.libelle} for t in types],
            "instruction": "Ask the caller which kind of appointment, then call again with its code in « type ».",
        }
    estampille["type"] = choisi.code
    if not lecture.personnes:
        return repli(ctx, reglages, "nobody with an agenda for this type", souhait, [], estampille, choisi.code)

    # The caller's position, only when something needs it.
    besoin_position = bool(reglages.trajets_comptes or reglages.zone_rayon_km or reglages.zone_communes
                           or reglages.repartition == "zone")
    appelant = await position_appelant(ctx) if besoin_position else {"raison": "not needed"}
    base = await position_etablissement(ctx, lecture.etablissement) if besoin_position else None

    # The zone served (P3): a commune outside the list, or a position beyond the radius.
    zone = "not checked"
    if reglages.zone_communes and appelant.get("commune"):
        zone = "inside" if appelant["commune"] in reglages.zone_communes else "outside"
    if zone != "outside" and reglages.zone_rayon_km and base:
        point = appelant.get("position") or appelant.get("centre")
        if point:
            zone = "inside" if trajets.distance_km(base, point) <= reglages.zone_rayon_km else "outside"
    estampille["zone"] = zone
    if zone == "outside":
        return repli(ctx, reglages, "the caller's address is outside the zone served", souhait,
                     lecture.personnes, {**estampille, "hors_zone": True}, choisi.code)

    trajet_min, raison_trajets = 0, None
    if reglages.trajets_comptes:
        if appelant.get("position") and base:
            trajet_min = trajets.duree_trajet_min(
                base, appelant["position"], coefficient=reglages.coefficient_trajet or 1.3,
                vitesse_kmh=reglages.vitesse_kmh or 50,
            )
        else:
            raison_trajets = appelant.get("raison") or "no position for the establishment"
    estampille["trajets"] = {"comptes": bool(reglages.trajets_comptes and raison_trajets is None),
                             "minutes": trajet_min, "raison": raison_trajets}

    premier = present + timedelta(hours=float(reglages.delai_minimal_h or 0))
    if souhait.des_le:
        premier = max(premier, datetime.combine(souhait.des_le, time(0), FUSEAU))
    horizon = (present.astimezone(UTC) + timedelta(days=int(reglages.horizon_jours or 14))).astimezone(FUSEAU)
    plages = reglages.plages or (ctx.appel or {}).get("horaires_ouverture")
    estampille["plages"] = "planner" if reglages.plages else ("establishment" if plages else "default")
    try:
        ranges = ouvertures(plages, premier, horizon)
    except Exception as erreur:  # noqa: BLE001 -- never raises during a call: stamped and logged
        logger.warning(f"[.mark] Planner ranges unreadable, default ranges used: {erreur!r}")
        ranges = ouvertures(None, premier, horizon)
        estampille["plages"] = "default (unreadable)"

    agendas = {p["cle"]: p["agenda"] for p in lecture.personnes}
    reste = max(0.5, delai_s - (horloge.monotonic() - debut_calcul) - 0.3)
    try:
        occupe = await hub_agenda.occupations(
            ctx.organization_id, lecture.systeme, list(agendas.values()),
            present - timedelta(days=1), horizon + timedelta(days=1), delai=reste,
        )
    except Exception as erreur:  # noqa: BLE001 -- never raises during a call: stamped and logged
        logger.warning(f"[.mark] Agendas not read, planner fallback: {erreur!r}")
        return repli(ctx, reglages, f"agendas unreadable ({type(erreur).__name__})", souhait,
                     lecture.personnes, estampille, choisi.code)

    # R-6: with journeys counted, where each person comes from (her previous appointment) and goes
    # to (the next one); any failure leaves her on the establishment's journey.
    etapes: dict[str, list[Etape]] = {}
    if reglages.trajets_comptes and raison_trajets is None:
        reste_lieux = min(TEMPS_MAX_LIEUX_S, max(0.3, delai_s - (horloge.monotonic() - debut_calcul) - 0.8))
        try:
            etapes, bilan = await asyncio.wait_for(
                etapes_des_agendas(
                    ctx, lecture.systeme, [a for a in agendas.values() if a in occupe],
                    present - timedelta(days=1), horizon + timedelta(days=1), reste_lieux,
                ),
                timeout=reste_lieux + 1.0,
            )
        except Exception as erreur:  # noqa: BLE001 -- never raises during a call: stamped and logged
            logger.warning(f"[.mark] Appointment places not read, journeys from the establishment: {erreur!r}")
            etapes, bilan = {}, {"agendas_lus": 0, "erreur": type(erreur).__name__}
        estampille["lieux_des_agendas"] = bilan

    candidats = []
    for p in lecture.personnes:
        if p["agenda"] not in occupe:
            continue  # unknown to the software: never free
        intervalles = occupe[p["agenda"]]
        charge = sum(int((min(b, horizon) - max(a, present)).total_seconds() // 60)
                     for a, b in intervalles if b > present and a < horizon)
        position = appelant.get("position") or appelant.get("centre")
        candidats.append(Candidat(
            cle=p["cle"], prenom=p["prenom"], agenda=p["agenda"], occupe=intervalles,
            trajet_min=trajet_min, attributions=lecture.attributions.get(p["cle"], 0),
            trajets=(
                trajets_du_creneau(
                    etapes[p["agenda"]], appelant=appelant["position"], base_min=trajet_min,
                    coefficient=reglages.coefficient_trajet or 1.3, vitesse_kmh=reglages.vitesse_kmh or 50,
                )
                if p["agenda"] in etapes else None
            ),
            charge_min=max(0, charge),
            distance_km=trajets.distance_km(base, position) if (base and position) else None,
        ))
    regles = Regles(
        duree_min=choisi.duree_min, marge_avant_min=choisi.marge_avant_min,
        marge_apres_min=choisi.marge_apres_min, nombre=int(reglages.nombre_creneaux or 3),
        pas_min=int(reglages.pas_min or 30), repartition=reglages.repartition or "premier_libre",
        jours_feries=reglages.jours_feries or "metropole",
    )
    creneaux = calculer(candidats, ranges, regles, souhait, premier, horizon)
    souhait_tenu = True
    if not creneaux and souhait.compris and souhait.reconnu:
        # Nothing fits the wish: the earliest slots, and the model is told the wish could not be met.
        creneaux = calculer(candidats, ranges, regles, lire_souhait(None, present), premier, horizon)
        souhait_tenu = False
    estampille.update({
        "systeme": lecture.systeme,
        "repartition": regles.repartition,
        "ordre": [c.cle for c in candidats],
        "creneaux": [_creneau(c, agendas) for c in creneaux],
        "duree_calcul_ms": int((horloge.monotonic() - debut_calcul) * 1000),
        "adresse_appelant": appelant.get("adresse"),
    })
    if not creneaux:
        return repli(ctx, reglages, "no slot fits", souhait, lecture.personnes, estampille, choisi.code)
    prenoms = {p["cle"]: p["prenom"] for p in lecture.personnes}
    resultat: dict = {
        "type": choisi.libelle,
        "creneaux": [
            {"debut": c.debut.isoformat(), "libelle": libelle(c.debut),
             **({"avec": prenoms.get(c.cle)} if reglages.personne_visible else {})}
            for c in creneaux
        ],
        CLE_A_NOTER: {CLE_ESTAMPILLE: estampille},
    }
    if not souhait.compris:
        resultat["souhait_compris"] = False
        resultat["instruction"] = ("The caller's wish was not understood: these are the earliest slots. "
                                   "Say so, and ask for another moment if none suits.")
    elif not souhait_tenu:
        resultat["souhait_tenu"] = False
        resultat["instruction"] = ("No slot fits the caller's wish: these are the earliest. Say so, "
                                   "and ask whether one of them suits.")
    return resultat


def _creneau(c: Creneau, agendas: dict[str, str]) -> dict:
    sortie = {"debut": c.debut.isoformat(), "fin": c.fin.isoformat(), "personne": c.cle,
              "agenda": agendas.get(c.cle), "rang": c.rang}
    if c.trajets is not None:
        # R-6: what was counted around this slot and where each journey started from, and why.
        sortie["trajets"] = {"avant_min": c.trajets.avant_min, "apres_min": c.trajets.apres_min,
                             "avant": c.trajets.avant, "apres": c.trajets.apres}
    return sortie


# --------------------------------------------------------------------------- #
# poser_rendez_vous
# --------------------------------------------------------------------------- #


def _proposition(fiche: dict | None, debut: datetime) -> tuple[dict, dict] | None:
    """The slot proposed in THIS call that starts at ``debut``, and its proposal (newest first)."""
    for entree in reversed(((fiche or {}).get(CLE_ESTAMPILLE)) or []):
        if not isinstance(entree, dict) or entree.get("action") != "proposer_creneaux":
            continue
        for c in entree.get("creneaux") or []:
            try:
                if datetime.fromisoformat(c["debut"]) == debut:
                    return c, entree
            except (KeyError, TypeError, ValueError):
                continue
    return None


def _derniers_proposes(fiche: dict | None) -> list[dict]:
    for entree in reversed(((fiche or {}).get(CLE_ESTAMPILLE)) or []):
        if isinstance(entree, dict) and entree.get("action") == "proposer_creneaux" and entree.get("creneaux"):
            return [{"debut": c["debut"], "libelle": libelle(datetime.fromisoformat(c["debut"]))}
                    for c in entree["creneaux"]]
    return []


async def poser(arguments: dict, ctx, delai_s: float) -> dict:
    debut_calcul = horloge.monotonic()
    brut = str(arguments.get("debut") or "")
    try:
        debut = datetime.fromisoformat(brut)
        if debut.tzinfo is None:
            debut = debut.replace(tzinfo=FUSEAU)
    except ValueError:
        debut = None
    trouve = _proposition(ctx.fiche, debut) if debut else None
    if trouve is None:
        return {
            "status": "refused",
            "reason": "not_proposed",
            "instruction": "Book only one of the slots proposed in this call, exactly as given in « debut ».",
            "creneaux": _derniers_proposes(ctx.fiche),
        }
    creneau, proposition = trouve
    estampille: dict = {"action": "poser_rendez_vous", "le": datetime.now(UTC).isoformat(),
                        "debut": creneau["debut"], "personne": creneau["personne"],
                        "type": proposition.get("type")}
    if not (ctx.organization_id and ctx.run_id):
        return repli(ctx, DEFAUTS, "no run to book for", None, [], estampille,
                     proposition.get("type"), creneau["debut"])
    # Pipecat runs the tool calls of a turn in parallel, and a caller changes his mind: ONE booking
    # at a time per call (first lock) and per agenda (second, across calls), always in this order.
    attente = max(1.0, delai_s - 0.5)
    try:
        async with (
            verrou(f"planificateur-run:{int(ctx.organization_id)}:{int(ctx.run_id)}", attente_s=attente),
            verrou(f"planificateur-agenda:{int(ctx.organization_id)}:{creneau.get('agenda')}", attente_s=attente),
        ):
            return await _poser(ctx, delai_s, debut_calcul, debut, creneau, proposition, estampille)
    except Occupe:
        logger.warning("[.mark] Appointment not booked, planner busy")
        return repli(ctx, DEFAUTS, "booking busy", None, [], estampille,
                     proposition.get("type"), creneau["debut"])


async def _deja_pose(ctx, delai_s: float, debut: datetime, creneau: dict, estampille: dict) -> dict | None:
    """What this call already booked, if anything: the same slot again gives the same answer
    (nothing is created twice); another slot is refused; a creation whose answer was lost is
    looked for in the agenda before anything is created again."""
    from api.services.hub import agenda as hub_agenda

    try:
        etat = await etat_pose.lire(ctx.organization_id, ctx.run_id)
    except Exception as erreur:  # fail closed: no second event on a doubt
        logger.error(f"[.mark] Booking state unreadable, nothing booked: {erreur!r}")
        raise Indisponible("booking state unreadable") from erreur
    pose = etat.get("pose")
    if pose:
        if pose.get("debut") == debut.isoformat() and pose.get("agenda") == creneau.get("agenda"):
            return {"pose": True, "libelle": pose.get("libelle"), "deja": True,
                    **({"avec": pose["avec"]} if pose.get("avec") else {}),
                    CLE_A_NOTER: {CLE_ESTAMPILLE: {**estampille, "refus": "already_booked_same_slot",
                                                    "id_externe": pose.get("id_externe")}}}
        return {
            "status": "already_booked",
            "libelle": pose.get("libelle"),
            "instruction": (
                "An appointment is already booked in this call (" + str(pose.get("libelle")) + "). "
                "Do not book another one. If the caller wants another moment, tell him a colleague will call "
                "him back to change it: a call-back request was noted."
            ),
            CLE_A_NOTER: {
                CLE_ESTAMPILLE: {**estampille, "refus": "already_booked"},
                CLE_RAPPEL: {"raison": "change of the appointment booked in this call", "creneau_choisi": creneau["debut"],
                             "mode": "rappel", "le": datetime.now(UTC).isoformat()},
            },
        }
    en_cours = etat.get("en_cours")
    if not en_cours:
        return None
    # A creation was started and its answer is not known (deadline, cut): is the event there?
    fin = datetime.fromisoformat(en_cours["fin"])
    debut_cree = datetime.fromisoformat(en_cours["debut"])
    trouve = None
    try:
        existants = await hub_agenda.evenements(
            ctx.organization_id, en_cours["systeme"], en_cours["agenda"],
            debut_cree - timedelta(minutes=1), fin + timedelta(minutes=1), delai=max(0.5, delai_s / 3),
        )
        trouve = next((e for e in existants if e["debut"] == debut_cree and e["fin"] == fin), None)
    except Exception as erreur:  # noqa: BLE001 -- unknown: no second event on a doubt
        logger.warning(f"[.mark] Booking of the previous try not checked: {erreur!r}")
    if trouve is None:
        return {
            "status": "booking_uncertain",
            "instruction": ("The previous booking may have gone through but is not confirmed. Do not book again: "
                            "tell the caller a colleague will confirm the appointment."),
            CLE_A_NOTER: {
                CLE_ESTAMPILLE: {**estampille, "refus": "previous_booking_unknown"},
                CLE_RAPPEL: {"raison": "previous booking unconfirmed", "creneau_choisi": en_cours["debut"],
                             "mode": "rappel", "le": datetime.now(UTC).isoformat()},
            },
        }
    # Found: adopted. Its identifier when the software gives it (else the hub does not link it).
    adopte = {**en_cours, "id_externe": trouve.get("id_externe")}
    return {"adopte": adopte}


def _incertain(erreur: BaseException) -> bool:
    """True when the software may have created the event although the answer is an error: a
    deadline, a cut line. False when it said no (a refusal, no connection, a malformed request)."""
    if isinstance(erreur, nango.NangoIndisponible):
        return not str(erreur).startswith("The software refused")
    return not isinstance(erreur, (nango.ConnexionAbsente, ValueError, Indisponible))


async def _creer(ctx, note_hub: dict, libelle_rdv: str, avec: str | None, rendez_vous: dict, reste: float) -> str:
    """The event created in the software, and what was done kept in the call's booking state.

    The state is written BEFORE (``en_cours``) and AFTER (``pose``) in a task the tool's deadline
    cannot cancel: if the deadline falls while the software answers, the event is still noted
    once the answer comes, and the next try of this call finds it instead of creating another."""
    from api.services.hub import agenda as hub_agenda

    org, run = ctx.organization_id, ctx.run_id
    intention = {"systeme": note_hub["systeme"], "agenda": note_hub["agenda"], "debut": note_hub["debut"],
                 "fin": note_hub["fin"], "libelle": libelle_rdv, "avec": avec, "note_hub": note_hub}
    await etat_pose.ecrire(org, run, {"en_cours": intention})

    async def creer_et_noter() -> str:
        try:
            id_externe = await hub_agenda.poser(org, note_hub["systeme"], rendez_vous, delai=reste)
            if not id_externe:
                raise Indisponible("the software gave no identifier")
        except BaseException as erreur:
            if not _incertain(erreur):
                await etat_pose.ecrire(org, run, {})  # the software said no: nothing to look for
            raise
        await etat_pose.ecrire(org, run, {"pose": {**intention, "id_externe": id_externe,
                                                   "note_hub": {**note_hub, "id_externe": id_externe}}})
        return id_externe

    return await asyncio.shield(asyncio.ensure_future(creer_et_noter()))


async def _adopter(ctx, en_cours: dict, estampille: dict) -> dict:
    """The event of a previous try, found in the agenda: given as booked, noted once."""
    id_externe = en_cours.get("id_externe")
    note_hub = {**en_cours["note_hub"], "id_externe": id_externe}
    await etat_pose.ecrire(ctx.organization_id, ctx.run_id,
                           {"pose": {**en_cours, "id_externe": id_externe, "note_hub": note_hub}})
    notes = {CLE_ESTAMPILLE: {**estampille, "id_externe": id_externe, "adopte": True}}
    if id_externe:
        notes[CLE_HUB] = note_hub  # without the software's identifier the hub cannot link it
    return {"pose": True, "libelle": en_cours.get("libelle"),
            **({"avec": en_cours["avec"]} if en_cours.get("avec") else {}), CLE_A_NOTER: notes}


async def _poser(ctx, delai_s: float, debut_calcul: float, debut: datetime, creneau: dict,
                 proposition: dict, estampille: dict) -> dict:
    from api.services.hub import agenda as hub_agenda

    try:
        deja = await _deja_pose(ctx, delai_s, debut, creneau, estampille)
    except Indisponible as erreur:
        return repli(ctx, DEFAUTS, str(erreur), None, [], estampille, proposition.get("type"), creneau["debut"])
    if deja is not None:
        if "adopte" not in deja:
            return deja
        return await _adopter(ctx, deja["adopte"], estampille)
    try:
        lecture, choisi, _types = await lire(ctx, proposition.get("type"))
    except Indisponible as erreur:
        return repli(ctx, DEFAUTS, str(erreur), None, [], estampille, proposition.get("type"), creneau["debut"])
    reglages = lecture.reglages
    if choisi is None:
        return repli(ctx, reglages, "appointment type no longer set", None, [], estampille,
                     proposition.get("type"), creneau["debut"])
    personne = next((p for p in lecture.personnes if p["cle"] == creneau["personne"]), None)
    if personne is None or personne["agenda"] != creneau.get("agenda"):
        return repli(ctx, reglages, "the person is no longer available for this type", None,
                     lecture.personnes, estampille, choisi.code, creneau["debut"])
    fin = datetime.fromisoformat(creneau["fin"])
    trajet = int(((proposition.get("trajets") or {}).get("minutes")) or 0)
    # R-6: the journeys counted around THIS slot (from the previous appointment or the establishment).
    propres = creneau.get("trajets") or {}
    garde_avant = timedelta(minutes=choisi.marge_avant_min + int(propres.get("avant_min", trajet) or 0))
    garde_apres = timedelta(minutes=choisi.marge_apres_min + int(propres.get("apres_min", trajet) or 0))
    try:
        reste = max(0.5, (delai_s - (horloge.monotonic() - debut_calcul)) / 2)
        occupe = await hub_agenda.occupations(
            ctx.organization_id, lecture.systeme, [personne["agenda"]],
            debut - garde_avant, fin + garde_apres, delai=reste,
        )
        if personne["agenda"] not in occupe:
            raise Indisponible("agenda unknown to the software")
        if any(debut - garde_avant < b and fin + garde_apres > a for a, b in occupe[personne["agenda"]]):
            return {
                "status": "slot_taken",
                "instruction": "This slot was just taken: propose slots again (call the slots action).",
            }
        modele = ctx.modele
        nom = " ".join(x for x in (modele.contact.prenom, modele.contact.nom) if x) or "appelant"
        adresse = proposition.get("adresse_appelant") or None
        lieu = modele.adresse.texte()
        lignes = [f"Type : {choisi.libelle}", f"Contact : {nom}",
                  *([f"Téléphone : {modele.contact.telephone}"] if modele.contact.telephone else []),
                  *([f"Adresse : {lieu}"] if lieu else []),
                  *([f"Motif : {modele.motif}"] if modele.motif else []),
                  "Posé par l'assistant vocal."]
        reste = max(0.5, delai_s - (horloge.monotonic() - debut_calcul) - 0.3)
        note_hub = {
            "systeme": lecture.systeme, "agenda": personne["agenda"], "id_externe": None,
            "debut": debut.isoformat(), "fin": fin.isoformat(), "personne": personne["cle"],
            "motif": ctx.modele.motif or choisi.libelle, "type": choisi.code, "adresse": adresse,
            "attribution": {"mode": proposition.get("repartition") or "premier_libre",
                            "rang": creneau.get("rang"),
                            "motif": f"rang {creneau.get('rang')} de l'ordre {proposition.get('repartition')}"},
        }
        id_externe = await _creer(
            ctx, note_hub, libelle(debut), personne["prenom"] if reglages.personne_visible else None,
            {"agenda": personne["agenda"], "debut": debut.isoformat(), "fin": fin.isoformat(),
             "fuseau": str(FUSEAU), "titre": f"{choisi.libelle} · {nom}",
             "description": "\n".join(lignes), "lieu": lieu},
            reste,
        )
        if not id_externe:
            raise Indisponible("the software gave no identifier")
    except Exception as erreur:  # noqa: BLE001 -- never raises during a call: stamped and logged
        logger.warning(f"[.mark] Appointment not booked, planner fallback: {erreur!r}")
        return repli(ctx, reglages, f"booking failed ({type(erreur).__name__})", None,
                     lecture.personnes, estampille, choisi.code, creneau["debut"])
    estampille["id_externe"] = id_externe
    estampille["duree_ms"] = int((horloge.monotonic() - debut_calcul) * 1000)
    note_hub["id_externe"] = id_externe
    return {
        "pose": True,
        "libelle": libelle(debut),
        **({"avec": personne["prenom"]} if reglages.personne_visible else {}),
        CLE_A_NOTER: {CLE_ESTAMPILLE: estampille, CLE_HUB: note_hub},
    }


async def executer(action, arguments: dict, ctx, delai_s: float) -> dict:
    """``executer_interne`` of the connector ``planificateur``."""
    if action.nom == "proposer_creneaux":
        return await proposer(arguments, ctx, delai_s)
    if action.nom == "poser_rendez_vous":
        return await poser(arguments, ctx, delai_s)
    raise RuntimeError(f"Unknown planner action « {action.nom} ».")
