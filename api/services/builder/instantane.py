"""[.mark] Builder partie 3, sous-lot 7 (SE-15 = E-2) : « Revenir avant » restaure TOUT, famille par famille.

Un instantané (``revue._ranger``) gardait le graphe seulement. Il garde maintenant, à côté, un **complément** : l'état des autres
familles au moment où il est pris. Revenir avant ouvre une fenêtre qui laisse choisir les familles à restaurer.

| Famille | Ce qui est gardé | Où ça vit |
|---|---|---|
| ``schema`` | le graphe (étapes, liaisons) | le brouillon de l'agent (déjà gardé : ``avant`` / ``apres``) |
| ``phrases`` | les règles de phrases du code (``phrases_regles``) | réglages du brouillon |
| ``reglages`` | tous les autres réglages de l'agent (fiche, modules, voix, tour de parole, publication...) | réglages du brouillon |
| ``vocabulaire`` | le lexique du métier | **l'organisation** (partagé par ses agents) |
| ``objets`` | les objets de l'agent (valeurs, tableaux) | **la base du client** (partagée par ses agents) |

* Un instantané est pris à chaque acceptation du builder, à chaque sauvegarde, à chaque restauration (pour la défaire) et **à chaque
  publication** (l'état tel que publié).
* Restaurer ne touche QUE les familles choisies ; tout est validé AVANT la première écriture (un refus n'écrit rien). Restaurer
  est un brouillon : jamais une publication. Une restauration range elle-même un instantané complet, donc elle se défait.
* Le vocabulaire et les objets sont partagés par toute l'organisation : la fenêtre le dit. Restaurer les objets réécrit ceux qui
  existaient (même nom) et ne SUPPRIME jamais un objet ajouté depuis.
* ``outils_epingles`` (décision 21, SA-L3d) : la version de chaque outil que l'agent joue au moment de l'instantané. Elle voyage avec
  le **schéma** (le graphe cite les outils) : restaurer le schéma ramène aussi la bonne version de chaque outil, dans le brouillon.
  ``branche`` : la branche où l'instantané a été pris (rangée par ``revue._ranger``).

⛔ Aucune valeur de réglage n'est jamais rendue par l'aperçu (une clé pourrait y être) : seulement des noms et des comptes.
"""

from __future__ import annotations

import copy
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.builder import brouillon

FAMILLES = ("schema", "phrases", "vocabulaire", "objets", "reglages")
PARTAGEES = ("vocabulaire", "objets")  # de l'organisation, pas de l'agent
VERSION_DU_COMPLEMENT = 2
CLE_PHRASES = "phrases_regles"


class ErreurInstantane(Exception):
    """Un refus normal (famille inconnue ou absente de l'instantané, valeur qui ne passerait plus), dit en une phrase."""


# --- prendre l'état des familles -------------------------------------------------------------------------------------------


async def _objets(user: Any, workflow: Any) -> list[dict[str, Any]] | None:
    """Les objets de l'agent tels que la base du client les garde, ou ``None`` (pas de base rattachée, personne pour les lire)."""
    if user is None:
        return None
    try:
        from api.schemas.objets_agent import ObjetEnvoye
        from api.services.builder.actions import objets
        from api.services.builder.actions.registre import Contexte

        vue = await objets.lister_les_objets(Contexte(user=user, workflow_id=workflow.id))
        champs = set(ObjetEnvoye.model_fields)
        return [ObjetEnvoye.model_validate(o.model_dump(include=champs)).model_dump(mode="json") for o in vue.objets]
    except Exception as erreur:  # noqa: BLE001 -- un instantané sans objets vaut mieux que pas d'instantané
        logger.info(f"[instantane] objets non gardés : {type(erreur).__name__}")
        return None


async def _vocabulaire(organization_id: int) -> dict[str, Any] | None:
    try:
        from api.services.lexique.stockage import lire_lexique_strict

        return (await lire_lexique_strict(organization_id)).model_dump(mode="json")
    except Exception as erreur:  # noqa: BLE001
        logger.info(f"[instantane] vocabulaire non gardé : {type(erreur).__name__}")
        return None


def separer_les_reglages(configurations: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """(règles de phrases, tous les autres réglages) : deux familles d'un même dictionnaire."""
    reglages = {cle: copy.deepcopy(v) for cle, v in configurations.items() if cle != CLE_PHRASES}
    return copy.deepcopy(configurations.get(CLE_PHRASES)), reglages


async def _epingles(organization_id: int, workflow: Any) -> dict[str, int] | None:
    """``{outil: version}`` de l'agent ouvert (brouillon sinon version en ligne), une version épinglée ou la courante. ``None`` : illisible."""
    try:
        vue = await db_client.outils_epingles_de_l_agent(organization_id, workflow.id)
        return {**{o["tool_uuid"]: o["epinglee"] for o in vue["outils"]}, **{f"bloc:{s}": n for s, n in (vue.get("blocs") or {}).items()}}
    except Exception as erreur:  # noqa: BLE001 -- un instantané sans épingles vaut mieux que pas d'instantané
        logger.info(f"[instantane] versions d'outils non gardées : {type(erreur).__name__}")
        return None


async def capturer(
    organization_id: int,
    workflow: Any,
    *,
    user: Any = None,
    configurations: dict[str, Any] | None = None,
    epingles: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Le complément d'un instantané : l'état des familles autres que le graphe. ``user`` permet de garder aussi les objets.
    ``epingles`` : les versions d'outils déjà connues de l'appelant (une version qu'on vient de publier) ; sinon lues."""
    courantes = configurations if configurations is not None else await brouillon.configurations_courantes(workflow)
    phrases, reglages = separer_les_reglages(courantes)
    complement: dict[str, Any] = {
        "version": VERSION_DU_COMPLEMENT,
        "phrases": phrases,
        "reglages": reglages,
        "vocabulaire": await _vocabulaire(organization_id),
        "objets": await _objets(user, workflow),
        # Décision 21 : les versions d'outils figées (voyagent avec le schéma). ``branche`` est posée par ``revue._ranger``.
        "branche": None,
        "outils_epingles": dict(epingles) if epingles else await _epingles(organization_id, workflow),
    }
    complement["familles"] = familles_gardees(complement)
    return complement


def familles_gardees(complement: dict[str, Any] | None) -> list[str]:
    """Les familles que ce complément sait restaurer : une famille non lue au moment de l'instantané (``None``) n'en est pas."""
    if not isinstance(complement, dict):
        return []
    gardees = []
    if "phrases" in complement:
        gardees.append("phrases")  # None = « aucune règle à ce moment » : restaurer retire les règles ajoutées depuis
    if isinstance(complement.get("reglages"), dict):
        gardees.append("reglages")
    if complement.get("vocabulaire") is not None:
        gardees.append("vocabulaire")
    if complement.get("objets") is not None:
        gardees.append("objets")
    return [f for f in FAMILLES if f in gardees]


def familles_d_un_instantane(ligne: dict[str, Any]) -> list[str]:
    """Le schéma d'abord (tout instantané a son graphe), puis les familles du complément."""
    return ["schema", *familles_gardees(ligne.get("complement"))] if ligne.get("avant") else familles_gardees(ligne.get("complement"))


# --- comparer (aperçu, sans effet) -----------------------------------------------------------------------------------------


def _termes(vocabulaire: dict[str, Any] | None) -> set[str]:
    termes = (vocabulaire or {}).get("termes") if isinstance(vocabulaire, dict) else None
    return {str((t or {}).get("terme") or t) for t in termes or []} if isinstance(termes, list) else set()


def comparer_les_familles(ligne: dict[str, Any], actuel: dict[str, Any]) -> list[dict[str, Any]]:
    """Pour chaque famille : est-elle dans l'instantané, change-t-elle, et de quoi (des noms et des comptes, jamais une valeur)."""
    complement = ligne.get("complement") if isinstance(ligne.get("complement"), dict) else {}
    gardees = set(familles_d_un_instantane(ligne))
    sortie = []
    for famille in FAMILLES:
        vue: dict[str, Any] = {"famille": famille, "disponible": famille in gardees, "partagee": famille in PARTAGEES, "change": None, "details": []}
        if famille == "schema" and famille in gardees:
            avant_o, maintenant_o = complement.get("outils_epingles"), actuel.get("outils_epingles")
            if isinstance(avant_o, dict) and isinstance(maintenant_o, dict):
                vue["outils"] = sorted(u for u in set(avant_o) & set(maintenant_o) if avant_o[u] != maintenant_o[u] and not u.startswith("bloc:"))[:40]
        if famille in gardees and famille != "schema":
            avant, maintenant = complement.get(famille), actuel.get(famille)
            if maintenant is None and famille in PARTAGEES:
                continue  # l'état d'aujourd'hui n'a pas pu être lu : on ne dit ni « change » ni « ne change pas »
            if famille == "reglages":
                noms = sorted(c for c in set(avant or {}) | set(maintenant or {}) if (avant or {}).get(c) != (maintenant or {}).get(c))
                vue.update(change=bool(noms), details=noms[:40])
            elif famille == "phrases":
                a = {r.get("motif") if isinstance(r, dict) else str(r) for r in avant or []}
                m = {r.get("motif") if isinstance(r, dict) else str(r) for r in maintenant or []}
                vue.update(change=avant != maintenant, details=sorted(str(x) for x in a ^ m)[:40])
            elif famille == "vocabulaire":
                a, m = _termes(avant), _termes(maintenant)
                vue.update(change=avant != maintenant, details=sorted(a ^ m)[:40])
            elif famille == "objets":
                a = {o.get("nom"): o for o in avant or []}
                m = {o.get("nom"): o for o in maintenant or []}
                noms = sorted(n for n in set(a) | set(m) if n in a and a.get(n) != m.get(n))
                vue.update(change=bool(noms), details=noms[:40], ajoutes_depuis=sorted(n for n in m if n not in a)[:40])
        sortie.append(vue)
    return sortie


# --- restaurer -------------------------------------------------------------------------------------------------------------


def choisir(ligne: dict[str, Any], familles: list[str] | None) -> list[str]:
    """Les familles à restaurer : toutes celles de l'instantané si rien n'est dit. Refus d'une famille inconnue ou qu'il n'a pas."""
    dispo = familles_d_un_instantane(ligne)
    if familles is None:
        return dispo
    inconnues = [f for f in familles if f not in FAMILLES]
    if inconnues:
        raise ErreurInstantane(f"Unknown family: {inconnues[0]}.")
    manquantes = [f for f in familles if f not in dispo]
    if manquantes:
        raise ErreurInstantane(f"This version did not keep «{manquantes[0]}»: choose another family.")
    if not familles:
        raise ErreurInstantane("Choose at least one family to restore.")
    return [f for f in FAMILLES if f in familles]


def configurations_restaurees(actuelles: dict[str, Any], complement: dict[str, Any], familles: list[str]) -> dict[str, Any]:
    """Les réglages du brouillon une fois les familles ``phrases`` et ``reglages`` remises ; ce qui n'est pas choisi ne bouge pas."""
    nouvelles = copy.deepcopy(actuelles)
    if "reglages" in familles:
        gardees = {cle: v for cle, v in nouvelles.items() if cle == CLE_PHRASES}
        nouvelles = {**gardees, **copy.deepcopy(complement["reglages"])}
    if "phrases" in familles:
        if complement.get("phrases") is None:
            nouvelles.pop(CLE_PHRASES, None)
        else:
            nouvelles[CLE_PHRASES] = copy.deepcopy(complement["phrases"])
    return nouvelles


async def verifier_avant_d_ecrire(ligne: dict[str, Any], actuelles: dict[str, Any], familles: list[str]) -> dict[str, Any] | None:
    """Tout ce qui sera écrit passe les validateurs de l'écran AVANT la première écriture. Rend les réglages à écrire (ou ``None``)."""
    complement = ligne.get("complement") or {}
    nouvelles = None
    if "phrases" in familles or "reglages" in familles:
        from api.services.builder.reglages_agent import ErreurReglage, _verifier

        nouvelles = configurations_restaurees(actuelles, complement, familles)
        try:
            _verifier(nouvelles)
        except ErreurReglage as erreur:
            raise ErreurInstantane(f"This version's settings no longer pass today's checks: {erreur}") from None
    if "vocabulaire" in familles:
        from pydantic import ValidationError

        from api.schemas.lexique_metier import LexiqueMetier

        try:
            LexiqueMetier.model_validate(complement["vocabulaire"])
        except ValidationError:
            raise ErreurInstantane("This version's vocabulary no longer passes today's checks.") from None
    return nouvelles


async def restaurer_les_partagees(organization_id: int, workflow: Any, ligne: dict[str, Any], familles: list[str], user: Any) -> dict[str, Any]:
    """Le vocabulaire et les objets (partagés par l'organisation). Rend ce qui a été fait ; ne retire jamais un objet."""
    complement = ligne.get("complement") or {}
    fait: dict[str, Any] = {}
    if "vocabulaire" in familles:
        from api.schemas.lexique_metier import LexiqueMetier
        from api.services.lexique.stockage import enregistrer_lexique

        await enregistrer_lexique(organization_id, LexiqueMetier.model_validate(complement["vocabulaire"]))
        fait["vocabulaire"] = {"restaure": True}
    if "objets" in familles:
        from api.schemas.objets_agent import ObjetEnvoye
        from api.services.builder.actions import objets
        from api.services.builder.actions.registre import Contexte

        if user is None:
            fait["objets"] = {"restaures": 0, "refuses": [{"nom": "*", "erreur": "no person to write them"}]}
        else:
            resultats = await objets.ecrire_des_objets(
                Contexte(user=user, workflow_id=workflow.id), [ObjetEnvoye.model_validate(o) for o in complement["objets"]]
            )
            fait["objets"] = {
                "restaures": sum(1 for r in resultats if r.get("ok")),
                "refuses": [{"nom": r.get("nom"), "erreur": r.get("erreur")} for r in resultats if not r.get("ok")],
            }
    return fait
