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

from api.services.actions_communes import conversation as CONV
from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from api.services.actions_communes import journal_du_dit as J
from api.db.bases_clients import dates_futures
from api.services.actions_communes.resultat import Resultat, avec_numero_affiche, avec_numeros_retenus
from api.services.mots_dits import heure_en_lettres, liste_dite, nombre_en_lettres
from api.services.phrases.catalogue import MOTIFS as MOTIFS_DES_PHRASES, NUMERO_AFFICHE_GARDE
from api.services.reservation import textes_de_secours as TS
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


def reservation_commencee(etat: dict[str, Any]) -> bool:
    """Un morceau de la réservation est dit (personnes, jour, heure, nom) et rien n'est enregistré ni retrouvé : une réservation commencée."""
    b = etat.get("brouillon") or {}
    return bool(any(b.get(k) for k in ("personnes", "jour", "heure", "prenom")) and not etat.get("derniere") and not etat.get("cible"))


def reservation_existante(etat: dict[str, Any]) -> bool:
    """Une réservation enregistrée dans l'appel ou retrouvée, pas annulée."""
    cible = etat.get("cible")
    return bool(cible and cible not in (etat.get("annulees") or []))


def reservation_de_l_appel(etat: dict[str, Any]) -> str | None:
    """R01 : le numéro de la réservation enregistrée dans CET appel (une seule par appel, E30), annulée ou non ; ``None`` sinon."""
    return etat.get("derniere") or None


def _une_seule_par_appel_annulee(numero: str, **demande: Any) -> Resultat:
    """Pierre F (E30, la décision reste : une seule réservation par appel) : « j'annule samedi et je réserve dimanche » n'est plus une impasse muette ; ``demande`` : ce que la personne
    demande de nouveau (jour, heure, personnes, prénom), donné au modèle et écrit pour l'équipe par la porte (lot 7b, reprise 2 : la promesse est tenue)."""
    faits = {"reservation": numero, "raison": "deja_une_reservation_dans_cet_appel", "deja_annulee": True}
    if any(v not in (None, "") for v in demande.values()):
        faits["demande"] = {k: v for k, v in demande.items() if v not in (None, "")}
    return _r("DEJA_FAIT", faits, "")  # le texte est dit par la porte (la porte range le refus en fait : ``transmise_a_l_equipe``)


def _r(statut: str, faits: dict | None = None, suggestion: str = "", manque: str | None = None) -> Resultat:
    return Resultat(statut, faits or {}, suggestion, manque)


def _empreinte(*morceaux: Any) -> str:
    return hashlib.sha256(json.dumps(morceaux, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _personnes_dites(n: int) -> str:
    return f"{nombre_en_lettres(n)} personne" + ("s" if n > 1 else "")


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


async def _groupe_refuse(source: Source, personnes: int) -> Resultat | None:
    """Le plus grand groupe pris, dit dès que le nombre est dit (avant le jour et l'heure) ; une source qui ne le sait pas ne refuse rien."""
    verifier = getattr(source, "groupe_trop_grand", None)
    return await verifier(personnes) if verifier is not None else None


def doute_leve_sur(brouillon: dict[str, Any], resolu: Resultat) -> None:
    """R02 : un doute sur le jour ou l'heure ne retire que la valeur visée (``resolu.manque``), jamais l'autre : « samedi » reste quand « sept heures »
    est ambigu. Une heure passée ne retire que l'heure."""
    champ = resolu.manque if resolu.manque in ("jour", "heure") else ("heure" if resolu.statut == "ARGUMENT_INVALIDE" else None)
    if champ is not None and resolu.statut in ("AMBIGU", "INTROUVABLE", "ARGUMENT_INVALIDE"):
        brouillon.pop(champ, None)


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
    """Les créneaux libres d'un jour pour un nombre de personnes. Avec ``heure``, les trois plus proches de cette heure ; sans, le premier de chaque heure.
    Rien n'est réservé. Complet : ``faits.complet`` vrai, aucun créneau inventé."""
    if not isinstance(personnes, int) or isinstance(personnes, bool) or personnes < 1:
        return _r("INCOMPLETE", {}, TS.combien_de_personnes({}), "personnes")
    if (refus := await _groupe_refuse(source, personnes)) is not None:
        return refus
    if not jour:
        return _r("INCOMPLETE", {}, TS.quel_jour({}), "jour")
    dates_futures.retenir_le_moment(etat, jour)
    resolu = await source.resoudre_une_date(jour, dates_futures.heure_avec_le_moment(etat, heure))
    if resolu.statut not in ("RETENU", "INCOMPLETE") or (resolu.statut == "INCOMPLETE" and resolu.manque != "heure"):
        return resolu
    le_jour = _jour_de(resolu)
    if le_jour is None:
        return _r("INTROUVABLE", {}, TS.quel_jour({}), "jour")
    libres = await source.disponibilites(le_jour, personnes)
    if libres.statut != "OK":
        return libres
    creneaux = libres.faits.get("creneaux") or []
    if not creneaux:
        return _r("OK", {"jour": le_jour.isoformat(), "creneaux": [], "complet": True}, TS.complets_ce_jour({}))
    partie = _partie_du_jour(jour, heure) if "heure_voulue" not in resolu.faits else None
    if partie is not None:
        # « samedi soir » : seuls les créneaux de ce moment-là sont proposés, jamais ceux du midi.
        mot, (de, a) = partie
        dans_la_partie = [c for c in creneaux if de <= c["debut"].hour < a]
        if not dans_la_partie:
            faits = {"jour": le_jour.isoformat(), "creneaux": [], "complet": True, "partie": mot}
            return _r("OK", faits, TS.complets_ce_jour(faits))
        creneaux = dans_la_partie
    souhaite = datetime.fromisoformat(resolu.faits["heure_voulue"]) if resolu.faits.get("heure_voulue") else None
    choisis, dit = _creneaux_dits(creneaux, souhaite)
    faits = {"jour": le_jour.isoformat(), "creneaux": [{"debut": c["debut"], "heure_dite": _heure_dite(c["debut"])} for c in choisis], "complet": False}
    return _r("OK", faits, TS.il_y_a_de_la_place(faits))


# --------------------------------------------------------------------------- #
# reserver
# --------------------------------------------------------------------------- #


QUESTION_NUMERO_AFFICHE = MOTIFS_DES_PHRASES[NUMERO_AFFICHE_GARDE].variantes_defaut[0]


async def reserver(
    source: Source, etat: dict[str, Any], appelant: Appelant, *, question_numero_affiche: str | None = QUESTION_NUMERO_AFFICHE, **gestes: Any
) -> Resultat:
    """Le geste, puis le numéro dicté et RETENU dans cet appel dit par le code (même mécanisme que la commande : ``avec_numeros_retenus``). Le numéro
    qui s'affiche n'est jamais relu ; un numéro déjà dit n'est pas redit tant qu'il ne change pas.

    M98 : quand le numéro gardé est celui qui s'affiche, la relecture finit par UNE question qui le dit (``question_numero_affiche``, phrase du
    code réglable ; vide : « C'est bon ? ») et il est porté dans les faits (``numero_affiche_dit``), jamais ajouté à la phrase."""
    deja = reservation_de_l_appel(etat)
    if deja:
        # R01 : « on sera cinq » après l'enregistrement ne crée jamais une seconde table : un changement passe par modifier
        if deja in (etat.get("annulees") or []):
            return _une_seule_par_appel_annulee(deja, jour=gestes.get("jour"), heure=gestes.get("heure"), personnes=gestes.get("personnes"), prenom=gestes.get("prenom"))
        return _r("DEJA_FAIT", {"reservation": deja, "raison": "deja_une_reservation_dans_cet_appel"}, TS.deja_une_reservation_dans_cet_appel({}), "modification")
    r = await _reserver(source, etat, appelant, question_numero_affiche=question_numero_affiche, **gestes)
    b = etat.get("brouillon") or {}
    if appelant.telephone_affiche and _vers_e164(b.get("telephone_dit") or appelant.telephone_affiche) == appelant.telephone_affiche:
        r = avec_numero_affiche(r, appelant.telephone_affiche)
    numero = _vers_e164(gestes["telephone"]) if gestes.get("telephone") else None
    if r.statut in ("ENREGISTREE", "DEJA_FAIT") or not numero or b.get("telephone_dit") != gestes.get("telephone"):
        return r
    if numero == appelant.telephone_affiche or b.get("numero_dit") == numero:
        return r
    b["numero_dit"] = numero
    return avec_numeros_retenus(r, numero)


async def _reserver(
    source: Source, etat: dict[str, Any], appelant: Appelant, *, jour: str | None = None, heure: str | None = None, personnes: int | None = None,
    prenom: str | None = None, telephone: str | None = None, note: str | None = None, confirmer: bool = False,
    question_numero_affiche: str | None = QUESTION_NUMERO_AFFICHE,
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
        b.pop("jour_dit", None)
    if heure:
        b["heure"] = heure
    if jour:
        dates_futures.retenir_le_moment(etat, jour)  # M85 : « vendredi soir » garde le soir pour « huit heures et demie »
    if telephone:
        b["telephone_dit"] = telephone
    if not isinstance(b.get("personnes"), int) or b["personnes"] < 1:
        return _r("INCOMPLETE", {}, TS.combien_de_personnes({}), "personnes")
    if (refus := await _groupe_refuse(source, b["personnes"])) is not None:
        return refus
    if not b.get("jour"):
        return _r("INCOMPLETE", {}, TS.quel_jour({}), "jour")
    resolu = await source.resoudre_une_date(b["jour"], dates_futures.heure_avec_le_moment(etat, b.get("heure")))
    if resolu.faits.get("jour_dit"):
        b["jour_dit"] = resolu.faits["jour_dit"]  # l'état le montre sans requête (``etat_pour_le_modele``)
    else:
        b.pop("jour_dit", None)
    if resolu.statut != "RETENU":
        doute_leve_sur(b, resolu)
        return resolu
    debut = datetime.fromisoformat(resolu.faits["heure_voulue"])
    quand_dit = f"{resolu.faits['jour_dit']} à {resolu.faits['heure_dite']}"
    if not b.get("prenom"):
        return _r("INCOMPLETE", {}, TS.a_quel_nom_je_mets_la_reservation({}), "prenom")
    numero = b.get("telephone_dit") or appelant.telephone_affiche
    if not numero:
        return _r("INCOMPLETE", {}, TS.quel_numero({}), "telephone")
    numero_e164 = _vers_e164(numero)
    if numero_e164 is None:
        b.pop("telephone_dit", None)
        return _r("ARGUMENT_INVALIDE", {"numero_illisible": True}, TS.numero_illisible({}), "telephone")
    # le créneau demandé est-il libre ? sinon les plus proches, jamais un créneau inventé
    libres = await source.disponibilites(debut.date(), b["personnes"])
    if libres.statut != "OK":
        return libres
    creneaux = libres.faits.get("creneaux") or []
    if not any(c["debut"] == debut for c in creneaux):
        if not creneaux:
            faits = {"raison": "autre", "detail": "complet", "propositions": []}
            return _r("REFUSEE", faits, TS.refus_complet_du_moteur(faits))
        choisis, _ = _creneaux_dits(creneaux, debut)
        faits = {"raison": "autre", "detail": "complet", "propositions": [{"debut": c["debut"], "heure_dite": _heure_dite(c["debut"])} for c in choisis]}
        return _r("REFUSEE", faits, TS.refus_complet_du_moteur(faits))
    empreinte = _empreinte(b["personnes"], debut.isoformat(), b["prenom"], numero_e164, b.get("note"))
    relue = etat.get("lecture")
    if not confirmer and relue and relue.get("empreinte") == empreinte:
        # M106/M107 : ``reserver`` rappelé sans rien de nouveau pendant la relecture (une question de la personne) : rien n'est redit, la parole
        # revient au modèle avec les faits pour qu'il lui réponde ; la relecture reste valable et un « oui » ensuite enregistre.
        return _r(
            "INCOMPLETE", {"a_confirmer": True, "relecture_deja_dite": True, "rien_de_nouveau": True, "personnes": b["personnes"], "quand": quand_dit,
                           "prenom": b["prenom"]}, "", "reponse_a_la_relecture",
        )
    if not (confirmer and relue and relue.get("empreinte") == empreinte):
        etat["lecture"] = {"empreinte": empreinte, "jeton": uuid.uuid4().hex}
        question = (question_numero_affiche or "").strip() if numero_e164 == appelant.telephone_affiche else ""
        phrase = PHRASES_DITES.relecture_de_la_reservation(personnes=_personnes_dites(b["personnes"]), quand=quand_dit, prenom=b["prenom"], question=question)
        return _r(
            "INCOMPLETE", {"a_confirmer": True, "personnes": b["personnes"], "quand": quand_dit, "prenom": b["prenom"]}, phrase, "relecture",
        )
    r = await source.creer(
        {"debut": debut, "personnes": b["personnes"], "prenom": b["prenom"], "telephone": numero_e164, "note": b.get("note"), "appel_id": appelant.appel_id}
    )
    if r.statut in ("ENREGISTREE", "DEJA_FAIT"):
        etat["derniere"] = etat["cible"] = r.faits.get("numero")
        etat.pop("brouillon", None)
        etat.pop("lecture", None)
        etat.pop(dates_futures.CLE_DU_MOMENT, None)
    return r


def _vers_e164(brut: str) -> str | None:
    from api.schemas.apres_appel import numero_e164

    return numero_e164(brut)


# --------------------------------------------------------------------------- #
# retrouver, désigner, modifier, annuler
# --------------------------------------------------------------------------- #


def _resume(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r.get(k) for k in ("numero", "quand_dit", "personnes", "prenom", "statut")}


async def _la_reservation(source: Source, etat: dict[str, Any]) -> tuple[dict | None, Resultat | None]:
    """La réservation VISÉE (``etat["cible"]`` : celle de l'appel, ou retrouvée) relue dans le classeur par son numéro, que le code a rangé : jamais un
    numéro attendu du modèle (B08). Aucune visée : on demande laquelle, par le nom et le jour."""
    numero = etat.get("cible")
    if not numero:
        return None, _r("INCOMPLETE", {}, TS.sous_quel_nom_et_quel_jour({}), "nom_et_jour_de_la_reservation")
    trouve = await source.retrouver(numero=numero)
    liste = (trouve.faits.get("reservations") or []) if trouve.statut == "OK" else []
    if not liste:
        return None, _r("INTROUVABLE", {}, TS.aucune_reservation_a_venir({}))
    return liste[0], None


RECHERCHE_SANS_RESULTAT = "recherche_sans_resultat"  # B6 : la clé du journal pour une recherche de réservation vaine


async def retrouver_une_reservation(source: Source, etat: dict[str, Any], appelant: Appelant, *, nom: str | None = None, jour: str | None = None) -> Resultat:
    """R05 : retrouver une réservation d'un appel précédent par le nom et le jour dits, sinon par le numéro qui s'affiche (le jour dit la filtre quand
    elle existe ce jour-là). Une seule : elle devient la réservation visée. Plusieurs : ``AMBIGU`` avec les candidats, que la porte numérote et que
    ses mots désignent (``choisir_le_candidat``). Le nom dit ici sert à retrouver, jamais à changer le nom de la réservation."""
    etat["recherche"] = True
    le_jour = None
    jours_possibles: list[date] = []
    if jour:
        resolu = await source.resoudre_une_date(jour, None)
        le_jour = _jour_de(resolu) if resolu.statut in ("RETENU", "INCOMPLETE") else None
        if le_jour is None:
            candidats = resolu.faits.get("candidats") if resolu.statut == "AMBIGU" else None
            if isinstance(candidats, list) and candidats and (nom or appelant.telephone_affiche):
                # Un jour ambigu (« jeudi » dit un jeudi) ne se redemande pas : on cherche une réservation à venir CHAQUE jour possible, et les données décident.
                jours_possibles = [date.fromisoformat(c["jour"]) for c in candidats if isinstance(c, dict) and c.get("jour")]
            if not jours_possibles:
                if resolu.statut == "AMBIGU":   # un doute sur le JOUR n'est pas un choix entre des réservations : on redemande le jour
                    return _r("INCOMPLETE", {k: v for k, v in resolu.faits.items() if k != "candidats"}, resolu.suggestion, "jour")
                return resolu
    par_le_nom = bool(nom and (le_jour or jours_possibles))
    if not par_le_nom and not appelant.telephone_affiche:
        return _r("INCOMPLETE", {"raison": "numero_masque"}, TS.sous_quel_nom_et_quel_jour({}), "nom_et_jour_de_la_reservation")
    liste: list[dict[str, Any]] = []
    for un_jour in (jours_possibles or [le_jour]):
        if par_le_nom:
            trouve = await source.retrouver(prenom=nom, jour=un_jour)
        else:
            trouve = await source.retrouver(telephone=appelant.telephone_affiche, **({"jour": un_jour} if un_jour else {}))
            if trouve.statut != "OK" and un_jour:
                trouve = await source.retrouver(telephone=appelant.telephone_affiche)  # le jour dit ne la filtre que s'il en trouve une ce jour-là
        if trouve.statut == "OK":
            liste += trouve.faits.get("reservations") or []
    if not liste:
        J.noter(etat, RECHERCHE_SANS_RESULTAT)  # P2 (B6, rustine 38 : au journal de ce qui est dit) : la recherche ne se redemande pas sans fin
        return _r("INTROUVABLE", {}, TS.aucune_reservation_a_venir({}))
    etat["recherche"] = False
    if len(liste) == 1:
        etat["cible"] = liste[0]["numero"]
        faits = {"reservation": _resume(liste[0])}
        return _r("OK", faits, TS.une_reservation_trouvee(faits))
    dites = [f"{r['quand_dit']}, pour {_personnes_dites(r['personnes'])}" for r in liste]
    faits = {"candidats": [{**_resume(r), "debut": r.get("debut"), "dit": d} for r, d in zip(liste, dites)]}
    return _r("AMBIGU", faits, TS.plusieurs_a_choisir(faits), "reservation")


_RANGS = (("premiere", "premier", "1"), ("deuxieme", "seconde", "second", "2"), ("troisieme", "3"))
_MOTS_VIDES = {"la", "le", "de", "du", "celle", "celui", "a", "pour", "personnes", "heures", "heure", "reservation", "novembre"}


def choisir_le_candidat(candidats: list[dict[str, Any]], valeurs: list[str] | None) -> list[dict[str, Any]]:
    """B08, R04 : les candidats que ses MOTS désignent (le jour, l'heure, le nom, le nombre de personnes, ou le rang dans l'ordre où le code les a dits :
    « la deuxième », « la dernière »), jamais un numéro de réservation. Valeurs seulement, jamais l'intention : un seul gagnant est un choix, zéro ou
    plusieurs est un doute que le code redemande (``choix_non_compris``). Recopie de ``banc-b13/reservation_b13.py`` ``_repondre`` (type ``choix``)."""
    from api.services.actions_communes.forme import norm

    mots = set(norm(" ".join(str(v) for v in (valeurs or []))).split()) - _MOTS_VIDES
    scores = []
    for c in candidats:
        debut = c.get("debut")
        if isinstance(debut, str):   # lot 20 (n5) : la question enregistrée garde l'heure écrite en ISO
            try:
                debut = datetime.fromisoformat(debut)
            except ValueError:
                debut = None
        jetons = set(norm(f"{c.get('quand_dit', '')} {c.get('prenom') or ''} {_personnes_dites(c['personnes'])} {c['personnes']}").split())
        if isinstance(debut, datetime):
            jetons |= {str(debut.day), f"{debut.hour}h"}
        scores.append([len(mots & jetons), c])
    for rang, mots_du_rang in enumerate(_RANGS):
        if mots & set(mots_du_rang) and rang < len(scores):
            scores[rang][0] += 5
    if mots & {"derniere"} and scores:
        scores[-1][0] += 5
    meilleur = max((s for s, _ in scores), default=0)
    return [c for s, c in scores if s == meilleur and s > 0]


def renoncer(etat: dict[str, Any]) -> Resultat:
    """Elle ne veut plus de la réservation commencée : rien n'est enregistré, rien n'est gardé (banc : ``annuler_la_reservation``)."""
    for cle in ("brouillon", "lecture", "modification", "lecture_modification", "annulation", dates_futures.CLE_DU_MOMENT):
        etat.pop(cle, None)
    CONV.poser_question(etat, None)
    return _r("OK", {"rien_enregistre": True})


async def modifier(
    source: Source, etat: dict[str, Any], appelant: Appelant, *, jour: str | None = None, heure: str | None = None, personnes: int | None = None,
    prenom: str | None = None, note: str | None = None, confirmer: bool = False,
) -> Resultat:
    """Change l'heure, le nombre de personnes, le nom ou la note de la réservation VISÉE, après relecture confirmée. R03 : ce qui est dit est gardé dans
    ``etat["modification"]`` d'une fiche à l'autre (le jour dit sans l'heure reste ; l'heure seule se résout sur le jour gardé, jamais sur l'ancien).
    La source revérifie la place (les unités de la réservation comptent comme libres). Seul le jour sans l'heure : l'heure est redemandée."""
    numero = etat.get("cible")
    if numero and numero in (etat.get("annulees") or []):
        if numero == reservation_de_l_appel(etat):  # ce qu'elle dit après avoir annulé la réservation de CET appel est une nouvelle demande, pas un changement (E30)
            return _une_seule_par_appel_annulee(numero, jour=jour, heure=heure, personnes=personnes, prenom=prenom)
        return _r("DEJA_FAIT", {"deja_annulee": True}, TS.deja_annulee({}))
    r, refus = await _la_reservation(source, etat)
    if refus is not None:
        return refus
    m = etat.setdefault("modification", {})
    if jour and jour.strip():
        m["jour"] = jour.strip()
    if heure and heure.strip():
        m["heure"] = heure.strip()
    if isinstance(personnes, int) and not isinstance(personnes, bool):
        m["personnes"] = personnes
    if prenom and prenom.strip():
        m["prenom"] = " ".join(prenom.split())[:60]
    if note and note.strip():
        m["note"] = note.strip()[:NOTE_MAX]
    changements: dict[str, Any] = {}
    dit: list[str] = []
    if m.get("jour"):
        voulu = await source.resoudre_une_date(m["jour"], None)
        if voulu.statut not in ("RETENU", "INCOMPLETE"):
            doute_leve_sur(m, voulu)
            return voulu
        if _jour_de(voulu) == _jour_de(await source.resoudre_une_date(r["jour_dit"], None)):
            m.pop("jour")  # le jour redit tel qu'il est n'est pas un changement
    if m.get("jour") and not m.get("heure"):
        return _r("INCOMPLETE", {"reservation": r["quand_dit"]}, TS.quelle_heure({}), "heure")
    if m.get("heure"):
        dates_futures.retenir_le_moment(etat, m.get("jour"))
        resolu = await source.resoudre_une_date(m.get("jour") or r["jour_dit"], dates_futures.heure_avec_le_moment(etat, m["heure"]))
        if resolu.statut != "RETENU":
            doute_leve_sur(m, resolu)
            return resolu
        changements["debut"] = datetime.fromisoformat(resolu.faits["heure_voulue"])
        dit.append(f"{resolu.faits['jour_dit']} à {resolu.faits['heure_dite']}")
    # M103 : seul ce qui CHANGE est pris et relu ; ce que le modèle renvoie tel quel (« au nom de Martin », déjà Martin) ne se redit pas.
    if changements.get("debut") is not None and r.get("debut") == changements["debut"]:
        changements.pop("debut")
        dit.clear()
    if isinstance(m.get("personnes"), int) and m["personnes"] != r.get("personnes"):
        changements["personnes"] = m["personnes"]
        dit.append(_personnes_dites(m["personnes"]))
    if m.get("prenom") and m["prenom"].casefold() != (r.get("prenom") or "").strip().casefold():
        changements["prenom"] = m["prenom"]
        dit.append(f"au nom de {changements['prenom']}")
    if m.get("note") and m["note"] != (r.get("note") or "").strip():
        changements["note"] = m["note"]
        dit.append("avec votre note")
    if not changements and m:
        etat.pop("modification", None)
        faits = {"reservation": r["numero"], "inchangee": True, "quand_dit": r["quand_dit"], "personnes": r["personnes"]}
        return _r("DEJA_FAIT", faits, TS.rien_ne_change(faits))
    if not changements:
        return _r("INCOMPLETE", {"reservation": r["quand_dit"]}, TS.que_change_je({}), "changement")
    empreinte = _empreinte(r["numero"], {k: str(v) for k, v in changements.items()})
    relue = etat.get("lecture_modification")
    if not (confirmer and relue and relue.get("empreinte") == empreinte):
        etat["lecture_modification"] = {"empreinte": empreinte, "jeton": uuid.uuid4().hex}
        return _r("INCOMPLETE", {"a_confirmer": True, "reservation": r["numero"]}, PHRASES_DITES.relecture_du_changement(liste_dite(dit).replace(" ou ", " et ")), "relecture")
    ecrit = await source.modifier(r["numero"], changements)
    if ecrit.statut in ("OK", "DEJA_FAIT"):
        etat.pop("lecture_modification", None)
        etat.pop("modification", None)
    return ecrit


async def annuler(source: Source, etat: dict[str, Any], appelant: Appelant, *, confirmer: bool = False) -> Resultat:
    """Annule la réservation VISÉE EN DEUX TEMPS : d'abord on la lui dit et on demande, puis seulement sur son « oui » ``confirmer`` (pour CETTE
    réservation) on annule. Un second « oui » rend ``DEJA_FAIT`` ; une réservation passée est figée."""
    numero = etat.get("cible")
    if numero and numero in (etat.get("annulees") or []):
        return _r("DEJA_FAIT", {"deja_annulee": True}, TS.deja_annulee({}))
    r, refus = await _la_reservation(source, etat)
    if refus is not None:
        return refus
    if not (confirmer and etat.get("annulation") == r["numero"]):
        etat["annulation"] = r["numero"]
        # B5 (audit des textes § 2.5) : avant d'annuler, le déplacement est proposé par la question du code (règle du métier, plus par le texte).
        return _r(
            "INCOMPLETE", {"a_confirmer": True, "reservation": r["numero"]},
            PHRASES_DITES.annulation_de_la_reservation(quand=r["quand_dit"], personnes=_personnes_dites(r["personnes"])), "confirmation",
        )
    fait = await source.annuler(r["numero"])
    if fait.statut in ("OK", "DEJA_FAIT"):
        etat.pop("annulation", None)
        etat.setdefault("annulees", []).append(r["numero"])
    return fait
