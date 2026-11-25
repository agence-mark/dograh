"""[.mark] La porte d'entrée de la commande (chantier Partie 1) : ce que le connecteur ``commande`` exécute.

- ``lire`` (lot 2, E16) : la lecture, qui n'écrit jamais rien (``services/commande/lire.py``) ;
- ``fiche`` : la fiche à cases, exécutée case par case dans l'ordre du banc (lot 3, ``executer_la_fiche``).

La source (le catalogue) est ouverte une fois par appel d'outil, comme avant ; une panne du catalogue ne lève pas : ``INDISPONIBLE`` au journal (R1).
"""

from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass, field, is_dataclass, replace
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.db.bases_clients.recherche_liste_moteur import norme_de_recherche
from api.db.bases_clients.horloge import horloge
from api.schemas.apres_appel import numero_e164
from api.schemas.workflow_configurations import DEFAULT_COMMANDE_FOIS_AVANT_LA_SORTIE
from api.services.actions_communes import issues as ISSUES
from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.moyens_de_paiement import MOYEN_DE_BASE_SELON_LA_FICHE
from api.services.actions_communes import barrieres as B
from api.services.actions_communes import consignes as C
from api.services.actions_communes import du as DU
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import porte_commune as PC
from api.services.actions_communes.arguments import en_json
from api.services.actions_communes.cases_liees import cases_ecartees
from api.services.actions_communes.enveloppe import Enveloppe
from api.services.actions_communes.forme import valeur_dite_par_elle
from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE, poser_le_suffixe_lu  # lot 7 : la même clé pour la commande et la réservation
from api.services.actions_communes.idempotence import case_deja_faite, cle_d_idempotence, deja_executee, noter_les_cases
from api.services.actions_communes.plafonds import plafond_d_operations
from api.services.actions_communes.repli import STATUTS_QUI_REFUSENT, poser_le_fait_bloquant, statut_qui_refuse
from api.services.actions_communes.resultat import avec_le_fait_du_numero_affiche
from api.services.actions_communes.types import ConsigneLivreur
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_COMMANDE
from api.services.commande import contrat, etat_pour_le_modele, moteur
from api.services.commande.moteur.socle import STATUTS_PERDUS
from api.services.commande.briques import formule_a_etapes, ligne_de_formule_limitee
from api.services.commande.briques import formule as FO
from api.services.commande import etape as ETAPE
from api.services.commande import panier as P
from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES
from api.services.commande import textes_de_secours as TS
from api.services.actions_communes import registre_des_questions as RC
from api.services.commande import registre as RQ
from api.services.commande import source as registre_des_sources
from api.services.commande.lire import CLE_DU_PRIX_A_DIRE, CLE_DU_SUFFIXE, lecture_sur_une_copie, lire
from api.services.commande.phrases_du_manque import Manque, phrase_du_manque
from api.services.commande.phrases_du_manque import texte_a_dire as texte_a_dire_du_manque
from api.services.commande.reglages import reglages_de_la_commande
from api.services.commande.resultat import (
    Resultat,
    question_apres_enregistrement,
    question_du_numero_affiche,
    question_du_numero_dicte,
)
from api.services.commande.source import Source
from api.services.integrations.connectors.outil import nom_vu
from api.services.restauration.mesures import mesures as mesures_du_module

SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur`` (reprise de ``action.py``)


def _regles(ctx: Any):
    regles = reglages_de_la_commande(ctx.configurations)
    if regles is not None and is_dataclass(regles):
        regles = replace(regles, question_numero_affiche=question_du_numero_affiche(ctx), question_apres_enregistrement=question_apres_enregistrement(ctx),
                         question_numero_dicte=question_du_numero_dicte(ctx))
    return regles


# --------------------------------------------------------------------------- la fiche de la commande (lot 3)

# L'ordre d'exécution des cases (``banc-b5/contrat_b5.py`` ``fiche_vers_items``, aux noms de la version finale ; vérifié contre le guichet de
# ``banc-b13/commande_b13.py`` ``executer_fiche``) : vider et annuler, réponse, retraits, changements, ajouts, informations, c'est tout.
ORDRE_DES_CASES = (
    "vider_le_panier", "annuler_la_commande", "annuler_une_commande_enregistree", "reponse", "retirer_article", "changer_quantite", "ajouter",
    "mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", *contrat.CASES_DE_FIN, "note_generale",  # les cases de fin viennent du contrat, dans son ordre
    "code_de_remise", "reduction_annoncee", "c_est_tout",
)
INFORMATIONS = ORDRE_DES_CASES[ORDRE_DES_CASES.index("mode_de_retrait"):ORDRE_DES_CASES.index("c_est_tout")]
CLE_DES_PAROLES = "paroles_de_la_personne"
CLE_DIT_PAR_LE_CODE = "dit_par_le_code"
TYPES_DE_QUESTION = {"CHOIX_OBLIGATOIRE": "variante", "AMBIGU": "ambiguite"}
MANQUES_DE_QUESTION = {"relecture": "relecture", "vente_en_plus": "proposition", "heure_proposee": "heure_proposee",  # aparté d'Evan (20/11)
                       "confirmer_numero": "numero_affiche", "confirmer_numero_dicte": RQ.TYPE_DU_NUMERO_DICTE}  # DC10  # C7 (lot 19 bis) : le numéro qui s'affiche est une question numérotée, sa réponse la cite
MANQUES_REFUSES_DE_QUESTION = {"heure_voulue": "heure_proposee"}  # lot 7b, ligne 12 : une heure refusée reste un manque, donc la question qui passe avant la relecture (``registre.ORDRE``)
# Lot 6, élément 1 (b) (B7 point 2, K4 du banc ``contrat_b4.texte_du_code``) : ce que le code dit lui-même, mot pour mot, au retour de la fiche ;
# rangé dans la fiche de l'appel pour la couche de parole, JAMAIS dans le retour montré au modèle (B10 point 4 : seulement le drapeau).
#   avant   : le récapitulatif, la confirmation de l'enregistrement : dit, et le tour s'arrête là ;
#   suffixe : le prix d'une proposition née dans ce tour : dit juste après la phrase du modèle (D33).
STATUT_MINIMUM = "MINIMUM_NON_ATTEINT"
A_FAIRE_DU_MINIMUM = "dis-lui avec tes mots le minimum de la livraison et ce qui manque (faits.minimum_de_la_commande), puis demande-lui ce qu'elle veut faire"
A_FAIRE_DE_L_HEURE = "demande-lui avec tes mots ce qui manque de l'heure voulue (faits.heure_a_dire : le jour et l'heure, ou l'heure de la réouverture)"
A_FAIRE_DE_LA_REGLE = "dis-lui avec tes mots la règle de la ligne ou de l'article (faits.regle_de_la_ligne, faits.regles_a_dire)"
A_FAIRE_DES_REFUS_A_DIRE = "dis-lui avec tes mots les refus de la fiche, avec leurs chiffres et leurs lieux (faits.refus_de_la_fiche)"
A_FAIRE_DE_L_ANNULATION = "demande-lui avec tes mots si elle est sûre de vouloir annuler sa commande, en disant le montant (faits.annulation_a_confirmer) ; rien n'est annulé avant son « oui »"
A_FAIRE_DE_LA_COMMANDE_PERDUE = ("sa commande n'a pas été confirmée par la cuisine : dis-le-lui, et propose-lui de laisser un message à l'équipe pour qu'elle la rappelle ; "
                                 "si elle dit oui, laisser_un_message avec l'objet")
A_FAIRE_DE_LA_QUESTION = "puis pose la question, dans une même phrase naturelle"  # la question née dans ce tour se pose quel que soit le refus dit avant


def _seuil_de_sortie(ctx: Any) -> int:
    """M6 : le nombre de fois avant la sortie, réglé par le restaurant (les réglages de la commande de l'appel) ; sans réglages : le défaut du schéma."""
    return getattr(getattr(ctx, "regles", None), "fois_avant_la_sortie", None) or DEFAULT_COMMANDE_FOIS_AVANT_LA_SORTIE


def _consigne_du_journal(etape: str) -> tuple[int, str]:
    """La consigne que le journal de ce qui est dit donne pour un refus redit (l'issue, puis la sortie), avec son rang ; ``(RESTE, "")`` quand il n'en donne pas."""
    return (C.SORTIE if etape == J.SORTIE else C.ISSUE, J.consigne(etape) or "")


def faits_du_minimum(p: dict[str, Any]) -> dict[str, Any] | None:
    """Les faits du minimum de la livraison : ``{commune, minimum, manque}`` (centimes), lus dans l'ÉTAT du panier à la fin de la fiche (minimum de sa zone et chiffrage retenus,
    ``etat_pour_le_modele.retenir``), pas dans la dernière opération (une proposition peut la suivre). ``None`` : pas en livraison, pas de lignes, minimum atteint ou inconnu."""
    from api.services.commande.etat_pour_le_modele import CLE_CONNU, _commune, cle_du_chiffrage

    if p.get("mode") != "livraison" or not p.get("zone") or not p.get("lignes") or p.get("enregistree") or p.get("annulee"):
        return None
    connu = p.get(CLE_CONNU) or {}
    zone_id = (p.get("zone") or {}).get("id")
    minimum = (connu.get("minimums") or {}).get(str(zone_id))
    chiffrage = connu.get("chiffrage") or {}
    commune = _commune(p)
    if not minimum or not commune or chiffrage.get("cle") != cle_du_chiffrage(p.get("mode"), P.pour_le_chiffrage(p), zone_id):
        return None
    sous_total = chiffrage.get("sous_total")
    if not isinstance(sous_total, int) or sous_total >= int(minimum):
        return None
    return {"commune": commune, "minimum": int(minimum), "manque": int(minimum) - sous_total}


def poser_le_minimum(ctx: Any, p: dict[str, Any], retour: dict[str, Any]) -> DU.Du | None:
    """Après la fiche et ce que la source a retenu : sous le minimum de la zone, le retour porte les faits du minimum (``minimum_de_la_commande``) et le modèle les dit avec ses mots ;
    rend l'élément de ``Du`` (ce que le modèle doit dire). ⛔ Ne lève jamais."""
    try:
        faits = faits_du_minimum(p)
        if not faits or not isinstance(getattr(ctx, "fiche", None), dict) or not isinstance(retour.get("faits"), dict):
            return None
        # B3 (M5, H6 : le minimum dit trois fois) : le journal de ce qui est dit ; la clé est le fait (un autre montant manquant est un autre fait).
        # Le minimum reste vrai d'une fiche à l'autre : déjà dit, il ne se redit pas ; seule « c'est tout » refusée par lui compte comme un échec
        cle = f"minimum {faits['commune']} {faits['minimum']} {faits['manque']}"
        bute = any(isinstance(r, dict) and r.get("statut_du_module") == STATUT_MINIMUM for r in retour.get("resultats") or [])
        if J.deja_dit(p, cle) and not bute:
            return None
        etape = J.fait_redit(p, cle, ctx.fiche.get(contrat.CLE_DU_TOUR), _seuil_de_sortie(ctx))
        if etape == J.DEJA_DANS_CE_TOUR:
            return None
        if etape != J.PREMIERE:
            return DU.Du(consignes=(_consigne_du_journal(etape),))
        retour["faits"]["minimum_de_la_commande"] = faits
        return DU.Du(consignes=((C.REFUS_A_DIRE, A_FAIRE_DU_MINIMUM),))
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] commande : les faits du minimum n'ont pas pu être posés")
    return None


def textes_du_code(p: dict[str, Any], dernier: Resultat | None, nee: dict[str, Any] | None, refus: list[dict], deja_enregistree: bool = False,
                   total_d_avant: Any = None, question_apres: str | None = None) -> dict[str, str]:
    """Les phrases que le code dit lui-même au retour de cette fiche (vide : aucune) : ce qui est dû à la personne (B2, M3), les faits accomplis
    (enregistrée, changée avec son nouveau total, annulée) et la question qui se dit mot pour mot. ``deja_enregistree`` : la commande l'était avant
    cette fiche (un changement se dit, ``remplace`` ; une réponse sans changement, non). RC1 (contrôle long, lot 3) : UNE seule question dans le tour. Quand une question du
    registre est posée (l'annulation demandée, un doute, une taille), la question que le code ajoute d'habitude après un fait accompli (« Puis-je faire autre chose pour
    vous ? », M108) cède sa place à celle-là : le fait est dit, puis la question posée, jamais deux."""
    textes: dict[str, str] = {}
    if dernier is None:
        return textes

    def avec_la_question(fait: str) -> str:
        """LA place où la question finale s'ajoute au fait accompli : la question en attente au registre, sinon celle du réglage ; réglage vide, aucune."""
        apres, q = (question_apres or "").strip(), CONV.question_de(p)
        if not apres:
            return fait
        return " ".join(x for x in (fait, RQ.texte_dit_de_la_question(q, p) if isinstance(q, dict) else apres) if x)

    def confirmation() -> str:
        return (dernier.faits or {}).get(moteur.CLE_CONFIRMATION) or dernier.suggestion

    def le_changement() -> str:
        # B2 (M3, TF2) : changée après l'être : son nouveau total dit par le code ; le total inchangé (l'heure), sa nouvelle confirmation
        change = (p.get("enregistree") or {}).get("total") != total_d_avant
        if change or not dernier.suggestion:
            return avec_la_question(RQ.texte_du_changement(p))
        if dernier.suggestion == J.fait_accompli(p):
            return avec_la_question(RQ.texte_du_changement(p, montant=False))  # rien de ce qui se dit n'a changé : jamais la même phrase redite (RC3)
        return avec_la_question(confirmation())  # l'heure a changé : la nouvelle confirmation la dit

    enregistree = dernier.statut in STATUTS_ENREGISTRES
    dite_par_la_question = nee is not None and nee.get("type") in ("relecture", RQ.TYPE_DU_NUMERO_DICTE) and nee.get("texte")
    avant_le_reste = PC.premier_cas((
        (enregistree and bool(dernier.faits.get("remplace")), le_changement),
        (enregistree and bool(dernier.suggestion) and not deja_enregistree, lambda: avec_la_question(confirmation())),
        (bool(dernier.faits.get("commande_annulee")), lambda: RQ.TEXTE_ANNULATION_CONFIRMEE),  # DC4, second temps : l'annulation faite se dit par le code
        (bool(dernier.faits.get("annulee") and dernier.suggestion), lambda: dernier.suggestion),
        (bool(dite_par_la_question), lambda: str(nee["texte"])),
    ))
    if avant_le_reste is not None:
        textes["avant"] = avant_le_reste
    elif nee is not None and nee.get("type") == "proposition" and nee.get("chiffre") and not nee.get("offerte") and not refus:
        textes["suffixe"] = str(nee["chiffre"])
    return textes


def ordre_des_cases(fiche: dict[str, Any]) -> list[str]:
    """Les cases remplies de la fiche, dans l'ordre du code (jamais celui du modèle)."""
    return [c for c in ORDRE_DES_CASES if fiche.get(c) not in (None, "", [], False)]


def _schema_de_la_fiche(ctx: Any) -> dict[str, Any]:
    from api.services.integrations.connectors.actions.commande import COMMANDE
    from api.services.integrations.connectors.outil import _propriete

    return {p.nom: _propriete(p, getattr(ctx, "appel", None) or {}) for p in COMMANDE.action("fiche").parametres}


def _cases_montrees(ctx: Any) -> list[str] | None:
    from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

    montrees = (getattr(ctx, "fiche", None) or {}).get(CLE_DES_CASES_MONTREES) or {}
    for nom in ("fiche", nom_vu(getattr(ctx, "fiche", None), "fiche")):
        if isinstance(montrees.get(nom), list):
            return montrees[nom]
    return None


def _question_de(r: Resultat, numero: int, tour: int, p_de_la_question: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """La question que pose un retour du moteur, numérotée par le code (E5) ; ``None`` quand le retour ne pose rien."""
    type_ = TYPES_DE_QUESTION.get(r.statut) or MANQUES_DE_QUESTION.get(r.manque or "") or (MANQUES_REFUSES_DE_QUESTION.get(r.manque or "") if statut_qui_refuse(r.statut) else None)
    if r.statut == "CHOIX_OBLIGATOIRE" and ((r.faits or {}).get("question") or {}).get("type") == formule_a_etapes.TYPE_DE_LA_QUESTION:
        type_ = formule_a_etapes.TYPE_DE_LA_QUESTION  # FOR2 : une étape de formule à choisir ouvre une question d'étape (sa réponse dans valeurs)
    if type_ is None:
        return None
    q = {"id": f"Q-{numero}", "type": type_, "texte": r.suggestion, "nee_au_tour": tour}
    proposition = (r.faits or {}).get("proposition")
    if type_ == "proposition" and isinstance(proposition, dict):
        q.update({"article_propose": proposition.get("nom"), "offerte": bool(proposition.get("offre")), "offre": proposition.get("offre")})
        cachee = p_de_la_question.get("proposition_en_plus") if isinstance(p_de_la_question, dict) else None
        if isinstance(cachee, dict):
            # ce que le code dit lui-même (le chiffre après la phrase du modèle, le repli de B8) : gardé dans la question, jamais dans le retour
            q.update({"chiffre": cachee.get("chiffre"), "repli": cachee.get("repli")})
    if isinstance((r.faits or {}).get("candidats"), list):
        q["choix"] = [str(c) for c in r.faits["candidats"]][:4]
    if type_ in ("variante", formule_a_etapes.TYPE_DE_LA_QUESTION) and (r.faits or {}).get("article"):
        q["article_en_question"] = str(r.faits["article"])  # RC9 : la ligne dont parle la question (son objet au registre)
    if type_ == "heure_proposee" and (r.faits or {}).get("heure_proposee"):
        q["heure"] = str(r.faits["heure_proposee"])  # l'heure de la réouverture proposée, posée au « oui »
    if type_ == "ambiguite" and isinstance((r.faits or {}).get(moteur.CLE_CANDIDATS), list):
        q[moteur.CLE_CANDIDATS] = r.faits[moteur.CLE_CANDIDATS]  # B5 (N1), n° 55
    if type_ == "ambiguite" and isinstance((r.faits or {}).get(CLE_ARTICLE_DIT), dict):
        q[CLE_ARTICLE_DIT] = r.faits[CLE_ARTICLE_DIT]
        if (r.faits or {}).get(moteur.CLE_OPTION_DITE):
            q[moteur.CLE_OPTION_DITE] = str(r.faits[moteur.CLE_OPTION_DITE])  # T1
    return q


def _faits_gardes() -> tuple[str, ...]:
    """Ce que le modèle ne voit jamais d'un résultat."""
    return ("panier", CLE_ARTICLE_DIT, moteur.CLE_OPTION_DITE, moteur.CLE_CANDIDATS, moteur.CLE_CONFIRMATION)


def _faits_publics(r: Resultat) -> dict[str, Any]:
    return PC.faits_publics(r, _faits_gardes())


def faits_vus_par_le_modele(r: Resultat) -> dict[str, Any]:
    """Les faits d'un refus tels que le modèle les reçoit : ce que doit suffire à dire un texte de secours (``textes_de_secours``)."""
    return _faits_publics(r)


def _resultat_public(operation: str, r: Resultat) -> dict[str, Any]:
    return PC.resultat_public(operation, r, _faits_gardes())


def _refus_pour_le_modele(r: Resultat) -> dict[str, Any]:
    """Un refus de la fiche donné au modèle comme un fait : ce que le module refuse (l'article dit, les plus proches…) et son explication, pour qu'il le dise avec ses mots."""
    explication = (r.suggestion or "").strip()
    return {"statut_du_module": r.statut, "manque": r.manque, "faits": _faits_publics(r), **({"explication": explication} if explication else {})}


async def repondre_a_la_question(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, question: dict, sens: str | None,
                                 valeurs: list[str] | None, ex: Execution) -> Resultat:
    """La réponse rangée par son identifiant (E5) et sa case fermée (E6), selon le type de la question ; le corps des règles est réécrit au lot 4."""
    texte = ", ".join(str(v) for v in valeurs or [] if str(v).strip()) or None
    if question["type"] == "relecture":
        if sens == "accepte":
            ETAPE.transition(p, ETAPE.ACCORD_DONNE)
            return Resultat("OK", {"recapitulatif": "accepte"}, "")
        ETAPE.transition(p, ETAPE.ACCORD_RETIRE)
        # B1 (C3 a) : « autre » à la relecture ne la ferme pas, elle reste posée.
        # B4 (M4, C3, RC1 E11 → G24) : « non » non plus : fermée, plus rien n'était demandé (cases de fin cachées, rien qui manque) ; elle reste
        # posée et le modèle demande ce qu'elle veut changer (comme la réservation)
        faits = {"recapitulatif": sens or "autre"}
        if sens == "refuse":
            faits["a_faire"] = "demande-lui ce qu'elle veut changer"
        return Resultat("OK", faits, "")
    if question["type"] == RQ.TYPE_DU_NUMERO_DICTE:
        return moteur.repondre_au_numero_dicte(p, sens, appelant)  # DC10
    if question["type"] == moteur.TYPE_DE_LA_QUESTION_DU_NUMERO:
        return moteur.repondre_au_numero_affiche(p, sens, appelant)  # C7 : la seule voie par laquelle le numéro qui s'affiche est gardé ou refusé
    if question["type"] == RQ.TYPE_ANNULATION:
        if sens == "accepte":
            return await moteur.annuler_commande_enregistree(source, p, regles)  # DC4, second temps : annulée, puis confirmée par le code
        if sens == "refuse":
            return Resultat("OK", {"annulation_abandonnee": True}, "")  # seul un « non » dit abandonne ; la commande reste enregistrée
        # Pierre 7 : « autre » (une fiche sans réponse, un mauvais numéro écartés, « euh attendez ») n'abandonne rien : la question reste posée
        return Resultat("OK", {"rien_ajoute": True}, "")
    if question["type"] == RQ.TYPE_NOUVELLE_COMMANDE:
        if sens == "accepte":
            RQ.repartir(p)  # DC5 : une commande neuve ; l'article se redit dans sa case
            return Resultat("OK", {"nouvelle_commande": True}, "")
        if sens == "refuse":
            return Resultat("OK", {"rien_ajoute": True}, "")  # seul un « non » dit la ferme ; un article dit plus tard la propose de nouveau (aucun drapeau définitif)
        return Resultat("OK", {"rien_ajoute": True}, "")  # Pierre 7 : « autre » ne ferme rien
    if question["type"] == "proposition":
        if sens == "autre":
            # DC3 (Evan, 22/11) : une proposition se ferme au premier « non » ou au premier tour sans « oui » ; elle ne revient pas (rien n'est ajouté)
            p.pop("proposition_en_plus", None)
            p["proposition_refusee"] = True
            return Resultat("OK", {"rien_ajoute": True, "proposition_fermee": True}, "")
        return await moteur.repondre_a_la_proposition(source, p, regles, appelant, sens, variante=texte)
    if question["type"] == formule_a_etapes.TYPE_DE_LA_QUESTION:
        return await repondre_a_l_etape(source, p, regles, question, valeurs)
    if question["type"] == "heure_proposee":
        return await _repondre_a_l_heure_proposee(source, p, regles, appelant, question, sens, texte, ex)
    if sens == "refuse" and not texte:
        return Resultat("OK", {"rien_ajoute": True}, "")
    article_dit = question.get(CLE_ARTICLE_DIT) if question["type"] == "ambiguite" else None
    if isinstance(article_dit, dict):
        return await _repondre_a_l_hesitation(source, p, regles, question, article_dit, sens, texte)
    choix = texte or (question.get("choix") or [None])[0] if sens == "accepte" else texte
    return await moteur.repondre_a_un_choix(source, p, regles, choix=choix, sans=None, note=None, moities=None)


def _article_avec_l_option_choisie(article_dit: dict[str, Any], option_dite: str, choisie: str) -> dict[str, Any]:
    """T1 : l'article dit, l'option en doute (« perles ») remplacée par celle que la personne a choisie (« Perles de tapioca ») ; sans mot à remplacer, elle est ajoutée aux choix."""
    voulue = norme_de_recherche(option_dite)

    def remplacer(liste: list[Any]) -> tuple[list[Any], bool]:
        sortie = [choisie if voulue and voulue in norme_de_recherche(str(x)) else x for x in liste]
        return sortie, sortie != liste

    composition, c1 = remplacer(list(article_dit.get("composition") or []))
    supplements, c2 = remplacer(list(article_dit.get("supplements") or []))
    if not (c1 or c2):
        composition = [*composition, choisie]
    return {**article_dit, "composition": composition, "supplements": supplements}


async def _repondre_a_l_hesitation(source: Source, p: dict[str, Any], regles: moteur.Reglages, question: dict, article_dit: dict, sens: str | None,
                                   texte: str | None) -> Resultat:
    """D24 (note de Pierre du 20/11, point 2 ; appel 2670) : la réponse à « Vous voulez dire : X ? » ajoute l'article choisi avec ce qui avait été dit
    (quantité, choix, retraits). « oui » seul ne vaut que s'il n'y a qu'un candidat ; un nom dit est cherché à son tour ; sinon la question reste posée.
    Le code ne devine jamais entre plusieurs candidats. Lot 19 bis : T1 (l'hésitation sur une OPTION range l'option choisie sur l'article dit), T2 (un texte qui ne
    nomme aucun candidat n'est un article que si la carte le trouve : « oui » écrit n'est jamais un article), T4 (ce qui était dit avec le nom est rejoué)."""
    choix = [str(c) for c in question.get("choix") or []]
    option_dite = question.get(moteur.CLE_OPTION_DITE)
    nom = None
    if texte:
        # B5 (N1) : un seul juge de « quel article ce texte désigne » : le nom égal sous la norme de la recherche, sinon la recherche elle-même
        from api.db.bases_clients.recherche_liste import normaliser

        nom = next((c for c in choix if normaliser(c) == normaliser(texte)), None)
        if nom is None and not option_dite:
            trouve = await source.chercher(texte)  # un autre article de la carte, nommé : la carte le confirme, jamais un mot de la réponse
            nom = texte if trouve.statut == "RETENU" else None
    elif sens == "accepte" and len(choix) == 1:
        nom = choix[0]
    if nom is None:
        return Resultat("OK", {"rien_ajoute": True}, "")
    if option_dite:
        return await ajouter_un_article(source, p, regles, _article_avec_l_option_choisie(article_dit, str(option_dite), nom))
    # B5 (N1, D03) : ce que la personne a glissé dans le nom n'est jamais deviné par le code (la liste des mots de liaison est retirée) : l'article
    # choisi est ajouté avec ce que le modèle a rangé dans ses cases (composition, suppléments), par son identifiant quand il est un candidat
    ref = next((c.get("id") for c in reversed(question.get(moteur.CLE_CANDIDATS) or []) if isinstance(c, dict) and c.get("libelle") == nom), None)
    return await ajouter_un_article(source, p, regles, {**article_dit, "article": nom, **({moteur.CLE_REF_CHOISIE: ref} if ref else {})})


async def _repondre_a_l_heure_proposee(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, question: dict,
                                       sens: str | None, texte: str | None, ex: Execution) -> Resultat:
    """Aparté d'Evan (20/11) : « Je vous la prépare pour dix-huit heures ? ». « oui » pose l'heure proposée ; une autre heure dite est posée à sa place ;
    « non » sans heure : on demande laquelle. L'heure posée, la commande va à sa relecture (comme après « c'est tout »)."""
    heure = texte or (question.get("heure") if sens == "accepte" else None)
    if not heure and sens == "autre":
        return Resultat("OK", {"rien_ajoute": True}, "")  # file d'attente : « autre » (elle dit ses pizzas) garde la question posée
    if not heure:
        faits = {"heure_manquante": True}
        return Resultat("INCOMPLETE", faits, TS.pour_quel_jour_alors(faits), "heure_voulue")
    r = await moteur.poser_l_heure(source, p, str(heure))
    if r is not None:
        return r
    if not ETAPE.c_est_tout_dit(p):
        # Evan, 21/11 : proposée dès le début (fermé), l'heure posée, la commande se prend comme d'habitude ; la relecture ne vient qu'après « c'est tout »
        return Resultat("OK", {"heure_voulue": p.get("heure_voulue")}, "")
    return Resultat("OK", {"heure_voulue": p.get("heure_voulue")}, "")  # la commande va à sa relecture à la fin de la fiche (``_mener_a_la_fin_de_la_fiche``)


async def repondre_a_l_etape(source: Source, p: dict[str, Any], regles: moteur.Reglages, question: dict, valeurs: list[str] | None) -> Resultat:
    """FOR2 (B10) : la réponse à une question d'étape, dans ``valeurs`` : une seule valeur (``plusieurs_choix`` sinon, ``choix_manquant`` sans valeur), rangée sur
    l'étape de la question et sur elle seule ; la question reste posée sur un refus."""
    dites = [str(v).strip() for v in valeurs or [] if str(v).strip()]
    if not dites:
        return Resultat("HORS_CARTE", {"raison": "choix_manquant", "question": question["id"], "choix": question.get("choix") or []}, "")
    if len(dites) > 1:
        return Resultat("HORS_CARTE", {"raison": "plusieurs_choix", "question": question["id"], "valeurs": dites}, "")
    return await moteur.repondre_a_un_choix(source, p, regles, choix=dites[0], sans=None, note=None, moities=None)


CLE_ARTICLE_DIT = RQ.CLE_ARTICLE_DIT  # D24 : l'article de la fiche gardé avec une question d'hésitation
QUESTIONS_SUR_UN_ARTICLE = ("variante", "ambiguite", formule_a_etapes.TYPE_DE_LA_QUESTION)


async def _article_redit_pendant_son_doute(source: Source, regles: moteur.Reglages, fiche: dict[str, Any], question: dict | None) -> int | None:
    """Le rang de l'entrée d'``ajouter`` qui REDIT l'article en doute de la question ouverte, ou ``None``. Constaté sur la carte, jamais sur les mots : même ensemble de
    candidats que la question, et mêmes précisions (quantité, variante, choix) que l'article gardé avec elle ; une précision de plus en fait un autre article."""
    if not question or question.get("type") != "ambiguite" or not isinstance(question.get(CLE_ARTICLE_DIT), dict):
        return None
    dit = question[CLE_ARTICLE_DIT]
    choix = {str(c).casefold() for c in question.get("choix") or []}

    def _precisions(a: dict) -> dict:
        return {k: v for k, v in a.items() if k != "article" and v not in (None, "", [], {})}

    for rang, a in enumerate(fiche.get("ajouter") or []):
        if not isinstance(a, dict) or not str(a.get("article") or "").strip() or _precisions(a) != _precisions(dit):
            continue
        trouve = await moteur.chercher_l_article(source, str(a["article"]), regles)
        candidats = {str(c.get("libelle") if isinstance(c, dict) else c).casefold() for c in (trouve.faits or {}).get("candidats") or []}
        if trouve.statut != "RETENU" and candidats and candidats == choix:
            return rang
    return None


async def garde_article_deja_en_question(source: Source, p: dict[str, Any], regles: moteur.Reglages, fiche: dict[str, Any],
                                         question: dict | None, refs_en_attente: set) -> tuple[dict[str, Any] | None, set[int]]:
    """Lot 19, D01 (FOR10-B, OPT8-B, n7 de B12) : la fiche répond à la question ouverte sur un article ET remet ce même article dans ``ajouter`` :
    la réponse le complète déjà ; la case ``ajouter`` est refusée avec la raison, rien n'est ajouté deux fois. Critère sur l'état (la ligne en attente,
    les choix de la question), jamais sur les mots (D1) ; le code ne devine pas un second exemplaire, il se dit après avec sa quantité.
    Rend le refus et les RANGS des articles refusés de ``ajouter`` : les autres articles de la case entrent (RC2 : « oui » + une margherita en doute + une regina, la regina n'est jamais perdue)."""
    reponse = fiche.get("reponse")
    redit = await _article_redit_pendant_son_doute(source, regles, fiche, question) if p.get("mode") else None
    # une réponse DITE par le modèle (même « autre ») est le choix de ne pas répondre à la question et d'ajouter un autre article ; seule la fiche sans réponse
    # (``implicite``) repose le même article : le même doute n'ouvre jamais une seconde question (RC9), l'article n'entre pas deux fois
    if redit is not None and (not isinstance(reponse, dict) or reponse.get("implicite")):
        dit = question[CLE_ARTICLE_DIT]
        return B.refus("article_deja_en_question", ["ajouter"], article=str(dit.get("article")), question=question.get("id"),
                       a_faire=f"rien n'est ajouté de {dit.get('article')} : il est déjà en question ({question.get('id')}) ; attends sa réponse"), {redit}
    if not question or not isinstance(reponse, dict) or not p.get("mode"):
        return None, set()
    if question.get("type") not in QUESTIONS_SUR_UN_ARTICLE and question.get("type") != "proposition":
        return None, set()
    valeurs = [str(v).strip() for v in reponse.get("valeurs") or [] if str(v).strip()]
    if not valeurs and reponse.get("sens") != "accepte":
        return None, set()  # une réponse qui ne choisit rien (« autre ») ne complète rien : l'article nommé est un article de plus, jamais un doublon
    choix = [str(c).strip() for c in question.get("choix") or [] if str(c).strip()]
    # B4 (M6, point 2 ; C9, trace 515) : ce que la réponse complète est CONSTATÉ, jamais supposé : le choix qu'elle nomme (ou le premier, sur un
    # « oui » sans mot) ; une réponse dont les mots ne nomment aucun choix ne complète rien, l'article remis n'est pas refusé
    nommes = {c.casefold() for c in choix if any(v.casefold() == c.casefold() for v in valeurs)}
    if not valeurs and choix:
        nommes = {choix[0].casefold()}
    propose = str(question.get("article_propose") or "").casefold()
    premier: dict[str, Any] | None = None
    doubles: set[int] = set()
    for rang, a in enumerate(fiche.get("ajouter") or []):
        nom = str(a.get("article") or "").strip()
        trouve = await moteur.chercher_l_article(source, nom, regles) if nom else None
        article = await source.article(trouve.faits["retenu"], p["mode"]) if trouve is not None and trouve.statut == "RETENU" else None
        if article is None:
            continue
        nom_carte = str(article.get("nom") or "").casefold()
        double = ((question.get("type") == "proposition" and reponse.get("sens") == "accepte" and bool(propose) and nom_carte.startswith(propose))
                  or (question.get("type") != "proposition" and article.get("id") in refs_en_attente)
                  or (question.get("type") == "ambiguite" and nom_carte in nommes))
        if double:  # B4 (M6, appel 530) : « oui » au Coca proposé ET un Coca dans ajouter : un seul Coca
            doubles.add(rang)
            premier = premier or B.refus("article_deja_en_question", ["ajouter"], article=article["nom"], question=question.get("id"),
                                         a_faire=f"rien n'est ajouté de {article['nom']} : ta réponse à {question.get('id')} le complète déjà ; "
                                                 "un second exemplaire se dit après, avec sa quantité")
    return premier, doubles


async def gardes_de_la_formule(source: Source, p: dict[str, Any], regles: moteur.Reglages, articles: list[dict[str, Any]]) -> dict[str, Any] | None:
    """B10 § 2 et B11 § 2 (point 6) : dans la MÊME fiche, un article qui est aussi le choix d'une étape d'une formule de la fiche (déjà rangé dans sa
    composition, ou d'une étape encore ouverte) n'est pas ajouté : refus de la fiche avec la raison et les deux choix ; le code ne devine pas. ``None`` : aucun conflit."""
    if not p.get("mode") or (len(articles) < 2 and not any(a.get("variante") for a in articles)):
        return None
    lus = []
    for a in articles:
        nom = str(a.get("article") or "").strip()
        trouve = await moteur.chercher_l_article(source, nom, regles) if nom else None
        article = await source.article(trouve.faits["retenu"], p["mode"]) if trouve is not None and trouve.statut == "RETENU" else None
        lus.append((a, nom, article))
    for a, _, article in lus:
        if article and article.get("formule") and a.get("variante") and FO.sans_declinaison(article):
            # conversations FOR12 du lot 11 : « Bouteille » mis en variante d'une formule qui n'a pas de taille ; refusé, jamais « Quelle taille : Menu partage ? »
            return B.refus("formule_sans_variante", ["ajouter"], article=article["nom"], variante=a["variante"],
                           a_faire="cette formule n'a ni taille ni nombre de personnes : refais la fiche sans variante, ce qu'elle a choisi va dans composition")
    formules = [(article, [*(a.get("composition") or []), *(a.get("supplements") or [])]) for a, _, article in lus if article and article.get("formule")]
    for a, nom, article in lus:
        if not nom or (article and article.get("formule")):
            continue
        for formule, mots in formules:
            refus = FO.article_deja_choix_de_la_formule(formule, mots, nom) or FO.article_aussi_choix_d_une_etape(formule, mots, nom)
            if refus is not None:
                return B.refus(refus.pop("raison"), ["ajouter"], **refus)
    return None


def poser_la_ligne_retiree(retour: dict[str, Any]) -> DU.Du | None:
    """Une ligne entière retirée de la commande est un fait qui engage (la parole ne dit pas « c'est fait » seule) : la porte le pose, d'après la case de SON contrat."""
    return DU.Du(faits_qui_engagent=(DU.RETRAIT_D_UNE_LIGNE,)) if "retirer_article" in (retour.get("cases_executees") or []) else None


def poser_le_prix_du_poids(ctx: Any, resultats: list[dict[str, Any]]) -> DU.Du | None:
    """QTE1 (D33) : le prix d'un article au poids est dit par le code après la phrase du modèle (suffixe) ; rend l'élément de ``Du`` (un prix à dire après), jamais la phrase. ⛔ Ne lève jamais."""
    du = None
    try:
        for r in resultats:
            faits = r.get("faits") or {}
            phrase = faits.pop("prix_a_dire", None)
            if phrase and isinstance(getattr(ctx, "fiche", None), dict):
                ctx.fiche.setdefault(CLE_TEXTES_DU_CODE, {})["suffixe"] = phrase
                du = DU.Du(prix_apres=True)
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] commande : le prix du poids n'a pas pu être posé")
    return du


async def poser_la_remise_du_code(ctx: Any, source: Any, p: dict[str, Any], regles: Any) -> DU.Du | None:
    """OFF3 (conversation OFF3-A, D33) : la remise à laquelle un code dit donne droit est dite PAR LE CODE, une fois, au moment où elle s'applique au panier (le code dit d'abord, ou les
    articles d'abord), après la phrase du modèle ; rend l'élément de ``Du`` (un prix à dire après), jamais la phrase. Sans cela la personne qui a dit son code n'entendait jamais que la remise était prise.
    ⛔ Ne lève jamais."""
    try:
        if not p.get("remises_du_code") or p.get("enregistree") or p.get("annulee") or not isinstance(getattr(ctx, "fiche", None), dict):
            return None
        if not (p["lignes"] and p["mode"]) or P.a_completer(p):
            return None
        chiffre = await moteur.chiffrer_le_panier(source, p, regles)
        if chiffre.statut != "OK":
            return None
        nouvelles = [r for r in chiffre.faits.get("remises") or [] if r["ref"] in p["remises_du_code"] and J.une_fois(p, moteur.cle_de_la_remise(r["ref"]))]
        if not nouvelles:
            return None
        textes = ctx.fiche.setdefault(CLE_TEXTES_DU_CODE, {})
        textes["suffixe"] = " ".join(x for x in (textes.get("suffixe"), *(moteur.phrase_d_une_remise_appliquee(r) for r in nouvelles)) if x)
        return DU.Du(prix_apres=True)
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] commande : la remise du code n'a pas pu être posée")
    return None


def poser_les_regles_de_l_article(resultats: list[dict[str, Any]], retour: dict[str, Any], p: dict[str, Any]) -> DU.Du | None:
    """FOR7, FOR9, FOR13 (conversations du lot 11) : la condition, le justificatif ou ce qui est servi avec un article ajouté sont des faits du retour (``regles_a_dire``) que le modèle
    dit avec ses mots, une seule fois par appel (le journal de ce qui est dit). ⛔ Ne lève jamais."""
    try:
        a_dire = [regle for r in resultats if isinstance(f := r.get("faits"), dict) and f.get("regle_a_dire") for regle in f.pop("regle_a_dire")]
        nouvelles = [x["fait"] for x in {r["id"]: r for r in a_dire}.values() if J.une_fois(p, f"regle:{x['id']}")]  # B3 (M5) : une fois par appel, au journal, par identifiant
        if not nouvelles or not isinstance(retour.get("faits"), dict):
            return None
        retour["faits"]["regles_a_dire"] = nouvelles
        return DU.Du(consignes=((C.REFUS_A_DIRE, A_FAIRE_DE_LA_REGLE),))
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] commande : la règle de l'article n'a pas pu être posée")
    return None


def poser_la_regle_de_la_ligne(resultats: list[dict[str, Any]], retour: dict[str, Any]) -> DU.Du | None:
    """FOR3 (B11 point 2, D33) : un choix refusé hors d'une ligne limitée par un prix : la règle est un fait du retour (``regle_de_la_ligne``) que le modèle dit avec ses mots ; rend
    l'élément de ``Du``. ⛔ Ne lève jamais."""
    try:
        for r in resultats:
            faits = r.get("faits") or {}
            if faits.get("raison") == ligne_de_formule_limitee.RAISON and faits.get("regle_prix_max") and isinstance(retour.get("faits"), dict):
                formule = str(faits.get("article") or "")
                retour["faits"]["regle_de_la_ligne"] = ligne_de_formule_limitee.fait_de_la_regle(formule, str(faits.get("etape") or ""), int(faits["regle_prix_max"]))
                faits.pop("regle_prix_max", None)
                return DU.Du(consignes=((C.REFUS_A_DIRE, A_FAIRE_DE_LA_REGLE),))
    except Exception:  # noqa: BLE001
        logger.exception("[.mark] commande : la règle de la ligne n'a pas pu être posée")
    return None


async def ajouter_un_article(source: Source, p: dict[str, Any], regles: moteur.Reglages, article: dict[str, Any]) -> Resultat:
    """Un article de la case ``ajouter``, structuré (sans phrase à redécouper) : la cuisine le prend ou le met en attente du préalable."""
    return await moteur.ajouter_un_article(source, p, regles, article)


async def vente_en_plus_apres_le_premier_article(source: Source, p: dict[str, Any], regles: moteur.Reglages, r: Resultat) -> Resultat | None:
    """Juste après le premier article pris, la proposition en plus de la cuisine (``moteur.proposer_un_article_en_plus``, une fois par commande ;
    note de Pierre, méthode Domino's) : sa réponse laisse la commande continuer, jamais un saut vers la fin."""
    if r.statut != "OK":
        return None
    proposition = await moteur.proposer_un_article_en_plus(source, p, regles)
    if proposition is None:
        return None
    if isinstance(p.get("proposition_en_plus"), dict):
        p["proposition_en_plus"]["tot"] = True  # n° 46 bis : faite juste après le premier article, elle porte son moment ; elle tombe avec elle
    return Resultat("OK", {**r.faits, **proposition.faits}, proposition.suggestion, "vente_en_plus")


async def poser_le_mode(source: Source, p: dict[str, Any], regles: moteur.Reglages, mode: str | None, adresse: str | None, commune: str | None) -> Resultat | None:
    """Le mode, l'adresse et la commune posés par la MÊME opération (S3) : jamais une adresse sans son mode, jamais l'adresse avalée ailleurs."""
    r = None
    if mode:
        r = await moteur.choisir_mode(source, p, regles, mode)
    if adresse and not commune:
        # la rue dite après la commune (« à Chantilly », puis « au 9 avenue du Bouteiller ») : la commune déjà posée reste celle de l'adresse
        commune = ((p.get("adresse") or {}).get("commune") if isinstance(p.get("adresse"), dict) else None) or p.get("commune_dite")
    if adresse or commune:
        r = await moteur.verifier_adresse(source, p, regles, adresse, commune)
    return r


# B1 (clôture) : les trois exceptions du lot 20 devant la barrière « réponse manquante » (numéro dicté, heure dite, changement pendant la relecture) sont
# retirées : une fiche sans ``reponse`` vaut « autre » pour la question posée, pour tous les types (``registre.reponse_implicite``).


async def executer_la_fiche(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    """La fiche du modèle exécutée par le code, dans son ordre ; rend l'enveloppe (statut, résultats, question numérotée, refus et ``a_faire``).
    Lot 3 (mécanisme X) : LIRE la fiche, l'APPLIQUER case par case, la CONCLURE ; UN SEUL ``finaliser`` par fiche (C7), porté par ``Execution``, plus de variable de contexte."""
    ex = Execution()
    try:
        return await _executer_la_fiche(fiche_du_modele, contexte, ex)
    except Exception as erreur:
        erreur.cases_executees = list(ex.executees)  # RC13 : le gestionnaire d'erreurs de l'outil les dit au retour
        raise


RIEN_CHANGE = DU.RIEN_CHANGE


def seul_autre_chose_manque(p: dict[str, Any]) -> bool:
    """DC6 : la commande a ses articles, rien n'attend, et ce qui manque ensuite n'est que « autre chose, ou c'est tout » (avant la relecture)."""
    from api.services.commande import etat_pour_le_modele as E

    if CONV.question_de(p) is not None:
        return False
    return E.ce_qui_manque(p, p.get(E.CLE_CONNU) or {})[0] is Manque.AUTRE_CHOSE


def _relecture_a_relancer(p: dict[str, Any], question_avant: dict | None, avant: str, executees: list[str]) -> bool:
    """n° 8 : la relecture posée a cessé de valoir pendant la fiche (l'étape est passée de « à relire » à « en cours » et le panier n'est plus celui qu'elle a lu) :
    elle repart. Lu dans l'étape, plus décidé d'après une empreinte comparée à la fin de la boucle."""
    return ((question_avant or {}).get("type") == "relecture" and avant == ETAPE.A_RELIRE and ETAPE.courante(p) == ETAPE.EN_COURS
            and not CONV.question_de(p) and "c_est_tout" not in executees and bool(p.get("mode")) and bool(P.lignes_pretes(p)))


def _accord_a_redonner(p: dict[str, Any], etat_avant: str) -> bool:
    """L'accord vaut (étape « accordée »), ou valait au début de la fiche et un changement du panier l'a retiré pendant elle (la relecture repart, sauf derrière un doute :
    elle se refait à « c'est tout »). Lu dans l'étape ; la commande finie n'a plus d'accord à redonner."""
    if ETAPE.finie(p):
        return False
    return ETAPE.accord(p) or (etat_avant == ETAPE.ACCORDEE and ETAPE.courante(p) == ETAPE.EN_COURS and not RQ.question_en_doute(p))


def _dire_c_est_tout(p: dict[str, Any], q: dict | None, executees: list[str]) -> None:
    """n° 45 : « c'est tout » est dit mais la relecture attend l'heure proposée : l'étape le dit (plus un drapeau posé sur la question)."""
    if q is not None and q.get("type") == "heure_proposee" and "c_est_tout" in executees and ETAPE.courante(p) in (ETAPE.EN_COURS, ETAPE.A_CLORE):
        ETAPE.transition(p, ETAPE.C_EST_TOUT_DIT)


@dataclass
class Execution:
    """Ce que UNE fiche a fait, porté explicitement de bout en bout (lot 3, mécanisme X).
    ``executees`` : les cases déjà exécutées ; si une case lâche (panne), le retour les DIT, le panier a pu changer, jamais en silence (RC13)."""

    executees: list[str] = field(default_factory=list)


@dataclass
class LaFiche:
    """La fiche LUE (ce qu'elle dit, ce que le code refuse, ce qui est déjà fait) puis APPLIQUÉE case par case, puis CONCLUE. Un seul objet, passé aux étapes."""

    ctx: Any
    ex: Execution
    fiche: dict[str, Any]
    tour: int = 0
    reponse: dict[str, Any] | None = None
    reponse_ecartee: dict | None = None
    case_ecartee: dict | None = None
    refus: list[dict] = field(default_factory=list)
    ecartees: set[str] = field(default_factory=set)
    deja_faites: set[str] = field(default_factory=set)
    question_avant: dict | None = None
    phase_d_avant: str = ""
    etat_avant: str = ""
    avant_enregistree: dict | None = None
    garde_en_question: dict | None = None
    reponse_sans_objet: bool = False
    informations_faites: bool = False
    resultats: list[dict] = field(default_factory=list)
    bruts: list[Resultat] = field(default_factory=list)  # les résultats des opérations de la fiche, dans l'ordre : ``refusants_de_la_fiche`` et ``heures_a_dire`` les lisent
    dernier: Resultat | None = None

    @property
    def source(self):
        return self.ctx.source

    @property
    def p(self) -> dict[str, Any]:
        return self.ctx.panier

    @property
    def regles(self):
        return self.ctx.regles

    @property
    def appelant(self):
        return moteur.Appelant(numero_e164((self.ctx.appel or {}).get("caller_number")), str(self.ctx.run_id) if getattr(self.ctx, "run_id", None) else None)


async def _executer_la_fiche(fiche_du_modele: dict[str, Any], contexte: Any, ex: Execution) -> dict[str, Any]:
    """Lire, appliquer, conclure ; puis ``constater`` ce que la personne vit de plus qu'avant (B2 : ce qui est dû, à la sortie de toute fiche)."""
    vu_avant = DU.ce_qui_se_voit(contexte.panier)
    retour = await _lire_appliquer_conclure(fiche_du_modele, contexte, ex)
    return DU.constater(retour, vu_avant, contexte.panier, texte_a_dire_du_manque, _seuil_de_sortie(contexte))


async def _lire_appliquer_conclure(fiche_du_modele: dict[str, Any], ctx: Any, ex: Execution) -> dict[str, Any]:
    p = ctx.panier
    CONV.de(p)["tour_de_l_appel"] = int((getattr(ctx, "fiche", None) or {}).get(contrat.CLE_DU_TOUR) or 0)  # lot 15 : l'allergie donnée au modèle dans un tour fini seulement lève le blocage
    if isinstance(getattr(ctx, "fiche", None), dict):
        ctx.fiche[CLE_TEXTES_DU_CODE] = {}  # ceux de la fiche d'avant ne sont jamais redits
        poser_le_fait_bloquant(ctx.fiche, None, None)
    f = await _lire(fiche_du_modele, ctx, ex)
    if isinstance(f, dict):
        return f  # l'enveloppe d'un refus entier, ou d'une fiche déjà faite
    await _appliquer(f)
    await _conclure(f)
    return await _dire(f)


# --------------------------------------------------------------------------- 1. lire

async def _lire_les_cases(ctx: Any, p: dict[str, Any], regles: Any, source: Any, fiche: dict[str, Any]):
    """La fiche entière : lisible, cases montrées dans ce tour (D52), bons types, réponse attendue, bonne question. Rend ``(fiche, réponse écartée, case écartée,
    refus entier)``."""
    entier = B.fiche_illisible(fiche)
    if entier is not None:
        return fiche, None, None, entier
    fiche = {k: v for k, v in fiche.items() if v is not None}
    montrees = _cases_montrees(ctx)
    if montrees is None:
        return fiche, None, None, B.refus("cases_pas_ouvertes", ["*"], reste="les cases de ce tour ne sont pas connues")
    reponse_ecartee = None
    question = CONV.question_de(p)
    posee = contrat.question_posee(question, (ctx.fiche or {}).get(contrat.CLE_DU_TOUR, 0))
    non_a_autre_chose = False
    if isinstance(fiche.get("reponse"), dict) and "reponse" not in montrees:
        # B1 : une réponse quand aucune question n'est montrée (la question est close) : sa case seule est écartée, jamais le reste (conv5)
        # DC6 : un « non » SEUL (rien d'autre à faire dans la fiche que sa phrase) ; « Non, on recommence tout » porte une demande (conv6)
        seul = not any(v not in (None, False, "", [], {}) for k, v in fiche.items() if k not in ("reponse", "a_dire"))
        apres_une_proposition_fermee = RQ.fermee_sans_reponse_au_tour_d_avant(p, "proposition")
        # Pierre F (DC3 avec DC6) : un « non merci » juste après la fermeture d'une proposition (« hein ? ») répond à la proposition que le modèle redit, pas à « autre chose ? »
        non_a_autre_chose = fiche["reponse"].get("sens") == "refuse" and seul and seul_autre_chose_manque(p) and not apres_une_proposition_fermee
        reponse_ecartee = None if non_a_autre_chose else RC.question_inconnue(fiche, None)
        fiche = {k: v for k, v in fiche.items() if k != "reponse"}
    fiche, case_ecartee, entier = B.ecarter_les_cases_sans_objet(fiche, montrees)  # B4 (M9 ; RC2 : l'article dit avec elle n'est plus perdu)
    if non_a_autre_chose and entier is None:
        fiche["c_est_tout"] = True  # DC6 (Evan, 22/11) : « Non merci » à « autre chose ? » (la question du modèle, pas du registre) = la fin de la prise de commande
    entier = entier or B.format(fiche, _schema_de_la_fiche(ctx), montrees) or B.sens_de_la_reponse(fiche)
    if entier is None:
        # B1 : une réponse à une autre question (ou sans question) n'écarte que sa case, jamais le reste de la fiche (RC2) ; la question posée
        # reçoit alors « autre », comme une fiche sans réponse (une seule règle pour tous les types)
        reponse_ecartee = reponse_ecartee or RC.question_inconnue(fiche, question)
        if reponse_ecartee is not None:
            fiche = {k: v for k, v in fiche.items() if k != "reponse"}
        fiche = RQ.reponse_implicite(fiche, question, posee)
    return fiche, reponse_ecartee, case_ecartee, entier


async def _refus_des_cases(f: LaFiche, refus: list[dict]) -> None:
    """Les barrières d'une case (D8 : le filet des cases liées vient après) : plafond, valeurs hors liste, commande déjà enregistrée, conflit sur une ligne,
    valeur pas dans ses mots, relecture pas acceptée."""
    fiche, p, ctx = f.fiche, f.p, f.ctx
    plafond = plafond_d_operations(fiche, lots=await moteur.lots_des_quantites_hautes(f.source, p, f.regles, fiche))
    if plafond is not None:
        refus.append(plafond)
    paroles = list((ctx.fiche or {}).get(CLE_DES_PAROLES) or [])
    dit = list((ctx.fiche or {}).get(CLE_DIT_PAR_LE_CODE) or [])
    for case, choix in (("mode_de_retrait", list(f.source.modes)), ("moyen_de_paiement", list(MOYEN_DE_BASE_SELON_LA_FICHE)), ("moyen_reste", list(MOYEN_DE_BASE_SELON_LA_FICHE))):
        if fiche.get(case) not in (None, ""):
            valeur, r = B.valeur_hors_liste(case, fiche[case], [*choix, contrat.AUTRE])
            if r is not None or valeur == contrat.AUTRE:
                refus.append(r or B.refus("valeur_hors_liste", [case], choix=choix))
            else:
                fiche[case] = valeur
    if p.get("enregistree") and fiche.get("c_est_tout") is True:
        refus.append(B.refus("deja_fait", ["c_est_tout"], reste="la commande de cet appel est déjà enregistrée"))
    visees = [str(n) for n in fiche.get("retirer_article") or []] + [str(c.get("ligne")) for c in fiche.get("changer_quantite") or [] if isinstance(c, dict)]
    doublees = sorted({v for v in visees if visees.count(v) > 1})
    if doublees:
        # B4 (M6, point 1 ; C8, DF8) : deux cases sur la même ligne (« enlevez-la, non mettez-en deux ») se lisent AVANT d'exécuter
        # l'une après l'autre, la seconde échouait (« Il n'y a encore rien dans la commande. ») ; les deux sont refusées, avec la question à poser
        refus.append(B.refus("conflit_sur_une_ligne", [c for c in ("retirer_article", "changer_quantite") if fiche.get(c)],
                             a_faire=f"rien n'est changé sur la ligne {', '.join(doublees)} : elle y a dit deux choses ; demande-lui ce qu'elle veut pour cette ligne"))
    fin_redite = [c for c in contrat.CASES_DE_FIN if fiche.get(c) not in (None, "")]
    if ETAPE.courante(p) == RQ.ENREGISTREE and fin_redite:
        # B4 (M7, table « phase → cases ») : enregistrée, le règlement, le numéro et le prénom ne changent plus rien ; avant, notés en silence et
        # « C'est noté » dit (RC4, E16 → G19)
        refus.append(B.refus("deja_fait", fin_redite, reste="la commande de cet appel est déjà enregistrée"))
    libres = B.valeur_pas_dans_ses_mots(fiche, paroles, dit)
    if libres is not None:
        refus.append(libres)
    accepte_ici = bool(f.reponse and f.reponse.get("sens") == "accepte" and (CONV.question_de(p) or {}).get("type") == "relecture")
    fin = B.recapitulatif_pas_accepte(fiche, contrat.CASES_DE_FIN, ETAPE.accord(p), accepte_ici)
    if fin is not None:
        refus.append(fin)


def _cases_qui_changent(fiche: dict[str, Any]) -> list[str]:
    return [c for c in (*contrat.CASES_QUI_CHANGENT_LA_COMMANDE, "c_est_tout", *contrat.CASES_DE_FIN) if fiche.get(c) not in (None, "", [], {}, False)]


def _refus_de_la_commande_annulee(f: LaFiche) -> None:
    """DC5 (Evan, 22/11) : la commande annulée n'existe plus ; rien n'y entre ; le code le dit et propose d'en passer une nouvelle."""
    repart = bool(f.reponse and f.reponse.get("sens") == "accepte" and (CONV.question_de(f.p) or {}).get("type") == RQ.TYPE_NOUVELLE_COMMANDE)  # B1 : la réponse écartée n'écarte rien d'autre
    if ETAPE.courante(f.p) == RQ.ANNULEE and not repart:
        dites = _cases_qui_changent(f.fiche)
        if dites:
            f.refus.append(B.refus("commande_annulee", dites, reste="la commande est annulée ; une nouvelle commande est proposée à la personne : dis-le avec tes mots (la commande est annulée, rien ne s'y ajoute, veut-elle en passer une nouvelle ?) et attends sa réponse"))
            RQ.proposer_une_nouvelle_commande(f.p)


def _refus_de_la_commande_annulee_dans_la_fiche(f: LaFiche, refusees_en_propre: set[str]) -> None:
    """DC5 et RC8 (Evan, 22/11) : annulée DANS cette fiche (« annulez », ou le « oui » à l'annulation d'une commande enregistrée, RC4), la commande n'existe plus,
    comme si elle l'était déjà : ni article, ni mode, ni « c'est tout » de la même fiche n'y entrent ; le code dit l'annulation. Ces cases sont écartées à part : un
    refus ordinaire écarterait aussi l'annulation (``DEPEND_DE_TOUT``), qui est justement ce que la personne a demandé."""
    p, fiche, reponse = f.p, f.fiche, f.reponse
    if fiche.get("annuler_la_commande") is True and ETAPE.courante(p) != RQ.ANNULEE and "*" not in f.ecartees and "annuler_la_commande" not in refusees_en_propre:
        f.ecartees.discard("annuler_la_commande")  # le refus d'une autre case (le règlement avant l'accord de la relecture) n'annule pas l'annulation voulue
        dites = _cases_qui_changent(fiche)
        if dites:
            f.refus.append(B.refus("commande_annulee", dites, pour=True, reste="ces cases : la commande vient d'être annulée ; le code le dit, attends la réponse de la personne"))
            f.ecartees |= set(dites)
    if ((CONV.question_de(p) or {}).get("type") == RQ.TYPE_ANNULATION and reponse and reponse.get("sens") == "accepte"
            and ETAPE.courante(p) == RQ.ENREGISTREE and "*" not in f.ecartees):
        dites = _cases_qui_changent(fiche)
        if dites:
            f.refus.append(B.refus("commande_annulee", dites, pour=True, reste="ces cases : la commande vient d'être annulée ; le code le dit, attends la réponse de la personne"))
            f.ecartees |= set(dites)


async def _lire_ce_qui_est_deja_pose(f: LaFiche) -> None:
    """L'état d'AVANT la fiche (la question posée, le panier d'avant, l'étape) et ce que la fiche ne peut pas faire : une réponse déjà sans objet, un article déjà en question."""
    p, fiche, source, regles = f.p, f.fiche, f.source, f.regles
    f.question_avant = CONV.question_de(p)
    if f.question_avant is not None and RQ.objet(f.question_avant, p) not in (CONV.de(p).get(RQ.CLE_DES_QUESTIONS) or {}):
        RQ.ouvrir(p, f.question_avant)  # B1 : la question posée est au registre (un état d'avant le registre, ou posée hors de lui)
    f.avant_enregistree = copy.deepcopy(p) if moteur.commande_de_l_appel(p) is not None else None  # E10 : le panier d'avant, si le changement ne passe pas
    f.phase_d_avant = ETAPE.courante(p)  # n° 25 : la phase avant cette fiche (une commande déjà enregistrée : un changement se dit, une réponse non)
    CONV.poser_question(p, None if f.reponse else f.question_avant)
    f.etat_avant = ETAPE.courante(p)  # n° 8 et n° 45 : l'étape d'AVANT la fiche ; ce que la fiche change se lit dans l'étape d'après
    # D01 : calculée AVANT la réponse, tant que la ligne qu'elle complète est encore en attente
    f.garde_en_question, doubles = await garde_article_deja_en_question(source, p, regles, fiche, f.question_avant, {l.get("ref") for l in P.a_completer(p)})
    if f.garde_en_question is not None and doubles and len(doubles) < len(fiche.get("ajouter") or []):
        # RC2 : seuls les articles déjà en question sont refusés ; les autres de la même case entrent
        f.refus.append(f.garde_en_question)
        f.fiche = {**fiche, "ajouter": [a for i, a in enumerate(fiche["ajouter"]) if i not in doubles]}
        f.garde_en_question = None
    # n° 42 : la question en attente portait sur le panier que cette même fiche vide ou annule : la réponse n'a plus d'objet. Lu dans la fiche, avant d'exécuter.
    f.reponse_sans_objet = bool(f.reponse and "reponse" not in f.ecartees and "*" not in f.ecartees and any(
        f.fiche.get(c) not in (None, "", [], False) and c not in f.ecartees and c not in f.deja_faites for c in ("vider_le_panier", "annuler_la_commande")))
    if f.reponse_sans_objet:
        f.refus.append(B.refus("question_inconnue", ["reponse"], pour=True, reste="reponse : la question en attente a disparu avec le panier"))


async def _lire(fiche_du_modele: dict[str, Any], ctx: Any, ex: Execution) -> LaFiche | dict[str, Any]:
    """Lire la fiche : ce qu'elle dit, ce que le code en refuse, ce qui est déjà fait. Rien n'est exécuté. Rend le plan, ou l'enveloppe d'un refus entier."""
    p = ctx.panier
    fiche, reponse_ecartee, case_ecartee, entier = await _lire_les_cases(ctx, p, ctx.regles, ctx.source, fiche_du_modele)
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier], "cases_refusees": entier["cases"],
                                                                                              "fiche_appliquee": False}).vers_json()
    tour = (ctx.fiche or {}).get(contrat.CLE_DU_TOUR, 0)
    if deja_executee(p, cle_d_idempotence(tour, "fiche", fiche)):  # rejouée à l'identique dans ce tour : rien ne change (E11)
        return Enveloppe("FAIT", faits={"deja_fait": True}, plus={"fiche_appliquee": False, "rien_ajoute": True}).vers_json()
    f = LaFiche(ctx=ctx, ex=ex, fiche=fiche, tour=tour, reponse_ecartee=reponse_ecartee, case_ecartee=case_ecartee,
                reponse=fiche.get("reponse") if isinstance(fiche.get("reponse"), dict) else None)
    f.refus = [x for x in (reponse_ecartee, case_ecartee) if x is not None]
    await _refus_des_cases(f, f.refus)
    _refus_de_la_commande_annulee(f)
    propres = [c for r in f.refus if r is not reponse_ecartee and r is not case_ecartee for c in r["cases"]]
    f.ecartees = cases_ecartees(propres)
    _refus_de_la_commande_annulee_dans_la_fiche(f, set(propres))
    # B4 (M6, point 3) : une case déjà faite dans ce tour, à l'identique (la fiche refaite après un refus partiel), n'est pas refaite
    f.deja_faites = {c for c, v in f.fiche.items() if c not in f.ecartees and case_deja_faite(p, tour, c, v)}
    await _lire_ce_qui_est_deja_pose(f)
    return f


# --------------------------------------------------------------------------- 2. appliquer

async def _case_reponse(f: LaFiche) -> tuple[Resultat, str | None]:
    r = await repondre_a_la_question(f.source, f.p, f.regles, f.appelant, f.question_avant or {}, f.reponse.get("sens"), f.reponse.get("valeurs"), f.ex)
    if not RC.repondu(RQ.TABLE, f.p, f.question_avant, f.reponse.get("sens"), r, f.reponse.get("valeurs")):  # n° 7 : la table du métier dit si cette réponse ferme la question (son numéro reste à son objet)
        r = replace(r, faits={**(r.faits or {}), "question_gardee": True})  # ce que le modèle recevait avant 7a : la question reste posée ; tiré du registre, jamais posé par la réponse
    if (f.question_avant or {}).get("type") in ("variante", "ambiguite", formule_a_etapes.TYPE_DE_LA_QUESTION):
        # l'article complété par la réponse est pris : la vente en plus suit, comme après un ajout
        f.resultats.append(_resultat_public("reponse", r))
        proposition = await vente_en_plus_apres_le_premier_article(f.source, f.p, f.regles, r)
        if proposition is None:
            f.dernier = r
            return r, None
        return proposition, "proposition"
    return r, "reponse"


def _garder_le_refus(f: LaFiche, r: Resultat) -> None:
    """Une case qui boucle sur plusieurs lignes (retirer, changer une quantité) : chaque refus est gardé, pas seulement le dernier, pour que ``refusants_de_la_fiche`` les dise tous."""
    if r.statut in STATUTS_QUI_REFUSENT:
        f.bruts.append(r)


async def _case_retirer(f: LaFiche) -> tuple[Resultat, None]:
    for n in f.fiche["retirer_article"]:
        r = await moteur.retirer(f.source, f.p, f.regles, ligne=str(n))
        f.resultats.append(_resultat_public("retirer_article", r))
        _garder_le_refus(f, r)
    f.dernier = r
    return r, None


async def _case_changer_quantite(f: LaFiche) -> tuple[Resultat, None]:
    for c in f.fiche["changer_quantite"]:
        choix = ", ".join([*(c.get("supplements") or []), *(c.get("composition") or [])]) or None
        variante = c.get("variante") if c.get("variante") not in (None, "", "autre") else None
        r = await moteur.modifier(f.source, f.p, f.regles, ligne=str(c.get("ligne")), quantite=c.get("quantite"), choix=choix, variante=variante,
                                  sans=", ".join(c.get("sans") or []) or None, note=c.get("precision_article"))
        f.resultats.append(_resultat_public("changer_quantite", r))
        _garder_le_refus(f, r)
    f.dernier = r
    return r, None


def _le_doute_est_leve_par_un_candidat(f: LaFiche, r: Resultat) -> bool:
    """Pierre 7 : la personne nomme un des candidats du doute, sans répondre à sa question : le doute est levé (« c'est tout » n'attend plus). Le candidat est reconnu par
    son identifiant (ceux que la question a gardés, ``moteur.CLE_CANDIDATS``), jamais par le début de son nom : « Napolitaine » n'est pas « Napoli » (n° 55)."""
    q = f.question_avant
    if not (r.statut == "OK" and q and q.get("type") == "ambiguite" and not (f.reponse and not f.reponse.get("implicite"))):
        return False
    candidats = {str(c.get("id")) for c in q.get(moteur.CLE_CANDIDATS) or [] if isinstance(c, dict)}
    return any(str(ligne.get("ref")) in candidats for ligne in f.p.get("lignes") or [] if ligne.get("nom") == (r.faits or {}).get("ajoute"))


async def _case_ajouter(f: LaFiche) -> tuple[Resultat, None] | None:
    """Les articles dits, un à un ; chaque article qui demande quelque chose ouvre sa question au registre (D25) ; l'état du panier après les ajouts (chiffrage, minimum de la
    zone) est le résultat du dernier ajout, comme ``moteur.ajouter`` le rend après sa phrase."""
    if f.garde_en_question is not None:
        f.refus.append(f.garde_en_question)  # D01 : la réponse de la même fiche complète déjà l'article remis dans ajouter
        return None
    garde_formule = await gardes_de_la_formule(f.source, f.p, f.regles, list(f.fiche["ajouter"]))
    if garde_formule is not None:
        f.refus.append(garde_formule)  # rien n'est ajouté de cette case : la fiche se refait selon ce qu'elle a dit
        return None
    publics: list[dict[str, Any]] = []
    premiere_demande: Resultat | None = None
    derniere_prise: Resultat | None = None
    place_de_la_prise = -1
    for article in f.fiche["ajouter"]:
        r = await ajouter_un_article(f.source, f.p, f.regles, article)
        publics.append(_resultat_public("ajouter", r))
        if r.statut == "OK":
            derniere_prise, place_de_la_prise = r, len(publics) - 1
        f.bruts.append(r)  # chaque article est un résultat de la fiche : ses refus se lisent sur l'ensemble (``refusants_de_la_fiche``)
        if _le_doute_est_leve_par_un_candidat(f, r):
            RQ.fermer(f.p, f.question_avant)
        if r.statut == "AMBIGU":
            # D24 : l'article dit (quantité, choix) est gardé avec la question d'hésitation, pour que « oui » l'ajoute (jamais montré au modèle)
            r = Resultat(r.statut, {**(r.faits or {}), CLE_ARTICLE_DIT: dict(article)}, r.suggestion, r.manque)
        if r.statut in ("AMBIGU", "CHOIX_OBLIGATOIRE"):
            # D25 : chaque article qui demande ouvre SA question au registre, qui les pose l'une après l'autre : aucun n'est perdu
            RQ.ouvrir(f.p, _question_de(r, 0, f.tour, f.p))
            premiere_demande = premiere_demande or r
    # Le résultat de la fiche ne dépend pas de l'ordre des articles : le premier article qui demande est le fait de la fiche ; sinon, dès qu'un article est pris, c'est l'état du
    # panier après le dernier article PRIS (total, proposition), qu'un refus placé avant ou après ne recouvre pas ; les refus se lisent sur tous les résultats (``refusants_de_la_fiche``)
    r = premiere_demande or derniere_prise or r
    if r.statut == "OK" and "garde" not in (r.faits or {}):
        etat = await moteur.etat_apres_ajout(f.source, f.p, f.regles, dict(r.faits or {}))
        r = Resultat(etat.statut, etat.faits, etat.suggestion, etat.manque)
        publics[place_de_la_prise] = _resultat_public("ajouter", r)  # le dernier article pris dit l'état du panier ; construit avant d'entrer dans la liste, jamais réécrit après coup
    f.resultats.extend(publics)
    proposition = await vente_en_plus_apres_le_premier_article(f.source, f.p, f.regles, r)
    if proposition is not None:
        f.resultats.append(_resultat_public("proposition", proposition))
        r = proposition
    f.dernier = r
    return r, None


async def _case_c_est_tout(f: LaFiche) -> tuple[Resultat, str] | None:
    doute = RQ.question_en_doute(f.p)
    if doute:
        # RC10 : on finit ce qui est commencé avant de relire (ordre du registre) : « c'est tout » avec un article encore en doute ne marque pas la
        # relecture comme faite, sans qu'elle soit dite ; la question en doute reste la seule posée, la personne dit « c'est tout » après sa réponse
        f.refus.append(B.refus("a_finir_avant", ["c_est_tout"], question=doute.get("id_pose"),
                               pour=True, reste="c_est_tout : un article est encore en doute ; la question posée vient d'abord, la relecture après"))
        return None
    return Resultat("OK", {}, ""), None  # « c'est tout » est dit : la fin se mène une fois, à la fin de la fiche


async def _case_annuler_enregistree(f: LaFiche) -> tuple[Resultat, str]:
    if moteur.commande_de_l_appel(f.p) is not None and moteur.annulation_possible(f.source):
        # DC4 (Evan, 22/11) : premier temps : la question de confirmation, avec le montant, dite par le code ; rien n'est annulé avant le « oui »
        RQ.demander_l_annulation(f.p)
        return Resultat("OK", {"confirmation_demandee": True}, ""), "annuler_une_commande_enregistree"
    return await moteur.annuler_commande_enregistree(f.source, f.p, f.regles), "annuler_une_commande_enregistree"  # la raison du refus (introuvable, impossible)


async def _appliquer_la_case(f: LaFiche, case: str) -> tuple[Resultat, str | None] | None:
    """Une case, par son opération nommée. ``None`` : rien n'est exécuté. Sinon ``(résultat, opération)`` ; sans opération, la case a déjà rangé ses résultats."""
    if case in INFORMATIONS:
        if f.informations_faites:
            return None
        f.informations_faites = True
        return await _poser_les_informations(f), "informations"
    if case == "vider_le_panier":
        r = await moteur.vider_commande(f.source, f.p, f.regles)
        RQ.tout_fermer(f.p)  # B1 : on recommence : les questions de la commande d'avant tombent avec elle (la proposition comprise)
        return r, case
    if case == "annuler_la_commande":
        r = await annuler(f.source, f.p, f.regles)
        RQ.tout_fermer(f.p)
        return r, case
    if case == "annuler_une_commande_enregistree":
        return await _case_annuler_enregistree(f)
    if case == "reponse":
        return None if f.reponse_sans_objet else await _case_reponse(f)
    cases = {"retirer_article": _case_retirer, "changer_quantite": _case_changer_quantite, "ajouter": _case_ajouter, "c_est_tout": _case_c_est_tout}
    return await cases[case](f) if case in cases else None


def heures_a_dire(f: LaFiche) -> list[Resultat]:
    """D33, D34 : l'heure voulue qui manque encore (fermé mais planifiable : « pour quel jour et à quelle heure ? ») est un fait de la fiche, que le modèle dit avec ses mots ;
    lu sur les résultats de la fiche (même quand une autre opération suit). Le refus d'une heure (créneau) est un refus comme un autre (``refusants_de_la_fiche``). Une question du
    registre déjà posée (la taille) passe avant : celle de l'heure n'est pas posée en plus, l'état la redonne au tour suivant (RC1)."""
    q = CONV.question_de(f.p)
    if q is not None and q["type"] != "heure_proposee":
        return []
    return [r for r in f.bruts if r.manque == "heure_voulue" and not statut_qui_refuse(r.statut) and r.statut not in ("RETENU", "OK")][:1]


async def _appliquer(f: LaFiche) -> None:
    """Les cases dans l'ordre du code, chacune par son opération nommée."""
    for case in ordre_des_cases(f.fiche):
        if case in f.ecartees or "*" in f.ecartees or case in f.deja_faites:
            continue
        sortie = await _appliquer_la_case(f, case)
        if sortie is None:
            continue
        r, operation = sortie
        if operation is not None:
            f.resultats.append(_resultat_public(operation, r))
            f.dernier = r
            f.bruts.append(r)
        f.ex.executees.append(case)


# --------------------------------------------------------------------------- 3. conclure

async def _proposition_apres_les_cases(f: LaFiche) -> None:
    """Les articles gardés faute de mode ou d'adresse sont pris quand la même fiche les pose : la vente en plus suit ce premier article pris ; hors zone, le refus de
    la zone reste le fait de la fiche et la proposition porte la question (B12, conversation 2)."""
    dernier = f.dernier
    if (dernier is not None and dernier.statut in ("OK", "RETENU", "HORS_ZONE") and not dernier.manque and not CONV.question_de(f.p) and "c_est_tout" not in f.ex.executees):
        proposition = await vente_en_plus_apres_le_premier_article(f.source, f.p, f.regles, Resultat("OK", {}, ""))
        if proposition is not None:
            f.resultats.append(_resultat_public("proposition", proposition))
            RQ.ouvrir(f.p, _question_de(proposition, 0, f.tour, f.p))  # sa question est au registre : elle est posée, quel que soit le résultat qui reste celui de la fiche
            if dernier.statut != "HORS_ZONE":
                f.dernier = proposition  # hors zone, le refus reste le fait de la fiche (B12, conversation 2)


async def _changement_apres_l_enregistrement(f: LaFiche) -> None:
    p, avant = f.p, f.avant_enregistree
    if (avant is None or moteur.commande_de_l_appel(p) is None or P.a_completer(p) or P.empreinte(p) == p.get("empreinte_enregistree")):
        return  # une ligne qui attend sa réponse (sa taille) ne part pas : elle part avec sa réponse ; le panier redevenu la commande enregistrée ne change rien ; un panier vidé en diffère (RC8)
    # RC8 : tout retirer d'une commande enregistrée, c'est l'annuler (DC4, M2) : rien ne change, la confirmation est posée
    # E10 : la commande de cet appel, déjà enregistrée, a changé : le changement part en caisse (ou rien ne change, avec la raison)
    f.dernier = await moteur.changer_commande_enregistree(f.source, p, f.regles, f.appelant, avant)
    f.resultats.append(_resultat_public("changer_la_commande_enregistree", f.dernier))
    if f.dernier.statut == "INCOMPLETE" and f.dernier.manque == "articles" and moteur.annulation_possible(f.source):
        RQ.demander_l_annulation(p)  # B4 (M2) + DC4 : tout retirer d'une commande enregistrée, c'est l'annuler : rien n'a changé, la confirmation en deux temps est posée


def _la_fin_est_due(f: LaFiche) -> str | None:
    """Décidé une fois, d'après l'étape et ce que la fiche a fait : la commande doit-elle être menée à sa fin ? Rend l'opération qui le dit au modèle, ou ``None``.
    « c'est tout » ; la relecture posée qui a cessé de valoir (B12, conversation 3) ; l'heure dite pendant « je vous la prépare pour … ? » (B1) ; l'accord qui valait
    et que la fiche a retiré, ou qui vaut avec un règlement, un numéro, un prénom ou une consigne dits (le code ne repose pas ce qui est accordé)."""
    p, ex = f.p, f.ex.executees
    if "c_est_tout" in ex or _relecture_a_relancer(p, f.question_avant, f.etat_avant, ex):
        return "c_est_tout"
    if (f.question_avant or {}).get("type") == "heure_proposee" and f.etat_avant in (ETAPE.A_CLORE, ETAPE.A_RELIRE) and p.get("heure_voulue"):  # A_RELIRE : l'heure refusée a laissé la relecture posée dessous (ligne 12)
        return "c_est_tout"
    ecartees = f.ecartees | f.deja_faites
    de_fin = any(f.fiche.get(k) not in (None, "") and k not in ecartees for k in (*contrat.CASES_DE_FIN, "consigne_livreur"))
    if de_fin and any(c in ex for c in INFORMATIONS) and ETAPE.accord(p) and not ETAPE.finie(p):
        return "enregistrer"
    if _accord_a_redonner(p, f.etat_avant) and "reponse" in ex and f.dernier is not None:
        return "enregistrer"
    return None


async def _mener_a_la_fin_de_la_fiche(f: LaFiche) -> None:
    """UN SEUL ``finaliser`` par fiche (C7), appelé ici et nulle part ailleurs ; le résultat est celui de la fiche. S'il lâche, « c'est tout » n'est pas dit fait."""
    operation = _la_fin_est_due(f)
    if operation is None:
        return
    try:
        f.dernier = await mener_a_la_fin(f.source, f.p, f.regles, f.appelant, confirmer=_accord_a_redonner(f.p, f.etat_avant))
    except Exception:
        if "c_est_tout" in f.ex.executees and operation == "c_est_tout":
            f.ex.executees.remove("c_est_tout")  # la panne dit les cases faites : celle-ci ne l'est pas (RC13)
        raise
    f.resultats.append(_resultat_public(operation, f.dernier))
    f.bruts.append(f.dernier)


async def _conclure(f: LaFiche) -> None:
    """Ce que la fiche appliquée laisse à faire : la vente en plus, la relecture qui repart, le changement d'une commande enregistrée, l'accord ; puis la question née de ce tour."""
    noter_les_cases(f.p, f.tour, {c: v for c, v in f.fiche.items() if c not in f.ecartees and c not in f.deja_faites and "*" not in f.ecartees})
    await _proposition_apres_les_cases(f)
    await _changement_apres_l_enregistrement(f)
    await _mener_a_la_fin_de_la_fiche(f)


def _poser_la_question(f: LaFiche) -> dict[str, Any] | None:
    """B1 : la question née de ce tour entre au registre ; UNE seule est posée, la première dont la condition est vraie (``registre.choisir``). Rend celle qui est née dans ce tour."""
    p, tour, dernier = f.p, f.tour, f.dernier
    q = _question_de(dernier, 0, tour, p) if dernier is not None else None
    if dernier is not None and dernier.statut in STATUTS_ENREGISTRES:
        f.ctx.enregistrement = dernier  # le résultat brut (dates comprises), lu par le flux du portail et le SMS
    _dire_c_est_tout(p, q, f.ex.executees)
    if not RQ.est_deja_ouverte(p, q):
        RQ.ouvrir(p, q)  # celle d'un article en doute est déjà au registre, ouverte à l'article (D25)
    for refus in (r for r in f.bruts if r.manque in MANQUES_REFUSES_DE_QUESTION and statut_qui_refuse(r.statut)):
        manque = _question_de(refus, 0, tour, p)  # ligne 12 : l'heure refusée est posée avant la relecture, le modèle dit le refus puis la demande
        if manque is not None and not RQ.est_deja_ouverte(p, manque):
            RQ.ouvrir(p, manque)
    attente = moteur.question_de_la_ligne_en_attente(p)
    posee = RQ.choisir(p, tour, [_question_de(attente, 0, tour, p)] if attente is not None else [])
    avant = f.question_avant
    # née dans ce tour : posée maintenant pour la première fois, ou reposée avec un autre texte (une relecture qui repart) ; dite par le code si c'est sa forme
    return posee if posee is not None and (not avant or posee["id"] != avant.get("id") or posee.get("texte") != avant.get("texte") or posee.get("nee_au_tour") == tour) else None


def _textes_de_la_fiche(f: LaFiche, nee: dict[str, Any] | None) -> list[tuple[int, str]]:
    """Ce que le code dit lui-même au retour de la fiche (rangé dans la fiche de l'appel : la relecture, la confirmation, le fait accompli) ; rend les consignes du retour avec leur rang.
    Un refus (hors zone, article inconnu, heure…) n'est jamais dit par le code : le modèle le dit d'après les faits (``refus_de_la_fiche``), le journal de ce qui est dit dit
    s'il l'a déjà entendu (une issue, puis la sortie)."""
    ctx, p, dernier, tour = f.ctx, f.p, f.dernier, f.tour
    textes = textes_du_code(p, dernier, nee, f.refus, deja_enregistree=f.phase_d_avant == RQ.ENREGISTREE,
                            total_d_avant=(moteur.commande_de_l_appel(f.avant_enregistree) or {}).get("total") if f.avant_enregistree else None,
                            question_apres=getattr(f.regles, "question_apres_enregistrement", None))
    refusants = refusants_de_la_fiche(f)
    raison = " ".join(x for x in (raison_du_fait_bloquant(r) for r in refusants) if x) or None
    consignes: list[tuple[int, str]] = []
    if heures_a_dire(f) and nee is None:
        consignes.append((C.QUESTION, A_FAIRE_DE_L_HEURE))
    if raison and "avant" not in textes:
        # Le refus se dit une fois comme un fait (B3, M5, C7, DF7) ; redit, le journal donne l'issue, puis la sortie. Une question née avec le refus se dit d'une seule voix avec lui.
        etape = J.fait_redit(p, " ".join(J.identite_du_refus(r) for r in refusants if raison_du_fait_bloquant(r)), tour, _seuil_de_sortie(ctx))
        if etape in (J.ISSUE, J.SORTIE) or (etape != J.PREMIERE and nee is None):
            consignes.append(_consigne_du_journal(etape))  # déjà dit : l'issue, puis la sortie (rien de plus dans le même tour)
        else:
            consignes.append((C.REFUS_A_DIRE, A_FAIRE_DES_REFUS_A_DIRE))
        if nee is not None:
            consignes.append((C.QUESTION, A_FAIRE_DE_LA_QUESTION))
    ctx.fiche[CLE_TEXTES_DU_CODE] = textes
    if textes.get("avant") and dernier is not None and (dernier.statut in STATUTS_ENREGISTRES or dernier.faits.get("commande_annulee") or dernier.faits.get("annulee")):
        J.dire_le_fait(p, textes["avant"], tour)  # B2 (M3, règle 3) : le fait accompli, que le repli redit au lieu de « je n'ai pas compris »
    poser_le_fait_bloquant(ctx.fiche, tour, " ".join(x for x in (phrase_du_fait_bloquant_de(r) for r in refusants) if x) or None)
    return consignes


async def _dire(f: LaFiche) -> dict[str, Any]:
    """Le retour de la fiche : la question née de ce tour, ce que le code dit lui-même, l'enveloppe."""
    nee = _poser_la_question(f)
    consignes: list[tuple[int, str]] = []
    if isinstance(getattr(f.ctx, "fiche", None), dict):
        consignes = _textes_de_la_fiche(f, nee)
    retour = _enveloppe_de_la_fiche(f.p, f.resultats, f.ex.executees, f.refus, f.ecartees, f.dernier, nee, refusants_de_la_fiche(f), heures_a_dire(f))
    if consignes:
        DU.assembler(retour, DU.Du(consignes=tuple(consignes)))  # ce que le modèle doit dire, puis le reste : les consignes se combinent
    return retour


def refusants_de_la_fiche(f: LaFiche) -> list[Resultat]:
    """TOUS les résultats de la fiche qui refusent (un article inconnu, la zone, l'heure…), lus sur l'ensemble des résultats : deux refus dans la même
    fiche sont dits tous les deux, et un refus n'est pas perdu parce qu'un autre résultat vient après. Le dernier résultat y est, s'il refuse et n'y est pas déjà."""
    tous = [*f.bruts, *([f.dernier] if f.dernier is not None and not any(f.dernier is r for r in f.bruts) else [])]
    vus: set[str] = set()
    refusants = []
    for r in tous:
        if r.statut in STATUTS_QUI_REFUSENT and J.identite_du_refus(r) not in vus:
            vus.add(J.identite_du_refus(r))
            refusants.append(r)
    return refusants


def raison_du_fait_bloquant(dernier: Any) -> str | None:
    """La raison d'un fait bloquant qui refuse, telle que le module la rend (hors zone : « Nous ne livrons pas à X. Nous livrons … »), ou ``None``."""
    if dernier is None or dernier.statut not in STATUTS_QUI_REFUSENT:
        return None
    return (dernier.suggestion or "").strip() or None


def phrase_du_fait_bloquant_de(dernier: Any) -> str | None:
    """Point de contrôle du lot 7 : la phrase du code pour un fait bloquant qui refuse (``repli.STATUTS_QUI_REFUSENT``), celle que le module rend
    (hors zone : « Nous ne livrons pas à X. Nous livrons … ») ; hors zone, suivie des autres modes ouverts par la phrase du mode (« À emporter ? »,
    ``phrases_du_manque``). Aucune phrase écrite ici. ``None`` : pas de fait bloquant qui refuse, ou le module ne rend pas de phrase."""
    phrase = raison_du_fait_bloquant(dernier)
    if phrase is None:
        return None
    autres = [m.get("libelle") or m.get("mode") for m in (dernier.faits or {}).get("autres_modes") or [] if isinstance(m, dict)]
    propose = phrase_du_manque(Manque.MODE, [a for a in autres if a]) if autres else None
    return f"{phrase} {propose}" if propose else phrase


def _a_faire_de_la_proposition(q: dict[str, Any]) -> tuple[str, bool]:
    """D33 (B9 § 2 point 4 ; B10 § 1 point 4) : la proposition née dans ce tour est posée par le modèle, avec ses mots et sans chiffre ; le code dit le
    prix juste après sa phrase (le drapeau seul est dans le retour, jamais la phrase). Une proposition offerte n'a pas de chiffre."""
    article = q.get("article_propose") or ""
    if q.get("offerte"):
        return f"propose-lui {article} offert en une question, avec tes mots", False
    return f"propose-lui {article} en une question, avec tes mots et sans aucun chiffre : le code dit son prix juste après ta phrase", bool(q.get("chiffre"))


def _faits_de_la_fiche(p, bloquant, dernier, refusants, heures, nee) -> dict[str, Any]:
    """Les faits que la fiche rend au modèle : le panier, le refus du module, les refus de la fiche, l'heure qui manque, le montant d'une annulation à confirmer."""
    faits: dict[str, Any] = {"panier": en_json(P.resume(p))}
    if bloquant:
        faits["fait_bloquant"] = {"statut_du_module": dernier.statut, "manque": dernier.manque}
    elif refusants:
        faits["fait_bloquant"] = {"statut_du_module": refusants[0].statut, "manque": refusants[0].manque}
    if refusants:
        faits["refus_de_la_fiche"] = [_refus_pour_le_modele(r) for r in refusants]  # tous les refus de la fiche, avec la question ouverte du registre : le modèle dit les deux
    if heures:
        faits["heure_a_dire"] = [_refus_pour_le_modele(r) for r in heures]  # ce qui manque de l'heure voulue : le modèle le demande avec ses mots
    if nee is not None and nee.get("type") == RQ.TYPE_ANNULATION and (p.get("enregistree") or {}).get("total") is not None:
        faits["annulation_a_confirmer"] = {"montant": p["enregistree"]["total"]}  # DC4 (Q2 = A) : le modèle pose la question, le montant est un fait que la barrière des chiffres laisse passer
    return faits


def _a_faire_de_la_fiche(refus, executees, nee) -> tuple[Any, bool]:
    """La consigne du tour (selon la question née, jamais quand la fiche a refusé) et si le prix est dit par le code après la phrase du modèle."""
    a_faire, prix_dit = B.a_faire_des_refus(refus, executees), False
    if nee is not None and nee.get("type") == RQ.TYPE_ANNULATION and not refus:
        a_faire = A_FAIRE_DE_L_ANNULATION
    if nee is not None and nee.get("type") == formule_a_etapes.TYPE_DE_LA_QUESTION and not refus:
        a_faire = formule_a_etapes.A_FAIRE
    if nee is not None and nee.get("type") == "proposition" and not refus:
        a_faire, prix_dit = _a_faire_de_la_proposition(nee)
    return a_faire, prix_dit


def _enveloppe_de_la_fiche(p, resultats, executees, refus, ecartees, dernier, nee=None, refusants=(), heures=()) -> dict[str, Any]:
    from api.services.actions_communes.enveloppe import Question

    q = CONV.question_de(p)
    question = None
    if isinstance(q, dict):
        reponses = formule_a_etapes.REPONSES if q["type"] == formule_a_etapes.TYPE_DE_LA_QUESTION else None  # FOR2 : son choix, dans valeurs (B10)
        question = Question(q["id"], q["type"], q.get("texte") or "", *((reponses,) if reponses else ()))
    bloquant = (dernier is not None and (statut_qui_refuse(dernier.statut) or dernier.statut in ("INCOMPLETE", STATUT_MINIMUM))  # C2 : tout refus du module (liste d'exclusion)
                and dernier.manque not in ("relecture",))
    statut = "PARTIEL" if refus or bloquant or refusants else ("ENREGISTREE" if dernier is not None and dernier.statut in STATUTS_ENREGISTRES else ("ANNULEE" if p.get("annulee") else "FAIT"))
    if question is not None and statut == "FAIT" and q.get("type") in ("variante", "ambiguite", formule_a_etapes.TYPE_DE_LA_QUESTION):
        statut = "A_PRECISER"
    plus: dict[str, Any] = {"fiche_appliquee": bool(executees), "cases_executees": executees}
    if refus:
        plus["refus"] = refus
        plus["cases_refusees"] = sorted({c for r in refus for c in r["cases"]})
        plus["cases_non_executees_car_liees"] = sorted(ecartees - set(plus["cases_refusees"]) - {"*"})
    faits = _faits_de_la_fiche(p, bloquant, dernier, refusants, heures, nee)
    premier = refus[0] if refus else None
    a_faire, prix_dit = _a_faire_de_la_fiche(refus, executees, nee)
    if prix_dit:
        plus["prix_dit_par_le_code_apres_ta_phrase"] = True
    return Enveloppe(statut, resultats=resultats, faits=faits, question=question, raison=premier["raison"] if premier else None,
                     a_faire=a_faire, plus=plus).vers_json()


async def _poser_les_informations(f: LaFiche) -> Resultat:
    """Les informations de la fiche : mode, adresse et commune ensemble (S3), consigne, heure, puis la fin (moyen, billet, téléphone, prénom)."""
    source, p, regles, fiche, ecartees = f.source, f.p, f.regles, f.fiche, f.ecartees | f.deja_faites
    garde = lambda k: fiche.get(k) if k not in ecartees else None
    r = await poser_le_mode(source, p, regles, garde("mode_de_retrait"), garde("adresse"), garde("commune"))
    if garde("consigne_livreur"):
        p["consigne_livreur"] = ConsigneLivreur(texte=str(fiche["consigne_livreur"]), source="modele").texte
    if garde("heure"):
        # E28 : l'heure est vérifiée dès qu'elle est posée, et à chaque correction (le créneau de l'heure résolue selon l'ouverture)
        r = await moteur.poser_l_heure(source, p, str(fiche["heure"])) or r
    if garde("note_generale"):
        r = moteur.noter_la_commande(p, regles, str(fiche["note_generale"])) or r
    if garde("code_de_remise") or garde("reduction_annoncee"):  # lot 14 (OFF3) : le code dit est vérifié par le code
        r = await moteur.poser_le_code_de_remise(source, p, regles, garde("code_de_remise"), bool(garde("reduction_annoncee"))) or r
    fin = {k: garde(k) for k in contrat.CASES_DE_FIN if garde(k) not in (None, "")}
    if fin:
        P.vouloir_le_reglement(p, fin)
        r = moteur.noter_le_client(p, telephone=fin.get("telephone"), prenom=fin.get("prenom")) or r
    return r or Resultat("OK", {}, "")


async def mener_a_la_fin(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, confirmer: bool = False) -> Resultat:
    """La commande menée à sa fin (la relecture, puis l'enregistrement après son accord), un manque à la fois. Ne se confond pas avec ``moteur.poser_la_relecture``, qui fait la PHRASE de relecture (M7)."""
    voulu = p.get("reglement_voulu") or {}
    r = await moteur.finaliser(source, p, regles, appelant, confirmer=confirmer, moyen=voulu.get("moyen_de_paiement"), rendu_sur=voulu.get("rendu_sur"),
                               part=voulu.get("part"), moyen_reste=voulu.get("moyen_reste"))
    return r


async def annuler(source: Source, p: dict[str, Any], regles: moteur.Reglages) -> Resultat:
    """Elle ne veut plus de la commande en cours : rien n'est enregistré, aucun panier n'est laissé ouvert (A04, E9)."""
    await moteur.vider_commande(source, p, regles)
    ETAPE.transition(p, ETAPE.ANNULEE_EN_COURS)
    CONV.poser_question(p, None)
    # Chantier Partie 1, lot 6 (L06-41, ``banc-b2/guichet_candidat.py`` op ``annuler``) : le code dit l'annulation lui-même, comme au banc.
    return Resultat("OK", {"annulee": True}, PHRASES_DITES.TEXTE_ANNULEE_EN_COURS)


def _laisser_un_message(message: Any, fiche: dict[str, Any], ctx: Any, resultats: list[dict], refus: list[dict]) -> None:
    """Le message à l'équipe, UNE fois par appel (E30) : la demande est écrite, l'issue de l'appel et sa mesure posées (lot 6, C10 ; sens repris de
    test_message_et_redites_m102_m113 et test_restauration_service_client, comme l'ancienne action ``laisser_un_message``). Un second message est refusé."""
    from api.services.service_client.action import _ecrire_la_demande

    if not (isinstance(message, dict) and str(message.get("objet") or "").strip()):
        return
    if fiche.get(CLE_MESSAGE_LAISSE):
        refus.append(B.refus("message_deja_laisse_dans_cet_appel", ["laisser_un_message"], reste="un seul message par appel"))
    elif _ecrire_la_demande(ctx, str(message["objet"]).strip()[:500], urgence := ("urgente" if _message_urgent(message, fiche) else "normale"), None):
        fiche[CLE_MESSAGE_LAISSE] = True
        resultats.append({"operation": "laisser_un_message", "statut_du_module": "OK", "faits": {"urgent": urgence == "urgente"}})
        poser_l_issue(ctx, "message_a_transmettre")
        from api.services.integrations.connectors import mesures as mesures_des_connecteurs

        mesures_des_connecteurs.ecrire(ctx.fiche, "service.message_laisse", "service.fiche", urgence)


async def executer_la_fiche_du_service(fiche_du_modele: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """La fiche du service (lot 3, étape 9) : retrouver une commande d'un appel précédent (par le numéro qui appelle, ou par un numéro dit ;
    un téléphone dicté seulement avec le numéro de la commande, D60 ; jamais un numéro qu'elle n'a pas dit, B7 point 8) et laisser un message à
    l'équipe, UNE fois par appel (E30)."""
    from api.services.integrations.connectors.actions.service import (
        retrouver_par_telephone_dicte_exige_le_numero,
    )

    entier = B.fiche_illisible(fiche_du_modele)
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier]}).vers_json()
    fiche = ctx.fiche if isinstance(ctx.fiche, dict) else {}
    affiche = numero_e164((ctx.appel or {}).get("caller_number"))
    paroles = list(fiche.get(CLE_DES_PAROLES) or [])
    resultats: list[dict] = []
    refus: list[dict] = []
    a_preciser: dict[str, str] = {}
    introuvable = ""
    perdue = ""  # une commande refusée ou en échec : l'offre du message, tenue par le modèle
    demande = fiche_du_modele.get("retrouver_une_commande_enregistree")
    if isinstance(demande, dict):
        numero_dit = str(demande.get("numero_de_commande") or "").strip() or None
        telephone = str(demande.get("telephone") or "").strip() or None
        inventes = [c for c, v in (("telephone", telephone), ("numero_de_commande", numero_dit)) if v and not valeur_dite_par_elle(v, c if c == "telephone" else "prenom", paroles)]
        if inventes:
            refus.append(B.refus("valeur_pas_dans_ses_mots", ["retrouver_une_commande_enregistree"], valeurs={c: "" for c in inventes},
                                 reste="un numéro se prend seulement s'il est dit"))
        else:
            exige = retrouver_par_telephone_dicte_exige_le_numero(fiche_du_modele, affiche, f"Q-{int(fiche.get('service_prochain_q') or 1)}")
            if exige is not None:
                fiche["service_prochain_q"] = int(fiche.get("service_prochain_q") or 1) + 1
                return exige
            regles = _regles(ctx)
            p = P.du_dossier(ctx.fiche)
            appelant = moteur.Appelant(affiche, str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
            from api.services.restauration.carte_et_allergenes.recherche_reglages import (
                reglages_de_la_recherche,
            )

            async with registre_des_sources.ouvrir((ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)) as source:
                r = await moteur.retrouver_commande(source, p, regles, appelant, numero_dit)
            # R-d : le suivi ne montre jamais le panier (un panier vide trompe) ; ce qui manque (le numéro de la commande) ou ce qui se choisit
            # (plusieurs commandes) est rendu avec sa phrase, jamais un « FAIT » muet que le modèle comble de lui-même.
            faits_du_suivi = {k: v for k, v in r.faits.items() if k not in ("panier", "candidats")}
            resultats.append({"operation": "retrouver_une_commande_enregistree", "statut_du_module": r.statut, "faits": en_json(faits_du_suivi)})
            if r.statut == "OK" and r.faits.get("statut"):
                fiche[CLE_COMMANDE_RETROUVEE] = r.faits["statut"]
                if r.faits["statut"] in STATUTS_PERDUS:
                    perdue = A_FAIRE_DE_LA_COMMANDE_PERDUE
            if r.statut in ("INCOMPLETE", "AMBIGU") and r.suggestion:
                a_preciser = {"manque": r.manque or "reference", "texte_a_dire": r.suggestion}
            elif r.statut == "INTROUVABLE":
                # P4 : le numéro de l'appel est connu et rien n'y est trouvé : le dire, puis chercher autrement ; jamais redemander ce numéro
                introuvable = "dis-lui qu'il n'y a pas de commande à ce numéro ; propose de chercher autrement (le numéro de la commande, ou un autre numéro) ; ne redemande pas le numéro de l'appel"
    _laisser_un_message(fiche_du_modele.get("laisser_un_message"), fiche, ctx, resultats, refus)
    statut = "PARTIEL" if refus and resultats else ("REJETEE" if refus else ("A_PRECISER" if a_preciser else ("INTROUVABLE" if introuvable else "FAIT")))
    premier = refus[0] if refus else None
    return Enveloppe(statut, resultats=resultats, raison=premier["raison"] if premier else None, a_faire=premier["a_faire"] if premier else (introuvable or perdue or None),
                     plus={**({"refus": refus} if refus else {}), **a_preciser}).vers_json()


CLE_MESSAGE_LAISSE = "service_message_laisse"
# B5 (audit des textes § 2.5, « urgent si la commande est en cours ») : le statut de la commande retrouvée dans cet appel, lu par le code ;
# un message laissé pendant qu'elle est en cours est urgent sans que le modèle ait à le juger.
CLE_COMMANDE_RETROUVEE = "service_commande_retrouvee_statut"
STATUTS_FINIS = frozenset({"terminee", "refusee", "annulee", "echec"})


def _message_urgent(message: dict, fiche: dict) -> bool:
    """Urgent : elle a dit que cela ne peut pas attendre (case du modèle), ou la commande retrouvée dans l'appel est en cours (le code)."""
    statut = fiche.get(CLE_COMMANDE_RETROUVEE)
    return message.get("urgent") is True or (bool(statut) and statut not in STATUTS_FINIS)
STATUTS_ENREGISTRES = ("ENREGISTREE", "TRANSMISE")


def _poser_l_issue_de_la_coupure(nom: str, p: dict[str, Any], ctx: Any) -> None:
    """Une fiche coupée par son délai : commande déjà enregistrée, l'issue reste « enregistrée » et rien n'est joint à l'équipe (A2, pas de doublon) ;
    sinon la commande en cours part à l'équipe."""
    if nom == "fiche" and ETAPE.enregistree(p):
        poser_l_issue(ctx, "commande_enregistree")
    elif _joindre_la_commande_au_message_de_l_equipe(p, ctx):
        poser_l_issue(ctx, "message_a_transmettre")


def _joindre_la_commande_au_message_de_l_equipe(p: dict[str, Any], ctx: Any) -> bool:
    """W24 (A35, sain, déplacé tel quel de ``action.py``) : une panne en pleine commande ne perd rien. Le contenu de la commande en cours est écrit
    dans la fiche comme demande de rappel (l'après-appel en fait le message laissé à l'équipe), une seule entrée « commande » par appel, remplacée à
    chaque panne."""
    if not p["lignes"] or not isinstance(ctx.fiche, dict):
        return False
    entree = {
        "origine": ORIGINE_COMMANDE, "mode": "rappel", "numero": numero_e164((ctx.appel or {}).get("caller_number")) or None,
        "objet": moteur.contenu_dit(p), "souhait": None, "le": horloge(getattr(ctx, "organization_id", None)).maintenant().isoformat(),
    }
    liste = ctx.fiche.setdefault(CLE_RAPPEL, [])
    if not isinstance(liste, list):
        liste = ctx.fiche[CLE_RAPPEL] = []
    for i, ancienne in enumerate(liste):
        if isinstance(ancienne, dict) and ancienne.get("origine") == ORIGINE_COMMANDE:
            liste[i] = entree
            return True
    liste.append(entree)
    return True


async def _dire_au_flux(source: Any, avant: int, p: dict[str, Any], enregistrement: Resultat | None, ctx: Any) -> None:
    """Ce que le portail montre en direct (reprise de ``action.py``) : le panier qui change, la commande créée. Jamais une panne de l'appel."""
    hook = getattr(source, "apres_le_geste", None)
    if hook is None:
        return
    try:
        if enregistrement is not None:
            await hook("finaliser", avant, p, enregistrement, ctx)
        else:
            await hook("fiche", avant, p, Resultat("OK", {}, ""), ctx)
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal ; un flux qui ne part pas ne casse jamais l'appel, le portail relit la base
        logger.error(f"[.mark] commande : flux du direct non écrit : {erreur!r}")


def _mesurer(fiche_de_l_appel: Any, retour: dict[str, Any], mode: str | None) -> None:
    """Les mesures du module (W13), d'après le statut de chaque opération (le Dashboard les lit)."""
    for r in retour.get("resultats") or []:
        mesures_du_module.de_la_commande(fiche_de_l_appel, r.get("operation") or "fiche", {"statut": r.get("statut_du_module"), "faits": {**(r.get("faits") or {}), "mode": mode}})


def _prendre_les_notes_du_greffier(p: dict[str, Any], source: Any, fiche_de_l_appel: Any) -> None:
    """E15, E22 (lot 6) : ce que le greffier a noté dans la fiche de l'appel, sous les noms EXACTS que la source déclare (A12, jamais un préfixe),
    gardé dans le panier comme une proposition : la note de la commande le joint sans rien écraser, aucune case n'est posée par lui."""
    champs = (getattr(source, "champs_du_greffier", None) or {}).get("note") or ()
    if isinstance(fiche_de_l_appel, dict) and champs:
        notes = {c: str(fiche_de_l_appel[c]) for c in champs if isinstance(fiche_de_l_appel.get(c), str) and fiche_de_l_appel[c].strip()}
        p[moteur.CLE_NOTES_DU_GREFFIER] = notes


# Lot 6 (C10, complément de Pierre point 2) : l'issue de l'appel posée par l'opération qui la fait, au moment où elle la fait, jamais devinée par
# le classement de fin. Le code est celui que l'outil règle (``reglages.issues``), sinon le nom de l'issue elle-même.
ISSUES_DE_LA_COMMANDE = ("commande_enregistree", "commande_annulee", "message_a_transmettre", "commande_abandonnee")
REGLAGE_DES_ISSUES = ISSUES.REGLAGE_DES_ISSUES


code_de_l_issue = ISSUES.code_de_l_issue  # le mécanisme est commun aux métiers (G2)
poser_l_issue = ISSUES.poser_l_issue


CLE_ISSUES_REGLEES = "commande_issues_reglees"  # les codes réglés sur l'outil, gardés dans la fiche pour la fin de l'appel


def _commande_commencee(fiche_de_l_appel: dict[str, Any]) -> bool:
    p = fiche_de_l_appel.get(P.CLE)
    return isinstance(p, dict) and bool(p.get("lignes")) and not p.get("enregistree") and not p.get("annulee")


def issue_de_fin_d_appel(fiche_de_l_appel: Any) -> str | None:
    """L06-15 : l'appel finit avec une commande commencée, ni enregistrée ni annulée, et aucune issue posée : ``commande_abandonnee`` (son code réglé)."""
    return ISSUES.issue_de_fin_d_appel(fiche_de_l_appel, CLE_ISSUES_REGLEES, "commande_abandonnee", _commande_commencee)


def _poser_l_issue_de_la_fiche(ctx: Any, p: dict[str, Any], avant: dict[str, Any]) -> None:
    """Après la fiche : enregistrée, ou annulée (en cours ou enregistrée) dans CE geste."""
    if p.get("enregistree") and not avant.get("enregistree"):
        poser_l_issue(ctx, "commande_enregistree")
    elif (p.get("annulee") and not avant.get("annulee")) or (p.get("numero_de_la_commande_annulee") and p.get("numero_de_la_commande_annulee") != avant.get("numero_de_la_commande_annulee")):
        poser_l_issue(ctx, "commande_annulee")


CLE_MESURES_DU_CODE = "mesures_du_code"  # lot 5 : le temps du code de chaque fiche, par tour (``partie_1/mesure_du_tour.py`` le lit)


def _noter_le_temps_du_code(ctx: Any, outil: str, debut: float) -> None:
    """Lot 5 (L05-12) : le temps de l'exécution de la fiche, base comprise, rangé dans la fiche de l'appel avec son tour. ⛔ Ne lève jamais."""
    try:
        if isinstance(ctx.fiche, dict):
            from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

            ctx.fiche.setdefault(CLE_MESURES_DU_CODE, []).append(
                {"tour": ctx.fiche.get(CLE_TOUR), "outil": outil, "ms": round((time.perf_counter() - debut) * 1000, 1)}
            )  # ``tour_appelant`` : le numéro de tour du pipeline, celui des événements du direct que ``mesure_du_tour`` lit
    except Exception as erreur:  # noqa: BLE001
        logger.debug(f"[.mark] commande : temps du code non noté : {erreur!r}")


def contexte_appelant_affiche(ctx: Any) -> str | None:
    """Le numéro qui s'affiche pour cet appel (E.164), ``None`` s'il est masqué."""
    return numero_e164((ctx.appel or {}).get("caller_number")) or None


# Les quatre outils de l'accueil (textes prouvés, ``textes/gemma-4/outils.json``) : des lectures et un envoi du moteur, sans écriture dans le panier
# (règle nommée ``lecture_sur_une_copie``). Le connecteur « service » les déclare, la porte les exécute avec la source de l'agent.
OUTILS_DE_L_ACCUEIL = ("ouverture_en_ce_moment", "heure_annoncee", "remises_disponibles", "envoyer_un_sms")


RAISON_DU_STATUT_DE_L_ACCUEIL = {
    "DEJA_FAIT": "deja_fait", "REFUSEE": "envoi_impossible", "INDISPONIBLE": "envoi_indisponible", "ARGUMENT_INVALIDE": "arguments_illisibles",
}


async def _outil_de_l_accueil(nom: str, source: Any, p: dict[str, Any], regles: Any, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    copie = lecture_sur_une_copie(p)
    mode = arguments.get("mode_de_retrait")
    mode = mode if mode in ("emporter", "livraison") else None
    appel_id = str(ctx.run_id) if getattr(ctx, "run_id", None) else None
    if nom == "ouverture_en_ce_moment":
        r = await moteur.etat_ouverture(source, copie, regles, mode)
    elif nom == "heure_annoncee":
        r = await moteur.heure_annoncee(source, copie, regles, mode)
    elif nom == "remises_disponibles":
        r = await moteur.remises_disponibles(source, copie, regles, demande=True, presse=False, refus=False, appel_id=appel_id)
    else:
        appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), appel_id)
        r = await moteur.envoyer_un_message(source, copie, regles, appelant, arguments.get("quoi"), getattr(ctx, "organization_id", None))
    faits = {k: v for k, v in (r.faits or {}).items() if k not in ("panier", CLE_DU_PRIX_A_DIRE)}
    resultats = [{"operation": nom, "statut_du_module": r.statut}]
    if nom != "envoyer_un_sms":
        # Les trois lectures : le fait lu va au modèle tel quel (fermé, en pause, heure non calculée) ; seul un mode ou une zone qui manque se précise.
        if r.statut == "INCOMPLETE":
            return Enveloppe("A_PRECISER", resultats=resultats, faits=faits, plus={"manque": r.manque}).vers_json()
        return Enveloppe("LU", resultats=resultats, faits=faits).vers_json()
    if r.statut in ("OK", "RETENU", "TROUVE", "LU"):
        return Enveloppe("LU", resultats=resultats, faits=faits).vers_json()
    # ligne 87 : un statut de l'envoi hors de l'enveloppe (éteint, déjà parti, refusé) est dit au modèle, jamais une erreur levée (panne dite au client)
    return Enveloppe("REJETEE", resultats=resultats, faits=faits, raison=RAISON_DU_STATUT_DE_L_ACCUEIL.get(r.statut, "rien_a_faire")).vers_json()


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    debut = time.perf_counter()
    try:
        return await _executer(action, arguments, ctx)
    finally:
        _noter_le_temps_du_code(ctx, getattr(action, "nom", "?"), debut)


# La panne pendant la fiche : le modèle la dit avec ses mots (la consigne ``a_faire``, le fait ``transmise_a_l_equipe``) ; s'il se tait deux fois, le repli dit le texte de secours
# (``textes_de_secours.panne_de_la_porte``, posé en fait bloquant du tour). Le code ne la dit jamais seul.
A_FAIRE_DE_LA_PANNE_TRANSMISE = ("le moteur est en panne : dis-lui avec tes mots que tu n'arrives pas à enregistrer sa commande pour le moment, "
                                 "qu'elle est transmise à l'équipe et que l'équipe la rappelle")
A_FAIRE_DE_LA_PANNE = "le moteur est en panne : dis-lui avec tes mots que tu n'arrives pas à faire cela pour le moment, sans promettre de rappel ni de transmission à l'équipe"


async def _executer(action: Any, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    regles = _regles(ctx)
    if regles is None:
        return Enveloppe("REJETEE", raison="rien_a_faire").vers_json()
    p = P.du_dossier(ctx.fiche)
    try:
        from api.services.restauration.carte_et_allergenes.recherche_reglages import (
            reglages_de_la_recherche,
        )

        async with registre_des_sources.ouvrir(
            (ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)
        ) as source_ouverte:
            source = etat_pour_le_modele.SourceQuiRetient(source_ouverte)
            if action.nom in OUTILS_DE_L_ACCUEIL:
                return await _outil_de_l_accueil(action.nom, source, p, regles, dict(arguments or {}), ctx)
            if action.nom == "lire":
                retour = await lire(source, p, regles, dict(arguments or {}), str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
                suffixe = retour.pop(CLE_DU_SUFFIXE, None)  # PRX5 : le prix lu est dit par le code après la phrase du modèle (D33)
                if suffixe:
                    poser_le_suffixe_lu(getattr(ctx, "fiche", None), suffixe)
                return retour
            if action.nom == "fiche":
                _prendre_les_notes_du_greffier(p, source, ctx.fiche)
                if isinstance(ctx.fiche, dict) and isinstance((ctx.reglages or {}).get(REGLAGE_DES_ISSUES), dict):
                    ctx.fiche[CLE_ISSUES_REGLEES] = dict(ctx.reglages[REGLAGE_DES_ISSUES])
                avant = p["version"]
                etat_d_avant = {k: p.get(k) for k in ("enregistree", "annulee", "numero_de_la_commande_annulee")}
                contexte = SimpleNamespace(source=source, panier=p, regles=regles, fiche=ctx.fiche, appel=ctx.appel, run_id=getattr(ctx, "run_id", None),
                                           enregistrement=None)
                retour = await executer_la_fiche(dict(arguments or {}), contexte)
                etat_pour_le_modele.retenir(p, source)
                DU.assembler(retour, poser_le_minimum(ctx, p, retour), await moteur.faits_du_metier_a_donner(ctx, source, p, regles, retour),
                             poser_la_regle_de_la_ligne(retour.get("resultats") or [], retour), poser_les_regles_de_l_article(retour.get("resultats") or [], retour, p),
                             poser_le_prix_du_poids(ctx, retour.get("resultats") or []), await poser_la_remise_du_code(ctx, source, p, regles), poser_la_ligne_retiree(retour))
                _poser_l_issue_de_la_fiche(ctx, p, etat_d_avant)
                await _dire_au_flux(source, avant, p, contexte.enregistrement, ctx)
                _mesurer(ctx.fiche, retour, p.get("mode"))
                return avec_le_fait_du_numero_affiche(retour, contexte_appelant_affiche(ctx))
    except asyncio.CancelledError:
        # P7 (lot 19 bis) : la fiche coupée par son délai (``wait_for``) est une ANNULATION, jamais attrapée par ``except Exception`` : la commande en cours (pas encore enregistrée) est jointe au message de l'équipe
        # comme pour une panne (la phrase d'échec promet un rappel), puis l'annulation est propagée.
        logger.error(f"[.mark] commande {action.nom} coupée par son délai")
        _poser_l_issue_de_la_coupure(action.nom, p, ctx)
        raise
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'appel continue, la commande en cours part à l'équipe (A35)
        logger.error(f"[.mark] commande {action.nom} en échec : {erreur!r}")
        if action.nom == "fiche" and ETAPE.enregistree(p):
            # A2 : l'erreur est tombée APRÈS l'écriture : la commande de cet appel est enregistrée (constat sur l'état), jamais redite « pas enregistrée » ni jointe en double au message de l'équipe
            poser_l_issue(ctx, "commande_enregistree")  # son issue est posée (jamais une seconde fois écrasée) : sortie avant ``_poser_l_issue_de_la_fiche``
            return Enveloppe("FAIT", faits={"commande_enregistree": True, "numero": (p.get("enregistree") or {}).get("numero")}).vers_json()
        transmise = _joindre_la_commande_au_message_de_l_equipe(p, ctx)
        if transmise:
            poser_l_issue(ctx, "message_a_transmettre")
        faits_de_la_panne = {"indisponible": True, "transmise_a_l_equipe": transmise}
        a_faire = None
        if action.nom == "fiche" and isinstance(ctx.fiche, dict):
            # R = A : le modèle dit la panne avec ses mots ; le texte de secours (``TS.panne_de_la_porte``) n'est dit que par le repli, s'il se tait deux fois. Il ne promet un rappel que si
            # la commande a bien été jointe à l'équipe (le fait ``transmise_a_l_equipe``, la même consigne).
            poser_le_fait_bloquant(ctx.fiche, ctx.fiche.get(contrat.CLE_DU_TOUR), TS.panne_de_la_porte(faits_de_la_panne))
            a_faire = A_FAIRE_DE_LA_PANNE_TRANSMISE if transmise else A_FAIRE_DE_LA_PANNE
        mesures_du_module.de_la_commande(ctx.fiche, action.nom, {"statut": "INDISPONIBLE", "faits": {}})
        faites = getattr(erreur, "cases_executees", None) if action.nom == "fiche" else None
        # RC13 : une case a lâché après d'autres : le panier a pu changer, le retour dit lesquelles sont faites (jamais un panier à moitié changé que personne ne décrit)
        plus = {"fiche_appliquee": bool(faites), "cases_executees": faites} if faites else {}
        return Enveloppe("REJETEE", raison="rien_a_faire", faits=faits_de_la_panne, a_faire=a_faire, plus=plus).vers_json()
    return Enveloppe("REJETEE", raison="operation_inconnue").vers_json()
