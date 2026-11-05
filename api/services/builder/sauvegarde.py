"""[.mark] Builder, lot M (pièce 3 de Cognigy, licence MIT) : pas de modification d'un agent existant sans sauvegarde.

Choix, ÉTEINT par défaut (option ``sauvegarde_avant_modification``, ``options.py``). Éteint, rien n'est lu ni écrit de plus.
Allumé, la première action du builder qui MODIFIE un agent existant est refusée (« NOTHING WAS CHANGED ») tant qu'une
sauvegarde n'a pas été prise (``sauvegarde_prendre``) ou refusée explicitement par la personne (``sauvegarde_refuser``).

* rien n'est retenu sur ce qui est lu, ni sur un agent que cette conversation vient de créer (``create_workflow``) ;
* la sauvegarde est un instantané du graphe du brouillon, rangé comme ceux de la revue : « Revenir avant » le restaure.
  Partie 3 (SE-15) : elle garde aussi phrases, réglages, vocabulaire et objets (``instantane.py``) ;
* la ligne ``MARK_BUILDER:<agent>:sauvegarde`` garde l'état : ``faite``, ``refusee`` ou ``cree_ici``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.services.builder import instantane, options, revue, stock
from api.services.builder.actions.registre import Contexte, ErreurAction
from api.services.builder.constantes import cle_builder

PARTIE = "sauvegarde"
# Les actions qui changent l'agent lui-même (son graphe ou ses réglages). Une écriture dans la bibliothèque, une lecture, un
# test, une carte ne comptent pas. Ce sont des noms d'actions du builder, jamais des noms de recette.
MODIFIENT_L_AGENT: frozenset[str] = frozenset(
    {
        "save_workflow",
        "brouillon_enregistrer",
        "phrases_regler",
        "reglages_regler",
        "lexique_remplir_depuis_fiche",
        "modeles_reglages_appliquer",
        "bibliotheque_appliquer",
        "objets_agent_ecrire",
        "publication_corriger_la_liste_vocale",
        "outil_passer_a_la_version",
    }
)
ETATS_QUI_LAISSENT_PASSER = frozenset({"faite", "refusee", "cree_ici"})


def _cle(workflow_id: int) -> str:
    return cle_builder(workflow_id, PARTIE)


async def etat(organisation: int, workflow_id: int) -> dict[str, Any] | None:
    return await stock.lire(organisation, _cle(workflow_id))


async def _allumee(contexte: Contexte) -> bool:
    return (await options.lire(await options.organisation_des_options(contexte.user))).sauvegarde_avant_modification


async def garde(nom: str, parametres: Any, contexte: Contexte) -> None:
    """Appelée par ``executer`` avant l'action. Ne fait rien si l'option est éteinte ou si l'action ne modifie pas l'agent."""
    if nom not in MODIFIENT_L_AGENT:
        return
    identifiant = getattr(parametres, "workflow_id", None) or contexte.workflow_id
    if identifiant is None or not await _allumee(contexte):
        return
    ligne = await etat(contexte.organisation_id, identifiant)
    if ligne and ligne.get("etat") in ETATS_QUI_LAISSENT_PASSER:
        return
    raise ErreurAction(
        "NOTHING WAS CHANGED. This agent already exists and has no backup yet: take one first (sauvegarde_prendre), or, if the "
        "person explicitly does not want one, record it (sauvegarde_refuser). Then redo this action.",
        "sauvegarde_requise",
    )


async def apres_creation(contexte: Contexte, resultat: dict[str, Any]) -> None:
    """Un agent créé dans la conversation n'a rien à sauvegarder : on le note, seulement si l'option est allumée."""
    nouveau = resultat.get("workflow_id") or resultat.get("id")
    try:
        if not isinstance(nouveau, int) or not await _allumee(contexte):
            return
        await stock.ecrire(contexte.organisation_id, _cle(nouveau), {"etat": "cree_ici", "date": datetime.now(UTC).isoformat()})
    except Exception:  # noqa: BLE001 -- l'agent est créé : une note manquée ne doit pas faire croire à un échec
        return


async def prendre(contexte: Contexte, workflow: Any) -> dict[str, Any]:
    from api.services.builder import brouillon

    graphe, version = await brouillon.source_courante(workflow)
    graphe = graphe or {"nodes": [], "edges": []}
    numero = await revue._ranger(  # noqa: SLF001 -- le même rangement que les instantanés de la revue : « Revenir avant » le restaure
        contexte.organisation_id,
        workflow.id,
        cause="sauvegarde du builder",
        avant=graphe,
        apres=graphe,
        version_avant=version,
        version_apres=version,
        fil_id=(contexte.conversation or {}).get("fil_id"),
        operations=[],
        complement=await instantane.capturer(contexte.organisation_id, workflow, user=contexte.user),
    )
    await stock.ecrire(
        contexte.organisation_id, _cle(workflow.id), {"etat": "faite", "instantane": numero, "date": datetime.now(UTC).isoformat()}
    )
    return {"instantane": numero, "version": version}


async def refuser(contexte: Contexte, workflow_id: int, raison: str) -> None:
    await stock.ecrire(
        contexte.organisation_id,
        _cle(workflow_id),
        {"etat": "refusee", "raison": raison[:300], "date": datetime.now(UTC).isoformat()},
    )
