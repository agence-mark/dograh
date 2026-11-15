"""[.mark] Module Restauration, lot 24 : les garde-fous des OUTILS de l'agent (arguments, échec répété, écritures en file).

Trois gardes, rattachés à l'exécution d'une action de connecteur (``execution.executer``), donc valables pour TOUS les outils d'intégration
(commande, réservation, planificateur…), aucun mot du métier. Conditions G1 à G5 (``reference/29``) : mécaniques, un interrupteur chacun,
zéro déclenchement sur un appel sain.

Chaque garde est une CLÉ DE RÉGLAGE de l'agent, **éteinte par défaut** (``True`` l'allume : le kit Restauration l'allume, un autre agent n'est pas
touché) :

- ``garde_arguments_controles`` : chaque argument est validé par schéma (type, taille, liste fermée) avant que l'outil ne tourne ; un argument
  qui n'a pas de sens ne rend jamais une erreur brute : l'outil demande à reformuler (``missing`` / ``ask_for``) ;
- ``garde_echec_repete`` : le même outil avec les mêmes arguments qui rend le même échec deux fois de suite n'est plus relancé ; il rend
  ``ECHEC_REPETE`` avec une AUTRE stratégie (les plus proches, reformuler la question, demande de rappel) ;
- ``garde_ecritures_en_file`` : les outils qui écrivent dans le même objet (le même panier, la même réservation) passent l'un après l'autre,
  même si le modèle les appelle en même temps ; les lectures restent en parallèle.

⛔ Ne lève jamais à la place de l'outil : dans le doute, l'outil tourne comme avant.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections import OrderedDict
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Any

from loguru import logger

CLE_ARGUMENTS = "garde_arguments_controles"
CLE_ECHEC_REPETE = "garde_echec_repete"
CLE_ECRITURES_EN_FILE = "garde_ecritures_en_file"
CLE_NOUVELLE_TENTATIVE = "garde_une_nouvelle_tentative"  # lot 7 (W21) : une seule nouvelle tentative, sur une lecture en panne seulement
CLES = (CLE_ARGUMENTS, CLE_ECHEC_REPETE, CLE_ECRITURES_EN_FILE, CLE_NOUVELLE_TENTATIVE)

LONGUEUR_MAX_D_UN_TEXTE = 500
VALEUR_MAX_D_UN_NOMBRE = 1_000_000_000
ECHECS_PERMIS = 2  # après deux échecs identiques de suite, le troisième appel identique n'est plus lancé
CLE_DE_LA_FICHE = "garde_des_outils"

# Les statuts fermés d'un outil qui disent « pas pu » (le même appel les rendra encore) : jamais INCOMPLETE ni OK.
STATUTS_D_ECHEC = frozenset({"INTROUVABLE", "REFUSEE", "INDISPONIBLE", "ARGUMENT_INVALIDE", "HORS_ZONE", "HORS_CARTE", "RUPTURE", "AMBIGU"})
STATUT_ECHEC_REPETE = "ECHEC_REPETE"
STRATEGIE = (
    "Cette demande a déjà échoué deux fois de la même façon : ne la renvoie pas. Change de stratégie : propose à l'appelant les plus proches, "
    "reformule la question pour obtenir autre chose, ou prends une demande de rappel."
)


def allumee(configurations: Mapping[str, Any] | None, cle: str) -> bool:
    """Éteinte par défaut : seul ``True`` allume. ⛔ Ne lève jamais."""
    try:
        return isinstance(configurations, Mapping) and configurations.get(cle) is True
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- arguments contrôlés


def _nombre(valeur: Any) -> bool:
    if isinstance(valeur, bool):
        return False
    if isinstance(valeur, (int, float)):
        return math.isfinite(valeur) and abs(valeur) <= VALEUR_MAX_D_UN_NOMBRE
    if isinstance(valeur, str) and len(valeur) <= 40:
        try:
            return math.isfinite(float(valeur.replace(",", "."))) and abs(float(valeur.replace(",", "."))) <= VALEUR_MAX_D_UN_NOMBRE
        except ValueError:
            return False
    return False


def arguments_invalides(action: Any, bruts: Mapping[str, Any] | None) -> list[str]:
    """Les noms des arguments déclarés dont la valeur n'a pas de sens : mauvais type, trop long, hors de la liste fermée. Une valeur absente ou vide
    n'est pas jugée ici (``manquants`` s'en charge). Un argument non déclaré est ignoré (``arguments_permis`` le coupe)."""
    invalides: list[str] = []
    for p in action.parametres:
        if not bruts or p.nom not in bruts:
            continue
        valeur = bruts[p.nom]
        if valeur is None or valeur == "":
            continue
        if p.type == "number":
            bon = _nombre(valeur)
        elif p.type == "boolean":
            bon = isinstance(valeur, bool) or (isinstance(valeur, str) and valeur.strip().casefold() in ("true", "false"))
        else:
            bon = isinstance(valeur, str) and len(valeur) <= LONGUEUR_MAX_D_UN_TEXTE
        if bon and p.choix and isinstance(valeur, str) and valeur.strip().casefold() not in {c.casefold() for c in p.choix}:
            bon = False
        if not bon:
            invalides.append(p.nom)
    return invalides


# --------------------------------------------------------------------------- échec répété


def cle_de_l_appel(connecteur: str, action: str, arguments: Mapping[str, Any]) -> str:
    contenu = json.dumps([connecteur, action, arguments], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(contenu.encode()).hexdigest()[:16]


def _registre(fiche: dict | None) -> dict[str, int] | None:
    if not isinstance(fiche, dict):
        return None
    registre = fiche.get(CLE_DE_LA_FICHE)
    if not isinstance(registre, dict):
        registre = fiche[CLE_DE_LA_FICHE] = {}
    return registre


def echecs_de_suite(fiche: dict | None, cle: str) -> int:
    registre = _registre(fiche)
    return int(registre.get(cle, 0)) if registre is not None else 0


def noter_le_resultat(fiche: dict | None, cle: str, *, echec: bool) -> None:
    """Un échec de plus pour cet appel exact ; un succès (ou un autre résultat) remet son compteur à zéro. Les autres appels ne bougent pas."""
    registre = _registre(fiche)
    if registre is None:
        return
    if echec:
        registre[cle] = int(registre.get(cle, 0)) + 1
    else:
        registre.pop(cle, None)


def est_un_echec(statut_de_l_execution: str, donnees: Mapping[str, Any] | None) -> bool:
    """``repli`` (délai, panne) ou un statut fermé de l'outil qui dit « pas pu »."""
    if statut_de_l_execution != "ok":
        return True
    return isinstance(donnees, Mapping) and donnees.get("statut") in STATUTS_D_ECHEC


def retour_d_echec_repete(dernier: str | None) -> dict[str, Any]:
    return {"statut": STATUT_ECHEC_REPETE, "faits": {"dernier_statut": dernier}, "suggestion": STRATEGIE}


# --------------------------------------------------------------------------- écritures en file

_VERROUS: OrderedDict[tuple[int, str], asyncio.Lock] = OrderedDict()
_MAX_VERROUS = 512  # un verrou par (appel, objet) : les plus anciens partent, un appel fini n'en a plus besoin


def verrou_de(fiche: dict | None, objet: str) -> asyncio.Lock:
    """Le verrou de CET objet dans CET appel (la fiche de l'appel en est la clé : un appel n'attend jamais un autre)."""
    cle = (id(fiche), objet)
    verrou = _VERROUS.get(cle)
    if verrou is None:
        verrou = _VERROUS[cle] = asyncio.Lock()
        while len(_VERROUS) > _MAX_VERROUS:
            ancien = next(iter(_VERROUS))
            if _VERROUS[ancien].locked():
                break  # jamais retirer un verrou tenu
            _VERROUS.popitem(last=False)
    else:
        _VERROUS.move_to_end(cle)
    return verrou


def en_file(configurations: Mapping[str, Any] | None, fiche: dict | None, action: Any) -> AbstractAsyncContextManager:
    """Le verrou à tenir pendant l'action (``nullcontext`` quand la garde est éteinte, que l'action ne déclare pas d'objet ou qu'il n'y a pas de fiche)."""
    objet = getattr(action, "serialise_avec", None)
    if not objet or not isinstance(fiche, dict) or not allumee(configurations, CLE_ECRITURES_EN_FILE):
        return nullcontext()
    return verrou_de(fiche, objet)


def tracer(genre: str, action: str, detail: str = "") -> None:
    logger.warning(f"[garde-outils] {genre} : {action} {detail}".rstrip())
