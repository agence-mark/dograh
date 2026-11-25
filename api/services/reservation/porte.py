"""[.mark] La porte d'entrée de la réservation (chantier Partie 1, lot 7 ; E20, D18) : ce que le connecteur ``reservation`` exécute.

- ``lire`` : la lecture, qui n'écrit jamais rien (``services/reservation/lire.py``) ;
- ``fiche`` : la fiche à cases, exécutée case par case dans l'ordre du banc (``banc-b13/reservation_b13.py`` ``ReservationV6.fiche``), sur le MOTEUR de la
  réservation (``moteur.py`` : reserver, modifier, annuler, retrouver, avec leur relecture liée à l'empreinte) qui reste le moteur (D18).

Même forme que ``commande/porte.py`` : les barrières de la fiche entière (``actions_communes/barrieres.py``, aucune copie), l'idempotence, les valeurs
libres qu'elle n'a pas dites, puis les cases ; la porte traduit le retour du moteur en enveloppe (``actions_communes/enveloppe.py``) et numérote la
question (« Q-n ») que le modèle posera : ``recapitulatif``, ``recap_modif``, ``annulation``, ``choix``. C6 n° 8 et 9 (décision d'Evan 25/11 9 h 30) : les relectures
et les faits accomplis (réservée, changée, annulée) sont dits par le modèle d'après les faits, les personnes et l'heure exigées de sa phrase (P2) ; le code ne dit que la
question réglée du numéro après une relecture (``textes_du_code``). L'issue de l'appel est posée par l'opération qui la fait (C10).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
import time
import uuid
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.services.actions_communes import journal_du_dit as J
from api.db.bases_clients.horloge import horloge
from api.schemas.apres_appel import numero_e164
from api.services.actions_communes import issues as ISSUES
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_RESERVATION
from api.services.actions_communes import barrieres as B
from api.services.actions_communes import porte_commune as PC
from api.services.actions_communes.consignes import en_une_phrase
from api.schemas.workflow_configurations import DEFAULT_RESERVATION_BOUCLE_FOIS_AVANT_LA_SORTIE, DEFAULT_RESERVATION_FOIS_AVANT_LA_SORTIE
from api.services.actions_communes.seuil_de_sortie import CLE_RESERVATION, CLE_RESERVATION_BOUCLE, seuil_de_sortie
from api.services.actions_communes import registre_des_questions as RC
from api.services.actions_communes.arguments import en_json, lire_un_entier, lire_un_texte
from api.services.actions_communes.enveloppe import Enveloppe, Question
from api.services.actions_communes.idempotence import cle_d_idempotence, deja_executee
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE
from api.services.actions_communes.repli import poser_le_fait_bloquant
from api.services.actions_communes.resultat import (
    CLE_NUMERO_AFFICHE, CLE_NUMERO_RETENU, Resultat, avec_le_fait_du_numero_affiche, phrase_du_code, question_du_numero_affiche,
)
from api.services.phrases.catalogue import NUMERO_DICTE_RELU
from api.services.reservation import etat_pour_le_modele, moteur
from api.services.reservation import textes_de_secours as TS
from api.services.reservation import source as registre_des_sources
from api.services.reservation.lire import lire
from api.services.actions_communes import du as DU
from api.services.reservation.phrases_du_manque import valeur_du_manque
from api.services.restauration.mesures import mesures as mesures_du_module
from api.services.workflow.cases_selon_l_etat import CLE_DES_PAROLES, CLE_DIT_DANS_L_APPEL, CLE_DU_TOUR, cases_montrees

SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur``

# L'ordre d'exécution des cases (``ReservationV6.fiche``) : renoncer, retrouver, réponse, annuler une réservation enregistrée, puis les valeurs.
ORDRE_DES_CASES = ("annuler_la_reservation", "retrouver_une_reservation_enregistree", "reponse", "annuler_une_reservation_enregistree")
VALEURS = ("personnes", "jour", "heure", "nom", "telephone", "precision")
CASES_LIBRES = ("nom", "jour", "heure")  # les valeurs libres qu'elle doit avoir dites (D57) ; règle de valeur du banc (``valeurs_hors_paroles``)
CHOIX_NON_COMPRIS = "choix_non_compris"  # B6 : la clé du journal pour un choix de réservation non compris

TYPES_DE_QUESTION = {"reserver": "recapitulatif", "modifier": "recap_modif", "annuler": "annulation"}
# C6 n° 8 (décision d'Evan 25/11 9 h 30) : le modèle dit les relectures avec ses mots d'après les faits ; ces valeurs sont exigées de sa phrase (P2), sinon il est relancé une fois.
VALEURS_EXIGEES = ("personnes", "heure")
A_FAIRE_DE_LA_RELECTURE = "relis-lui la réservation avec tes mots d'après les faits du retour (le nombre de personnes, le jour et l'heure, le nom)"
SANS_QUESTION = "sans question : le code pose la question juste après ta phrase"
AVEC_QUESTION = "puis demande-lui si c'est bon, en une question"
A_FAIRE_DU_CHANGEMENT = "dis-lui avec tes mots ce qui change dans sa réservation d'après les faits du retour (ce_qui_change), puis demande-lui si c'est bon, en une question"
A_FAIRE_DU_FAIT_ACCOMPLI = {  # C6 n° 9 : le modèle dit le fait accompli d'après les faits du retour (le code n'en dit plus la phrase)
    "reserver": "dis-lui avec tes mots que sa réservation est enregistrée, avec le jour, l'heure et le nombre de personnes des faits",
    "modifier": "dis-lui avec tes mots que sa réservation est changée, avec le jour, l'heure et le nombre de personnes des faits",
    "annuler": "dis-lui avec tes mots que sa réservation est annulée",
}
A_FAIRE_DE_L_ANNULATION = ("demande-lui avec tes mots si elle veut vraiment annuler sa réservation, en disant le jour, l'heure et le nombre de personnes des faits, et propose-lui "
                           "de la déplacer plutôt, en une question ; rien n'est annulé avant son « oui »")




def _objet_de_la_question(q: dict[str, Any], e: dict[str, Any], naitre: bool) -> str:
    """L'objet d'une question de réservation : un « laquelle ? » porte sur CES réservations-là (deux recherches, deux objets) ; les autres types n'ont qu'un objet."""
    if q.get("type") == "choix":
        return "choix:" + ",".join(str(c.get("numero")) for c in q.get("candidats") or [])
    return str(q.get("type"))


def _ferme(q: dict[str, Any], sens: str | None, r: Resultat, valeurs: list[str] | None) -> bool:
    """Lot 7a (n° 7) : seul un choix non compris laisse « laquelle ? » posée, sous le même numéro ; toute autre réponse ferme sa question."""
    return not (q.get("type") == "choix" and r.statut == "REFUSEE" and (r.faits or {}).get("detail") == "choix_non_compris")


TABLE = RC.Table(ordre=("choix", "recapitulatif", "recap_modif", "annulation"), condition=lambda e, q: True, objet_de_naissance=_objet_de_la_question,
                 ferme=_ferme)  # la réservation pose ce que son moteur rend


def _numerotee(q: dict[str, Any], e: dict[str, Any]) -> dict[str, Any]:
    """RC9 : la question naît (son objet est fixé) et prend le numéro attaché à son objet."""
    return {**q, "id": RC.numero(e, RC.nommer(TABLE, q, e)), "objet": q["objet"]}
MANQUES_DU_MODELE = {"prenom": "nom", "reference": "nom_et_jour_de_la_reservation"}   # les mots du classeur sont traduits à la source
RAISONS_DE_REFUS = {"complet": "complet_a_cette_heure"}  # le reste : le détail du classeur, tel quel (rangé « métier »)
GESTES_DE_LA_SOURCE = {"reserver": "reserver", "modifier": "modifier_reservation", "annuler": "annuler_reservation"}
STATUTS_ENREGISTRES = ("ENREGISTREE",)

ISSUES_DE_LA_RESERVATION = ("reservation_enregistree", "reservation_modifiee", "reservation_annulee", "reservation_abandonnee")
REGLAGE_DES_ISSUES = ISSUES.REGLAGE_DES_ISSUES
CLE_ISSUES_REGLEES = "reservation_issues_reglees"  # les codes réglés sur l'outil, gardés dans la fiche pour la fin de l'appel
CLE_MESURES_DU_CODE = "mesures_du_code"


def _schema_de_la_fiche(ctx: Any) -> dict[str, Any]:
    from api.services.integrations.connectors.actions.reservation import RESERVATION
    from api.services.integrations.connectors.outil import propriete_json

    return {p.nom: propriete_json(p, getattr(ctx, "appel", None) or {}) for p in RESERVATION.action("fiche").parametres}


def _raison_du_refus(r: Resultat) -> str:
    detail = str((r.faits or {}).get("detail") or "")
    return RAISONS_DE_REFUS.get(detail, detail) or "rien_a_faire"


FAITS_GARDES_PAR_LA_RESERVATION = ("candidats", "reservations", "tables")  # E4 : le modèle ne voit jamais les tables


def _resultat_public(operation: str, r: Resultat) -> dict[str, Any]:
    return PC.resultat_public(operation, r, FAITS_GARDES_PAR_LA_RESERVATION, MANQUES_DU_MODELE)


def _question_de(operation: str, r: Resultat, e: dict[str, Any], tour: Any) -> dict[str, Any] | None:
    """La question que pose un retour du moteur, numérotée par le code (E5), son numéro attaché à son objet (RC9, registre commun) ; ``None`` quand le retour ne pose rien."""
    if operation == "retrouver" and r.statut == "AMBIGU" and isinstance((r.faits or {}).get("candidats"), list):
        # Lot 20 (n5) : la question vit dans l'état de l'appel, enregistré en JSON au clavier : l'heure des candidats y est écrite en ISO.
        candidats = en_json(r.faits["candidats"])
        # Lot 20 (n4) : la question dit les réservations (la phrase du moteur), jamais « Laquelle ? » seul
        return _numerotee({"type": "choix", "texte": (r.suggestion or TS.laquelle({})), "nee_au_tour": tour, "candidats": candidats, "candidats_dits": [c["dit"] for c in candidats]}, e)
    if operation in TYPES_DE_QUESTION and r.manque in ("relecture", "confirmation"):
        # C6 n° 8 : la relecture est dite par le modèle, sans texte ; son JETON (neuf à chaque relecture posée) est son identité et lie le « oui » à la relecture entendue
        return _numerotee({"type": TYPES_DE_QUESTION[operation], "texte": "", "nee_au_tour": tour, "jeton": uuid.uuid4().hex}, e)
    return None


async def _reserver(ctx: Any, confirmer: bool = False, **valeurs: Any) -> Resultat:
    return await moteur.reserver(ctx.source, ctx.etat, ctx.appelant, confirmer=confirmer, **valeurs)


async def repondre_a_la_question(ctx: Any, question: dict[str, Any], sens: str | None, valeurs: list[str] | None) -> tuple[str, Resultat]:
    """La réponse rangée par son identifiant (E5) et sa case fermée (E6), selon le type de la question : l'opération qui la suit et son résultat."""
    e, source, appelant = ctx.etat, ctx.source, ctx.appelant
    t = question["type"]
    if t in TYPES_DE_QUESTION.values() and sens == "accepte" and not PAROLE.total_dit(e, question.get("jeton")):
        return await _reposer_la_relecture(ctx, t)
    if t == "recapitulatif":
        if sens == "accepte":
            return "reserver", await _reserver(ctx, confirmer=True)
        e.pop("lecture", None)
        return "reponse", Resultat("OK", {"reponse": sens, "a_faire": "dis-lui ce qu'elle veut changer"})
    if t == "recap_modif":
        if sens == "accepte":
            return "modifier", await moteur.modifier(source, e, appelant, confirmer=True)
        e.pop("modification", None)
        e.pop("lecture_modification", None)
        return "reponse", Resultat("OK", {"reponse": sens, "rien_change": True})
    if t == "annulation":
        if sens == "accepte":
            return "annuler", await moteur.annuler(source, e, appelant, confirmer=True)
        e.pop("annulation", None)
        return "reponse", Resultat("OK", {"reponse": sens, "reservation_gardee": True})
    gagnants = moteur.choisir_le_candidat(question.get("candidats") or [], valeurs)  # t == "choix" : ses mots désignent l'une de ses réservations (R04)
    if len(gagnants) == 1:
        e["cible"] = gagnants[0]["numero"]
        e["recherche"] = False
        return "reponse", Resultat("OK", {"reservation_choisie": en_json({k: gagnants[0].get(k) for k in ("numero", "quand_dit", "personnes", "prenom")})})
    # B6 (rustine 38) : les choix non compris comptés au journal de ce qui est dit (avant : un compteur à part)
    if J.noter(e, CHOIX_NON_COMPRIS) >= seuil_de_sortie(ctx.configurations, CLE_RESERVATION, DEFAULT_RESERVATION_FOIS_AVANT_LA_SORTIE):  # E28 : la clarification est bornée à deux, sauf réglage de l'établissement (M6)
        return "reponse", Resultat("REFUSEE", {"detail": "choix_non_compris_deux_fois", "a_faire": "propose-lui de laisser un message à l'équipe"})
    return "reponse", Resultat("REFUSEE", {"detail": "choix_non_compris", "candidats_dits": question.get("candidats_dits") or []})


async def _reposer_la_relecture(ctx: Any, t: str) -> tuple[str, Resultat]:
    """C6 n° 8 : un « oui » à une relecture qui n'a pas été DITE (relance échouée, phrase réglée « pas compris », coupure) ne vaut pas accord : rien n'est enregistré, changé ni annulé ;
    la relecture est reposée (un autre jeton) et le modèle la redit."""
    e, source, appelant = ctx.etat, ctx.source, ctx.appelant
    if t == "recapitulatif":
        e.pop("lecture", None)
        return "reserver", await _reserver(ctx)
    if t == "recap_modif":
        e.pop("lecture_modification", None)
        return "modifier", await moteur.modifier(source, e, appelant)
    e.pop("annulation", None)
    return "annuler", await moteur.annuler(source, e, appelant)


def _statut(e: dict[str, Any], dernier: Resultat | None, operation: str | None, refus: list[dict]) -> str:
    if dernier is not None and dernier.statut in STATUTS_ENREGISTRES:
        return "ENREGISTREE"
    if dernier is not None and operation == "annuler" and dernier.statut in ("OK", "DEJA_FAIT") and not dernier.manque:
        return "ANNULEE"
    if refus:
        return "PARTIEL"
    if dernier is not None and dernier.statut == "INTROUVABLE":
        return "INTROUVABLE"
    if CONV.question_de(e) is not None or (dernier is not None and dernier.statut in ("INCOMPLETE", "AMBIGU", "ARGUMENT_INVALIDE", "RETENU")):
        return "A_PRECISER"
    return "FAIT"


def _textes_de_la_relecture(nee: dict[str, Any], dernier: Resultat, question_du_code: str | None) -> dict[str, Any]:
    """C6 n° 8 (décision d'Evan 25/11 9 h 30 ; P2 ; Q2 = A) : la relecture (réserver, changer, annuler) est dite par le MODÈLE ; sa phrase doit dire les personnes et l'heure des faits
    (``chiffres_exiges`` : pour un changement, celles qui changent). Le code ne dit après elle que la question réglée du numéro (``question_du_code``), seule question, à la fin ; sans
    elle, le modèle pose la question."""
    faits = dernier.faits or {}
    t = nee.get("type")
    source = (faits.get("ce_qui_change") or {}) if t == "recap_modif" else faits
    exiges = {k: str(source[k]) for k in VALEURS_EXIGEES if source.get(k) not in (None, "")}
    suffixe = (question_du_code or "").strip() if t == "recapitulatif" else ""
    if t == "recap_modif":
        a_faire = A_FAIRE_DU_CHANGEMENT
    elif t == "annulation":
        a_faire = A_FAIRE_DE_L_ANNULATION
    else:
        a_faire = f"{A_FAIRE_DE_LA_RELECTURE}, {SANS_QUESTION if suffixe else AVEC_QUESTION}"
    return {"chiffres_exiges": exiges, **({"suffixe": suffixe} if suffixe else {}), "a_faire": a_faire}


def question_du_code(ctx: Any, dernier: Resultat | None) -> str | None:
    """C6 n° 8 (Q2 = A) : la question réglée que le code dit après la relecture du modèle : celle du numéro qui s'affiche quand il est gardé (M98, ``numero_affiche_garde``), sinon celle
    du numéro dicté dans ce geste (DC10, ``numero_dicte_relu``, le numéro en lettres) ; ``None`` sans numéro à relire ou phrase éteinte (le modèle pose alors la question)."""
    faits = (dernier.faits or {}) if dernier is not None else {}
    if faits.get(CLE_NUMERO_AFFICHE):
        return question_du_numero_affiche(ctx)
    if faits.get(CLE_NUMERO_RETENU):
        return phrase_du_code(ctx, NUMERO_DICTE_RELU, numero=str(faits[CLE_NUMERO_RETENU]))
    return None


def _textes_du_fait_accompli(dernier: Resultat, operation: str | None) -> dict[str, Any]:
    """C6 n° 9 (décision d'Evan 25/11 9 h 30 ; P2) : la réservation enregistrée, changée ou annulée est dite par le MODÈLE ; sa phrase doit dire les personnes et l'heure (``chiffres_exiges`` ;
    rien pour une annulation). ``fait_accompli`` : le texte de secours de la base, gardé au journal du dit (le repli le redit quand le modèle se tait), jamais dit à la place du modèle."""
    faits = dernier.faits or {}
    geste = "reserver" if dernier.statut in STATUTS_ENREGISTRES else operation
    exiges = {} if geste == "annuler" else {k: str(v) for k, v in (("personnes", faits.get("personnes")), ("heure", faits.get("heure_dite"))) if v not in (None, "")}
    return {"chiffres_exiges": exiges, "fait_accompli": dernier.suggestion, "a_faire": A_FAIRE_DU_FAIT_ACCOMPLI.get(geste or "", A_FAIRE_DU_FAIT_ACCOMPLI["reserver"])}


def textes_du_code(e: dict[str, Any], dernier: Resultat | None, operation: str | None, nee: dict[str, Any] | None, deja_enregistree: bool,
                   question_du_code: str | None = None) -> dict[str, Any]:
    """Ce que le code dit lui-même au retour de cette fiche, et ce que le modèle doit dire (C6, décision d'Evan 25/11 9 h 30) : une relecture née dans ce tour (n° 8,
    ``_textes_de_la_relecture``, ``question_du_code`` la suit) ou le fait accompli (n° 9, ``_textes_du_fait_accompli`` : enregistrée, changée, annulée) sont dits par le modèle ;
    vide : rien."""
    if nee is not None and nee.get("type") in TYPES_DE_QUESTION.values() and dernier is not None:
        return _textes_de_la_relecture(nee, dernier, question_du_code)
    if dernier is not None and bool(dernier.suggestion) and (
            dernier.statut in STATUTS_ENREGISTRES or (operation in ("modifier", "annuler") and dernier.statut == "OK" and not dernier.manque)):
        return _textes_du_fait_accompli(dernier, operation)
    return {}


def _refus_de_la_fiche(fiche: dict[str, Any], question_avant: dict | None, ctx: Any, montrees: Any) -> dict | None:
    """Le format, puis le sens de la réponse (remis en forme sur place), puis l'identifiant de la question. Sans question en attente, le format ne compte pas
    ``reponse`` : sa présence est refusée plus loin, case seule, comme à la commande."""
    vue = fiche if question_avant else {k: v for k, v in fiche.items() if k != "reponse"}
    return (B.format(vue, _schema_de_la_fiche(ctx.ctx), montrees) or B.sens_de_la_reponse(fiche)
            or (RC.question_inconnue(fiche, question_avant) if question_avant else None))


async def _repondre(ctx: Any, e: dict[str, Any], question_avant: dict[str, Any] | None, reponse: dict[str, Any]) -> tuple[str, Resultat]:
    """La réponse à la question posée ; le registre dit si elle la ferme (un choix non compris la laisse posée, sous le même numéro)."""
    CONV.poser_question(e, question_avant)  # une panne ou une coupure à l'enregistrement (Pierre A5) la laisse posée : un second « oui » aboutit
    op, r = await repondre_a_la_question(ctx, question_avant or {}, reponse.get("sens"), reponse.get("valeurs"))
    CONV.poser_question(e, None if RC.repondu(TABLE, e, question_avant, reponse.get("sens"), r, reponse.get("valeurs")) else question_avant)
    return op, r


async def executer_la_fiche_de_reservation(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    """La fiche du modèle exécutée par le code, dans son ordre ; rend l'enveloppe (statut, résultats, question numérotée, refus et ``a_faire``)."""
    ctx = contexte
    e, fiche = ctx.etat, fiche_du_modele
    fiche_de_l_appel = ctx.fiche if isinstance(ctx.fiche, dict) else {}
    # 1. La fiche entière : lisible, cases montrées dans ce tour (D52), bons types, réponse attendue, bonne question.
    entier = B.fiche_illisible(fiche)
    case_ecartee = None
    question_avant = CONV.question_de(e)
    tour = fiche_de_l_appel.get(CLE_DU_TOUR, 0)
    if entier is None:
        fiche = {k: v for k, v in fiche.items() if v is not None}
        montrees = cases_montrees(fiche_de_l_appel)
        if montrees is None:
            entier = B.refus("cases_pas_ouvertes", ["*"], reste="les cases de ce tour ne sont pas connues")
        else:
            fiche, case_ecartee, entier = B.ecarter_les_cases_sans_objet(fiche, montrees)  # B4 (M9) : comme la commande
            # une fiche sans ``reponse`` quand une question attend vaut « autre » pour elle (comme la commande, RC15) : la question reste posée, rien n'est refusé
            entier = entier or _refus_de_la_fiche(fiche, question_avant, ctx, montrees)
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier], "cases_refusees": entier["cases"],
                                                                                              "fiche_appliquee": False}).vers_json()
    # 2. Rejouée à l'identique dans ce tour : rien ne change (E11).
    if deja_executee(e, cle_d_idempotence(tour, "fiche", fiche)):
        return Enveloppe("FAIT", faits={"deja_fait": True}, plus={"fiche_appliquee": False, "rien_ajoute": True}).vers_json()
    # 3. Les valeurs libres qu'elle n'a pas dites : refusées, les autres cases passent (une case refusée n'écarte qu'elle-même).
    refus: list[dict] = [case_ecartee] if case_ecartee is not None else []
    libres = B.valeur_pas_dans_ses_mots(fiche, list(fiche_de_l_appel.get(CLE_DES_PAROLES) or []), list(fiche_de_l_appel.get(CLE_DIT_DANS_L_APPEL) or []), cases=CASES_LIBRES)
    if libres is not None:
        refus.append(libres)
    if isinstance(fiche.get("reponse"), dict) and not question_avant:
        # Aucune question n'attend (le modèle a recopié un « manque » comme identifiant) : la réponse seule est refusée, les autres cases passent ;
        # rien ne se range à la devinette, mais l'heure ou le jour dits dans leur case ne sont jamais perdus ni redemandés.
        refus.append(B.refus("question_inconnue", ["reponse"], a_faire="aucune question n'attend : ne mets pas reponse, dis la valeur dans sa case"))
        fiche = {k: v for k, v in fiche.items() if k != "reponse"}
    ecartees = {c for r in refus for c in r["cases"]}
    # 4. Les cases dans l'ordre du code, chacune par son opération nommée.
    resultats: list[dict] = []
    executees: list[str] = []
    dernier: Resultat | None = None
    operation: str | None = None
    reponse = RC.reponse_donnee(fiche, question_avant, bool(question_avant))  # RC15 : sans ``reponse``, la fiche vaut « autre » pour la question posée (mécanisme commun) : elle reste posée
    reponse_refusee = False
    ctx.operations = []
    deja_enregistree = bool(moteur.reservation_de_l_appel(e))

    def noter(nom: str, r: Resultat, op: str | None = None) -> None:
        nonlocal dernier, operation
        resultats.append(_resultat_public(nom, r))
        ctx.operations.append((op or nom, r))
        if dernier is not None and dernier.statut in STATUTS_ENREGISTRES and r.statut == "DEJA_FAIT" and (r.faits or {}).get("inchangee"):
            # Clôture, lot B4 (M2, C12, DF12) : « oui c'est bon, à vingt heures » : l'accord enregistre, la valeur redite ne change rien ; le fait
            # accompli de la fiche n'est jamais effacé par une opération qui n'a rien fait (avant : « rien ne change » cachait « enregistrée »)
            return
        dernier, operation = r, op or nom

    if fiche.get("annuler_la_reservation") is True:  # elle ne veut plus de la réservation commencée : rien d'autre n'est fait
        noter("annuler_la_reservation", moteur.renoncer(e), "renoncer")
        executees.append("annuler_la_reservation")
        return _enveloppe(ctx, resultats, executees, refus, ecartees, dernier, operation, question_avant, tour, deja_enregistree)
    CONV.poser_question(e, None if reponse else question_avant)
    retrouver = fiche.get("retrouver_une_reservation_enregistree")
    if isinstance(retrouver, dict) and not (e.get("cible") or moteur.reservation_commencee(e) or (question_avant or {}).get("type") == "choix"):
        noter("retrouver_une_reservation_enregistree",
              await moteur.retrouver_une_reservation(ctx.source, e, ctx.appelant, nom=lire_un_texte(retrouver, "nom"), jour=lire_un_texte(retrouver, "jour")), "retrouver")
        executees.append("retrouver_une_reservation_enregistree")
    if reponse and _accord_avec_une_valeur_nouvelle(e, question_avant, reponse, fiche, ecartees, ctx.appelant.telephone_affiche):
        # Pierre 14 : « oui, mais prenez plutôt le 06… » : un accord qui porte une valeur NOUVELLE n'enregistre pas l'ancienne relecture (la réservation partait avec le numéro affiché,
        # le SMS vers lui, puis le changement ne disait rien) : la valeur s'applique d'abord, la relecture est refaite et le « oui » viendra après
        reponse = None
    if reponse:
        op, r = await _repondre(ctx, e, question_avant, reponse)
        noter("reponse", r, op)
        executees.append("reponse")
        reponse_refusee = r.statut == "REFUSEE"   # P1 : l'acceptation d'un changement qui ne peut pas se faire dit sa raison ; ses valeurs redites ne le redemandent pas
    if fiche.get("annuler_une_reservation_enregistree") is True:
        if not (e.get("cible") or moteur.reservation_de_l_appel(e)):
            r = await moteur.retrouver_une_reservation(ctx.source, e, ctx.appelant)
            noter("annuler_une_reservation_enregistree", r, "retrouver")
        if e.get("cible"):
            noter("annuler_une_reservation_enregistree", await moteur.annuler(ctx.source, e, ctx.appelant), "annuler")
        executees.append("annuler_une_reservation_enregistree")
    valeurs = {k: fiche[k] for k in VALEURS if fiche.get(k) not in (None, "", []) and k not in ecartees and not reponse_refusee}
    if "retrouver_une_reservation_enregistree" in executees and not e.get("cible") and (valeurs.get("nom") or valeurs.get("jour")):
        # R-c : le nom et le jour dits AVEC la recherche servent à la chercher (déjà fait), jamais à ouvrir une réservation
        valeurs.pop("nom", None)
        valeurs.pop("jour", None)
    if e.get("recherche") and not e.get("cible") and (valeurs.get("nom") or valeurs.get("jour")) and not isinstance(retrouver, dict):
        # R05 : le nom et le jour dits pour retrouver servent à retrouver, jamais à changer le nom ni le jour d'une réservation
        noter("retrouver_une_reservation_enregistree",
              await moteur.retrouver_une_reservation(ctx.source, e, ctx.appelant, nom=valeurs.pop("nom", None), jour=valeurs.pop("jour", None)), "retrouver")
    if valeurs and set(valeurs) == {"precision"} and not (e.get("cible") or moteur.reservation_commencee(e)):
        # B8 point 4 : une précision seule n'ouvre pas une création ; elle est gardée pour la réservation qui viendra
        e.setdefault("brouillon", {})["note"] = str(valeurs["precision"]).strip()[: moteur.NOTE_MAX]
        noter("precision", Resultat("OK", {"precision_gardee": True}), "precision")
        valeurs = {}
    if valeurs:
        personnes = lire_un_entier(valeurs.get("personnes")) if "personnes" in valeurs else None
        if e.get("cible"):  # R01 : après l'enregistrement (ou une réservation retrouvée), ce qu'elle dit change CETTE réservation
            noter("modifier", await moteur.modifier(
                ctx.source, e, ctx.appelant, jour=valeurs.get("jour"), heure=valeurs.get("heure"), personnes=personnes, prenom=valeurs.get("nom"),
                note=valeurs.get("precision")))
        else:
            noter("reserver", await _reserver(
                ctx, jour=valeurs.get("jour"), heure=valeurs.get("heure"), personnes=personnes, prenom=valeurs.get("nom"), telephone=valeurs.get("telephone"),
                note=valeurs.get("precision")))
        executees.append("valeurs")
    return _enveloppe(ctx, resultats, executees, refus, ecartees, dernier, operation, question_avant, tour, deja_enregistree)


def _a_faire_des_refus(refus: list[dict], executees: list[str]) -> str | None:
    """La consigne des refus. Un refus du MÉTIER (aucune case nommée : la place prise, l'heure passée…) garde sa consigne : « le reste de la fiche est déjà fait » serait faux
    (la réponse au « oui » n'a pas abouti) et ``a_faire_du_refus_partiel`` ne parle que d'un refus de CASES (Pierre 14)."""
    if refus and not refus[0].get("cases"):
        return en_une_phrase(str(r["a_faire"]) for r in refus if r.get("a_faire"))
    return B.a_faire_des_refus(refus, executees)


def _accord_avec_une_valeur_nouvelle(e: dict[str, Any], question: dict | None, reponse: dict, fiche: dict[str, Any], ecartees: set[str], telephone_affiche: str | None) -> bool:
    """Un « oui » à la relecture d'une réservation PAS ENCORE enregistrée, dans la même fiche qu'une valeur différente de celles du brouillon ; une valeur redite à l'identique n'en est pas une."""
    if (question or {}).get("type") != "recapitulatif" or reponse.get("sens") != "accepte" or e.get("cible"):
        return False
    b = e.get("brouillon") or {}
    dites = {k: fiche[k] for k in VALEURS if fiche.get(k) not in (None, "", []) and k not in ecartees}
    gardees = {"personnes": b.get("personnes"), "jour": b.get("jour"), "heure": b.get("heure"), "nom": b.get("prenom"), "telephone": b.get("telephone_dit"), "precision": b.get("note")}

    def propre(v: Any) -> str:
        return " ".join(str(v).split()).casefold()

    for k, v in dites.items():
        if k == "telephone":
            if moteur._vers_e164(v) != moteur._vers_e164(gardees["telephone"] or telephone_affiche or ""):
                return True
        elif propre(v) != propre(gardees.get(k)):
            return True
    return False


def _transmettre_la_demande_a_l_equipe(ctx: Any, demande: Any) -> bool:
    """Lot 7b-B (reprise 2, ligne 67) : la nouvelle réservation demandée après l'annulation de celle de l'appel est écrite pour l'équipe dans la liste des rappels de l'appel (la même que la
    commande en panne), une seule entrée par appel, remplacée si la demande change. ``True`` si elle est écrite."""
    if not isinstance(ctx.fiche, dict):
        return False
    d = demande if isinstance(demande, dict) else {}
    objet = ", ".join(str(x) for x in (f"{d['personnes']} personnes" if d.get("personnes") else None, d.get("jour"), d.get("heure"), d.get("prenom")) if x) or None
    entree = {"origine": ORIGINE_RESERVATION, "mode": "rappel", "numero": numero_e164((ctx.appel or {}).get("caller_number")) or None, "objet": objet, "souhait": None,
              "le": horloge(getattr(ctx, "organization_id", None)).maintenant().isoformat()}
    liste = ctx.fiche.get(CLE_RAPPEL)
    if not isinstance(liste, list):
        liste = ctx.fiche[CLE_RAPPEL] = []
    for i, ancienne in enumerate(liste):
        if isinstance(ancienne, dict) and ancienne.get("origine") == ORIGINE_RESERVATION:
            liste[i] = entree
            return True
    liste.append(entree)
    return True


METIER_DU_FAIT_BLOQUANT = "reservation"  # la case du fait bloquant de la fiche est partagée avec la commande : chaque porte n'écrit et ne retire que la sienne
OPERATIONS_QUI_ECRIVENT = ("reserver", "modifier", "annuler")  # les gestes de la fiche qui créent, changent ou annulent une réservation (``noter``, ``executer_la_fiche_de_reservation``)


def _enveloppe(ctx: Any, resultats: list[dict], executees: list[str], refus: list[dict], ecartees: set[str], dernier: Resultat | None, operation: str | None,
               question_avant: dict | None, tour: Any, deja_enregistree: bool) -> dict[str, Any]:
    e = ctx.etat
    # La prochaine question, numérotée (E5) ; une question née dans ce tour cache sa case (B8 point 1).
    q = _question_de(operation or "", dernier, e, tour) if dernier is not None else None
    if q is not None:
        CONV.poser_question(e, q)
        if q["type"] == "choix":
            J.oublier(e, CHOIX_NON_COMPRIS)  # un nouveau choix : ses essais repartent
    nee = q
    for op, r in ctx.operations:  # ce que les gestes ont dit de la réservation visée, pour l'état (aucune requête de plus)
        faits = r.faits or {}
        if (op in ("modifier", "reserver") and r.statut in ("ENREGISTREE", "OK")) or (op == "retrouver" and r.statut == "OK" and "reservation" in faits):
            etat_pour_le_modele.retenir_la_reservation_visee(e, faits.get("reservation") if isinstance(faits.get("reservation"), dict) else faits)
        elif op == "reponse" and "reservation_choisie" in faits:
            etat_pour_le_modele.retenir_la_reservation_visee(e, faits["reservation_choisie"])
    metier = []
    transmise = False
    if dernier is not None and dernier.statut == "DEJA_FAIT" and (dernier.faits or {}).get("raison") == "deja_une_reservation_dans_cet_appel":
        if (dernier.faits or {}).get("deja_annulee"):  # Pierre F : la réservation de l'appel est annulée ; une nouvelle ne se prend pas ici, l'équipe la prend
            transmise = _transmettre_la_demande_a_l_equipe(ctx, dernier.faits.get("demande"))
            une_par_appel = "dis-lui que tu ne prends qu'une réservation par appel"
            metier.append({"raison": "deja_une_reservation_dans_cet_appel", "cases": [],
                           "a_faire": f"{une_par_appel}, que sa demande est transmise et que l'équipe le rappelle" if transmise else une_par_appel})  # la transmission n'est dite que si elle est faite
        else:
            metier.append({"raison": "deja_une_reservation_dans_cet_appel", "cases": [], "a_faire": "un changement passe par les cases personnes, jour, heure"})
    if dernier is not None and dernier.statut == "INCOMPLETE" and dernier.manque == "capacite":
        # Lot 7 (E2) : ni table ni capacité dite au formulaire : ce n'est pas « complet » et le modèle n'a aucune case pour y répondre.
        metier.append({"raison": "capacite_non_reglee", "cases": [], "a_faire": "dis-lui que tu ne peux pas confirmer une place pour l'instant et propose de laisser un message à l'équipe"})
    if dernier is not None and dernier.statut == "REFUSEE":
        raison = _raison_du_refus(dernier)
        # B4 (M9) : « propose les horaires libres » seulement quand il y en a (avant : la consigne de tout refus, même d'un choix non compris)
        defaut = "dis-lui la raison et propose les horaires libres" if (dernier.faits or {}).get("propositions") else "dis-lui la raison"
        metier.append({"raison": raison, "cases": [], "a_faire": str((dernier.faits or {}).get("a_faire") or defaut)})
    statut = _statut(e, dernier, operation, [*refus, *metier])
    faits: dict[str, Any] = {}
    if dernier is not None:
        faits = en_json({k: v for k, v in (dernier.faits or {}).items() if k not in ("candidats", "reservations", "tables", "debut", "fin", "numero", "a_faire", "detail")})
        if transmise:
            faits["transmise_a_l_equipe"] = True  # la promesse est tenue : le modèle peut dire que la demande est transmise
        faits = {k: v for k, v in faits.items() if k != "raison"}
        if dernier.statut == "AMBIGU" and isinstance(posee_choix := CONV.question_de(e), dict) and posee_choix.get("type") == "choix":
            faits["candidats_dits"] = list(posee_choix.get("candidats_dits") or [])  # 7b-C4 : les réservations de la personne, que le modèle dit avec ses mots
        if isinstance((dernier.faits or {}).get("propositions"), list):
            faits["horaires_libres"] = [p.get("heure_dite") or p.get("quand_dit") for p in dernier.faits["propositions"]]  # B4 (M9), Pierre 14 : la base rend ``quand_dit``, le moteur ``heure_dite`` (avant : null)
    plus: dict[str, Any] = {"fiche_appliquee": bool(executees), "cases_executees": executees}
    toutes_les_refus = [*refus, *metier]
    if toutes_les_refus:
        plus["refus"] = toutes_les_refus
        plus["cases_refusees"] = sorted({c for r in toutes_les_refus for c in r["cases"]})
        plus["cases_non_executees_car_liees"] = sorted(ecartees - set(plus["cases_refusees"]) - {"*"})
    premier = toutes_les_refus[0] if toutes_les_refus else None
    posee = CONV.question_de(e)
    question = Question(posee["id"], posee["type"], posee.get("texte") or "") if posee is not None else None
    jour_a_demander = None
    if question is None and not toutes_les_refus and dernier is not None and (dernier.faits or {}).get("precision_gardee") is None:
        manque = MANQUES_DU_MODELE.get(dernier.manque, dernier.manque) if dernier.manque not in (None, "relecture", "confirmation") else None
        jour_a_demander = etat_pour_le_modele.LE_JOUR if dernier.statut == "INCOMPLETE" and dernier.manque == "jour" else None  # C5 : la valeur fermée de ce qui manque (jamais la phrase de ``suggestion``)
        if manque:
            plus["manque"] = manque
    textes = textes_du_code(e, dernier, operation, nee, deja_enregistree, question_du_code(ctx.ctx, dernier) if nee is not None else None)
    a_faire = _a_faire_des_refus(toutes_les_refus, executees) if premier else (str(dernier.faits.get("a_faire")) if dernier is not None and (dernier.faits or {}).get("a_faire") else None)
    if not a_faire and textes.get("a_faire"):
        a_faire = str(textes["a_faire"])  # C6 n° 8 : la relecture, dite par le modèle
    if dernier is not None and dernier.statut == "INTROUVABLE" and not a_faire:
        # P2 : le code dit qu'il n'y a pas de réservation à ce nom et ce jour, puis la suite : une autre recherche une fois, ensuite l'équipe
        if J.fois(e, moteur.RECHERCHE_SANS_RESULTAT) >= seuil_de_sortie(ctx.configurations, CLE_RESERVATION, DEFAULT_RESERVATION_FOIS_AVANT_LA_SORTIE):
            a_faire = "dis-lui que tu ne trouves pas de réservation et propose de laisser un message à l'équipe ; ne cherche plus"
        else:
            a_faire = "dis-lui qu'il n'y a pas de réservation à ce nom et ce jour ; propose une autre recherche (un autre nom ou un autre jour) ou l'équipe"
    if isinstance(ctx.fiche, dict):
        ctx.fiche[CLE_TEXTES_DU_CODE] = textes
        if textes.get("fait_accompli"):
            J.dire_le_fait(e, str(textes["fait_accompli"]), tour)  # C6 n° 9 : le fait accompli dit par le modèle ; le journal en garde le texte de secours, que le repli redit
        if "chiffres_exiges" in textes and nee is not None:
            # C6 n° 8 : ce qui prouve que la relecture est entendue (les valeurs exigées, la question du code) ; un « oui » ne vaut accord que pour elle
            etat = PAROLE.etat_du_tour(ctx.fiche)
            etat.total_a_dire = {"jeton": nee.get("jeton"), "texte": textes.get("suffixe"), "exiges": textes["chiffres_exiges"]}
            PAROLE.garder(ctx.fiche, etat)
        if refuse_a_dire(dernier):  # C5 : le modèle se tait, le code le relance avec le refus (jamais une phrase de secours)
            poser_le_fait_bloquant(ctx.fiche, tour, METIER_DU_FAIT_BLOQUANT, [{"statut_du_module": dernier.statut, "raison": metier[0]["raison"] if metier else None, "manque": dernier.manque, "faits": faits}])  # la raison : le statut est générique (REFUSEE, DEJA_FAIT), elle dit de quoi il s'agit
        elif operation in OPERATIONS_QUI_ECRIVENT:  # une écriture sans refus remplace le refus posé plus tôt dans ce tour ; une lecture ou une question ne touche à rien (même fiche, même clé que la commande)
            poser_le_fait_bloquant(ctx.fiche, tour, METIER_DU_FAIT_BLOQUANT)
    retour = Enveloppe(statut, resultats=resultats, faits=faits, question=question, raison=premier["raison"] if premier else None, a_faire=a_faire, plus=plus).vers_json()
    if jour_a_demander:
        retour[DU.CLE_DU] = {"manque": jour_a_demander}  # le jour à demander, rangé dans le constat caché, jamais dans le retour du modèle
    return retour


def refuse_a_dire(dernier: Any) -> bool:
    """Le dernier retour du module est un refus que le modèle doit dire : un refus ou un introuvable, la règle « une seule réservation par appel » (la réservation de l'appel est annulée),
    la capacité non réglée. Rien pour le reste."""
    if dernier is None:
        return False
    faits = dernier.faits or {}
    return (dernier.statut in ("REFUSEE", "INTROUVABLE")
            or (dernier.statut == "DEJA_FAIT" and faits.get("raison") == "deja_une_reservation_dans_cet_appel" and bool(faits.get("deja_annulee")))
            or (dernier.statut == "INCOMPLETE" and dernier.manque == "capacite"))


# --------------------------------------------------------------------------- l'issue de l'appel (C10), posée par l'opération qui la fait


code_de_l_issue = ISSUES.code_de_l_issue  # le mécanisme est commun aux métiers (G2)
poser_l_issue = ISSUES.poser_l_issue


def issue_de_fin_d_appel(fiche_de_l_appel: Any) -> str | None:
    """L'appel finit avec une réservation commencée, ni enregistrée ni retrouvée, et aucune issue posée : ``reservation_abandonnee`` (son code réglé)."""
    return ISSUES.issue_de_fin_d_appel(fiche_de_l_appel, CLE_ISSUES_REGLEES, "reservation_abandonnee", lambda f: moteur.reservation_commencee(f.get(moteur.CLE) or {}))


def _poser_l_issue_de_la_fiche(ctx: Any, operations: list[tuple[str, Resultat]]) -> None:
    for op, r in operations:
        if op == "reserver" and r.statut == "ENREGISTREE":
            poser_l_issue(ctx, "reservation_enregistree")
        elif op == "modifier" and r.statut == "OK" and not r.manque:
            poser_l_issue(ctx, "reservation_modifiee")
        elif op == "annuler" and r.statut == "OK" and not r.manque:
            poser_l_issue(ctx, "reservation_annulee")


async def _dire_au_flux(ctx: Any, source: Any, operations: list[tuple[str, Resultat]]) -> None:
    """Ce que le portail apprend en direct, et le SMS : ``source.apres_le_geste`` (inchangé, D18). Une panne ne casse jamais l'appel (R1)."""
    for op, r in operations:
        geste = GESTES_DE_LA_SOURCE.get(op)
        if geste is not None and r.statut in ("ENREGISTREE", "OK") and not r.manque:
            try:
                await source.apres_le_geste(geste, r, ctx)
            except Exception as erreur:  # noqa: BLE001
                logger.error(f"[.mark] Reservation {geste}: live feed not written: {erreur!r}")


def _mesurer(fiche_de_l_appel: Any, operations: list[tuple[str, Resultat]]) -> None:
    for op, r in operations:
        mesures_du_module.de_la_reservation(fiche_de_l_appel, op, {"statut": r.statut, "faits": r.faits})


def _noter_le_temps_du_code(ctx: Any, outil: str, debut: float) -> None:
    """Lot 5 (L05-12) : le temps de l'exécution de la fiche, base comprise, rangé dans la fiche de l'appel avec son tour. ⛔ Ne lève jamais."""
    try:
        if isinstance(ctx.fiche, dict):
            from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

            ctx.fiche.setdefault(CLE_MESURES_DU_CODE, []).append({"tour": ctx.fiche.get(CLE_TOUR), "outil": outil, "ms": round((time.perf_counter() - debut) * 1000, 1)})
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[.mark] réservation : temps du code non noté : {erreur!r}")


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    debut = time.perf_counter()
    try:
        return await _executer(action, arguments, ctx)
    finally:
        _noter_le_temps_du_code(ctx, getattr(action, "nom", "?"), debut)


async def _executer(action: Any, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    e = moteur.etat_du_dossier(ctx.fiche)
    appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
    e["numero_affiche"] = bool(appelant.telephone_affiche)
    try:
        async with registre_des_sources.ouvrir((ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx) as source:
            if action.nom == "lire":
                return await lire(source, e, dict(arguments or {}))
            if action.nom == "fiche":
                if isinstance(ctx.fiche, dict) and isinstance((ctx.reglages or {}).get(REGLAGE_DES_ISSUES), dict):
                    ctx.fiche[CLE_ISSUES_REGLEES] = dict(ctx.reglages[REGLAGE_DES_ISSUES])
                contexte = SimpleNamespace(source=source, etat=e, appelant=appelant, fiche=ctx.fiche, appel=ctx.appel, ctx=ctx, operations=[],
                                           run_id=getattr(ctx, "run_id", None), organization_id=getattr(ctx, "organization_id", None),
                                           reglages=getattr(ctx, "reglages", None), configurations=getattr(ctx, "configurations", None),
                                           phrase_du_code=getattr(ctx, "phrase_du_code", None))
                vu_avant = DU.ce_qui_se_voit(e)
                retour = await executer_la_fiche_de_reservation(dict(arguments or {}), contexte)
                retour = DU.constater(retour, vu_avant, e, valeur_du_manque, seuil_de_sortie(contexte.configurations, CLE_RESERVATION_BOUCLE, DEFAULT_RESERVATION_BOUCLE_FOIS_AVANT_LA_SORTIE))  # B2 : ce qui est dû, comme la commande (même faute, même traitement)
                _poser_l_issue_de_la_fiche(ctx, contexte.operations)
                await _dire_au_flux(ctx, source, contexte.operations)
                _mesurer(ctx.fiche, contexte.operations)
                return avec_le_fait_du_numero_affiche(retour, appelant.telephone_affiche)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'outil dit « indisponible », l'appel continue
        logger.error(f"[.mark] Reservation tool {action.nom} failed: {erreur!r}")
        mesures_du_module.de_la_reservation(ctx.fiche, action.nom, {"statut": "INDISPONIBLE", "faits": {}})
        return Enveloppe("REJETEE", raison="rien_a_faire", faits={"indisponible": True}).vers_json()
    return Enveloppe("REJETEE", raison="operation_inconnue").vers_json()
