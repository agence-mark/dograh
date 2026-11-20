"""[.mark] Chantier Partie 1, lot 19 bis (S1) : la porte d'acceptation garde aussi la publication d'une branche et la fusion dans la principale.

Avant : ``verifier_avant_publication`` (tests obligatoires rejoués sur CE brouillon, contrôles de publication) n'avait qu'un appelant, la publication directe de
l'agent. Une retouche d'un agent installé passe pourtant par une branche (sa principale est protégée dès la première publication) : publier la branche ou la
fusionner mettait en ligne sans aucun test. Une seule fonction, ``exiger_la_porte``, relit le même contrôle pour les deux gestes, et le forçage suit la règle
de la publication directe (une raison écrite au journal ; les tests GÉNÉRÉS rouges ne se forcent que par une session de l'équipe .mark).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from api.db.branches_client import ErreurDeBranche


async def exiger_la_porte(
    organization_id: int,
    agent: Any,
    *,
    graphe: dict[str, Any] | None,
    reglages: dict[str, Any] | None,
    version: int | None,
    user: Any,
    geste: str,
    forcer: bool = False,
    raison: str | None = None,
) -> None:
    """Ne rend rien si la porte est ouverte (ou forcée par qui en a le droit) ; sinon ``ErreurDeBranche`` de code ``porte`` ou ``forcage_interdit``.
    ``graphe``, ``reglages``, ``version`` : ce qui entrerait en ligne (le brouillon de la branche, ou le résultat de la fusion)."""
    from api.services.builder.tests_agent.publication import verifier_avant_publication
    from api.services.equipe_mark.acces import journaliser
    from api.services.gabarits.diffusion import forcage_permis, tests_generes_rouges
    from api.services.publication.controles import RaisonObligatoire, raison_valide

    a_publier = SimpleNamespace(workflow_json=graphe, workflow_configurations=reglages, version_number=version)
    refus = await verifier_avant_publication(agent, a_publier, organization_id, getattr(user, "id", None))
    if refus is None:
        return
    resume = "; ".join(str(e.get("message")) for e in refus.get("errors", []))[:600]
    if not forcer or user is None:
        raise ErreurDeBranche(f"The acceptance gate refuses this {geste}: {resume}", "porte")
    try:
        raison_ecrite = raison_valide(raison)
    except RaisonObligatoire as erreur:
        raise ErreurDeBranche(str(erreur), "porte") from None
    if not await forcage_permis(user, refus):
        await journaliser(
            user, "agents.publier_force_refuse", organization_id,
            {"agent": agent.id, "geste": geste, "tests_generes_rouges": [t["slug"] for t in tests_generes_rouges(refus)][:20]},
        )
        raise ErreurDeBranche("Only a member of the .mark team can force a gate whose generated required tests are red.", "forcage_interdit")
    await journaliser(
        user, "agents.publier_force", organization_id,
        {"agent": agent.id, "geste": geste, "version": version, "raison": raison_ecrite, "ce_qui_bloquait": [e["message"] for e in refus.get("errors", [])][:20]},
    )
