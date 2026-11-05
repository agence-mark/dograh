"""[.mark] Partie 3, N3b (décision 20 de l'audit) : les tests d'un agent lancés par une automatisation (n8n) avec la clé de l'organisation.

Pas d'écran dédié : une adresse qui lance la suite de tests d'un agent et rend une réponse que l'automatisation lit sans rien
déchiffrer (``statut`` en mot, compteurs, tests, échecs, dépense). Rien de neuf côté exécution : c'est ``execution.rejouer_la_suite``,
la fonction de l'écran et du builder, donc le MÊME plafond de rejeu et les MÊMES budgets du mois des rôles (un budget atteint arrête
la suite, ``statut`` = ``plafond``). Un test d'un client n'appelle jamais un tiers : il joue sur les cerveaux réglés de l'organisation.

* **appel par une clé : le budget du mois doit être réglé** (revue RV, point 2) : sans budget (0 = aucun plafond), une clé appelée en boucle ferait
  dépenser sans fin ; ``verifier_le_budget`` refuse avec une phrase claire. Une limite de débit par organisation tient la route
  (``PAR_HEURE``) ; la dépense du modèle de l'agent pendant le rejeu est comptée dans la dépense du mois (``execution.compter_le_modele_de_l_agent``) ;
* un seul rejeu à la fois par agent (verrou nommé organisation + agent) : une automatisation qui boucle ne double pas la dépense ;
* arrêtable : au bout de ``DELAI_MAX_S`` la requête rend 504, les résultats déjà rangés se lisent avec ``dernier`` ;
* aucun texte interne (pile, requête, message de fournisseur) dans la réponse : seulement ce que le code des tests écrit.
"""

from __future__ import annotations

import asyncio
from typing import Any

from api.services import verrou
from api.services.builder.tests_agent import execution, stockage

DELAI_MAX_S = 900.0
REPETITIONS_PAR_DEFAUT = 1
CHAMPS_ECHEC = ("test", "nom", "obligatoire", "critere", "raison", "replique")


PAR_HEURE = 20  # lancements par organisation et par heure (le limiteur existant, comme ``/builder/miroir``)


class BudgetNonRegle(RuntimeError):
    """Une clé ne lance rien tant que le budget du mois n'est pas posé (> 0) : la phrase est celle que la route rend."""


class DejaEnCours(RuntimeError):
    """Un rejeu de cet agent est déjà en cours."""


class TropLong(RuntimeError):
    """Le rejeu a dépassé ``DELAI_MAX_S`` : ce qui était fini est rangé, à lire avec ``dernier``."""


def _statut(rendu: dict[str, Any]) -> str:
    if rendu.get("disponible") is False:
        return "sans_test"
    if rendu.get("plafond"):
        return "plafond"
    if not rendu.get("total"):
        return "sans_test"
    if not rendu.get("suite_complete"):
        return "incomplet"
    return "ok" if rendu.get("ok") else "echec"


def lisible(workflow_id: int, rendu: dict[str, Any]) -> dict[str, Any]:
    """Le rendu de ``rejouer_la_suite`` réduit à ce qu'une automatisation lit. Pur : ne lit que des champs écrits par le code des tests."""
    statut = _statut(rendu)
    return {
        "agent_id": workflow_id,
        "ok": statut == "ok",
        "statut": statut,
        "tests_total": int(rendu.get("total") or 0),
        "tests_reussis": int(rendu.get("reussis") or 0),
        "suite_complete": bool(rendu.get("suite_complete")),
        "obligatoire_en_echec": bool(rendu.get("refus")),
        "version": rendu.get("version"),
        "plafond": rendu.get("plafond"),
        "depense": rendu.get("depense"),
        "message": (rendu.get("message") or None),
        "tests": [
            {k: r.get(k) for k in ("slug", "nom", "obligatoire", "statut", "reussis", "total")} for r in (rendu.get("resultats") or [])
        ],
        "echecs": [{k: e.get(k) for k in CHAMPS_ECHEC} for e in (rendu.get("echecs") or [])],
    }


async def verifier_le_budget(user: Any) -> None:
    """Revue RV (point 2) : un appel PAR UNE CLÉ est refusé tant que le budget du mois n'est pas réglé. Il faut celui de l'appelant simulé
    (où se compte aussi le modèle de l'agent pendant le rejeu) et celui du juge quand il tourne sur une clé d'API. La session d'une
    personne n'est pas concernée : elle voit la dépense à l'écran."""
    if not getattr(user, "par_cle_api", False):
        return
    from api.services import sources_cerveaux
    from api.services.appel_simule import reglages as appel_simule

    organisation = user.selected_organization_id
    roles = await sources_cerveaux.surcharger_les_roles(organisation, await appel_simule.lire_reglages(organisation))
    manquants = []
    if roles.appelant.budget_mois <= 0:
        manquants.append("simulated caller")
    if roles.juge.actif and roles.juge.source == "cle_api" and roles.juge.budget_mois <= 0:
        manquants.append("judge")
    if manquants:
        raise BudgetNonRegle(
            f"Set the monthly budget of the {' and of the '.join(manquants)} (Labo settings > Simulated caller) before launching tests with an API key: "
            "without it nothing would stop an automation that loops."
        )


async def lancer(user: Any, workflow: Any, *, tests: list[str] | None, repetitions: int = REPETITIONS_PAR_DEFAUT) -> dict[str, Any]:
    """Joue la suite (ou les ``tests`` nommés) de l'agent ; ``DejaEnCours`` si un rejeu de cet agent tourne, ``TropLong`` au-delà du délai."""
    nom = f"tests-api:{user.selected_organization_id}:{workflow.id}"
    try:
        async with verrou.verrou(nom, bail_s=DELAI_MAX_S + 30, attente_s=0.2):
            try:
                rendu = await asyncio.wait_for(
                    execution.rejouer_la_suite(user, workflow, noms=tests, repetitions=repetitions), timeout=DELAI_MAX_S
                )
            except asyncio.TimeoutError:
                raise TropLong from None
    except verrou.Occupe:
        raise DejaEnCours from None
    return lisible(workflow.id, rendu)


async def dernier(organisation_id: int, workflow_id: int) -> dict[str, Any]:
    """La dernière exécution rangée de chaque test de l'agent (sans rien jouer, sans rien dépenser), dans la même forme que ``lancer``."""
    tous = await stockage.lister(organisation_id, workflow_id)
    lignes: list[dict[str, Any]] = []
    for test in tous:
        for essai in (await stockage.resultats(organisation_id, workflow_id, test["slug"]))[:1]:
            lignes.append(
                {
                    "slug": test["slug"],
                    "nom": test["nom"],
                    "obligatoire": bool(test.get("obligatoire")),
                    "statut": essai.get("statut"),
                    "reussis": essai.get("reussis"),
                    "total": essai.get("total"),
                    "le": essai.get("le"),
                    "version": essai.get("version"),
                }
            )
    complete = bool(tous) and len(lignes) == len(tous)
    tout_vert = complete and all(ligne["statut"] == "ok" for ligne in lignes)
    statut = "sans_test" if not tous else "incomplet" if not complete else "ok" if tout_vert else "echec"
    return {
        "agent_id": workflow_id,
        "ok": statut == "ok",
        "statut": statut,
        "tests_total": len(tous),
        "tests_reussis": sum(1 for ligne in lignes if ligne["statut"] == "ok"),
        "suite_complete": complete,
        "obligatoire_en_echec": any(ligne["obligatoire"] and ligne["statut"] != "ok" for ligne in lignes),
        "version": max((ligne["version"] for ligne in lignes if isinstance(ligne.get("version"), int)), default=None),
        "plafond": None,
        "depense": None,
        "message": None,
        "tests": lignes,
        "echecs": [],
    }
