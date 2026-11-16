"""[.mark] Mécanisme commun : les gestes de la réservation par capacité (lot 8, E-48).

Chaque geste prend la SOURCE (la capacité vraie), l'état de la réservation en cours (dans la fiche de l'appel) et rend un ``Resultat`` fermé
(statut, faits, suggestion, manque). Le modèle choisit comment le dire ; le code tient les faits :

- un manque à la fois (personnes, jour, heure, nom, numéro) ; rien de ce qui a été dit n'est perdu ;
- les jours et heures sont calculés par le code, jamais par le modèle (``resoudre_une_date``) ;
- le créneau demandé est vérifié contre les disponibilités ; sinon les plus proches sont proposées, jamais inventées ;
- on ne réserve, ne change et n'annule qu'après une RELECTURE que l'appelant a confirmée (le jeton lie la confirmation à ce qui a été relu :
  un changement depuis la relecture invalide la confirmation) ; l'annulation se fait en deux temps ;
- la place est revérifiée par la source à l'enregistrement : elle peut refuser alors même que la relecture était bonne.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from api.services.commande.parole import _lettres, heure_en_lettres, liste_dite
from api.services.commande.resultat import Resultat
from api.services.reservation.source import Source

CLE = "reservation_etat"
NOTE_MAX = 200


@dataclass(frozen=True)
class Appelant:
    """Ce que le code sait de l'appelant : le numéro qui s'affiche (E.164, ``None`` s'il est masqué) et l'identifiant de l'appel."""

    telephone_affiche: str | None = None
    appel_id: str | None = None


def etat_du_dossier(fiche: dict | None) -> dict[str, Any]:
    """L'état de la réservation en cours, dans la fiche de l'appel (créé au premier besoin). Sans fiche : un état jetable."""
    if not isinstance(fiche, dict):
        return {}
    existant = fiche.get(CLE)
    if not isinstance(existant, dict):
        existant = fiche[CLE] = {}
    return existant


def _r(statut: str, faits: dict | None = None, suggestion: str = "", manque: str | None = None) -> Resultat:
    return Resultat(statut, faits or {}, suggestion, manque)


def _empreinte(*morceaux: Any) -> str:
    return hashlib.sha256(json.dumps(morceaux, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _personnes_dites(n: int) -> str:
    return f"{_lettres(n)} personne" + ("s" if n > 1 else "")


def _heure_dite(debut: datetime) -> str:
    return heure_en_lettres(debut.hour, debut.minute)


def _creneaux_dits(creneaux: list[dict], souhaite: datetime | None, n: int = 5) -> tuple[list[dict], str]:
    """Au plus ``n`` créneaux à dire : les plus proches de l'heure souhaitée, sinon le premier de chaque heure."""
    if souhaite is not None:
        proches = sorted(creneaux, key=lambda c: (abs((c["debut"] - souhaite).total_seconds()), c["debut"]))[:3]
        choisis = sorted(proches, key=lambda c: c["debut"])
    else:
        vus: set[tuple[int, int]] = set()
        choisis = []
        for c in creneaux:
            cle = (c["debut"].day, c["debut"].hour)
            if cle not in vus:
                vus.add(cle)
                choisis.append(c)
        choisis = choisis[:n]
    return choisis, liste_dite([_heure_dite(c["debut"]) for c in choisis])


# SA-18 (C14) : une partie de la journée dite sans heure (« samedi soir ») : les heures de début qu'elle couvre. Ce sont des mots de la langue.
_PARTIES_DU_JOUR = (
    ("après-midi", (13, 19)), ("apres-midi", (13, 19)), ("midi", (11, 15)), ("matin", (0, 12)), ("soir", (17, 24)),
)


def _partie_du_jour(*textes: str | None) -> tuple[str, tuple[int, int]] | None:
    """La partie de la journée nommée dans ces textes (« soir », « midi »…), avec ses heures, ou ``None``. Une heure précise l'emporte : sans effet."""
    dit = " ".join(t for t in textes if t).casefold()
    return next(((mot, heures) for mot, heures in _PARTIES_DU_JOUR if mot in dit), None)


def _jour_de(resolu: Resultat) -> date | None:
    jour = resolu.faits.get("jour") or (resolu.faits.get("heure_voulue") or "")[:10]
    try:
        return date.fromisoformat(jour)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# disponibilites
# --------------------------------------------------------------------------- #


async def disponibilites(source: Source, etat: dict[str, Any], jour: str | None, personnes: int | None, heure: str | None = None) -> Resultat:
    """Les créneaux libres d'un jour pour un effectif. Avec ``heure``, les trois plus proches de cette heure ; sans, le premier de chaque heure.
    Rien n'est réservé. Complet : ``faits.complet`` vrai, aucun créneau inventé."""
    if not isinstance(personnes, int) or isinstance(personnes, bool) or personnes < 1:
        return _r("INCOMPLETE", {}, "Pour combien de personnes ?", "personnes")
    if not jour:
        return _r("INCOMPLETE", {}, "Pour quel jour ?", "jour")
    resolu = await source.resoudre_une_date(jour, heure)
    if resolu.statut not in ("RETENU", "INCOMPLETE") or (resolu.statut == "INCOMPLETE" and resolu.manque != "heure"):
        return resolu
    le_jour = _jour_de(resolu)
    if le_jour is None:
        return _r("INTROUVABLE", {}, "Pour quel jour ?", "jour")
    libres = await source.disponibilites(le_jour, personnes)
    if libres.statut != "OK":
        return libres
    creneaux = libres.faits.get("creneaux") or []
    if not creneaux:
        return _r("OK", {"jour": le_jour.isoformat(), "creneaux": [], "complet": True}, "Nous sommes complets ce jour-là.")
    partie = _partie_du_jour(jour, heure) if "heure_voulue" not in resolu.faits else None
    if partie is not None:
        # « samedi soir » : seuls les créneaux de ce moment-là sont proposés, jamais ceux du midi.
        mot, (de, a) = partie
        dans_la_partie = [c for c in creneaux if de <= c["debut"].hour < a]
        if not dans_la_partie:
            return _r("OK", {"jour": le_jour.isoformat(), "creneaux": [], "complet": True, "partie": mot}, f"Nous sommes complets ce jour-là, pour le {mot}.")
        creneaux = dans_la_partie
    souhaite = datetime.fromisoformat(resolu.faits["heure_voulue"]) if resolu.faits.get("heure_voulue") else None
    choisis, dit = _creneaux_dits(creneaux, souhaite)
    return _r(
        "OK", {"jour": le_jour.isoformat(), "creneaux": [{"debut": c["debut"], "heure_dite": _heure_dite(c["debut"])} for c in choisis], "complet": False},
        f"Il y a de la place à {dit}.",
    )


# --------------------------------------------------------------------------- #
# reserver
# --------------------------------------------------------------------------- #


async def reserver(
    source: Source, etat: dict[str, Any], appelant: Appelant, *, jour: str | None = None, heure: str | None = None, personnes: int | None = None,
    prenom: str | None = None, telephone: str | None = None, note: str | None = None, confirmer: bool = False,
) -> Resultat:
    """Conduit une réservation jusqu'à son enregistrement, UN manque à la fois : personnes, jour, heure, nom, numéro (jamais redemandé quand il
    s'affiche), puis la RELECTURE. L'enregistrement n'a lieu que sur ``confirmer`` après une relecture valide ; la place est revérifiée par la
    source. Tout ce qui a été dit est gardé d'un appel du geste au suivant."""
    b = etat.setdefault("brouillon", {})
    if isinstance(personnes, int) and not isinstance(personnes, bool):
        b["personnes"] = personnes
    if prenom and prenom.strip():
        b["prenom"] = " ".join(prenom.split())[:60]
    if note and note.strip():
        b["note"] = note.strip()[:NOTE_MAX]
    if jour:
        b["jour"] = jour
    if heure:
        b["heure"] = heure
    if telephone:
        b["telephone_dit"] = telephone
    if not isinstance(b.get("personnes"), int) or b["personnes"] < 1:
        return _r("INCOMPLETE", {}, "Pour combien de personnes ?", "personnes")
    if not b.get("jour"):
        return _r("INCOMPLETE", {}, "Pour quel jour ?", "jour")
    resolu = await source.resoudre_une_date(b["jour"], b.get("heure"))
    if resolu.statut != "RETENU":
        if resolu.statut in ("AMBIGU", "INTROUVABLE"):
            b.pop("jour", None)
        if resolu.statut == "ARGUMENT_INVALIDE":
            b.pop("heure", None)
        return resolu
    debut = datetime.fromisoformat(resolu.faits["heure_voulue"])
    quand_dit = f"{resolu.faits['jour_dit']} à {resolu.faits['heure_dite']}"
    if not b.get("prenom"):
        return _r("INCOMPLETE", {}, "À quel nom je mets la réservation ?", "prenom")
    numero = b.get("telephone_dit") or appelant.telephone_affiche
    if not numero:
        return _r("INCOMPLETE", {}, "Quel est votre numéro de téléphone ?", "telephone")
    numero_e164 = _vers_e164(numero)
    if numero_e164 is None:
        b.pop("telephone_dit", None)
        return _r("ARGUMENT_INVALIDE", {}, "Je n'ai pas bien compris le numéro : vous pouvez le redire ?", "telephone")
    # le créneau demandé est-il libre ? sinon les plus proches, jamais un créneau inventé
    libres = await source.disponibilites(debut.date(), b["personnes"])
    if libres.statut != "OK":
        return libres
    creneaux = libres.faits.get("creneaux") or []
    if not any(c["debut"] == debut for c in creneaux):
        if not creneaux:
            return _r("REFUSEE", {"raison": "autre", "detail": "complet", "propositions": []}, "Nous sommes complets ce jour-là.")
        choisis, dit = _creneaux_dits(creneaux, debut)
        return _r(
            "REFUSEE", {"raison": "autre", "detail": "complet", "propositions": [{"debut": c["debut"], "heure_dite": _heure_dite(c["debut"])} for c in choisis]},
            f"Nous ne pouvons pas à cette heure-là. Je peux vous proposer {dit}.",
        )
    empreinte = _empreinte(b["personnes"], debut.isoformat(), b["prenom"], numero_e164, b.get("note"))
    relue = etat.get("lecture")
    if not (confirmer and relue and relue.get("empreinte") == empreinte):
        etat["lecture"] = {"empreinte": empreinte, "jeton": uuid.uuid4().hex}
        phrase = f"Je vous réserve pour {_personnes_dites(b['personnes'])}, {quand_dit}, au nom de {b['prenom']}. C'est bon ?"
        return _r(
            "INCOMPLETE", {"a_confirmer": True, "personnes": b["personnes"], "quand": quand_dit, "prenom": b["prenom"]}, phrase, "relecture",
        )
    r = await source.creer(
        {"debut": debut, "effectif": b["personnes"], "prenom": b["prenom"], "telephone": numero_e164, "note": b.get("note"), "appel_id": appelant.appel_id}
    )
    if r.statut in ("ENREGISTREE", "DEJA_FAIT"):
        etat["derniere"] = r.faits.get("numero")
        etat.pop("brouillon", None)
        etat.pop("lecture", None)
    return r


def _vers_e164(brut: str) -> str | None:
    from api.schemas.apres_appel import numero_e164

    return numero_e164(brut)


# --------------------------------------------------------------------------- #
# retrouver, modifier, annuler
# --------------------------------------------------------------------------- #


async def _la_reservation(source: Source, appelant: Appelant, reference: str | None, jour: str | None = None, prenom: str | None = None) -> tuple[dict | None, Resultat | None]:
    """La réservation DE CET appelant : par numéro de réservation, sinon par le numéro qui s'affiche. Plusieurs : on demande laquelle (jamais choisie
    au hasard) ; aucune : le refus fermé."""
    if reference:
        trouve = await source.retrouver(numero=reference)
    elif prenom and jour:
        resolu = await source.resoudre_une_date(jour, None)
        le_jour = _jour_de(resolu) if resolu.statut in ("RETENU", "INCOMPLETE") else None
        if le_jour is None:
            return None, resolu
        trouve = await source.retrouver(prenom=prenom, jour=le_jour)
    elif appelant.telephone_affiche:
        trouve = await source.retrouver(telephone=appelant.telephone_affiche)
    else:
        return None, _r("INCOMPLETE", {}, "Sous quel nom, et pour quel jour ?", "reference")
    if trouve.statut != "OK":
        return None, _r("INTROUVABLE", {}, "Je ne trouve pas de réservation à venir.")
    liste = trouve.faits.get("reservations") or []
    if len(liste) > 1:
        dites = [r["quand_dit"] for r in liste]
        return None, _r(
            "AMBIGU", {"candidats": [{"numero": r["numero"], "quand_dit": r["quand_dit"], "effectif": r["effectif"]} for r in liste]},
            "Vous en avez plusieurs : " + liste_dite(dites) + ". Laquelle ?", "reference",
        )
    return liste[0], None


async def retrouver(source: Source, etat: dict[str, Any], appelant: Appelant, *, reference: str | None = None, jour: str | None = None, prenom: str | None = None) -> Resultat:
    """Dit où en est la réservation de l'appelant (statut lu dans le classeur, jamais deviné)."""
    r, refus = await _la_reservation(source, appelant, reference, jour, prenom)
    if refus is not None:
        return refus
    return _r(
        "OK", {"reservation": {k: r[k] for k in ("numero", "quand_dit", "effectif", "prenom", "statut")}},
        f"Vous avez une réservation {r['quand_dit']} pour {_personnes_dites(r['effectif'])}.",
    )


async def modifier(
    source: Source, etat: dict[str, Any], appelant: Appelant, *, reference: str | None = None, jour: str | None = None, heure: str | None = None,
    personnes: int | None = None, prenom: str | None = None, note: str | None = None, confirmer: bool = False,
) -> Resultat:
    """Change l'heure, l'effectif, le nom ou la note d'UNE réservation de l'appelant, après relecture confirmée. La source revérifie la place
    (les unités de la réservation comptent comme libres). Seul le jour sans l'heure : l'heure est redemandée."""
    r, refus = await _la_reservation(source, appelant, reference)
    if refus is not None:
        return refus
    changements: dict[str, Any] = {}
    dit: list[str] = []
    if jour or heure:
        if jour and not heure:
            return _r("INCOMPLETE", {}, "À quelle heure ?", "heure")
        resolu = await source.resoudre_une_date(jour or r["jour_dit"], heure)
        if resolu.statut != "RETENU":
            return resolu
        changements["debut"] = datetime.fromisoformat(resolu.faits["heure_voulue"])
        dit.append(f"{resolu.faits['jour_dit']} à {resolu.faits['heure_dite']}")
    if isinstance(personnes, int) and not isinstance(personnes, bool):
        changements["effectif"] = personnes
        dit.append(_personnes_dites(personnes))
    if prenom and prenom.strip():
        changements["prenom"] = " ".join(prenom.split())[:60]
        dit.append(f"au nom de {changements['prenom']}")
    if note and note.strip():
        changements["note"] = note.strip()[:NOTE_MAX]
        dit.append("avec votre note")
    if not changements:
        return _r("INCOMPLETE", {"reservation": r["quand_dit"]}, "Qu'est-ce que je change : l'heure, le nombre de personnes ?", "changement")
    empreinte = _empreinte(r["numero"], {k: str(v) for k, v in changements.items()})
    relue = etat.get("lecture_modification")
    if not (confirmer and relue and relue.get("empreinte") == empreinte):
        etat["lecture_modification"] = {"empreinte": empreinte, "jeton": uuid.uuid4().hex}
        return _r("INCOMPLETE", {"a_confirmer": True, "reservation": r["numero"]}, f"Je change votre réservation : {liste_dite(dit).replace(' ou ', ' et ')}. C'est bon ?", "relecture")
    ecrit = await source.modifier(r["numero"], changements)
    if ecrit.statut in ("OK", "DEJA_FAIT"):
        etat.pop("lecture_modification", None)
    return ecrit


async def annuler(source: Source, etat: dict[str, Any], appelant: Appelant, *, reference: str | None = None, confirmer: bool = False) -> Resultat:
    """Annule UNE réservation de l'appelant EN DEUX TEMPS : d'abord on la lui dit et on demande, puis seulement sur son « oui » ``confirmer``
    (pour CETTE réservation) on annule. Un second « oui » rend ``DEJA_FAIT`` ; une réservation passée est figée."""
    r, refus = await _la_reservation(source, appelant, reference)
    if refus is not None:
        return refus
    if not (confirmer and etat.get("annulation") == r["numero"]):
        etat["annulation"] = r["numero"]
        return _r(
            "INCOMPLETE", {"a_confirmer": True, "reservation": r["numero"]}, f"Vous voulez annuler la réservation {r['quand_dit']} pour {_personnes_dites(r['effectif'])} ?", "confirmation",
        )
    fait = await source.annuler(r["numero"])
    if fait.statut in ("OK", "DEJA_FAIT"):
        etat.pop("annulation", None)
    return fait
