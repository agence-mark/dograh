"""[.mark] Builder partie 2, U5 : la revue des changements, champ par champ, et les versions de brouillon restaurables.

Les opérations que le builder prépare restent « en attente » (``brouillon``). Ici une personne les relit UNE PAR UNE, sur une
seule modification d'un seul champ (« changement 2/5 ») : ``eclater`` découpe d'abord chaque opération en changements d'un
champ, de façon déterministe (le même brouillon donne toujours les mêmes rangs, à la lecture comme à l'acceptation).

* ``lister``   : chaque changement avec ce qu'il vise, son champ, la valeur d'avant et celle d'après ;
* ``accepter`` : applique ceux qu'on accepte (tous si ``rangs`` est vide), enregistre UNE version de brouillon, et range un
  **instantané** (le graphe d'avant et d'après) dans le stock du builder : chaque acceptation se restaure ;
* ``refuser``  : retire des changements en attente, sans rien écrire dans l'agent ;
* ``restaurer``: remet le graphe d'avant d'un instantané comme nouveau brouillon (la restauration a elle-même son instantané).

Partie 3, sous-lot 7 (SE-15) : un instantané garde aussi un **complément** (phrases, réglages, vocabulaire, objets : voir
``instantane.py``), pris à chaque acceptation, sauvegarde, restauration et **publication** ; ``restaurer`` rend les familles choisies.

Jamais une publication.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from api.db import db_client
from api.services.builder import brouillon, instantane, stock
from api.services.builder.constantes import cle_builder

INSTANTANES_GARDES = 50
PARTIE = "instantanes"


class ErreurRevue(Exception):
    """Un refus normal (rang inconnu, brouillon qui a bougé, graphe invalide), dit en une phrase."""


# --- découper en changements d'un champ ------------------------------------------------------------------------------------


def eclater(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une opération qui touche plusieurs champs devient plusieurs opérations d'un champ. Les autres passent telles quelles."""
    sortie: list[dict[str, Any]] = []
    for op in operations:
        if op.get("op") != "modifier_noeud":
            sortie.append(op)
            continue
        champs: list[dict[str, Any]] = []
        base = {"op": "modifier_noeud", "id": op.get("id")}
        if op.get("nom") is not None:
            champs.append({**base, "nom": op["nom"]})
        if op.get("prompt") is not None:
            champs.append({**base, "prompt": op["prompt"]})
        for cle, valeur in (op.get("donnees") or {}).items():
            champs.append({**base, "donnees": {cle: valeur}})
        sortie.extend(champs or [op])
    return sortie


def _valeur_du_noeud(graphe: dict[str, Any], identifiant: str | None, champ: str) -> Any:
    noeud = next((n for n in graphe.get("nodes", []) if n.get("id") == identifiant), None)
    if noeud is None:
        return None
    donnees = noeud.get("data") or {}
    return donnees.get("name") if champ == "nom" else donnees.get(champ)


def _decrire(graphe: dict[str, Any], rang: int, op: dict[str, Any]) -> dict[str, Any]:
    genre, cible = op.get("op"), op.get("id")
    base = {"rang": rang, "op": genre, "cible": cible}
    if genre in ("modifier_noeud", "modifier_prompt"):
        if op.get("prompt") is not None:
            champ, apres = "prompt", op["prompt"]
        elif op.get("nom") is not None:
            champ, apres = "nom", op["nom"]
        elif op.get("donnees"):
            champ, apres = next(iter(op["donnees"])), next(iter(op["donnees"].values()))
        else:
            champ, apres = "", None
        return {**base, "champ": champ, "avant": _valeur_du_noeud(graphe, cible, champ), "apres": apres}
    if genre == "ajouter_noeud":
        return {**base, "champ": "noeud", "avant": None, "apres": {"type": op.get("type"), "nom": op.get("nom")}}
    if genre == "supprimer_noeud":
        return {**base, "champ": "noeud", "avant": _valeur_du_noeud(graphe, cible, "nom"), "apres": None}
    if genre == "ajouter_liaison":
        return {
            **base,
            "champ": "liaison",
            "avant": None,
            "apres": {"source": op.get("source"), "target": op.get("target"), "label": op.get("label")},
        }
    if genre == "supprimer_liaison":
        return {**base, "champ": "liaison", "avant": cible, "apres": None}
    liaison = next((e for e in graphe.get("edges", []) if e.get("id") == cible), None) or {}
    champ = "condition" if op.get("condition") is not None else "label" if op.get("label") is not None else "liaison"
    return {**base, "champ": champ, "avant": (liaison.get("data") or {}).get(champ), "apres": op.get(champ)}


async def lister(organization_id: int, workflow: Any) -> dict[str, Any]:
    """Les changements en attente, un par champ. Le « avant » d'un changement est le graphe avec les précédents déjà faits."""
    etat = await brouillon.lire_en_attente(organization_id, workflow.id)
    graphe, _version = await brouillon.source_courante(workflow)
    courant = copy.deepcopy(graphe) if graphe else {"nodes": [], "edges": []}
    changements = []
    for rang, op in enumerate(eclater(list(etat.get("operations") or []))):
        changements.append(_decrire(courant, rang, op))
        try:
            brouillon.appliquer_une(courant, brouillon.Operation.model_validate(op))
        except brouillon.ErreurOperation:
            changements[-1]["invalide"] = True
    return {"changements": changements, "total": len(changements)}


# --- les instantanés --------------------------------------------------------------------------------------------------------


def _cle(workflow_id: int, numero: int) -> str:
    return cle_builder(workflow_id, f"{PARTIE}:{numero:06d}")


async def _ranger(
    organization_id: int,
    workflow_id: int,
    *,
    cause: str,
    avant: dict[str, Any] | None,
    apres: dict[str, Any] | None,
    version_avant: int | None,
    version_apres: int | None,
    fil_id: int | None,
    operations: list[dict[str, Any]],
    complement: dict[str, Any] | None = None,
) -> int:
    # V4 : seulement les clés (le numéro est le dernier morceau de la clé), jamais les graphes des instantanés déjà rangés.
    existants = await stock.cles(organization_id, cle_builder(workflow_id, f"{PARTIE}:"))
    numero = int(existants[-1].rsplit(":", 1)[1]) + 1 if existants else 1
    await stock.ecrire(
        organization_id,
        _cle(workflow_id, numero),
        {
            "numero": numero,
            "cause": cause,
            "date": datetime.now(UTC).isoformat(),
            "fil_id": fil_id,
            "version_avant": version_avant,
            "version_apres": version_apres,
            "operations": operations,
            "avant": avant,
            "apres": apres,
            # Sous-lot 7 : l'état des autres familles ; ``familles`` (légère) dit lesquelles, pour la liste sans charger le complément.
            "complement": complement,
            "familles": instantane.familles_d_un_instantane({"avant": avant, "complement": complement}),
        },
    )
    for cle in existants[: max(0, len(existants) + 1 - INSTANTANES_GARDES)]:
        await stock.supprimer(organization_id, cle)
    return numero


async def instantanes(organization_id: int, workflow_id: int, fil_id: int | None = None, *, complets: bool = False) -> list[dict[str, Any]]:
    """Les versions restaurables, de la plus récente à la plus ancienne (sans les graphes, lourds, sauf ``complets``)."""
    # V4 : sans ``complets``, la base retire les deux graphes de chaque instantané (50 x 2 graphes lus pour rien avant).
    prefixe = cle_builder(workflow_id, f"{PARTIE}:")
    lignes = (
        await stock.lister(organization_id, prefixe)
        if complets
        else await stock.lister_sans(organization_id, prefixe, ["avant", "apres", "complement"])
    )
    sortie = []
    for _cle_ligne, v in reversed(lignes):
        if fil_id is not None and v.get("fil_id") != fil_id:
            continue
        if complets:
            sortie.append(v)
        else:
            sortie.append(
                {
                    **{k: v.get(k) for k in ("numero", "cause", "date", "fil_id", "version_avant", "version_apres", "operations")},
                    "familles": v.get("familles") if isinstance(v.get("familles"), list) else ["schema"],
                }
            )
    return sortie


# --- accepter, refuser, restaurer ------------------------------------------------------------------------------------------


def _choisir(operations: list[dict[str, Any]], rangs: list[int] | None) -> tuple[list[int], list[int]]:
    tous = list(range(len(operations)))
    if not rangs:
        return tous, []
    inconnus = [r for r in rangs if r not in tous]
    if inconnus:
        raise ErreurRevue(f"Unknown change(s): {inconnus}.")
    choisis = sorted(set(rangs))
    return choisis, [r for r in tous if r not in choisis]


async def accepter(organization_id: int, workflow: Any, rangs: list[int] | None = None, fil_id: int | None = None) -> dict[str, Any]:
    from api.services.workflow import schema_du_parcours
    from api.services.workflow.layout import reconcile_positions

    etat = await brouillon.lire_en_attente(organization_id, workflow.id)
    operations = eclater(list(etat.get("operations") or []))
    if not operations:
        raise ErreurRevue("No pending change.")
    graphe, version = await brouillon.source_courante(workflow)
    if etat.get("base_version") != version:
        raise ErreurRevue("The agent's draft changed since these changes were prepared: refuse them or ask the builder to redo them.")
    choisis, restants = _choisir(operations, rangs)
    acceptees = [operations[r] for r in choisis]
    gardees = [operations[r] for r in restants]
    try:
        nouveau = brouillon.appliquer(graphe, [brouillon.Operation.model_validate(o) for o in acceptees])
        if gardees:  # ce qui reste doit encore s'appliquer au graphe accepté, sinon rien n'est écrit
            brouillon.appliquer(nouveau, [brouillon.Operation.model_validate(o) for o in gardees])
    except brouillon.ErreurOperation as erreur:
        raise ErreurRevue(f"These changes cannot be accepted on their own: {erreur}") from None
    nouveau = reconcile_positions(nouveau, graphe)
    erreurs = await brouillon.valider(nouveau, organization_id)
    if erreurs:
        raise ErreurRevue("The graph would not be valid: " + "; ".join(erreurs[:3]))
    nouveau = await schema_du_parcours.a_l_enregistrement(workflow.id, organization_id, nouveau, None) or nouveau
    enregistre = await db_client.save_workflow_draft(workflow_id=workflow.id, workflow_definition=nouveau)
    numero = await _ranger(
        organization_id,
        workflow.id,
        cause="acceptation",
        avant=graphe,
        apres=nouveau,
        version_avant=version,
        version_apres=enregistre.version_number,
        fil_id=fil_id,
        operations=acceptees,
        complement=await instantane.capturer(organization_id, workflow),
    )
    await brouillon.ecrire_en_attente(organization_id, workflow.id, {"operations": gardees, "base_version": enregistre.version_number})
    return {"acceptes": len(acceptees), "restants": len(gardees), "version": enregistre.version_number, "instantane": numero}


async def refuser(organization_id: int, workflow: Any, rangs: list[int] | None = None) -> dict[str, Any]:
    etat = await brouillon.lire_en_attente(organization_id, workflow.id)
    operations = eclater(list(etat.get("operations") or []))
    if not operations:
        raise ErreurRevue("No pending change.")
    choisis, restants = _choisir(operations, rangs)
    await brouillon.ecrire_en_attente(
        organization_id, workflow.id, {"operations": [operations[r] for r in restants], "base_version": etat.get("base_version")}
    )
    return {"refuses": len(choisis), "restants": len(restants)}


async def restaurer(
    organization_id: int, workflow: Any, numero: int, fil_id: int | None = None, *, familles: list[str] | None = None, user: Any = None
) -> dict[str, Any]:
    """Remet un instantané dans le BROUILLON, pour les ``familles`` choisies (toutes celles qu'il a si rien n'est dit).

    Tout est validé avant la première écriture ; le vocabulaire et les objets (partagés par l'organisation) s'écrivent après le
    brouillon. La restauration range elle-même un instantané complet : elle se défait. Jamais une publication."""
    ligne = await stock.lire(organization_id, _cle(workflow.id, numero))
    if ligne is None or not ligne.get("avant"):
        raise ErreurRevue(f"Unknown version: {numero}.")
    try:
        choisies = instantane.choisir(ligne, familles)
        graphe, version = await brouillon.source_courante(workflow)
        actuelles = await brouillon.configurations_courantes(workflow)
        nouvelles = await instantane.verifier_avant_d_ecrire(ligne, actuelles, choisies)
        avant_la_restauration = await instantane.capturer(organization_id, workflow, user=user, configurations=actuelles)
        if "schema" in choisies or nouvelles is not None:
            # Un brouillon qui n'existe pas encore se crée avec le graphe d'aujourd'hui, jamais vide.
            enregistre = await db_client.save_workflow_draft(
                workflow_id=workflow.id,
                workflow_definition=ligne["avant"] if "schema" in choisies else graphe,
                workflow_configurations=nouvelles if nouvelles is not None else actuelles,
            )
            numero_du_brouillon = enregistre.version_number
        else:
            numero_du_brouillon = version  # seules des familles partagées : le brouillon ne bouge pas
        partagees = await instantane.restaurer_les_partagees(organization_id, workflow, ligne, choisies, user)
    except instantane.ErreurInstantane as erreur:
        raise ErreurRevue(str(erreur)) from None
    nouveau = await _ranger(
        organization_id,
        workflow.id,
        cause=f"restauration de {numero}",
        avant=graphe,
        apres=ligne["avant"] if "schema" in choisies else graphe,
        version_avant=version,
        version_apres=numero_du_brouillon,
        fil_id=fil_id,
        operations=[],
        complement=avant_la_restauration,
    )
    await brouillon.ecrire_en_attente(organization_id, workflow.id, {"operations": [], "base_version": numero_du_brouillon})
    return {"version": numero_du_brouillon, "instantane": nouveau, "familles": choisies, **partagees}


async def apres_une_publication(organization_id: int, workflow: Any, publiee: Any, user: Any = None) -> int | None:
    """Un instantané de l'état PUBLIÉ (graphe, phrases, réglages, vocabulaire, objets). Ne lève jamais : une publication faite ne rate pas
    parce que son instantané n'a pas pu être pris."""
    try:
        graphe = copy.deepcopy(getattr(publiee, "workflow_json", None) or {})
        complement = await instantane.capturer(
            organization_id, workflow, user=user, configurations=dict(getattr(publiee, "workflow_configurations", None) or {})
        )
        return await _ranger(
            organization_id,
            workflow.id,
            cause="publication",
            avant=graphe,
            apres=graphe,
            version_avant=getattr(publiee, "version_number", None),
            version_apres=getattr(publiee, "version_number", None),
            fil_id=None,
            operations=[],
            complement=complement,
        )
    except Exception as erreur:  # noqa: BLE001
        from loguru import logger

        logger.warning(f"[revue] instantané de publication non pris : {type(erreur).__name__}")
        return None
