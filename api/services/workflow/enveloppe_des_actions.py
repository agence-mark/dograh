"""[.mark] Chantier fiabilite-orchestration : l'enveloppe des actions (outils HTTP, MCP, connecteurs).

Toute action qu'un agent ou le cerveau de fond appelle passe par cette enveloppe, posée au moment
où ``CustomToolManager`` enregistre son gestionnaire. Elle ne change rien à l'action ; elle lit son
résultat pour :

- **lot 1 (R3, G2)** : écrire les champs de la fiche « remplis par l'outil » (``rempli_par_outil``)
  depuis le résultat de cet outil, et seulement de lui. La valeur : la clé du même nom dans la
  réponse, sinon son statut, sinon la première valeur permise du champ, sinon « oui ». Un échec
  n'écrit rien. Les contrôles restent ceux du point d'écriture unique (liste fermée comprise).

Les portes, passations, transferts et la fin d'appel n'y passent jamais : ce ne sont pas des actions.
⛔ Ne lève jamais : l'action rend toujours son résultat, l'enveloppe ne fait que regarder.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

_ERREURS = frozenset({"error", "erreur", "echec", "échec", "failed", "failure", "ko"})


def _normaliser(nom: Any) -> str:
    from api.services.workflow.tools.custom_tool import custom_tool_function_name

    return custom_tool_function_name(str(nom or ""))


def _lire(resultat: Any) -> Any:
    if isinstance(resultat, str):
        try:
            return json.loads(resultat)
        except (TypeError, ValueError):
            return resultat
    return resultat


def est_un_echec(resultat: Any) -> bool:
    lu = _lire(resultat)
    if isinstance(lu, dict):
        if lu.get("error") not in (None, "", False):
            return True
        for cle in ("statut", "status"):
            valeur = lu.get(cle)
            if isinstance(valeur, str) and valeur.strip().casefold() in _ERREURS:
                return True
    return False


def valeur_pour_le_champ(champ: Any, resultat: Any) -> Any:
    """La valeur qu'un résultat d'outil réussi écrit dans ``champ`` (voir l'en-tête)."""
    lu = _lire(resultat)
    if isinstance(lu, dict):
        if lu.get(champ.nom) not in (None, ""):
            return lu[champ.nom]
        for cle in ("statut", "status"):
            if isinstance(lu.get(cle), str) and lu[cle].strip():
                return lu[cle].strip()
    if champ.valeurs:
        return champ.valeurs[0]
    return "oui"


def remplir_par_l_action(moteur: Any, nom_outil: str, resultat: Any) -> list[str]:
    """Écrit les champs que ``nom_outil`` remplit. Rend les noms des champs écrits. ⛔ Ne lève jamais."""
    ecrits: list[str] = []
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        if reglages is None or not isinstance(fiche, dict):
            return ecrits
        cible = _normaliser(nom_outil)
        champs = [
            c
            for c in reglages.champs
            if c.rempli_par_outil and _normaliser(c.rempli_par_outil) == cible
        ]
        if not champs:
            return ecrits
        if est_un_echec(resultat):
            logger.info(f"[fiche] {nom_outil} en échec : {', '.join(c.nom for c in champs)} non écrits")
            return ecrits
        from api.services.workflow.fiche_au_fil_de_leau import (
            SOURCE_ACTION,
            ecrire_dans_la_fiche,
        )

        for champ in champs:
            verdict = ecrire_dans_la_fiche(
                fiche, reglages, champ.nom, valeur_pour_le_champ(champ, resultat), source=SOURCE_ACTION
            )
            if verdict.statut == "ecrit":
                ecrits.append(champ.nom)
            logger.info(f"[fiche] {champ.nom} par {nom_outil} : {verdict.statut} ({verdict.raison})")
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[fiche] résultat de {nom_outil} non lu pour la fiche : {erreur!r}")
    return ecrits


STATUT_INCOMPLET = "incomplet"


def garde_de_l_etape(moteur: Any, agent: Any) -> dict | None:
    """Lot 2 (F9, C3 ; run 1468 : rendez-vous posé « nom et adresse à venir ») : l'étape de
    ``agent`` déclare la liste de ses champs, la case « connu et attendu » est allumée, et des
    champs manquent encore : l'outil ne s'exécute pas, il rend ``{"statut": "incomplet", "manque":
    [...]}`` (le modèle le lit et demande). Sans liste, sans fiche, case éteinte, ou rien ne
    manque : ``None`` (l'outil s'exécute comme avant). ⛔ Ne lève jamais."""
    try:
        reglages = getattr(moteur, "_fiche", None)
        fiche = getattr(moteur, "_gathered_context", None)
        noeud = getattr(agent, "current_node", None)
        champs_etape = tuple(getattr(noeud, "champs_etape", None) or ())
        if reglages is None or not isinstance(fiche, dict) or not champs_etape:
            return None
        if not getattr(reglages, "etiquettes", False):
            return None
        from api.services.fiche.traces import valeurs_des_traces
        from api.services.groupe.notes import champs_attendus, nom_lisible

        manque = champs_attendus(reglages, fiche, champs_etape, valeurs_des_traces(reglages, fiche))
        if not manque:
            return None
        return {"statut": STATUT_INCOMPLET, "manque": [nom_lisible(n) for n in manque]}
    except Exception as erreur:  # noqa: BLE001 -- dans le doute, l'outil s'exécute comme avant
        logger.warning(f"[fiche] garde de l'étape illisible : {erreur!r}")
        return None


Gestionnaire = Callable[[Any], Awaitable[None]]


def envelopper_l_action(
    moteur: Any,
    nom_outil: str,
    gestionnaire: Gestionnaire,
    agent: Any = None,
    *,
    garde: bool = True,
) -> Gestionnaire:
    """Le gestionnaire de l'action, enveloppé : la garde de l'étape d'``agent`` (lot 2), puis son
    résultat lu avant de partir au modèle (lot 1). ``garde=False`` : une action qui agit sur
    l'appel (une action interne qui peut transférer), jamais gardée."""

    async def enveloppe(params: Any) -> None:
        if garde and agent is not None:
            refus = garde_de_l_etape(moteur, agent)
            if refus is not None:
                logger.info(f"[fiche] {nom_outil} retenu : {refus['manque']} manquent")
                await params.result_callback(refus)
                return
        rendre = params.result_callback

        async def result_callback(resultat: Any, *args: Any, **kwargs: Any) -> None:
            proprietes = kwargs.get("properties")
            # Un résultat intermédiaire (``is_final=False``) n'est pas encore la réponse de l'outil.
            if getattr(proprietes, "is_final", True) is not False:
                remplir_par_l_action(moteur, nom_outil, resultat)
            await rendre(resultat, *args, **kwargs)

        try:
            params.result_callback = result_callback
        except Exception as erreur:  # noqa: BLE001 -- paramètres figés : l'action passe telle quelle
            logger.debug(f"[fiche] résultat de {nom_outil} non lu : {erreur!r}")
        await gestionnaire(params)

    return enveloppe
