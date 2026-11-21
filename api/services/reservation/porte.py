"""[.mark] La porte d'entrée de la réservation (chantier Partie 1, lot 7 ; E20, D18) : ce que le connecteur ``reservation`` exécute.

- ``lire`` : la lecture, qui n'écrit jamais rien (``services/reservation/lire.py``) ;
- ``fiche`` : la fiche à cases, exécutée case par case dans l'ordre du banc (``banc-b13/reservation_b13.py`` ``ReservationV6.fiche``), sur le MOTEUR de la
  réservation (``moteur.py`` : reserver, modifier, annuler, retrouver, avec leur relecture liée à l'empreinte) qui reste le moteur (D18).

Même forme que ``commande/porte.py`` : les barrières de la fiche entière (``actions_communes/barrieres.py``, aucune copie), l'idempotence, les valeurs
libres qu'elle n'a pas dites, puis les cases ; la porte traduit le retour du moteur en enveloppe (``actions_communes/enveloppe.py``) et numérote la
question (« Q-n ») que le modèle posera : ``recapitulatif``, ``recap_modif``, ``annulation``, ``choix``. Le code dit mot pour mot la relecture et la
confirmation (``textes_du_code``) ; le reste est dit par le modèle. L'issue de l'appel est posée par l'opération qui la fait (C10).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.schemas.apres_appel import numero_e164
from api.services.actions_communes.issues import poser_l_issue_de_l_appel
from api.services.actions_communes import barrieres as B
from api.services.actions_communes.arguments import en_json, lire_un_entier, lire_un_texte
from api.services.actions_communes.enveloppe import Enveloppe, Question
from api.services.actions_communes.idempotence import cle_d_idempotence, deja_executee
from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE
from api.services.actions_communes.resultat import Resultat, avec_le_fait_du_numero_affiche, question_du_numero_affiche
from api.services.reservation import contrat, etat_pour_le_modele, moteur
from api.services.reservation import source as registre_des_sources
from api.services.reservation.lire import lire
from api.services.reservation.phrases_du_manque import texte_a_dire as texte_a_dire_du_manque
from api.services.restauration import mesures as mesures_du_module
from api.services.workflow.cases_selon_l_etat import CLE_DES_PAROLES, CLE_DIT_DANS_L_APPEL, CLE_DU_TOUR, cases_montrees

SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur``

# L'ordre d'exécution des cases (``ReservationV6.fiche``) : renoncer, retrouver, réponse, annuler une réservation enregistrée, puis les valeurs.
ORDRE_DES_CASES = ("annuler_la_reservation", "retrouver_une_reservation_enregistree", "reponse", "annuler_une_reservation_enregistree")
VALEURS = ("personnes", "jour", "heure", "nom", "telephone", "precision")
CASES_LIBRES = ("nom", "jour", "heure")  # les valeurs libres qu'elle doit avoir dites (D57) ; règle de valeur du banc (``valeurs_hors_paroles``)
TYPES_DE_QUESTION = {"reserver": "recapitulatif", "modifier": "recap_modif", "annuler": "annulation"}
MANQUES_DU_MODELE = {"prenom": "nom", "reference": "nom_et_jour_de_la_reservation"}   # les mots du classeur sont traduits à la source
RAISONS_DE_REFUS = {"complet": "complet_a_cette_heure"}  # le reste : le détail du classeur, tel quel (rangé « métier »)
TEXTE_DU_CHOIX = "Laquelle ?"
GESTES_DE_LA_SOURCE = {"reserver": "reserver", "modifier": "modifier_reservation", "annuler": "annuler_reservation"}
STATUTS_ENREGISTRES = ("ENREGISTREE",)

ISSUES_DE_LA_RESERVATION = ("reservation_enregistree", "reservation_modifiee", "reservation_annulee", "reservation_abandonnee")
REGLAGE_DES_ISSUES = "issues"
CLE_ISSUES_REGLEES = "reservation_issues_reglees"  # les codes réglés sur l'outil, gardés dans la fiche pour la fin de l'appel
CLE_MESURES_DU_CODE = "mesures_du_code"


def _schema_de_la_fiche(ctx: Any) -> dict[str, Any]:
    from api.services.integrations.connectors.actions.reservation import RESERVATION
    from api.services.integrations.connectors.outil import propriete_json

    return {p.nom: propriete_json(p, getattr(ctx, "appel", None) or {}) for p in RESERVATION.action("fiche").parametres}


def _raison_du_refus(r: Resultat) -> str:
    detail = str((r.faits or {}).get("detail") or "")
    return RAISONS_DE_REFUS.get(detail, detail) or "rien_a_faire"


def _resultat_public(operation: str, r: Resultat) -> dict[str, Any]:
    faits = en_json({k: v for k, v in (r.faits or {}).items() if k not in ("candidats", "reservations", "tables")})   # E4 : le modèle ne voit jamais les tables
    return {"operation": operation, "statut_du_module": r.statut, **({"manque": MANQUES_DU_MODELE.get(r.manque, r.manque)} if r.manque else {}), "faits": faits}


def _question_de(operation: str, r: Resultat, numero: int, tour: Any) -> dict[str, Any] | None:
    """La question que pose un retour du moteur, numérotée par le code (E5) ; ``None`` quand le retour ne pose rien."""
    if operation == "retrouver" and r.statut == "AMBIGU" and isinstance((r.faits or {}).get("candidats"), list):
        # Lot 20 (n5) : la question vit dans l'état de l'appel, enregistré en JSON au clavier : l'heure des candidats y est écrite en ISO.
        candidats = en_json(r.faits["candidats"])
        # Lot 20 (n4) : la question dit les réservations (la phrase du moteur), jamais « Laquelle ? » seul
        return {"id": f"Q-{numero}", "type": "choix", "texte": (r.suggestion or TEXTE_DU_CHOIX), "nee_au_tour": tour, "candidats": candidats, "candidats_dits": [c["dit"] for c in candidats]}
    if operation in TYPES_DE_QUESTION and r.manque in ("relecture", "confirmation") and r.suggestion:
        return {"id": f"Q-{numero}", "type": TYPES_DE_QUESTION[operation], "texte": r.suggestion, "nee_au_tour": tour}
    return None


async def _reserver(ctx: Any, confirmer: bool = False, **valeurs: Any) -> Resultat:
    return await moteur.reserver(
        ctx.source, ctx.etat, ctx.appelant, confirmer=confirmer, question_numero_affiche=question_du_numero_affiche(ctx.ctx), **valeurs
    )


async def repondre_a_la_question(ctx: Any, question: dict[str, Any], sens: str | None, valeurs: list[str] | None) -> tuple[str, Resultat]:
    """La réponse rangée par son identifiant (E5) et sa case fermée (E6), selon le type de la question : l'opération qui la suit et son résultat."""
    e, source, appelant = ctx.etat, ctx.source, ctx.appelant
    t = question["type"]
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
    e["essais_choix"] = int(e.get("essais_choix") or 0) + 1
    if e["essais_choix"] >= 2:  # E28 : la clarification est bornée à deux
        return "reponse", Resultat("REFUSEE", {"detail": "choix_non_compris_deux_fois", "a_faire": "propose de laisser un message à l'équipe, par rendre_la_main"})
    return "reponse", Resultat("REFUSEE", {"detail": "choix_non_compris", "candidats_dits": question.get("candidats_dits") or []})


def _statut(e: dict[str, Any], dernier: Resultat | None, operation: str | None, refus: list[dict]) -> str:
    if dernier is not None and dernier.statut in STATUTS_ENREGISTRES:
        return "ENREGISTREE"
    if dernier is not None and operation == "annuler" and dernier.statut in ("OK", "DEJA_FAIT") and not dernier.manque:
        return "ANNULEE"
    if refus:
        return "PARTIEL"
    if dernier is not None and dernier.statut == "INTROUVABLE":
        return "INTROUVABLE"
    if isinstance(e.get("question"), dict) or (dernier is not None and dernier.statut in ("INCOMPLETE", "AMBIGU", "ARGUMENT_INVALIDE", "RETENU")):
        return "A_PRECISER"
    return "FAIT"


def textes_du_code(e: dict[str, Any], dernier: Resultat | None, operation: str | None, nee: dict[str, Any] | None, deja_enregistree: bool) -> dict[str, str]:
    """Les phrases que le code dit lui-même au retour de cette fiche (vide : aucune) : la relecture, la confirmation de l'enregistrement, du changement
    ou de l'annulation (D5, banc : ``deja_dit_par_le_code``)."""
    textes: dict[str, str] = {}
    if nee is not None and nee.get("type") in ("recapitulatif", "recap_modif", "annulation", "choix") and nee.get("texte"):  # lot 20 : le choix porte jours et heures
        textes["avant"] = str(nee["texte"])
    elif dernier is not None and dernier.suggestion and (
        dernier.statut in STATUTS_ENREGISTRES or (operation in ("modifier", "annuler") and dernier.statut == "OK" and not dernier.manque)
    ):
        textes["avant"] = dernier.suggestion
    elif dernier is not None and dernier.statut == "REFUSEE" and (dernier.faits or {}).get("detail") == "complet" and dernier.suggestion:
        # Lot 20 (n2) : le refus faute de place et les heures proposées portent des chiffres : dits par le code, jamais par le modèle (la barrière des
        # chiffres retenait sa phrase jusqu'au « Pardon » du repli).
        textes["avant"] = dernier.suggestion
    return textes


async def executer_la_fiche_de_reservation(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    """La fiche du modèle exécutée par le code, dans son ordre ; rend l'enveloppe (statut, résultats, question numérotée, refus et ``a_faire``)."""
    ctx = contexte
    e, fiche = ctx.etat, fiche_du_modele
    fiche_de_l_appel = ctx.fiche if isinstance(ctx.fiche, dict) else {}
    # 1. La fiche entière : lisible, cases montrées dans ce tour (D52), bons types, réponse attendue, bonne question.
    entier = B.fiche_illisible(fiche)
    question_avant = e.get("question") if isinstance(e.get("question"), dict) else None
    tour = fiche_de_l_appel.get(CLE_DU_TOUR, 0)
    if entier is None:
        fiche = {k: v for k, v in fiche.items() if v is not None}
        montrees = cases_montrees(fiche_de_l_appel)
        if montrees is None:
            entier = B.refus("cases_pas_ouvertes", ["*"], a_faire="rien n'est changé : les cases de ce tour ne sont pas connues")
        else:
            posee = contrat.question_posee(question_avant, tour)
            entier = (B.case_sans_objet(fiche, montrees) or B.format(fiche, _schema_de_la_fiche(ctx.ctx)) or B.sens_de_la_reponse(fiche)
                      or B.reponse_manquante(fiche, question_avant, posee) or (B.question_inconnue(fiche, question_avant) if question_avant else None))
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier], "cases_refusees": entier["cases"],
                                                                                              "fiche_appliquee": False}).vers_json()
    # 2. Rejouée à l'identique dans ce tour : rien ne change (E11).
    if deja_executee(e, cle_d_idempotence(tour, "fiche", fiche)):
        return Enveloppe("FAIT", faits={"deja_fait": True}, plus={"fiche_appliquee": False, "rien_ajoute": True}).vers_json()
    # 3. Les valeurs libres qu'elle n'a pas dites : refusées, les autres cases passent (une case refusée n'écarte qu'elle-même).
    refus: list[dict] = []
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
    reponse = fiche.get("reponse") if isinstance(fiche.get("reponse"), dict) else None
    reponse_refusee = False
    ctx.operations = []
    deja_enregistree = bool(moteur.reservation_de_l_appel(e))

    def noter(nom: str, r: Resultat, op: str | None = None) -> None:
        nonlocal dernier, operation
        resultats.append(_resultat_public(nom, r))
        ctx.operations.append((op or nom, r))
        dernier, operation = r, op or nom

    if fiche.get("annuler_la_reservation") is True:  # elle ne veut plus de la réservation commencée : rien d'autre n'est fait
        noter("annuler_la_reservation", moteur.renoncer(e), "renoncer")
        executees.append("annuler_la_reservation")
        return _enveloppe(ctx, resultats, executees, refus, ecartees, dernier, operation, question_avant, tour, deja_enregistree)
    e["question"] = None if reponse else question_avant
    retrouver = fiche.get("retrouver_une_reservation_enregistree")
    if isinstance(retrouver, dict) and not (e.get("cible") or moteur.reservation_commencee(e) or (question_avant or {}).get("type") == "choix"):
        noter("retrouver_une_reservation_enregistree",
              await moteur.retrouver_une_reservation(ctx.source, e, ctx.appelant, nom=lire_un_texte(retrouver, "nom"), jour=lire_un_texte(retrouver, "jour")), "retrouver")
        executees.append("retrouver_une_reservation_enregistree")
    if reponse:
        op, r = await repondre_a_la_question(ctx, question_avant or {}, reponse.get("sens"), reponse.get("valeurs"))
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


def _enveloppe(ctx: Any, resultats: list[dict], executees: list[str], refus: list[dict], ecartees: set[str], dernier: Resultat | None, operation: str | None,
               question_avant: dict | None, tour: Any, deja_enregistree: bool) -> dict[str, Any]:
    e = ctx.etat
    # La prochaine question, numérotée (E5) ; une question née dans ce tour cache sa case (B8 point 1).
    q = _question_de(operation or "", dernier, int(e.get("prochain_q") or 1), tour) if dernier is not None else None
    if q is not None:
        e["prochain_q"] = int(e.get("prochain_q") or 1) + 1
        e["question"] = q
        if q["type"] == "choix":
            e["essais_choix"] = 0
    elif e.get("question") is None and question_avant and dernier is not None and (dernier.faits or {}).get("detail") == "choix_non_compris":
        e["question"] = question_avant  # un choix non compris : la même question reste posée, sous le même identifiant
    nee = q
    for op, r in ctx.operations:  # ce que les gestes ont dit de la réservation visée, pour l'état (aucune requête de plus)
        faits = r.faits or {}
        if (op in ("modifier", "reserver") and r.statut in ("ENREGISTREE", "OK")) or (op == "retrouver" and r.statut == "OK" and "reservation" in faits):
            etat_pour_le_modele.retenir_la_reservation_visee(e, faits.get("reservation") if isinstance(faits.get("reservation"), dict) else faits)
        elif op == "reponse" and "reservation_choisie" in faits:
            etat_pour_le_modele.retenir_la_reservation_visee(e, faits["reservation_choisie"])
    metier = []
    if dernier is not None and dernier.statut == "DEJA_FAIT" and (dernier.faits or {}).get("raison") == "deja_une_reservation_dans_cet_appel":
        metier.append({"raison": "deja_une_reservation_dans_cet_appel", "cases": [], "a_faire": "un changement passe par les cases personnes, jour, heure"})
    if dernier is not None and dernier.statut == "INCOMPLETE" and dernier.manque == "capacite":
        # Lot 7 (E2) : ni table ni capacité dite au formulaire : ce n'est pas « complet » et le modèle n'a aucune case pour y répondre.
        metier.append({"raison": "capacite_non_reglee", "cases": [], "a_faire": "dis-lui que tu ne peux pas confirmer une place pour l'instant et propose de passer à l'équipe"})
    if dernier is not None and dernier.statut == "REFUSEE":
        raison = _raison_du_refus(dernier)
        metier.append({"raison": raison, "cases": [], "a_faire": str((dernier.faits or {}).get("a_faire") or "dis-lui la raison et propose les horaires libres")})
    statut = _statut(e, dernier, operation, [*refus, *metier])
    faits: dict[str, Any] = {}
    if dernier is not None:
        faits = en_json({k: v for k, v in (dernier.faits or {}).items() if k not in ("candidats", "reservations", "tables", "debut", "fin", "numero", "a_faire", "detail")})
        faits = {k: v for k, v in faits.items() if k != "raison"}
        if isinstance((dernier.faits or {}).get("propositions"), list):
            faits["horaires_libres"] = [p.get("quand_dit") for p in dernier.faits["propositions"]]
    plus: dict[str, Any] = {"fiche_appliquee": bool(executees), "cases_executees": executees}
    toutes_les_refus = [*refus, *metier]
    if toutes_les_refus:
        plus["refus"] = toutes_les_refus
        plus["cases_refusees"] = sorted({c for r in toutes_les_refus for c in r["cases"]})
        plus["cases_non_executees_car_liees"] = sorted(ecartees - set(plus["cases_refusees"]) - {"*"})
    premier = toutes_les_refus[0] if toutes_les_refus else None
    question = Question(e["question"]["id"], e["question"]["type"], e["question"].get("texte") or "") if isinstance(e.get("question"), dict) else None
    if question is None and not toutes_les_refus and dernier is not None and (dernier.faits or {}).get("precision_gardee") is None:
        manque = MANQUES_DU_MODELE.get(dernier.manque, dernier.manque) if dernier.manque not in (None, "relecture", "confirmation") else None
        phrase = (dernier.suggestion if dernier.statut == "INCOMPLETE" and dernier.manque == "jour" and dernier.suggestion else None) or texte_a_dire_du_manque(e)
        if manque:
            plus["manque"] = manque
        if phrase:
            plus["texte_a_dire"] = phrase
    a_faire = B.a_faire_du_refus_partiel(premier, executees) if premier else (str(dernier.faits.get("a_faire")) if dernier is not None and (dernier.faits or {}).get("a_faire") else None)
    if dernier is not None and dernier.statut == "INTROUVABLE" and not a_faire:
        # P2 : le code dit qu'il n'y a pas de réservation à ce nom et ce jour, puis la suite : une autre recherche une fois, ensuite l'équipe
        if int(e.get("recherches_sans_resultat") or 0) >= 2:
            a_faire = "dis-lui que tu ne trouves pas de réservation et propose de laisser un message à l'équipe ; ne cherche plus"
        else:
            a_faire = "dis-lui qu'il n'y a pas de réservation à ce nom et ce jour ; propose une autre recherche (un autre nom ou un autre jour) ou l'équipe"
    textes = textes_du_code(e, dernier, operation, nee, deja_enregistree)
    if isinstance(ctx.fiche, dict):
        ctx.fiche[CLE_TEXTES_DU_CODE] = textes
    return Enveloppe(statut, resultats=resultats, faits=faits, question=question, raison=premier["raison"] if premier else None, a_faire=a_faire, plus=plus).vers_json()


# --------------------------------------------------------------------------- l'issue de l'appel (C10), posée par l'opération qui la fait


def code_de_l_issue(reglages: Any, issue: str) -> str:
    reglees = (reglages or {}).get(REGLAGE_DES_ISSUES) if isinstance(reglages, dict) else None
    code = reglees.get(issue) if isinstance(reglees, dict) else None
    return code.strip() if isinstance(code, str) and code.strip() else issue


def poser_l_issue(ctx: Any, issue: str) -> None:
    """L'issue de l'appel, posée dans la fiche de l'appel comme celle de la commande. ⛔ Ne lève jamais."""
    try:
        poser_l_issue_de_l_appel(getattr(ctx, "fiche", None), issue, code_de_l_issue(getattr(ctx, "reglages", None), issue))  # P6 : « commande enregistrée » n'est jamais écrasée
    except Exception:  # noqa: BLE001
        pass


def issue_de_fin_d_appel(fiche_de_l_appel: Any) -> str | None:
    """L'appel finit avec une réservation commencée, ni enregistrée ni retrouvée, et aucune issue posée : ``reservation_abandonnee`` (son code réglé).
    ``None`` sinon. ⛔ Ne lève jamais."""
    try:
        if not isinstance(fiche_de_l_appel, dict) or fiche_de_l_appel.get("call_disposition"):
            return None
        if not moteur.reservation_commencee(fiche_de_l_appel.get(moteur.CLE) or {}):
            return None
        return code_de_l_issue({REGLAGE_DES_ISSUES: fiche_de_l_appel.get(CLE_ISSUES_REGLEES)}, "reservation_abandonnee")
    except Exception:  # noqa: BLE001
        return None


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
                retour = await executer_la_fiche_de_reservation(dict(arguments or {}), contexte)
                _poser_l_issue_de_la_fiche(ctx, contexte.operations)
                await _dire_au_flux(ctx, source, contexte.operations)
                _mesurer(ctx.fiche, contexte.operations)
                return avec_le_fait_du_numero_affiche(retour, appelant.telephone_affiche)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'outil dit « indisponible », l'appel continue
        logger.error(f"[.mark] Reservation tool {action.nom} failed: {erreur!r}")
        mesures_du_module.de_la_reservation(ctx.fiche, action.nom, {"statut": "INDISPONIBLE", "faits": {}})
        return Enveloppe("REJETEE", raison="rien_a_faire", faits={"indisponible": True}).vers_json()
    return Enveloppe("REJETEE", raison="operation_inconnue").vers_json()
