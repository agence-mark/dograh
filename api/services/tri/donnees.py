"""[.mark] passages-fiables (lot G) : ce que la file de tri et les alertes lisent dans le run.

Aucune migration, aucune recopie. Tout ce que le code et l'agent notent pendant l'appel vit déjà dans
``gathered_context`` ; ce module sait LE LIRE (jamais le recopier ailleurs) et dit à la base quels runs valent un détour.

- ``signalements`` : l'agent (lot F, source ``agent``) ;
- les traces du code qui méritent un tri : impasse, porte inconnue de l'arbitre, désaccord agent/arbitre, passage par le
  code qui n'a pas abouti, garde du modèle (lent deux fois) ;
- ``alertes`` : le problème du CLIENT (appel en erreur, outil en échec, panne du modèle, transfert échoué).

Le statut d'un signalement (``ouvert`` · ``en cours`` · ``résolu`` · ``fusionné``) n'est PAS dans ``gathered_context`` : la
route de la page l'écrit après l'appel dans ``annotations["tri"]`` du run, une entrée par identifiant de signalement.

Un identifiant de signalement est stable : ``<type>:<rang>`` (les listes de traces ne font que s'allonger ; l'impasse
est numérotée par son compteur, le journal de l'impasse étant glissant).

⛔ Zéro vocabulaire métier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

# --- Les clés du run ---------------------------------------------------------------------------------------------
CLE_SIGNALEMENTS = "signalements"
CLE_ALERTES = "alertes"
CLE_ALERTES_MAIL = "alertes_mail"
CLE_TRI = "tri"  # dans ``annotations``, pas dans ``gathered_context``

# Les clés des traces du code lues par la file (leurs modules les écrivent, ce module ne fait que les lire).
CLE_IMPASSE = "impasse"
CLE_ARBITRE = "arbitre"
CLE_DESACCORDS = "desaccords_arbitre"
CLE_PASSAGES = "passages_par_le_code"
CLE_DEPASSEMENTS = "depassements_modele"
CLE_RETENUES = "retenues_verite"  # écrite par ``workflow/verite_des_actions.tracer_une_retenue``

# --- L'agent ---------------------------------------------------------------------------------------------------
SOURCE_AGENT = "agent"
SOURCE_CODE = "code"
CATEGORIES = ("demande ambiguë", "règle inconnue", "outil en échec", "autre")
CATEGORIE_PAR_DEFAUT = "autre"
MAX_SIGNALEMENTS_PAR_APPEL = 2
LONGUEUR_MAX_MOTIF = 300

# --- Les types lus dans le code -------------------------------------------------------------------------------
TYPE_AGENT = "agent"
TYPE_IMPASSE = "impasse"
TYPE_PORTE_INCONNUE = "porte_inconnue"
TYPE_DESACCORD = "desaccord"
TYPE_PASSAGE = "passage_sans_suite"
TYPE_GARDE_MODELE = "garde_modele"
TYPE_RETENUE = "retenue_verite"
TYPES_DU_CODE = (
    TYPE_IMPASSE,
    TYPE_PORTE_INCONNUE,
    TYPE_DESACCORD,
    TYPE_PASSAGE,
    TYPE_GARDE_MODELE,
    TYPE_RETENUE,
)

# Un passage par le code qui a abouti (ou que la personne a rendu sans objet en reparlant) ne mérite aucun tri.
RESULTATS_NORMAUX_D_UN_PASSAGE = (
    "prise",
    "jetee_la_personne_parle",
    "jetee_autre_visite",
    "jetee_appel_occupe",
    "delai_option_1_jouera",
)
RESULTAT_ARBITRE_A_TRIER = "porte_inconnue"
# Le garde du modèle : une fois, c'est un hoquet (le gardien relance) ; deux fois, c'est à regarder.
DEPASSEMENTS_A_TRIER = 2

# --- Les alertes -------------------------------------------------------------------------------------------------
ALERTE_APPEL_EN_ERREUR = "appel_en_erreur"
ALERTE_OUTIL_EN_ECHEC = "outil_en_echec"
ALERTE_PANNE_MODELE = "panne_modele"
ALERTE_TRANSFERT_ECHOUE = "transfert_echoue"
TYPES_D_ALERTE = (ALERTE_APPEL_EN_ERREUR, ALERTE_OUTIL_EN_ECHEC, ALERTE_PANNE_MODELE, ALERTE_TRANSFERT_ECHOUE)
MAX_ALERTES_PAR_APPEL = 20

# --- Le tri ----------------------------------------------------------------------------------------------------
STATUTS = ("ouvert", "en cours", "résolu", "fusionné")
STATUT_PAR_DEFAUT = "ouvert"

# Borne de lecture (R7) : 30 jours, les runs qui ont quelque chose, 50 par page.
JOURS_DE_LECTURE = 30
RUNS_PAR_PAGE = 50


def _entier(valeur: Any) -> int:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else 0


def chemin_des_runs_a_trier() -> str:
    """Le filtre SQL (``jsonpath``) des runs qui portent au moins un signalement : celui de l'agent ou une trace du code
    qui mérite un tri. Écrit à partir des mêmes constantes que la lecture ci-dessous : les deux ne se séparent pas."""
    normaux = " && ".join(f'@.resultat != "{r}"' for r in RESULTATS_NORMAUX_D_UN_PASSAGE)
    return (
        "$ ? ("
        f"exists(@.{CLE_SIGNALEMENTS}[*])"
        f" || exists(@.{CLE_DESACCORDS}[*])"
        f" || exists(@.{CLE_RETENUES}[*])"
        f" || @.{CLE_IMPASSE}.impasses > 0"
        f" || @.{CLE_DEPASSEMENTS} >= {DEPASSEMENTS_A_TRIER}"
        f' || exists(@.{CLE_ARBITRE}[*] ? (@.resultat == "{RESULTAT_ARBITRE_A_TRIER}"))'
        f" || exists(@.{CLE_PASSAGES}[*] ? ({normaux}))"
        ")"
    )


def chemin_des_runs_en_alerte() -> str:
    return f"$ ? (exists(@.{CLE_ALERTES}[*]))"


CLES_LUES_POUR_LE_TRI = (
    CLE_SIGNALEMENTS,
    CLE_IMPASSE,
    CLE_ARBITRE,
    CLE_DESACCORDS,
    CLE_PASSAGES,
    CLE_DEPASSEMENTS,
    CLE_RETENUES,
)
CLES_LUES_POUR_LES_ALERTES = (CLE_ALERTES, CLE_ALERTES_MAIL)


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------------------------------------------
# Écrire (pendant l'appel)
# ---------------------------------------------------------------------------------------------------------------


def _tour(contexte: dict) -> int | None:
    from api.services.fiche.traces import CLE_TOUR

    tour = contexte.get(CLE_TOUR)
    return tour if isinstance(tour, int) else None


def nombre_de_signalements_de_l_agent(contexte: dict) -> int:
    liste = contexte.get(CLE_SIGNALEMENTS)
    return len(liste) if isinstance(liste, list) else 0


def ajouter_un_signalement_de_l_agent(contexte: Any, *, motif: str, categorie: str, etape: str | None) -> bool:
    """Un signalement de l'agent dans le run. ``False`` : refusé (plafond de deux par appel, pas de fiche). ⛔ Ne lève jamais."""
    try:
        if not isinstance(contexte, dict) or nombre_de_signalements_de_l_agent(contexte) >= MAX_SIGNALEMENTS_PAR_APPEL:
            return False
        motif = " ".join(str(motif or "").split())[:LONGUEUR_MAX_MOTIF]
        categorie = categorie if categorie in CATEGORIES else CATEGORIE_PAR_DEFAUT
        contexte.setdefault(CLE_SIGNALEMENTS, []).append(
            {
                "source": SOURCE_AGENT,
                "motif": motif,
                "categorie": categorie,
                "etape": etape,
                "tour": _tour(contexte),
                "heure": maintenant(),
            }
        )
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[tri] signalement non écrit : {erreur!r}")
        return False


def ajouter_une_alerte(
    contexte: Any, type_d_alerte: str, *, detail: str | None = None, deja_notifiee: bool = False, **plus: Any
) -> bool:
    """Une alerte (le problème du client) dans le run. ``deja_notifiee`` : un autre mécanisme (le gardien de panne) a déjà
    écrit au client et à .mark : le mail regroupé de l'appel ne la redit pas. ⛔ Ne lève jamais."""
    try:
        if not isinstance(contexte, dict) or type_d_alerte not in TYPES_D_ALERTE:
            return False
        liste = contexte.setdefault(CLE_ALERTES, [])
        if not isinstance(liste, list) or len(liste) >= MAX_ALERTES_PAR_APPEL:
            return False
        liste.append(
            {
                "type": type_d_alerte,
                "detail": None if detail is None else " ".join(str(detail).split())[:LONGUEUR_MAX_MOTIF],
                "tour": _tour(contexte),
                "heure": maintenant(),
                "deja_notifiee": bool(deja_notifiee),
                **{cle: valeur for cle, valeur in plus.items() if valeur is not None},
            }
        )
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[tri] alerte non écrite : {erreur!r}")
        return False


# ---------------------------------------------------------------------------------------------------------------
# Lire (après l'appel, ou pendant)
# ---------------------------------------------------------------------------------------------------------------


def _liste(contexte: dict, cle: str) -> list[dict]:
    brut = contexte.get(cle)
    return [e for e in brut if isinstance(e, dict)] if isinstance(brut, list) else []


def lire_les_signalements(contexte: Any) -> list[dict]:
    """Tous les signalements d'un run, de l'agent et du code, chacun avec son identifiant stable. ⛔ Ne lève jamais."""
    try:
        if not isinstance(contexte, dict):
            return []
        lignes: list[dict] = []
        for rang, e in enumerate(_liste(contexte, CLE_SIGNALEMENTS)):
            lignes.append(
                {
                    "id": f"{TYPE_AGENT}:{rang}",
                    "source": SOURCE_AGENT,
                    "type": TYPE_AGENT,
                    "categorie": e.get("categorie") if e.get("categorie") in CATEGORIES else CATEGORIE_PAR_DEFAUT,
                    "motif": str(e.get("motif") or ""),
                    "etape": e.get("etape"),
                    "tour": e.get("tour"),
                }
            )
        impasse = contexte.get(CLE_IMPASSE)
        if isinstance(impasse, dict):
            for e in impasse.get("journal") or []:
                if isinstance(e, dict) and _entier(e.get("impasse")) > 0:
                    lignes.append(
                        {
                            "id": f"{TYPE_IMPASSE}:{e['impasse']}",
                            "source": SOURCE_CODE,
                            "type": TYPE_IMPASSE,
                            "motif": str(e.get("motif") or ""),
                            "etape": impasse.get("etape"),
                            "tour": e.get("tour"),
                        }
                    )
        for rang, e in enumerate(_liste(contexte, CLE_ARBITRE)):
            if e.get("resultat") == RESULTAT_ARBITRE_A_TRIER:
                lignes.append(
                    {
                        "id": f"{TYPE_PORTE_INCONNUE}:{rang}",
                        "source": SOURCE_CODE,
                        "type": TYPE_PORTE_INCONNUE,
                        "motif": str(e.get("choix") or ""),
                        "etape": e.get("etape"),
                        "tour": e.get("tour"),
                    }
                )
        for rang, e in enumerate(_liste(contexte, CLE_DESACCORDS)):
            lignes.append(
                {
                    "id": f"{TYPE_DESACCORD}:{rang}",
                    "source": SOURCE_CODE,
                    "type": TYPE_DESACCORD,
                    "motif": str(e.get("arbitre") or ""),
                    "etape": e.get("etape_de_depart"),
                    "tour": e.get("tour"),
                }
            )
        for rang, e in enumerate(_liste(contexte, CLE_RETENUES)):
            lignes.append(
                {
                    "id": f"{TYPE_RETENUE}:{rang}",
                    "source": SOURCE_CODE,
                    "type": TYPE_RETENUE,
                    # le genre (technique, lisible à l'écran par ``libelles.ts``) puis le détail
                    "motif": " : ".join(x for x in (str(e.get("genre") or ""), str(e.get("outil") or ""), str(e.get("detail") or "")) if x),
                    "etape": None,
                    "tour": e.get("tour"),
                }
            )
        for rang, e in enumerate(_liste(contexte, CLE_PASSAGES)):
            if e.get("resultat") not in RESULTATS_NORMAUX_D_UN_PASSAGE:
                lignes.append(
                    {
                        "id": f"{TYPE_PASSAGE}:{rang}",
                        "source": SOURCE_CODE,
                        "type": TYPE_PASSAGE,
                        "motif": str(e.get("resultat") or ""),
                        "etape": e.get("etape"),
                        "tour": e.get("tour"),
                    }
                )
        if _entier(contexte.get(CLE_DEPASSEMENTS)) >= DEPASSEMENTS_A_TRIER:
            lignes.append(
                {
                    "id": f"{TYPE_GARDE_MODELE}:0",
                    "source": SOURCE_CODE,
                    "type": TYPE_GARDE_MODELE,
                    "motif": str(contexte[CLE_DEPASSEMENTS]),
                    "etape": None,
                    "tour": None,
                }
            )
        return lignes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[tri] lecture des signalements en échec : {erreur!r}")
        return []


def lire_les_alertes(contexte: Any) -> list[dict]:
    """Les alertes d'un run, avec un identifiant stable. ⛔ Ne lève jamais."""
    try:
        if not isinstance(contexte, dict):
            return []
        mail = contexte.get(CLE_ALERTES_MAIL)
        etat_du_mail = mail.get("etat") if isinstance(mail, dict) else None
        lignes = []
        for rang, e in enumerate(_liste(contexte, CLE_ALERTES)):
            if e.get("type") not in TYPES_D_ALERTE:
                continue
            lignes.append(
                {
                    "id": f"alerte:{rang}",
                    "type": e["type"],
                    "detail": e.get("detail"),
                    "etape": e.get("etape"),
                    "outil": e.get("outil"),
                    "tour": e.get("tour"),
                    "heure": e.get("heure"),
                    # « envoye » · « non_envoye » (pas de serveur, jamais perdue) · « deja_notifiee » · None (pas tenté)
                    "mail": "deja_notifiee" if e.get("deja_notifiee") else (e.get("mail") or etat_du_mail),
                }
            )
        return lignes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[tri] lecture des alertes en échec : {erreur!r}")
        return []


def statut_d_un_signalement(annotations: Any, identifiant: str) -> str:
    try:
        tri = annotations.get(CLE_TRI) if isinstance(annotations, dict) else None
        entree = tri.get(identifiant) if isinstance(tri, dict) else None
        statut = entree.get("statut") if isinstance(entree, dict) else None
        return statut if statut in STATUTS else STATUT_PAR_DEFAUT
    except Exception:  # noqa: BLE001
        return STATUT_PAR_DEFAUT
