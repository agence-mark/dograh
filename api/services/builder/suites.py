"""[.mark] Builder, lot M (pièce 5 de Cognigy, licence MIT) : la consigne de suite dans le résultat de chaque action.

Le résultat d'une action porte une clé ``suite`` = ``{"avertissement": ..., "prochaine": ...}`` : ce qui n'est PAS prouvé par ce
résultat, et la prochaine action à faire. Le cerveau doit la suivre. La clé est posée par les DEUX PORTES, au moment de rendre le résultat (le moteur de l'écran, ``OutilDuBuilder.run`` du MCP) ; ``executer`` lui-même ne change pas.

Ajout seulement : aucune clé existante d'un résultat n'est changée, et un résultat qui porte déjà une ``suite`` la garde.
Les textes sont de la mécanique du builder (jamais le nom d'une recette ni le métier d'un client).
"""

from __future__ import annotations

from typing import Any

PROCHAINE_PAR_ACTION: dict[str, str] = {
    "brouillon_operation": "Check the result with brouillon_voir, then save ONE draft with brouillon_enregistrer once the operations are complete.",
    "brouillon_voir": "If the graph is valid, save it with brouillon_enregistrer; otherwise fix the listed errors with brouillon_operation.",
    "brouillon_enregistrer": "Run the prompt control, try each tool, then replay the tests. The person reviews the changes; only a person publishes.",
    "brouillon_jeter": "Prepare the operations again if the work must continue.",
    "save_workflow": "Run the prompt control, try each tool, then replay the tests. Only a person publishes.",
    "create_workflow": "Build the agent with the draft operations, using the recipe of this agent.",
    "tests_creer": "Replay the test (tests_rejouer) before saying it passes.",
    "tests_rejouer": "Read the verdicts; for a failure, name the cause on the faulty reply before changing anything.",
    "prompt_controler": "Fix every blocking finding, then run the control again.",
    "sauvegarde_prendre": "Redo the action that was refused.",
    "sauvegarde_refuser": "Redo the action that was refused.",
    "agent_montrer_le_graphe": "Use the drawing to check the steps and links; it shows the saved draft, not the live agent.",
}

AVERTISSEMENT_PAR_CODE: dict[str, str] = {
    "conception": "Nothing was built: the design document is not approved yet.",
    "sauvegarde_requise": "Nothing was changed: the backup rule stopped it.",
    "recette": "Nothing was changed: the recipe of this agent does not allow it.",
    "sous_agent": "Nothing was done: a sub-agent only reads and tests.",
}


def _par_defaut(ecriture: bool) -> str:
    return (
        "Check with a read action before saying it is done."
        if ecriture
        else "Use what you just read; do not describe it as a change."
    )


def suite_de(nom: str, resultat: dict[str, Any], *, ecriture: bool) -> dict[str, str]:
    if resultat.get("ok") is False:
        avertissement = AVERTISSEMENT_PAR_CODE.get(str(resultat.get("code") or ""), "This action did not do what was asked: do not announce it as done.")
        return {
            "avertissement": avertissement,
            "prochaine": "Read the error, fix the arguments or ask the person; never repeat the same call unchanged.",
        }
    if resultat.get("disponible") is False:
        return {"avertissement": "This action is not available yet: nothing was done.", "prochaine": "Do not announce it; say it is not available."}
    return {
        "avertissement": "Only what this result shows is proven." if ecriture else "A reading proves nothing was changed.",
        "prochaine": PROCHAINE_PAR_ACTION.get(nom) or _par_defaut(ecriture),
    }


def ajouter(nom: str, resultat: dict[str, Any], *, ecriture: bool) -> dict[str, Any]:
    if not isinstance(resultat, dict) or "suite" in resultat:
        return resultat
    return {**resultat, "suite": suite_de(nom, resultat, ecriture=ecriture)}


def avec_la_suite_de(nom: str, resultat: dict[str, Any]) -> dict[str, Any]:
    """Les deux portes l'appellent sur le résultat de ``executer`` : le registre dit si l'action écrit."""
    from api.services.builder.actions.registre import REGISTRE

    action = REGISTRE.get(nom)
    return ajouter(nom, resultat, ecriture=bool(action and action.ecriture))
