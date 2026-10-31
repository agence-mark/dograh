"""[.mark] Builder (B48, complément du lot 1) : créer, modifier et lister les OBJETS DE L'AGENT, par les deux portes.

Un objet est un fait que l'agent reçoit en ``{{nom}}`` (valeur ou petit tableau, dans la base du client, lu une fois au
décroché). Le client le modifie lui-même depuis son portail : les faits sortent du prompt, qui reste une recette
standard. Ces actions REPRENNENT les routes existantes (``routes/objets_agent.py``) donc leurs garde-fous : plafond de
taille appliqué par la base du client, nom réservé au code ou à une phrase du catalogue refusé (409), type obligatoire
d'une valeur seule, base du client rattachée exigée. Rien n'est réécrit ici.

Un objet est TOUJOURS injecté (B47) : il n'a ni déclencheur ni chargement à la demande, et se place dans « Ce que tu
sais » par ``{{nom}}``. Base du client injoignable : l'appel garde le comportement d'aujourd'hui (le ``{{nom}}`` reste
écrit tel quel, l'appel continue) ; ces actions, elles, le disent au cerveau (503) au lieu de faire semblant.

La bibliothèque (famille ``objets-agent-types``) fournit des modèles (horaires, zone, marques, tarifs) : ``depuis`` en
applique un. Contenu attendu d'un élément : ``{"objets": [<objet>, ...]}`` au format d'un objet ci-dessous.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from api.schemas.objets_agent import LigneObjet, ObjetEnvoye
from api.services.builder.actions.registre import (
    Action,
    Contexte,
    ErreurAction,
    enregistrer,
)
from api.services.builder.bibliotheque import service as service_bibliotheque
from api.services.builder.bibliotheque.service import ErreurBibliotheque

FAMILLE_OBJETS_TYPES = "objets-agent-types"


def _route():
    """Les routes existantes (importées à l'appel : elles tirent la base du client, pas nécessaire au démarrage)."""
    from api.routes import objets_agent

    return objets_agent


def _refus_http(erreur: HTTPException) -> ErreurAction:
    return ErreurAction(str(erreur.detail), f"objets_{erreur.status_code}")


def _resume(objet: Any) -> dict[str, Any]:
    return {
        "nom": objet.nom,
        "placeholder": "{{" + objet.nom + "}}",
        "libelle": objet.libelle,
        "forme": objet.forme,
        "type": objet.type,
        "taille": getattr(objet, "taille", None),
        "utilise_par": [a.nom for a in getattr(objet, "utilise_par", [])],
    }


async def lister_les_objets(contexte: Contexte) -> Any:
    try:
        return await _route().get_objets(contexte.user)
    except HTTPException as erreur:
        raise _refus_http(erreur) from None


async def ecrire_des_objets(contexte: Contexte, objets: list[ObjetEnvoye]) -> list[dict[str, Any]]:
    """Crée ou réécrit chaque objet (le même nom = réécriture). Un refus d'un objet n'arrête pas les autres."""
    actuels = {o.nom: o.id for o in (await lister_les_objets(contexte)).objets}
    resultats: list[dict[str, Any]] = []
    for objet in objets:
        identifiant = actuels.get(objet.nom)
        try:
            ecrit = await _route()._ecrire(contexte.user, objet, identifiant)
        except HTTPException as erreur:
            resultats.append({"nom": objet.nom, "ok": False, "code": erreur.status_code, "erreur": str(erreur.detail)})
            continue
        actuels[objet.nom] = ecrit.id
        resultats.append({"ok": True, "action": "modifie" if identifiant is not None else "cree", **_resume(ecrit)})
    return resultats


# --- lister ----------------------------------------------------------------------------------------------------------


class _Rien(BaseModel):
    pass


async def _lister(contexte: Contexte, parametres: _Rien) -> dict[str, Any]:
    vue = await lister_les_objets(contexte)
    return {
        "ok": True,
        "objets": [_resume(o) for o in vue.objets],
        "plafond_caracteres": vue.plafond_caracteres,
        "placement": "Put each object in the « what you know » part of the prompt with its {{name}}.",
    }


# --- écrire ----------------------------------------------------------------------------------------------------------


class _Ecrire(BaseModel):
    objets: list[ObjetEnvoye] | None = Field(
        default=None,
        max_length=30,
        description=(
            "Objects to create, or to rewrite when the name exists. A value (forme=valeur, with a type) or a small table "
            "(forme=liste, columns and lines). Names: lowercase letters, digits, underscore. Always injected: no trigger."
        ),
    )
    depuis: str | None = Field(default=None, description="Slug of an 'objets-agent-types' library element, applied instead of objets.")
    valeurs: dict[str, str] = Field(default_factory=dict, description="With depuis: object name -> value, for a model made of single values.")
    lignes: dict[str, list[dict[str, str]]] = Field(
        default_factory=dict, description="With depuis: object name -> lines {column label: cell}, for a model made of tables."
    )


def _depuis_un_modele(contenu: dict[str, Any], valeurs: dict[str, str], lignes: dict[str, list[dict[str, str]]]) -> list[ObjetEnvoye]:
    brutes = contenu.get("objets")
    if not isinstance(brutes, list) or not brutes:
        raise ErreurAction("This library element holds no objects (expected {\"objets\": [...]}).", "modele")
    objets: list[ObjetEnvoye] = []
    for brut in brutes:
        try:
            objet = ObjetEnvoye.model_validate(brut)
        except ValidationError as erreur:
            raise ErreurAction(f"A model object is invalid ({erreur.errors()[0].get('msg', 'invalid')}).", "modele") from None
        if objet.nom in valeurs and objet.forme == "valeur":
            objet = objet.model_copy(update={"valeur": valeurs[objet.nom]})
        if objet.nom in lignes and objet.forme == "liste":
            objet = objet.model_copy(
                update={"lignes": [LigneObjet(ordre=i, valeurs=ligne) for i, ligne in enumerate(lignes[objet.nom])]}
            )
        objets.append(objet)
    return objets


async def _ecrire(contexte: Contexte, parametres: _Ecrire) -> dict[str, Any]:
    if bool(parametres.objets) == bool(parametres.depuis):
        raise ErreurAction("Give either objets or a library element (depuis), not both and not none.")
    if parametres.depuis:
        try:
            element = await service_bibliotheque.lire_element(FAMILLE_OBJETS_TYPES, parametres.depuis)
        except ErreurBibliotheque as erreur:
            raise ErreurAction(str(erreur), f"bibliotheque_{erreur.statut}") from None
        objets = _depuis_un_modele(element.courante.contenu, parametres.valeurs, parametres.lignes)
    else:
        objets = parametres.objets or []
    resultats = await ecrire_des_objets(contexte, objets)
    ok = all(r["ok"] for r in resultats)
    return {
        "ok": ok,
        "objets": resultats,
        "carte": {"type": "objets", "objets": resultats},
        "message": "Place each object in the « what you know » part of the prompt with its {{name}}; an object never has a trigger.",
    }


for _nom, _description, _parametres, _fonction, _ecriture in (
    (
        "objets_agent_lister",
        "List the agent's objects (facts the agent always receives as {{name}}: hours, area, brands, prices, numbers), with their size and who reads them.",
        _Rien,
        _lister,
        False,
    ),
    (
        "objets_agent_ecrire",
        "Create or rewrite objects of the agent (same guards as the screen: size ceiling, names reserved by the code refused), or apply a library model. A person edits them later from the portal.",
        _Ecrire,
        _ecrire,
        True,
    ),
):
    enregistrer(
        Action(nom=_nom, description=_description, parametres=_parametres, fonction=_fonction, ecriture=_ecriture, groupe="objets")
    )
