"""[.mark] La porte d'entrée de la commande (chantier Partie 1) : ce que le connecteur ``commande`` exécute.

- ``lire`` (lot 2, E16) : la lecture, qui n'écrit jamais rien (``services/commande/lire.py``) ;
- ``fiche`` : la fiche à cases, exécutée case par case dans l'ordre du banc (lot 3, ``executer_la_fiche``).

La source (le catalogue) est ouverte une fois par appel d'outil, comme avant ; une panne du catalogue ne lève pas : ``INDISPONIBLE`` au journal (R1).
"""

from __future__ import annotations

import asyncio
import copy
import time
from contextvars import ContextVar
from dataclasses import is_dataclass, replace
from types import SimpleNamespace
from typing import Any

from loguru import logger

from api.db.bases_clients.horloge import horloge
from api.schemas.apres_appel import numero_e164
from api.services.actions_communes.issues import poser_l_issue_de_l_appel
from api.services.actions_communes import barrieres as B
from api.services.actions_communes import du as DU
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.arguments import en_json
from api.services.actions_communes.cases_liees import cases_ecartees
from api.services.actions_communes.enveloppe import Enveloppe
from api.services.actions_communes.forme import valeur_dite_par_elle
from api.services.actions_communes.parole import CLE_FAITS_A_DIRE, CLE_TEXTES_DU_CODE, poser_le_suffixe_lu  # lot 7 : la même clé pour la commande et la réservation
from api.services.actions_communes.idempotence import case_deja_faite, cle_d_idempotence, deja_executee, noter_les_cases
from api.services.actions_communes.plafonds import plafond_d_operations
from api.services.actions_communes.repli import CLE_DU_DERNIER_FAIT, STATUTS_QUI_REFUSENT, poser_le_fait_bloquant, statut_qui_refuse
from api.services.actions_communes.resultat import avec_le_fait_du_numero_affiche
from api.services.actions_communes.types import ConsigneLivreur
from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_COMMANDE
from api.services.commande import contrat, etat_pour_le_modele, moteur
from api.services.commande.briques import for2, for3
from api.services.commande.briques import formule as FO
from api.services.commande import panier as P
from api.services.commande import registre as RQ
from api.services.commande import source as registre_des_sources
from api.services.commande.lire import CLE_DU_PRIX_A_DIRE, CLE_DU_SUFFIXE, lecture_sur_une_copie, lire
from api.services.commande.phrases_du_manque import MODE as MODE_DU_MANQUE
from api.services.commande.phrases_du_manque import phrase_du_manque
from api.services.commande.phrases_du_manque import texte_a_dire as texte_a_dire_du_manque
from api.services.commande.reglages import reglages_de_la_commande
from api.services.commande.resultat import (
    Resultat,
    question_apres_enregistrement,
    question_du_numero_affiche,
)
from api.services.commande.source import Source
from api.services.integrations.connectors.outil import nom_vu
from api.services.restauration import mesures as mesures_du_module

SOURCE_DE_L_OUTIL = "source"  # clé du réglage de l'outil qui nomme sa source ; vide : ``classeur`` (reprise de ``action.py``)


def _regles(ctx: Any):
    regles = reglages_de_la_commande(ctx.configurations)
    if regles is not None and is_dataclass(regles):
        regles = replace(regles, question_numero_affiche=question_du_numero_affiche(ctx), question_apres_enregistrement=question_apres_enregistrement(ctx))
    return regles


# --------------------------------------------------------------------------- la fiche de la commande (lot 3)

# L'ordre d'exécution des cases (``banc-b5/contrat_b5.py`` ``fiche_vers_items``, aux noms de la version finale ; vérifié contre le guichet de
# ``banc-b13/commande_b13.py`` ``executer_fiche``) : vider et annuler, réponse, retraits, changements, ajouts, informations, c'est tout.
ORDRE_DES_CASES = (
    "vider_le_panier", "annuler_la_commande", "annuler_une_commande_enregistree", "reponse", "retirer_article", "changer_quantite", "ajouter",
    "mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", "moyen_de_paiement", "rendu_sur", "part", "moyen_reste", "telephone", "prenom", "note_generale",
    "code_de_remise", "reduction_annoncee", "c_est_tout",
)
INFORMATIONS = ("mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", "moyen_de_paiement", "rendu_sur", "part", "moyen_reste", "telephone", "prenom", "note_generale",
                "code_de_remise", "reduction_annoncee")
CLE_DES_PAROLES = "paroles_de_la_personne"
CLE_DIT_PAR_LE_CODE = "dit_par_le_code"
MOYENS_DE_LA_FICHE = {"carte_bancaire": "carte", "especes": "especes", "titre_restaurant": "titre_restaurant", "carte_bancaire_a_la_livraison": "carte_livraison"}
TYPES_DE_QUESTION = {"CHOIX_OBLIGATOIRE": "variante", "AMBIGU": "ambiguite"}
MANQUES_DE_QUESTION = {"relecture": "relecture", "vente_en_plus": "proposition", "heure_proposee": "heure_proposee",  # aparté d'Evan (20/11)
                       "confirmer_numero": "numero_affiche"}  # C7 (lot 19 bis) : le numéro qui s'affiche est une question numérotée, sa réponse la cite
# Lot 6, élément 1 (b) (B7 point 2, K4 du banc ``contrat_b4.texte_du_code``) : ce que le code dit lui-même, mot pour mot, au retour de la fiche ;
# rangé dans la fiche de l'appel pour la couche de parole, JAMAIS dans le retour montré au modèle (B10 point 4 : seulement le drapeau).
#   avant   : le récapitulatif, la confirmation de l'enregistrement : dit, et le tour s'arrête là ;
#   prefixe : la règle chiffrée qui bloque (le minimum de la zone) : dit, puis le modèle repasse pour sa phrase, sans chiffre ;
#   suffixe : le prix d'une proposition née dans ce tour : dit juste après la phrase du modèle (D33).
STATUT_MINIMUM = "MINIMUM_NON_ATTEINT"
A_FAIRE_DU_MINIMUM = "le code vient de dire le minimum et ce qui manque : ta phrase suit, sans aucun chiffre ; demande-lui ce qu'elle veut faire"
A_FAIRE_DU_REFUS_DIT = "le code vient de lui dire ce qui est refusé et pourquoi : ta phrase suit, sans le redire"


def phrase_du_minimum(p: dict[str, Any]) -> str | None:
    """« En livraison à Chantilly, le minimum de commande est de cinquante euros : il manque trente-neuf euros dix. » (``bloquants_commande`` du
    banc) : lu dans l'ÉTAT du panier à la fin de la fiche (minimum de sa zone et chiffrage retenus, ``etat_pour_le_modele.retenir``), pas dans la
    dernière opération (une proposition peut la suivre). ``None`` : pas en livraison, pas de lignes, minimum atteint ou inconnu."""
    from api.services.commande.etat_pour_le_modele import CLE_CONNU, _commune, cle_du_chiffrage
    from api.services.mots_dits import montant_en_lettres

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
    return f"En livraison à {commune}, le minimum de commande est de {montant_en_lettres(int(minimum))} : il manque {montant_en_lettres(int(minimum) - sous_total)}."


A_FAIRE_DE_L_ALLERGIE = "l'allergie de la personne est connue : réponds-lui avec tes mots d'après faits.allergie ; ce qui est à confirmer par l'équipe, dis-le"


async def poser_les_faits_de_l_allergie(ctx: Any, source: Source, p: dict[str, Any], regles: moteur.Reglages, retour: dict[str, Any]) -> None:
    """Lot 15 (D22) : dès qu'une allergie est connue dans l'appel (la case du greffier), le code lit lui-même les allergènes validés du panier et les DONNE au modèle dans le retour (``faits.allergie``),
    comme un ``lire`` qu'il n'aurait pas eu à appeler. Aucune phrase du code : le modèle répond avec ses mots. ⛔ Ne lève jamais."""
    try:
        if moteur.allergie_a_donner(p) is None:
            return  # connue et pas encore donnée : même panier vide (la carte concernée est donnée avec)
        if p.get("allergie_donnee") == moteur.allergie_connue(p):
            faits = await moteur.faits_a_redonner_pour_les_lignes_nouvelles(source, p)  # A2 : seulement les lignes ajoutées ou changées depuis
            if faits is None:
                moteur.noter_l_allergie_donnee(p, int(p.get("allergie_donnee_au_tour") or 0))  # sans enjeu : empreinte mise à jour, rien n'est redit
                return
        else:
            faits = await moteur.faits_de_l_allergie(source, p)
        if not faits:
            return
        moteur.noter_l_allergie_donnee(p, int(p.get("tour_de_l_appel") or 0))
        retour["faits"] = {**(retour.get("faits") or {}), "allergie": faits}
        retour[CLE_FAITS_A_DIRE] = True  # lot 20 (conv4) : la phrase écrite avant ce retour ne les connaissait pas : le modèle repasse et les dit
        retour["a_faire"] = " ; ".join(x for x in (A_FAIRE_DE_L_ALLERGIE, retour.get("a_faire")) if x)
    except Exception:  # noqa: BLE001
        pass


def poser_le_minimum(ctx: Any, p: dict[str, Any], retour: dict[str, Any]) -> None:
    """Après la fiche et ce que la source a retenu : sous le minimum de la zone, le code le dit avant la phrase du modèle (préfixe), le retour
    porte le drapeau et ce qu'il y a à faire, jamais la phrase (B10 point 4, B11 point 2). ⛔ Ne lève jamais."""
    try:
        phrase = phrase_du_minimum(p)
        if not phrase or not isinstance(getattr(ctx, "fiche", None), dict):
            return
        # B3 (M5, H6 : le minimum dit trois fois) : le journal de ce qui est dit ; la clé est la phrase (un autre montant manquant est un autre fait).
        # Le minimum reste vrai d'une fiche à l'autre : déjà dit, il ne se redit pas ; seule « c'est tout » refusée par lui compte comme un échec
        bute = any(isinstance(r, dict) and r.get("statut_du_module") == STATUT_MINIMUM for r in retour.get("resultats") or [])
        if J.deja_dit(p, phrase) and not bute:
            return
        etape = J.fait_redit(p, phrase, ctx.fiche.get(contrat.CLE_DU_TOUR))
        if etape == J.DEJA_DANS_CE_TOUR:
            return
        if etape != J.PREMIERE:
            retour["a_faire"] = " ; ".join(x for x in (J.consigne(etape), retour.get("a_faire")) if x)
            return
        ctx.fiche.setdefault(CLE_TEXTES_DU_CODE, {})["prefixe"] = phrase
        retour["dit_avant_ta_phrase"] = True
        retour["a_faire"] = " ; ".join(x for x in (A_FAIRE_DU_MINIMUM, retour.get("a_faire")) if x)
    except Exception:  # noqa: BLE001
        pass


def textes_du_code(p: dict[str, Any], dernier: Resultat | None, nee: dict[str, Any] | None, refus: list[dict], deja_enregistree: bool = False,
                   total_d_avant: Any = None, question_apres: str | None = None) -> dict[str, str]:
    """Les phrases que le code dit lui-même au retour de cette fiche (vide : aucune) : ce qui est dû à la personne (B2, M3), les faits accomplis
    (enregistrée, changée avec son nouveau total, annulée) et la question qui se dit mot pour mot. ``deja_enregistree`` : la commande l'était avant
    cette fiche (un changement se dit, ``remplace`` ; une réponse sans changement, non)."""
    textes: dict[str, str] = {}
    if nee is not None and nee.get("type") == RQ.TYPE_NOUVELLE_COMMANDE and nee.get("texte"):
        return {"avant": str(nee["texte"])}  # DC5 : dit par le code, même quand rien de la fiche n'a été exécuté
    if dernier is None:
        return textes
    if dernier.statut in STATUTS_ENREGISTRES and dernier.faits.get("remplace"):
        # B2 (M3, TF2) : changée après l'être : son nouveau total dit par le code ; le total inchangé (l'heure), sa nouvelle confirmation
        change = (p.get("enregistree") or {}).get("total") != total_d_avant
        if change or not dernier.suggestion:
            textes["avant"] = RQ.texte_du_changement(p, question_apres)
        elif dernier.suggestion == p.get(CLE_DU_DERNIER_FAIT):
            textes["avant"] = RQ.texte_du_changement(p, question_apres, montant=False)  # rien de ce qui se dit n'a changé : jamais la même phrase redite (RC3)
        else:
            textes["avant"] = dernier.suggestion  # l'heure a changé : la nouvelle confirmation la dit
    elif dernier.statut in STATUTS_ENREGISTRES and dernier.suggestion and not deja_enregistree:
        textes["avant"] = dernier.suggestion
    elif dernier.faits.get("commande_annulee"):
        textes["avant"] = RQ.TEXTE_ANNULATION_CONFIRMEE  # DC4, second temps : l'annulation faite se dit par le code (avant : phrase vide, rien dit)
    elif dernier.faits.get("annulee") and dernier.suggestion:
        textes["avant"] = dernier.suggestion
    elif nee is not None and nee.get("type") in ("relecture", RQ.TYPE_NOUVELLE_COMMANDE, RQ.TYPE_ANNULATION) and nee.get("texte"):
        textes["avant"] = str(nee["texte"])
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
    type_ = TYPES_DE_QUESTION.get(r.statut) or MANQUES_DE_QUESTION.get(r.manque or "")
    if r.statut == "CHOIX_OBLIGATOIRE" and ((r.faits or {}).get("question") or {}).get("type") == for2.TYPE_DE_LA_QUESTION:
        type_ = for2.TYPE_DE_LA_QUESTION  # FOR2 : une étape de formule à choisir ouvre une question d'étape (sa réponse dans valeurs)
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
    if type_ == "heure_proposee" and (r.faits or {}).get("heure_proposee"):
        q["heure"] = str(r.faits["heure_proposee"])  # l'heure de la réouverture proposée, posée au « oui »
    if type_ == "ambiguite" and isinstance((r.faits or {}).get(CLE_ARTICLE_DIT), dict):
        q[CLE_ARTICLE_DIT] = r.faits[CLE_ARTICLE_DIT]
        if (r.faits or {}).get(moteur.CLE_OPTION_DITE):
            q[moteur.CLE_OPTION_DITE] = str(r.faits[moteur.CLE_OPTION_DITE])  # T1
    return q


def _resultat_public(operation: str, r: Resultat) -> dict[str, Any]:
    faits = en_json({k: v for k, v in (r.faits or {}).items() if k not in ("panier", CLE_ARTICLE_DIT, moteur.CLE_OPTION_DITE)})
    return {"operation": operation, "statut_du_module": r.statut, **({"manque": r.manque} if r.manque else {}), "faits": faits}


async def repondre_a_la_question(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, question: dict, sens: str | None,
                                 valeurs: list[str] | None) -> Resultat:
    """La réponse rangée par son identifiant (E5) et sa case fermée (E6), selon le type de la question ; le corps des règles est réécrit au lot 4."""
    texte = ", ".join(str(v) for v in valeurs or [] if str(v).strip()) or None
    if question["type"] == "relecture":
        if sens == "accepte":
            p["relecture_acceptee"] = True
            return Resultat("OK", {"recapitulatif": "accepte"}, "")
        p["relecture_acceptee"] = False
        # B1 (C3 a) : « autre » à la relecture ne la ferme pas, elle reste posée (avant : fermée, aucune question, le panier « accord attendu »).
        # B4 (M4, C3, RC1 E11 → G24) : « non » non plus : fermée, plus rien n'était demandé (cases de fin cachées, rien qui manque) ; elle reste
        # posée et le modèle demande ce qu'elle veut changer (comme la réservation)
        faits = {"recapitulatif": sens or "autre", "question_gardee": True}
        if sens == "refuse":
            faits["a_faire"] = "demande-lui ce qu'elle veut changer"
        return Resultat("OK", faits, "")
    if question["type"] == moteur.TYPE_DE_LA_QUESTION_DU_NUMERO:
        return moteur.repondre_au_numero_affiche(p, sens)  # C7 : la seule voie par laquelle le numéro qui s'affiche est gardé ou refusé
    if question["type"] == RQ.TYPE_ANNULATION:
        if sens == "accepte":
            return await moteur.annuler_commande_enregistree(source, p, regles)  # DC4, second temps : annulée, puis confirmée par le code
        return Resultat("OK", {"annulation_abandonnee": True}, "")  # « non » ou autre chose : la commande reste enregistrée
    if question["type"] == RQ.TYPE_NOUVELLE_COMMANDE:
        if sens == "accepte":
            RQ.repartir(p)  # DC5 : une commande neuve ; l'article se redit dans sa case
            return Resultat("OK", {"nouvelle_commande": True}, "")
        p["nouvelle_commande_refusee"] = True
        return Resultat("OK", {"rien_ajoute": True}, "")
    if question["type"] == "proposition":
        if sens == "autre":
            # DC3 (Evan, 22/11) : une proposition se ferme au premier « non » ou au premier tour sans « oui » ; elle ne revient pas (rien n'est ajouté)
            p.pop("proposition_en_plus", None)
            p.pop("vente_en_plus_tot", None)
            p["proposition_refusee"] = True
            return Resultat("OK", {"rien_ajoute": True, "proposition_fermee": True}, "")
        return await moteur.repondre_a_la_proposition(source, p, regles, appelant, sens, variante=texte)
    if question["type"] == for2.TYPE_DE_LA_QUESTION:
        return await repondre_a_l_etape(source, p, regles, question, valeurs)
    if question["type"] == "heure_proposee":
        return await _repondre_a_l_heure_proposee(source, p, regles, appelant, question, sens, texte)
    if sens == "refuse" and not texte:
        return Resultat("OK", {"rien_ajoute": True}, "")
    article_dit = question.get(CLE_ARTICLE_DIT) if question["type"] == "ambiguite" else None
    if isinstance(article_dit, dict):
        return await _repondre_a_l_hesitation(source, p, regles, question, article_dit, sens, texte)
    choix = texte or (question.get("choix") or [None])[0] if sens == "accepte" else texte
    return await moteur._repondre(source, p, regles, choix=choix, sans=None, note=None, moities=None)


MOTS_DE_LIAISON_DU_NOM_DIT = frozenset({"avec", "des", "de", "du", "la", "le", "les", "et", "un", "une", "sans", "l", "d"})


def _reste_du_nom_dit(dit: str, candidat: str) -> str:
    """T4 (lot 19 bis) : ce que la personne a glissé dans le NOM de l'article et qui n'est pas le nom du candidat (« bubble tea avec des perles » pour « Bubble tea » : « perles »), sans les mots de liaison.
    Rejoué en choix avec le candidat accepté."""
    connus = set(moteur.norme_de_recherche(candidat).split())
    reste = [m for m in dit.split() if moteur.norme_de_recherche(m) not in connus and moteur.norme_de_recherche(m) not in MOTS_DE_LIAISON_DU_NOM_DIT]
    return " ".join(reste)


def _article_avec_l_option_choisie(article_dit: dict[str, Any], option_dite: str, choisie: str) -> dict[str, Any]:
    """T1 : l'article dit, l'option en doute (« perles ») remplacée par celle que la personne a choisie (« Perles de tapioca ») ; sans mot à remplacer, elle est ajoutée aux choix."""
    voulue = moteur.norme_de_recherche(option_dite)

    def remplacer(liste: list[Any]) -> tuple[list[Any], bool]:
        sortie = [choisie if voulue and voulue in moteur.norme_de_recherche(str(x)) else x for x in liste]
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
        dit = texte.strip().casefold()
        nom = next((c for c in choix if c.casefold() == dit), None) or next((c for c in choix if dit in c.casefold() or c.casefold() in dit), None)
        if nom is None and not option_dite:
            trouve = await source.chercher(texte)  # un autre article de la carte, nommé : la carte le confirme, jamais un mot de la réponse
            nom = texte if trouve.statut == "RETENU" else None
    elif sens == "accepte" and len(choix) == 1:
        nom = choix[0]
    if nom is None:
        return Resultat("OK", {"rien_ajoute": True, "question_gardee": True}, "")
    if option_dite:
        return await ajouter_un_article(source, p, regles, _article_avec_l_option_choisie(article_dit, str(option_dite), nom))
    reste = _reste_du_nom_dit(str(article_dit.get("article") or ""), nom)
    if reste:
        avec_le_reste = await ajouter_un_article(source, p, regles, {**article_dit, "article": nom, "composition": [*(article_dit.get("composition") or []), reste]})
        if avec_le_reste.statut not in ("HORS_CARTE", "AMBIGU"):
            return avec_le_reste  # le reste dit est une option de l'article : rejoué ; sinon l'article seul, comme avant
    return await ajouter_un_article(source, p, regles, {**article_dit, "article": nom})


async def _repondre_a_l_heure_proposee(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, question: dict,
                                       sens: str | None, texte: str | None) -> Resultat:
    """Aparté d'Evan (20/11) : « Je vous la prépare pour dix-huit heures ? ». « oui » pose l'heure proposée ; une autre heure dite est posée à sa place ;
    « non » sans heure : on demande laquelle. L'heure posée, la commande va à sa relecture (comme après « c'est tout »)."""
    heure = texte or (question.get("heure") if sens == "accepte" else None)
    if not heure and sens == "autre":
        return Resultat("OK", {"rien_ajoute": True, "question_gardee": True}, "")  # file d'attente : « autre » (elle dit ses pizzas) garde la question posée
    if not heure:
        return Resultat("INCOMPLETE", {}, "Pour quel jour et à quelle heure, alors ?", "heure_voulue")
    r = await moteur.poser_l_heure(source, p, str(heure))
    if r is not None:
        return r
    if not question.get(APRES_C_EST_TOUT):
        # Evan, 21/11 : proposée dès le début (fermé), l'heure posée, la commande se prend comme d'habitude ; la relecture ne vient qu'après « c'est tout »
        return Resultat("OK", {"heure_voulue": p.get("heure_voulue")}, "")
    return await recapituler(source, p, regles, appelant)


async def repondre_a_l_etape(source: Source, p: dict[str, Any], regles: moteur.Reglages, question: dict, valeurs: list[str] | None) -> Resultat:
    """FOR2 (B10) : la réponse à une question d'étape, dans ``valeurs`` : une seule valeur (``plusieurs_choix`` sinon, ``choix_manquant`` sans valeur), rangée sur
    l'étape de la question et sur elle seule ; la question reste posée sur un refus."""
    dites = [str(v).strip() for v in valeurs or [] if str(v).strip()]
    if not dites:
        return Resultat("HORS_CARTE", {"raison": "choix_manquant", "question": question["id"], "choix": question.get("choix") or [], "question_gardee": True}, "")
    if len(dites) > 1:
        return Resultat("HORS_CARTE", {"raison": "plusieurs_choix", "question": question["id"], "valeurs": dites, "question_gardee": True}, "")
    return await moteur._repondre(source, p, regles, choix=dites[0], sans=None, note=None, moities=None)


CLE_ARTICLE_DIT = "article_dit"  # D24 : l'article de la fiche gardé avec une question d'hésitation
QUESTIONS_SUR_UN_ARTICLE = ("variante", "ambiguite", for2.TYPE_DE_LA_QUESTION)


async def garde_article_deja_en_question(source: Source, p: dict[str, Any], regles: moteur.Reglages, fiche: dict[str, Any],
                                         question: dict | None, refs_en_attente: set) -> dict[str, Any] | None:
    """Lot 19, D01 (FOR10-B, OPT8-B, n7 de B12) : la fiche répond à la question ouverte sur un article ET remet ce même article dans ``ajouter`` :
    la réponse le complète déjà ; la case ``ajouter`` est refusée avec la raison, rien n'est ajouté deux fois. Critère sur l'état (la ligne en attente,
    les choix de la question), jamais sur les mots (D1) ; le code ne devine pas un second exemplaire, il se dit après avec sa quantité."""
    reponse = fiche.get("reponse")
    if not question or not isinstance(reponse, dict) or not p.get("mode"):
        return None
    if question.get("type") not in QUESTIONS_SUR_UN_ARTICLE and question.get("type") != "proposition":
        return None
    valeurs = [str(v).strip() for v in reponse.get("valeurs") or [] if str(v).strip()]
    if not valeurs and reponse.get("sens") != "accepte":
        return None  # une réponse qui ne choisit rien (« autre ») : c'est l'article remis avec sa variante qui complète la ligne (DEC3), jamais un doublon
    choix = [str(c).strip() for c in question.get("choix") or [] if str(c).strip()]
    # B4 (M6, point 2 ; C9, trace 515) : ce que la réponse complète est CONSTATÉ, jamais supposé : le choix qu'elle nomme (ou le premier, sur un
    # « oui » sans mot) ; une réponse dont les mots ne nomment aucun choix ne complète rien, l'article remis n'est pas refusé (avant : perdu)
    nommes = {c.casefold() for c in choix if any(v.casefold() == c.casefold() for v in valeurs)}
    if not valeurs and choix:
        nommes = {choix[0].casefold()}
    propose = str(question.get("article_propose") or "").casefold()
    for a in fiche.get("ajouter") or []:
        nom = str(a.get("article") or "").strip()
        trouve = await moteur._chercher_l_article(source, nom, regles) if nom else None
        article = await source.article(trouve.faits["retenu"], p["mode"]) if trouve is not None and trouve.statut == "RETENU" else None
        if article is None:
            continue
        nom_carte = str(article.get("nom") or "").casefold()
        double = ((question.get("type") == "proposition" and reponse.get("sens") == "accepte" and bool(propose) and nom_carte.startswith(propose))
                  or (question.get("type") != "proposition" and article.get("id") in refs_en_attente)
                  or (question.get("type") == "ambiguite" and nom_carte in nommes))
        if double:  # B4 (M6, appel 530) : « oui » au Coca proposé ET un Coca dans ajouter : un seul Coca
            return B.refus("article_deja_en_question", ["ajouter"], article=article["nom"], question=question.get("id"),
                           a_faire=f"rien n'est ajouté de ajouter : ta réponse à {question.get('id')} complète déjà {article['nom']} ; "
                                   "un second exemplaire se dit après, avec sa quantité")
    return None


async def gardes_de_la_formule(source: Source, p: dict[str, Any], regles: moteur.Reglages, articles: list[dict[str, Any]]) -> dict[str, Any] | None:
    """B10 § 2 et B11 § 2 (point 6) : dans la MÊME fiche, un article qui est aussi le choix d'une étape d'une formule de la fiche (déjà rangé dans sa
    composition, ou d'une étape encore ouverte) n'est pas ajouté : refus de la fiche avec la raison et les deux choix ; le code ne devine pas. ``None`` : aucun conflit."""
    if not p.get("mode") or (len(articles) < 2 and not any(a.get("variante") for a in articles)):
        return None
    lus = []
    for a in articles:
        nom = str(a.get("article") or "").strip()
        trouve = await moteur._chercher_l_article(source, nom, regles) if nom else None
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


def poser_le_prix_du_poids(ctx: Any, resultats: list[dict[str, Any]], retour: dict[str, Any]) -> None:
    """QTE1 (D33) : le prix d'un article au poids est dit par le code après la phrase du modèle (suffixe) ; le retour porte le drapeau, jamais la phrase. ⛔ Ne lève jamais."""
    try:
        for r in resultats:
            faits = r.get("faits") or {}
            phrase = faits.pop("prix_a_dire", None)
            if phrase and isinstance(getattr(ctx, "fiche", None), dict):
                ctx.fiche.setdefault(CLE_TEXTES_DU_CODE, {})["suffixe"] = phrase
                retour["prix_dit_par_le_code_apres_ta_phrase"] = True
    except Exception:  # noqa: BLE001
        pass


async def poser_la_remise_du_code(ctx: Any, source: Any, p: dict[str, Any], regles: Any, retour: dict[str, Any]) -> None:
    """OFF3 (conversation OFF3-A, D33) : la remise à laquelle un code dit donne droit est dite PAR LE CODE, une fois, au moment où elle s'applique au panier (le code dit d'abord, ou les
    articles d'abord), après la phrase du modèle ; le retour porte le drapeau, jamais la phrase. Sans cela la personne qui a dit son code n'entendait jamais que la remise était prise.
    ⛔ Ne lève jamais."""
    try:
        if not p.get("remises_du_code") or p.get("enregistree") or p.get("annulee") or not isinstance(getattr(ctx, "fiche", None), dict):
            return
        if not (p["lignes"] and p["mode"]) or P.a_completer(p):
            return
        chiffre = await moteur._chiffrer(source, p, regles)
        if chiffre.statut != "OK":
            return
        nouvelles = [r for r in chiffre.faits.get("remises") or [] if r["ref"] in p["remises_du_code"] and J.une_fois(p, moteur.cle_de_la_remise(r["ref"]))]
        if not nouvelles:
            return
        textes = ctx.fiche.setdefault(CLE_TEXTES_DU_CODE, {})
        textes["suffixe"] = " ".join(x for x in (textes.get("suffixe"), *(moteur._phrase_d_une_remise_appliquee(r) for r in nouvelles)) if x)
        retour["prix_dit_par_le_code_apres_ta_phrase"] = True
    except Exception:  # noqa: BLE001
        pass


def poser_les_regles_de_l_article(ctx: Any, resultats: list[dict[str, Any]], retour: dict[str, Any], p: dict[str, Any]) -> None:
    """FOR7, FOR9, FOR13 (conversations du lot 11) : la condition, le justificatif ou ce qui est servi avec un article ajouté sont dits par le code avant la phrase
    du modèle (préfixe, comme la règle de FOR3), une seule fois par appel ; le retour garde les faits et porte les drapeaux, jamais la phrase. ⛔ Ne lève jamais."""
    try:
        fiche = getattr(ctx, "fiche", None)
        a_dire = [str(f.pop("regle_a_dire")) for r in resultats if isinstance(f := r.get("faits"), dict) and f.get("regle_a_dire")]
        if not isinstance(fiche, dict):
            return
        nouvelles = [x for x in dict.fromkeys(a_dire) if J.une_fois(p, f"regle:{x}")]  # B3 (M5) : une fois par appel, au journal
        if not nouvelles:
            return
        textes = fiche.setdefault(CLE_TEXTES_DU_CODE, {})
        textes["prefixe"] = " ".join(x for x in (textes.get("prefixe"), *nouvelles) if x)
        retour["dit_avant_ta_phrase"] = True
        retour["regle_dite_par_le_code"] = True
        retour.setdefault("a_faire", "le code vient de lui dire la règle de l'article : ta phrase suit, sans la redire")
    except Exception:  # noqa: BLE001
        pass


def poser_la_regle_de_la_ligne(ctx: Any, resultats: list[dict[str, Any]], retour: dict[str, Any]) -> None:
    """FOR3 (B11 point 2, D33) : un choix refusé hors d'une ligne limitée par un prix : le code dit la règle avant la phrase du modèle (préfixe), le retour porte
    les drapeaux, jamais la phrase. ⛔ Ne lève jamais."""
    try:
        for r in resultats:
            faits = r.get("faits") or {}
            if faits.get("raison") == for3.RAISON and faits.get("regle_prix_max") and isinstance(getattr(ctx, "fiche", None), dict):
                formule = str(faits.get("article") or "")
                ctx.fiche.setdefault(CLE_TEXTES_DU_CODE, {})["prefixe"] = for3.phrase_de_la_regle(formule, str(faits.get("etape") or ""), int(faits["regle_prix_max"]))
                retour["dit_avant_ta_phrase"] = True
                retour["regle_dite_par_le_code"] = True
                faits.pop("regle_prix_max", None)
                return
    except Exception:  # noqa: BLE001
        pass


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
    p["vente_en_plus_tot"] = True
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
CASES_QUI_CHANGENT_LA_COMMANDE = ("ajouter", *contrat.CASES_DES_LIGNES, "mode_de_retrait", "adresse", "commune", "heure")


_FINALISER_DE_LA_FICHE: ContextVar[list | None] = ContextVar("finaliser_de_la_fiche", default=None)


def finalise_deja_dans_la_fiche() -> bool:
    """C7 : la fiche en cours a déjà mené la commande vers sa fin (un seul ``finaliser`` par fiche)."""
    return bool(_FINALISER_DE_LA_FICHE.get())


async def executer_la_fiche(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    """La fiche du modèle exécutée par le code, dans son ordre ; rend l'enveloppe (statut, résultats, question numérotée, refus et ``a_faire``).
    C7 (lot 19 bis) : UN SEUL ``finaliser`` par fiche (le second validait la question du numéro que le premier venait de poser) : le résultat du premier est celui de la fiche."""
    jeton = _FINALISER_DE_LA_FICHE.set([])
    try:
        return await _executer_la_fiche(fiche_du_modele, contexte)
    finally:
        _FINALISER_DE_LA_FICHE.reset(jeton)


RIEN_CHANGE = DU.RIEN_CHANGE


async def _executer_la_fiche(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    vu_avant = DU.ce_qui_se_voit(contexte.panier)
    retour = await _executer_la_fiche_sans_le_constat(fiche_du_modele, contexte)
    return DU.constater(retour, vu_avant, contexte.panier, texte_a_dire_du_manque)  # B2 : ce qui est dû, à la sortie de toute fiche


async def _executer_la_fiche_sans_le_constat(fiche_du_modele: dict[str, Any], contexte: Any) -> dict[str, Any]:
    ctx = contexte
    source, p, regles = ctx.source, ctx.panier, ctx.regles
    fiche = fiche_du_modele
    p["tour_de_l_appel"] = int((getattr(ctx, "fiche", None) or {}).get(contrat.CLE_DU_TOUR) or 0)  # lot 15 : l'allergie donnée au modèle dans un tour fini seulement lève le blocage
    if isinstance(getattr(ctx, "fiche", None), dict):
        ctx.fiche[CLE_TEXTES_DU_CODE] = {}  # ceux de la fiche d'avant ne sont jamais redits
        poser_le_fait_bloquant(ctx.fiche, None, None)
    # 1. La fiche entière : lisible, cases montrées dans ce tour (D52), bons types, réponse attendue, bonne question.
    entier = B.fiche_illisible(fiche)
    reponse_ecartee = None
    case_ecartee = None  # B4 : une case que ce tour ne montre pas, écartée seule
    if entier is None:
        fiche = {k: v for k, v in fiche.items() if v is not None}
        montrees = _cases_montrees(ctx)
        if montrees is None:
            entier = B.refus("cases_pas_ouvertes", ["*"], a_faire="rien n'est changé : les cases de ce tour ne sont pas connues")
        else:
            question = p.get("question") if isinstance(p.get("question"), dict) else None
            posee = contrat.question_posee(question, (ctx.fiche or {}).get(contrat.CLE_DU_TOUR, 0))
            if isinstance(fiche.get("reponse"), dict) and "reponse" not in montrees:
                # B1 : une réponse quand aucune question n'est montrée (la question est close) : sa case seule est écartée, jamais le reste (conv5)
                reponse_ecartee = B.question_inconnue(fiche, None)
                fiche = {k: v for k, v in fiche.items() if k != "reponse"}
            sans_objet = B.case_sans_objet(fiche, montrees)
            if sans_objet is not None and all("[" not in c and "." not in c for c in sans_objet["cases"]) and set(fiche) - set(sans_objet["cases"]) - {"a_dire"}:
                # B4 (M9 : même faute, même traitement ; RC2) : une case que ce tour ne montre pas n'écarte qu'elle, comme une réponse sans question ;
                # avant : la fiche entière refusée, l'article dit avec elle perdu
                case_ecartee = B.refus("case_sans_objet", sans_objet["cases"],
                                       a_faire="pas ouvert maintenant, rien n'en est pris ; le reste de la fiche est fait")
                fiche = {k: v for k, v in fiche.items() if k not in sans_objet["cases"]}
            else:
                entier = sans_objet
            entier = entier or B.format(fiche, _schema_de_la_fiche(ctx)) or B.sens_de_la_reponse(fiche)
            if entier is None:
                # B1 : une réponse à une autre question (ou sans question) n'écarte que sa case, jamais le reste de la fiche (RC2) ; la question posée
                # reçoit alors « autre », comme une fiche sans réponse (une seule règle pour tous les types)
                reponse_ecartee = reponse_ecartee or B.question_inconnue(fiche, question)
                if reponse_ecartee is not None:
                    fiche = {k: v for k, v in fiche.items() if k != "reponse"}
                fiche = RQ.reponse_implicite(fiche, question, posee)
    if entier is not None:
        return Enveloppe("REJETEE", raison=entier["raison"], a_faire=entier["a_faire"], plus={"refus": [entier], "cases_refusees": entier["cases"],
                                                                                              "fiche_appliquee": False}).vers_json()
    # 2. Rejouée à l'identique dans ce tour : rien ne change (E11).
    tour = (ctx.fiche or {}).get(contrat.CLE_DU_TOUR, 0)
    if deja_executee(p, cle_d_idempotence(tour, "fiche", fiche)):
        return Enveloppe("FAIT", faits={"deja_fait": True}, plus={"fiche_appliquee": False, "rien_ajoute": True}).vers_json()
    # 3. Les barrières d'une case, puis le filet des cases liées (D8).
    refus: list[dict] = [x for x in (reponse_ecartee, case_ecartee) if x is not None]
    plafond = plafond_d_operations(fiche, lots=await moteur.lots_des_quantites_hautes(source, p, regles, fiche))
    if plafond is not None:
        refus.append(plafond)
    paroles = list((ctx.fiche or {}).get(CLE_DES_PAROLES) or [])
    dit = list((ctx.fiche or {}).get(CLE_DIT_PAR_LE_CODE) or [])
    for case, choix in (("mode_de_retrait", list(source.modes)), ("moyen_de_paiement", list(MOYENS_DE_LA_FICHE)), ("moyen_reste", list(MOYENS_DE_LA_FICHE))):
        if fiche.get(case) not in (None, ""):
            valeur, r = B.valeur_hors_liste(case, fiche[case], [*choix, contrat.AUTRE])
            if r is not None or valeur == contrat.AUTRE:
                refus.append(r or B.refus("valeur_hors_liste", [case], choix=choix))
            else:
                fiche[case] = valeur
    if p.get("enregistree") and fiche.get("c_est_tout") is True:
        refus.append(B.refus("deja_fait", ["c_est_tout"], a_faire="rien n'est changé : la commande de cet appel est déjà enregistrée"))
    visees = [str(n) for n in fiche.get("retirer_article") or []] + [str(c.get("ligne")) for c in fiche.get("changer_quantite") or [] if isinstance(c, dict)]
    doublees = sorted({v for v in visees if visees.count(v) > 1})
    if doublees:
        # B4 (M6, point 1 ; C8, DF8) : deux cases sur la même ligne (« enlevez-la, non mettez-en deux ») se lisent AVANT d'exécuter ; avant : exécutées
        # l'une après l'autre, la seconde échouait (« Il n'y a encore rien dans la commande. ») ; les deux sont refusées, avec la question à poser
        refus.append(B.refus("conflit_sur_une_ligne", [c for c in ("retirer_article", "changer_quantite") if fiche.get(c)],
                             a_faire=f"rien n'est changé sur la ligne {', '.join(doublees)} : elle y a dit deux choses ; demande-lui ce qu'elle veut pour cette ligne"))
    fin_redite = [c for c in contrat.CASES_DE_FIN if fiche.get(c) not in (None, "")]
    if RQ.phase(p) == RQ.ENREGISTREE and fin_redite:
        # B4 (M7, table « phase → cases ») : enregistrée, le règlement, le numéro et le prénom ne changent plus rien ; avant, notés en silence et
        # « C'est noté » dit (RC4, E16 → G19)
        refus.append(B.refus("deja_fait", fin_redite, a_faire="rien n'est changé : la commande de cet appel est déjà enregistrée"))
    libres = B.valeur_pas_dans_ses_mots(fiche, paroles, dit)
    if libres is not None:
        refus.append(libres)
    reponse = fiche.get("reponse") if isinstance(fiche.get("reponse"), dict) else None
    accepte_ici = bool(reponse and reponse.get("sens") == "accepte" and (p.get("question") or {}).get("type") == "relecture")
    fin = B.recapitulatif_pas_accepte(fiche, contrat.CASES_DE_FIN, bool(p.get("relecture_acceptee")), accepte_ici)
    if fin is not None:
        refus.append(fin)
    # B1 : la réponse écartée (elle visait une question close ou une autre) n'est pas une faute sur la commande : elle n'écarte rien d'autre
    repart = bool(reponse and reponse.get("sens") == "accepte" and (p.get("question") or {}).get("type") == RQ.TYPE_NOUVELLE_COMMANDE)
    if RQ.phase(p) == RQ.ANNULEE and not repart:
        dites = [c for c in (*CASES_QUI_CHANGENT_LA_COMMANDE, "c_est_tout", *contrat.CASES_DE_FIN) if fiche.get(c) not in (None, "", [], {}, False)]
        if dites:
            # DC5 (Evan, 22/11) : la commande annulée n'existe plus ; rien n'y entre ; le code le dit et propose d'en passer une nouvelle
            refus.append(B.refus("commande_annulee", dites, a_faire="rien n'est changé : la commande est annulée ; le code vient de proposer une nouvelle commande, attends sa réponse"))
            RQ.proposer_une_nouvelle_commande(p)
    ecartees = cases_ecartees(c for r in refus if r is not reponse_ecartee and r is not case_ecartee for c in r["cases"])
    # B4 (M6, point 3) : une case déjà faite dans ce tour, à l'identique (la fiche refaite après un refus partiel), n'est pas refaite
    deja_faites = {c for c, v in fiche.items() if c not in ecartees and case_deja_faite(p, tour, c, v)}
    # 4. Les cases dans l'ordre du code, chacune par son opération nommée.
    resultats: list[dict] = []
    executees: list[str] = []
    dernier: Resultat | None = None
    appelant = moteur.Appelant(numero_e164((ctx.appel or {}).get("caller_number")), str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
    question_avant = p.get("question") if isinstance(p.get("question"), dict) else None
    if question_avant is not None and RQ.objet(question_avant, p) not in (p.get(RQ.CLE_DES_QUESTIONS) or {}):
        RQ.ouvrir(p, question_avant)  # B1 : la question posée est au registre (un état d'avant le registre, ou posée hors de lui)
    avant_enregistree = copy.deepcopy(p) if moteur.commande_de_l_appel(p) is not None else None  # E10 : le panier d'avant, si le changement ne passe pas
    p["question"] = None if reponse else question_avant
    empreinte_avant = P.empreinte(p) if p.get("mode") else None
    informations_faites = False
    heure_refusee: str | None = None  # D33, D34 : ce que le code dit de l'heure voulue (refus du créneau, fermé mais planifiable)
    gardee = False
    # D01 : calculée AVANT la réponse, tant que la ligne qu'elle complète est encore en attente
    garde_en_question = await garde_article_deja_en_question(source, p, regles, fiche, question_avant, {l.get("ref") for l in P.a_completer(p)})
    for case in ordre_des_cases(fiche):
        if case in ecartees or "*" in ecartees or case in deja_faites:
            continue
        if case in INFORMATIONS:
            if informations_faites:
                continue
            informations_faites = True
            r = await _poser_les_informations(source, p, regles, appelant, fiche, ecartees | deja_faites)
            operation = "informations"
        elif case == "vider_le_panier":
            r, operation = await moteur.vider_commande(source, p, regles), case
            RQ.tout_fermer(p)  # B1 : on recommence : les questions de la commande d'avant tombent avec elle (la proposition comprise)
        elif case == "annuler_la_commande":
            r, operation = await annuler(source, p, regles), case
            RQ.tout_fermer(p)
        elif case == "annuler_une_commande_enregistree":
            if moteur.commande_de_l_appel(p) is not None and moteur.annulation_possible(source):
                # DC4 (Evan, 22/11) : premier temps : la question de confirmation, avec le montant, dite par le code ; rien n'est annulé avant le « oui »
                RQ.demander_l_annulation(p)
                r, operation = Resultat("OK", {"confirmation_demandee": True}, ""), case
            else:
                r, operation = await moteur.annuler_commande_enregistree(source, p, regles), case  # la raison du refus (introuvable, impossible)
        elif case == "reponse" and ({"vider_le_panier", "annuler_la_commande"} & set(executees)):
            # la question en attente portait sur le panier que cette même fiche vient de vider ou d'annuler : la réponse n'a plus d'objet
            refus.append(B.refus("question_inconnue", ["reponse"], a_faire="rien n'est changé pour reponse : la question en attente a disparu avec le panier"))
            continue
        elif case == "reponse":
            r, operation = await repondre_a_la_question(source, p, regles, appelant, question_avant or {}, reponse.get("sens"), reponse.get("valeurs")), case
            gardee = bool((r.faits or {}).get("question_gardee"))
            if not gardee:
                RQ.fermer(p, question_avant)  # B1 : la question a sa réponse, elle quitte le registre (son numéro reste à son objet)
            if p.get("hesitations_a_poser") and not gardee and r.statut in ("OK", "RETENU"):
                # T3 : la réponse est prise ; l'hésitation suivante de la même fiche est posée à son tour
                suivante = p["hesitations_a_poser"].pop(0)
                r_suivante = await ajouter_un_article(source, p, regles, suivante)
                if r_suivante.statut == "AMBIGU":
                    r_suivante = Resultat(r_suivante.statut, {**(r_suivante.faits or {}), CLE_ARTICLE_DIT: dict(suivante)}, r_suivante.suggestion, r_suivante.manque)
                if r_suivante.statut != "OK":
                    resultats.append(_resultat_public(operation, r))
                    r = r_suivante
            if (question_avant or {}).get("type") in ("variante", "ambiguite", for2.TYPE_DE_LA_QUESTION):
                # l'article complété par la réponse est pris : la vente en plus suit, comme après un ajout
                resultats.append(_resultat_public(operation, r))
                proposition = await vente_en_plus_apres_le_premier_article(source, p, regles, r)
                r, operation = (proposition, "proposition") if proposition is not None else (r, None)
                if operation is None:
                    dernier = r
                    executees.append(case)
                    continue
        elif case == "retirer_article":
            for n in fiche["retirer_article"]:
                r = await moteur.retirer(source, p, regles, ligne=str(n))
                resultats.append(_resultat_public(case, r))
            dernier, operation = r, None
        elif case == "changer_quantite":
            for c in fiche["changer_quantite"]:
                choix = ", ".join([*(c.get("supplements") or []), *(c.get("composition") or [])]) or None
                variante = c.get("variante") if c.get("variante") not in (None, "", "autre") else None
                r = await moteur.modifier(source, p, regles, ligne=str(c.get("ligne")), quantite=c.get("quantite"), choix=choix, variante=variante,
                                          sans=", ".join(c.get("sans") or []) or None, note=c.get("precision_article"))
                resultats.append(_resultat_public(case, r))
            dernier, operation = r, None
        elif case == "ajouter" and garde_en_question is not None:
            refus.append(garde_en_question)  # D01 : la réponse de la même fiche complète déjà l'article remis dans ajouter
            continue
        elif case == "ajouter" and (garde_formule := await gardes_de_la_formule(source, p, regles, list(fiche["ajouter"]))) is not None:
            refus.append(garde_formule)  # rien n'est ajouté de cette case : la fiche se refait selon ce qu'elle a dit
            continue
        elif case == "ajouter":
            demande = None  # D25 : le premier résultat qui demande quelque chose porte la question et le statut, jamais écrasé par le suivant
            en_attente: list[dict[str, Any]] = []  # T3 : les hésitations suivantes, posées l'une après l'autre
            for article in fiche["ajouter"]:
                r = await ajouter_un_article(source, p, regles, article)
                resultats.append(_resultat_public(case, r))
                if r.statut == "AMBIGU":
                    # D24 : l'article dit (quantité, choix) est gardé avec la question d'hésitation, pour que « oui » l'ajoute (jamais montré au modèle)
                    r = Resultat(r.statut, {**(r.faits or {}), CLE_ARTICLE_DIT: dict(article)}, r.suggestion, r.manque)
                if r.statut in ("AMBIGU", "CHOIX_OBLIGATOIRE") or r.statut in STATUTS_QUI_REFUSENT:  # T3 : toute réponse en attente compte (une taille à choisir aussi)
                    if demande is None:
                        demande = r
                    elif r.statut == "AMBIGU":
                        en_attente.append(dict(article))
            if en_attente:
                p["hesitations_a_poser"] = [*(p.get("hesitations_a_poser") or []), *en_attente]
            if demande is not None:
                r = demande
            if r.statut == "OK" and "garde" not in (r.faits or {}):
                # l'état du panier après les ajouts (chiffrage, minimum de la zone), comme ``moteur.ajouter`` le rend après sa phrase
                etat = await moteur._etat_apres_ajout(source, p, regles, dict(r.faits or {}))
                r = Resultat(etat.statut, etat.faits, etat.suggestion, etat.manque)
                resultats[-1] = _resultat_public(case, r)
            proposition = await vente_en_plus_apres_le_premier_article(source, p, regles, r)
            if proposition is not None:
                resultats.append(_resultat_public("proposition", proposition))
                r = proposition
            dernier, operation = r, None
        elif case == "c_est_tout":
            r, operation = await recapituler(source, p, regles, appelant), case
        else:
            continue
        if operation is not None:
            resultats.append(_resultat_public(operation, r))
            dernier = r
            if heure_refusee is None and r.manque in ("heure_voulue", "heure_proposee") and (r.suggestion or "").strip() and r.statut not in ("RETENU", "OK"):
                # D33, D34 : ce que le code dit de l'heure voulue (le refus de son créneau ; fermé mais planifiable : « Pour quel jour et à quelle
                # heure ? ») est dit par le code, même quand une autre opération suit ou que l'opération n'ouvre pas de question
                heure_refusee = r.suggestion.strip()
        executees.append(case)
    noter_les_cases(p, tour, {c: v for c, v in fiche.items() if c not in ecartees and c not in deja_faites and "*" not in ecartees})
    porteur = None  # le retour qui porte la question quand ce n'est pas le dernier (la proposition après un hors zone)
    if (dernier is not None and dernier.statut in ("OK", "RETENU", "HORS_ZONE") and not dernier.manque and not p.get("question")
            and "c_est_tout" not in executees):
        # les articles gardés faute de mode ou d'adresse sont pris quand la même fiche les pose : la vente en plus suit ce premier article pris ;
        # hors zone, le refus de la zone reste le fait de la fiche et la proposition porte la question (B12, conversation 2)
        proposition = await vente_en_plus_apres_le_premier_article(source, p, regles, Resultat("OK", {}, ""))
        if proposition is not None:
            resultats.append(_resultat_public("proposition", proposition))
            if dernier.statut == "HORS_ZONE":
                porteur = proposition
            else:
                dernier = proposition
    if ((question_avant or {}).get("type") == "relecture" and not p.get("relecture_acceptee") and not p.get("question") and "c_est_tout" not in executees
            and p.get("mode") and P.lignes_pretes(p) and P.empreinte(p) != empreinte_avant and not finalise_deja_dans_la_fiche()):
        # un changement pendant la relecture : la relecture repart (B12, conversation 3 ; banc : le changement de ligne relance le récapitulatif)
        dernier = await recapituler(source, p, regles, appelant)
        resultats.append(_resultat_public("c_est_tout", dernier))
    if ((question_avant or {}).get("type") == "heure_proposee" and question_avant.get(APRES_C_EST_TOUT) and p.get("heure_voulue")
            and "c_est_tout" not in executees and not finalise_deja_dans_la_fiche()):
        # B1 : l'heure dite pendant « je vous la prépare pour … ? » après « c'est tout » est sa réponse : la commande va à sa relecture
        dernier = await recapituler(source, p, regles, appelant)
        resultats.append(_resultat_public("c_est_tout", dernier))
    if (avant_enregistree is not None and moteur.commande_de_l_appel(p) is not None
            and P.empreinte(p) != P.empreinte(avant_enregistree)):
        # E10 : la commande de cet appel, déjà enregistrée, a changé : le changement part en caisse (ou rien ne change, avec la raison)
        dernier = await moteur.changer_commande_enregistree(source, p, regles, appelant, avant_enregistree)
        resultats.append(_resultat_public("changer_la_commande_enregistree", dernier))
        if dernier.statut == "INCOMPLETE" and dernier.manque == "articles" and moteur.annulation_possible(source):
            # B4 (M2) + DC4 : tout retirer d'une commande enregistrée, c'est l'annuler : rien n'a changé, la confirmation en deux temps est posée
            RQ.demander_l_annulation(p)
    if (p.get("relecture_acceptee") and not p.get("enregistree") and not p.get("annulee") and "reponse" in executees and dernier is not None
            and not finalise_deja_dans_la_fiche()):
        dernier = await recapituler(source, p, regles, appelant, confirmer=True)
        resultats.append(_resultat_public("enregistrer", dernier))
    # 5. B1 : la question née de ce tour entre au registre ; UNE seule est posée, la première dont la condition est vraie (registre.choisir).
    q = _question_de(porteur or dernier, 0, tour, p) if dernier is not None else None
    if dernier is not None and dernier.statut in STATUTS_ENREGISTRES:
        ctx.enregistrement = dernier  # le résultat brut (dates comprises), lu par le flux du portail et le SMS
    if q is not None and q.get("type") == "heure_proposee" and "c_est_tout" in executees:
        q[APRES_C_EST_TOUT] = True
    RQ.ouvrir(p, q)
    if not refus and not (dernier is not None and statut_qui_refuse(dernier.statut)) and not any(
            x.get("type") == "ambiguite" for x in (p.get(RQ.CLE_DES_QUESTIONS) or {}).values()):
        while p.get("hesitations_a_poser"):
            # T3 : l'article suivant en doute (même fiche) est cherché à son tour ; sa question entre au registre
            article = p["hesitations_a_poser"].pop(0)
            r_h = await ajouter_un_article(source, p, regles, article)
            resultats.append(_resultat_public("ajouter", r_h))
            if r_h.statut == "AMBIGU":
                r_h = Resultat(r_h.statut, {**(r_h.faits or {}), CLE_ARTICLE_DIT: dict(article)}, r_h.suggestion, r_h.manque)
            q_h = _question_de(r_h, 0, tour, p)
            if q_h is not None:
                RQ.ouvrir(p, q_h)
                break
    attente = moteur.question_de_la_ligne_en_attente(p)
    posee = RQ.choisir(p, tour, [_question_de(attente, 0, tour, p)] if attente is not None else [])
    q = posee
    # née dans ce tour : posée maintenant pour la première fois, ou reposée avec un autre texte (une relecture qui repart) ; dite par le code si c'est sa forme
    nee = posee if posee is not None and (not question_avant or posee["id"] != question_avant.get("id") or posee.get("texte") != question_avant.get("texte")
                                          or posee.get("nee_au_tour") == tour) else None
    raison_dite = None
    consigne_du_journal = None  # B3 : la consigne du journal quand le fait bloquant n'est pas redit par le code
    if isinstance(getattr(ctx, "fiche", None), dict):
        textes = textes_du_code(p, dernier, nee, refus, deja_enregistree=avant_enregistree is not None,
                                total_d_avant=(moteur.commande_de_l_appel(avant_enregistree) or {}).get("total") if avant_enregistree else None,
                                question_apres=getattr(regles, "question_apres_enregistrement", None))
        raison = raison_du_fait_bloquant(dernier)
        if heure_refusee and heure_refusee != raison:
            # Lot 19, D33 (run 208) : l'heure refusée par son créneau (« Je ne prends pas de commande pour plus tard. ») était perdue quand une autre
            # opération de la fiche suivait (la relecture) : le modèle confirmait l'heure. Elle est dite par le code, avant le reste.
            if "avant" in textes:
                textes["avant"] = f"{heure_refusee} {textes['avant']}"
            else:
                raison = f"{heure_refusee} {raison}" if raison else heure_refusee
            raison_dite = heure_refusee
        if raison and "avant" not in textes:
            # Point de contrôle du lot 7 (règle du lot 6) : un fait bloquant qui refuse est dit par le code, avant la phrase du modèle (préfixe) :
            # la phrase du modèle peut ne pas le dire (conv2 : « C'est bien noté … à Compiègne »). B3 (M5, C7, DF7) : la première fois ; ensuite le
            # journal de ce qui est dit : le modèle propose une issue, puis la sortie au deuxième échec
            etape = J.fait_redit(p, raison, tour)
            if etape == J.PREMIERE:
                textes["prefixe"] = raison
                raison_dite = raison
            else:
                consigne_du_journal = J.consigne(etape)
        ctx.fiche[CLE_TEXTES_DU_CODE] = textes
        if textes.get("avant") and dernier is not None and (dernier.statut in STATUTS_ENREGISTRES or dernier.faits.get("commande_annulee")
                                                            or dernier.faits.get("annulee")):
            p[CLE_DU_DERNIER_FAIT] = textes["avant"]  # B2 (M3, règle 3) : le fait accompli, que le repli redit au lieu de « je n'ai pas compris »
        poser_le_fait_bloquant(ctx.fiche, tour, phrase_du_fait_bloquant_de(dernier), deja_dit=raison_dite)
    retour = _enveloppe_de_la_fiche(p, resultats, executees, refus, ecartees, dernier, nee)
    if raison_dite:
        retour["dit_avant_ta_phrase"] = True
        retour["a_faire"] = " ; ".join(x for x in (A_FAIRE_DU_REFUS_DIT, retour.get("a_faire")) if x)
    elif consigne_du_journal:
        retour["a_faire"] = " ; ".join(x for x in (consigne_du_journal, retour.get("a_faire")) if x)
    return retour


APRES_C_EST_TOUT = "apres_c_est_tout"  # l'heure proposée à la relecture (« c'est tout ») mène à la relecture ; proposée au début, non
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
    propose = phrase_du_manque(MODE_DU_MANQUE, [a for a in autres if a]) if autres else None
    return f"{phrase} {propose}" if propose else phrase


def _a_faire_de_la_proposition(q: dict[str, Any]) -> tuple[str, bool]:
    """D33 (B9 § 2 point 4 ; B10 § 1 point 4) : la proposition née dans ce tour est posée par le modèle, avec ses mots et sans chiffre ; le code dit le
    prix juste après sa phrase (le drapeau seul est dans le retour, jamais la phrase). Une proposition offerte n'a pas de chiffre."""
    article = q.get("article_propose") or ""
    if q.get("offerte"):
        return f"propose-lui {article} offert en une question, avec tes mots", False
    return f"propose-lui {article} en une question, avec tes mots et sans aucun chiffre : le code dit son prix juste après ta phrase", bool(q.get("chiffre"))


def _enveloppe_de_la_fiche(p, resultats, executees, refus, ecartees, dernier, nee=None) -> dict[str, Any]:
    from api.services.actions_communes.enveloppe import Question

    q = p.get("question")
    question = None
    if isinstance(q, dict):
        reponses = for2.REPONSES if q["type"] == for2.TYPE_DE_LA_QUESTION else None  # FOR2 : son choix, dans valeurs (B10)
        question = Question(q["id"], q["type"], q.get("texte") or "", *((reponses,) if reponses else ()))
    bloquant = (dernier is not None and (statut_qui_refuse(dernier.statut) or dernier.statut in ("INCOMPLETE", STATUT_MINIMUM))  # C2 : tout refus du module (liste d'exclusion)
                and dernier.manque not in ("relecture",))
    statut = "PARTIEL" if refus or bloquant else ("ENREGISTREE" if dernier is not None and dernier.statut in STATUTS_ENREGISTRES else ("ANNULEE" if p.get("annulee") else "FAIT"))
    if question is not None and statut == "FAIT" and q.get("type") in ("variante", "ambiguite", for2.TYPE_DE_LA_QUESTION):
        statut = "A_PRECISER"
    plus: dict[str, Any] = {"fiche_appliquee": bool(executees), "cases_executees": executees}
    if refus:
        plus["refus"] = refus
        plus["cases_refusees"] = sorted({c for r in refus for c in r["cases"]})
        plus["cases_non_executees_car_liees"] = sorted(ecartees - set(plus["cases_refusees"]) - {"*"})
    faits: dict[str, Any] = {"panier": en_json(P.resume(p))}
    if bloquant:
        faits["fait_bloquant"] = {"statut_du_module": dernier.statut, "manque": dernier.manque}
    premier = refus[0] if refus else None
    a_faire = B.a_faire_du_refus_partiel(premier, executees) if premier else None
    if nee is not None and nee.get("type") == for2.TYPE_DE_LA_QUESTION and not refus:
        a_faire = for2.A_FAIRE
    if nee is not None and nee.get("type") == "proposition" and not refus:
        a_faire, prix_dit = _a_faire_de_la_proposition(nee)
        if prix_dit:
            plus["prix_dit_par_le_code_apres_ta_phrase"] = True
    return Enveloppe(statut, resultats=resultats, faits=faits, question=question, raison=premier["raison"] if premier else None,
                     a_faire=a_faire, plus=plus).vers_json()


async def _poser_les_informations(source, p, regles, appelant, fiche, ecartees) -> Resultat:
    """Les informations de la fiche : mode, adresse et commune ensemble (S3), consigne, heure, puis la fin (moyen, billet, téléphone, prénom)."""
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
        p.setdefault("fin_dite", {}).update({k: (MOYENS_DE_LA_FICHE.get(v, v) if k in ("moyen_de_paiement", "moyen_reste") else v) for k, v in fin.items()})
        moyen_dit = MOYENS_DE_LA_FICHE.get(fin.get("moyen_de_paiement"), fin.get("moyen_de_paiement"))
        if "rendu_sur" not in fin and moyen_dit and moyen_dit != "especes" and (p.get("paiement") or {}).get("moyen_reste") != "especes":
            P.effacer_le_billet(p)  # C3 : « finalement par carte » après « un billet de cinquante » : le billet ne repart plus
    if (fin or garde("consigne_livreur")) and p.get("relecture_acceptee") and not p.get("enregistree") and not p.get("annulee"):
        r = await recapituler(source, p, regles, appelant, confirmer=True)
    return r or Resultat("OK", {}, "")


async def recapituler(source: Source, p: dict[str, Any], regles: moteur.Reglages, appelant: moteur.Appelant, confirmer: bool = False) -> Resultat:
    """« c'est tout » : la commande menée à son récapitulatif (puis à l'enregistrement après son accord), un manque à la fois ; le corps est réécrit
    au lot 4 en fonctions nommées, la signature reste."""
    deja = _FINALISER_DE_LA_FICHE.get()
    if deja:
        return deja[0]  # C7 : un seul ``finaliser`` par fiche
    fin = p.get("fin_dite") or {}
    r = await moteur.finaliser(source, p, regles, appelant, confirmer=confirmer, prenom=fin.get("prenom"), telephone=fin.get("telephone"),
                               moyen=fin.get("moyen_de_paiement"), rendu_sur=fin.get("rendu_sur"), part=fin.get("part"), moyen_reste=fin.get("moyen_reste"))
    if deja is not None:
        deja.append(r)
    return r


async def annuler(source: Source, p: dict[str, Any], regles: moteur.Reglages) -> Resultat:
    """Elle ne veut plus de la commande en cours : rien n'est enregistré, aucun panier n'est laissé ouvert (A04, E9)."""
    await moteur.vider_commande(source, p, regles)
    p["annulee"] = True
    p["question"] = None
    # Chantier Partie 1, lot 6 (L06-41, ``banc-b2/guichet_candidat.py`` op ``annuler``) : le code dit l'annulation lui-même, comme au banc.
    return Resultat("OK", {"annulee": True}, "Je ne l'enregistre pas.")


async def executer_la_fiche_du_service(fiche_du_modele: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """La fiche du service (lot 3, étape 9) : retrouver une commande d'un appel précédent (par le numéro qui appelle, ou par un numéro dit ;
    un téléphone dicté seulement avec le numéro de la commande, D60 ; jamais un numéro qu'elle n'a pas dit, B7 point 8) et laisser un message à
    l'équipe, UNE fois par appel (E30)."""
    from api.services.integrations.connectors.actions.service import (
        retrouver_par_telephone_dicte_exige_le_numero,
    )
    from api.services.service_client.action import _ecrire_la_demande

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
    demande = fiche_du_modele.get("retrouver_une_commande_enregistree")
    if isinstance(demande, dict):
        numero_dit = str(demande.get("numero_de_commande") or "").strip() or None
        telephone = str(demande.get("telephone") or "").strip() or None
        inventes = [c for c, v in (("telephone", telephone), ("numero_de_commande", numero_dit)) if v and not valeur_dite_par_elle(v, c if c == "telephone" else "prenom", paroles)]
        if inventes:
            refus.append(B.refus("valeur_pas_dans_ses_mots", ["retrouver_une_commande_enregistree"], valeurs={c: "" for c in inventes},
                                 a_faire="rien n'est changé : un numéro se prend seulement s'il est dit"))
        else:
            exige = retrouver_par_telephone_dicte_exige_le_numero(fiche_du_modele, affiche, f"Q-{int(fiche.get('service_prochain_q') or 1)}")
            if exige is not None:
                fiche["service_prochain_q"] = int(fiche.get("service_prochain_q") or 1) + 1
                return exige
            regles = _regles(ctx)
            p = P.du_dossier(ctx.fiche)
            appelant = moteur.Appelant(affiche, str(ctx.run_id) if getattr(ctx, "run_id", None) else None)
            from api.services.restauration.recherche_reglages import (
                reglages_de_la_recherche,
            )

            async with registre_des_sources.ouvrir((ctx.reglages or {}).get(SOURCE_DE_L_OUTIL), ctx, reglages_de_recherche=reglages_de_la_recherche(ctx.configurations)) as source:
                r = await moteur.retrouver_commande(source, p, regles, appelant, numero_dit)
            # R-d : le suivi ne montre jamais le panier (un panier vide trompe) ; ce qui manque (le numéro de la commande) ou ce qui se choisit
            # (plusieurs commandes) est rendu avec sa phrase, jamais un « FAIT » muet que le modèle comble de lui-même.
            faits_du_suivi = {k: v for k, v in r.faits.items() if k not in ("panier", "candidats")}
            resultats.append({"operation": "retrouver_une_commande_enregistree", "statut_du_module": r.statut, "faits": en_json(faits_du_suivi)})
            if r.statut in ("INCOMPLETE", "AMBIGU") and r.suggestion:
                a_preciser = {"manque": r.manque or "reference", "texte_a_dire": r.suggestion}
            elif r.statut == "INTROUVABLE":
                # P4 : le numéro de l'appel est connu et rien n'y est trouvé : le dire, puis chercher autrement ; jamais redemander ce numéro
                introuvable = "dis-lui qu'il n'y a pas de commande à ce numéro ; propose de chercher autrement (le numéro de la commande, ou un autre numéro) ; ne redemande pas le numéro de l'appel"
    message = fiche_du_modele.get("laisser_un_message")
    if isinstance(message, dict) and str(message.get("objet") or "").strip():
        if fiche.get(CLE_MESSAGE_LAISSE):
            refus.append(B.refus("message_deja_laisse_dans_cet_appel", ["laisser_un_message"], a_faire="rien n'est changé : un seul message par appel"))
        elif _ecrire_la_demande(ctx, str(message["objet"]).strip()[:500], urgence := ("urgente" if message.get("urgent") is True else "normale"), None):
            fiche[CLE_MESSAGE_LAISSE] = True
            resultats.append({"operation": "laisser_un_message", "statut_du_module": "OK", "faits": {"urgent": message.get("urgent") is True}})
            # Lot 6 (C10 ; sens repris de test_message_et_redites_m102_m113 et test_restauration_service_client) : l'issue de l'appel posée par
            # le message laissé, et sa mesure pour le tableau de bord, comme l'ancienne action ``laisser_un_message``.
            poser_l_issue(ctx, "message_a_transmettre")
            from api.services.integrations.connectors import mesures as mesures_des_connecteurs

            mesures_des_connecteurs.ecrire(ctx.fiche, "service.message_laisse", "service.fiche", urgence)
    statut = "PARTIEL" if refus and resultats else ("REJETEE" if refus else ("A_PRECISER" if a_preciser else ("INTROUVABLE" if introuvable else "FAIT")))
    premier = refus[0] if refus else None
    return Enveloppe(statut, resultats=resultats, raison=premier["raison"] if premier else None, a_faire=premier["a_faire"] if premier else (introuvable or None),
                     plus={**({"refus": refus} if refus else {}), **a_preciser}).vers_json()


CLE_MESSAGE_LAISSE = "service_message_laisse"
STATUTS_ENREGISTRES = ("ENREGISTREE", "TRANSMISE")


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
REGLAGE_DES_ISSUES = "issues"


def code_de_l_issue(reglages: Any, issue: str) -> str:
    reglees = (reglages or {}).get(REGLAGE_DES_ISSUES) if isinstance(reglages, dict) else None
    code = reglees.get(issue) if isinstance(reglees, dict) else None
    return code.strip() if isinstance(code, str) and code.strip() else issue


def poser_l_issue(ctx: Any, issue: str) -> None:
    """L'issue de l'appel, posée dans la fiche de l'appel comme le message laissé (M102). ⛔ Ne lève jamais."""
    try:
        poser_l_issue_de_l_appel(getattr(ctx, "fiche", None), issue, code_de_l_issue(getattr(ctx, "reglages", None), issue))  # P6 : « commande enregistrée » n'est jamais écrasée
    except Exception:  # noqa: BLE001
        pass


CLE_ISSUES_REGLEES = "commande_issues_reglees"  # les codes réglés sur l'outil, gardés dans la fiche pour la fin de l'appel


def issue_de_fin_d_appel(fiche_de_l_appel: Any) -> str | None:
    """L06-15 : l'appel finit avec une commande commencée, ni enregistrée ni annulée, et aucune issue posée : ``commande_abandonnee`` (son code
    réglé). ``None`` sinon. ⛔ Ne lève jamais."""
    try:
        if not isinstance(fiche_de_l_appel, dict) or fiche_de_l_appel.get("call_disposition"):
            return None
        p = fiche_de_l_appel.get(P.CLE)
        if not isinstance(p, dict) or not p.get("lignes") or p.get("enregistree") or p.get("annulee"):
            return None
        return code_de_l_issue({REGLAGE_DES_ISSUES: fiche_de_l_appel.get(CLE_ISSUES_REGLEES)}, "commande_abandonnee")
    except Exception:  # noqa: BLE001
        return None


def _poser_l_issue_de_la_fiche(ctx: Any, p: dict[str, Any], avant: dict[str, Any]) -> None:
    """Après la fiche : enregistrée, ou annulée (en cours ou enregistrée) dans CE geste."""
    if p.get("enregistree") and not avant.get("enregistree"):
        poser_l_issue(ctx, "commande_enregistree")
    elif (p.get("annulee") and not avant.get("annulee")) or (p.get("commande_annulee") and p.get("commande_annulee") != avant.get("commande_annulee")):
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
    statut = "LU" if r.statut in ("OK", "RETENU", "TROUVE", "LU") else r.statut
    return Enveloppe(statut, resultats=[{"operation": nom, "statut_du_module": r.statut}], faits=faits).vers_json()


async def executer(action: Any, arguments: dict[str, Any], ctx: Any, delai_s: float) -> dict[str, Any]:
    debut = time.perf_counter()
    try:
        return await _executer(action, arguments, ctx)
    finally:
        _noter_le_temps_du_code(ctx, getattr(action, "nom", "?"), debut)


PHRASE_PANNE_COMMANDE_JOINTE = "Je n'arrive pas à enregistrer votre commande pour le moment. Je la transmets à l'équipe, qui vous rappelle."
PHRASE_PANNE_SANS_COMMANDE = "Je n'arrive pas à faire cela pour le moment."


async def _executer(action: Any, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    regles = _regles(ctx)
    if regles is None:
        return Enveloppe("REJETEE", raison="rien_a_faire").vers_json()
    p = P.du_dossier(ctx.fiche)
    try:
        from api.services.restauration.recherche_reglages import (
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
                etat_d_avant = {k: p.get(k) for k in ("enregistree", "annulee", "commande_annulee")}
                contexte = SimpleNamespace(source=source, panier=p, regles=regles, fiche=ctx.fiche, appel=ctx.appel, run_id=getattr(ctx, "run_id", None),
                                           enregistrement=None)
                retour = await executer_la_fiche(dict(arguments or {}), contexte)
                etat_pour_le_modele.retenir(p, source)
                poser_le_minimum(ctx, p, retour)
                await poser_les_faits_de_l_allergie(ctx, source, p, regles, retour)
                poser_la_regle_de_la_ligne(ctx, retour.get("resultats") or [], retour)
                poser_les_regles_de_l_article(ctx, retour.get("resultats") or [], retour, p)
                poser_le_prix_du_poids(ctx, retour.get("resultats") or [], retour)
                await poser_la_remise_du_code(ctx, source, p, regles, retour)
                _poser_l_issue_de_la_fiche(ctx, p, etat_d_avant)
                await _dire_au_flux(source, avant, p, contexte.enregistrement, ctx)
                _mesurer(ctx.fiche, retour, p.get("mode"))
                return avec_le_fait_du_numero_affiche(retour, contexte_appelant_affiche(ctx))
    except asyncio.CancelledError:
        # P7 (lot 19 bis) : la fiche coupée par son délai (``wait_for``) est une ANNULATION, jamais attrapée par ``except Exception`` : la commande en cours est jointe au message de l'équipe
        # comme pour une panne (la phrase d'échec promet un rappel), puis l'annulation est propagée.
        logger.error(f"[.mark] commande {action.nom} coupée par son délai")
        if _joindre_la_commande_au_message_de_l_equipe(p, ctx):
            poser_l_issue(ctx, "message_a_transmettre")
        raise
    except Exception as erreur:  # noqa: BLE001 -- R1 : au journal, l'appel continue, la commande en cours part à l'équipe (A35)
        logger.error(f"[.mark] commande {action.nom} en échec : {erreur!r}")
        transmise = _joindre_la_commande_au_message_de_l_equipe(p, ctx)
        if transmise:
            poser_l_issue(ctx, "message_a_transmettre")
        if action.nom == "fiche" and isinstance(ctx.fiche, dict):
            # V10 (lot 19 bis) : la panne est dite par le CODE (jamais une phrase improvisée au second passage) ; elle ne promet un rappel que si la commande a bien été jointe à l'équipe
            ctx.fiche[CLE_TEXTES_DU_CODE] = {"avant": PHRASE_PANNE_COMMANDE_JOINTE if transmise else PHRASE_PANNE_SANS_COMMANDE}
        mesures_du_module.de_la_commande(ctx.fiche, action.nom, {"statut": "INDISPONIBLE", "faits": {}})
        return Enveloppe("REJETEE", raison="rien_a_faire", faits={"indisponible": True, "transmise_a_l_equipe": transmise}).vers_json()
    return Enveloppe("REJETEE", raison="operation_inconnue").vers_json()
