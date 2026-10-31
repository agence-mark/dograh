"""[.mark] Builder, lot 6 : mettre à jour les agents existants quand une recette change (B30).

Une recette acceptée affiche **la liste des agents qui l'utilisent** (avec la version qu'ils utilisent). Pour chacun, de l'organisation
de la personne :

* la recette n'a pas bougé pour lui (``a_jour``) : rien ;
* il ne l'a **pas personnalisée** et la famille s'applique par une action (phrases du code, modèle de réglages, lexique) : un
  **brouillon** est préparé avec la nouvelle version, **sa suite est rejouée**, le résultat est présenté ;
* il l'a **personnalisée** (ce que l'agent contient a changé depuis la version qu'il utilisait) ou la famille est écrite par le
  builder (prompts, structures...) : une **proposition**, jamais un écrasement.

Rien n'est publié : une personne publie **agent par agent**. Un agent d'une autre organisation n'est pas touché d'ici (on le liste :
il se prépare depuis son organisation).
"""

from __future__ import annotations

from typing import Any

from api.services.builder import reglages_agent
from api.services.builder.actions.registre import Contexte, ErreurAction
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.familles import FAMILLES, MODE_APPLIQUE

ETAT_A_JOUR = "a_jour"
ETAT_BROUILLON = "brouillon_prepare"
ETAT_PROPOSITION = "proposition"
ETAT_AUTRE_ORGANISATION = "autre_organisation"
ETAT_REFUSE = "refuse"


async def agents_qui_utilisent(famille: str, slug: str) -> dict[str, Any]:
    """La recette, sa version courante et les agents qui l'utilisent (la version qu'ils utilisent)."""
    element = await service.lire_element(famille, slug)
    utilisateurs = await service.utilisation(famille, slug)
    return {
        "famille": famille,
        "slug": slug,
        "titre": element.titre,
        "version": element.courante.numero,
        "agents": [{**u, "a_jour": (u["version"] or 0) >= element.courante.numero} for u in utilisateurs],
    }


def _contenu_de_la_version(element, numero: int | None) -> dict[str, Any] | None:
    version = next((v for v in element.versions if v.numero == numero), None)
    return dict(version.contenu) if version else None


async def personnalisee(famille: str, ancien_contenu: dict[str, Any] | None, organisation_id: int, workflow_id: int) -> tuple[bool, str]:
    """(personnalisée, pourquoi). Comparaison de ce que la VERSION UTILISÉE écrivait avec ce que l'agent contient maintenant."""
    if ancien_contenu is None:
        return True, "The version this agent uses is unknown: nothing is overwritten."
    if FAMILLES[famille].mode != MODE_APPLIQUE:
        return True, "This family is written by the builder into the agent's text: it is proposed, never overwritten."
    configurations = await reglages_agent._configurations(organisation_id, workflow_id)
    if famille == "phrases-du-code":
        from api.schemas.phrases_du_code import ReglePhrase
        from api.services.phrases.regles import regles_de

        actuelles = {r.cle: r.model_dump(mode="json") for r in regles_de(configurations)}
        for brute in ancien_contenu.get("regles") or []:
            regle = ReglePhrase.model_validate(brute)
            if actuelles.get(regle.cle) != regle.model_dump(mode="json"):
                return True, f"The rule « {regle.motif} » was changed in this agent."
        return False, ""
    if famille == "modeles-reglages":
        for cle, valeur in (ancien_contenu.get("valeurs") or {}).items():
            if configurations.get(cle) != valeur:
                return True, f"The setting « {cle} » was changed in this agent."
        return False, ""
    return False, ""  # lexiques : on ajoute, on n'écrase rien


async def preparer(
    contexte: Contexte, famille: str, slug: str, *, rejouer_la_suite: bool = True, workflows: dict[int, Any] | None = None
) -> dict[str, Any]:
    """Prépare, agent par agent de l'organisation, la mise à jour vers la version courante. Ne publie rien."""
    from api.services.builder.actions.bibliotheque import appliquer_un_element
    from api.services.builder.tests_agent import execution

    element = await service.lire_element(famille, slug)
    courante = element.courante.numero
    sortie: list[dict[str, Any]] = []
    for u in await service.utilisation(famille, slug):
        ligne: dict[str, Any] = {"agent": u["agent"], "organisation": u["organisation"], "version_utilisee": u["version"], "version": courante}
        if u["organisation"] != contexte.organisation_id:
            sortie.append({**ligne, "etat": ETAT_AUTRE_ORGANISATION, "message": "Prepare it from this agent's own organization."})
            continue
        if (u["version"] or 0) >= courante:
            sortie.append({**ligne, "etat": ETAT_A_JOUR})
            continue
        ctx = Contexte(user=contexte.user, workflow_id=u["agent"], porte=contexte.porte)
        perso, pourquoi = await personnalisee(famille, _contenu_de_la_version(element, u["version"]), contexte.organisation_id, u["agent"])
        if perso:
            sortie.append({**ligne, "etat": ETAT_PROPOSITION, "message": pourquoi})
            continue
        try:
            await appliquer_un_element(ctx, famille, slug, u["agent"])
        except ErreurAction as erreur:
            sortie.append({**ligne, "etat": ETAT_REFUSE, "message": str(erreur)})
            continue
        ligne = {**ligne, "etat": ETAT_BROUILLON, "message": "A draft holds the new version. Nothing is published."}
        if rejouer_la_suite:
            from api.db import db_client

            workflow = (workflows or {}).get(u["agent"]) or await db_client.get_workflow(u["agent"], organization_id=contexte.organisation_id)
            suite = await execution.rejouer_la_suite(contexte.user, workflow)
            ligne["suite"] = {
                "ok": suite["ok"],
                "total": suite["total"],
                "echecs": len(suite["echecs"]),
                "disponible": suite.get("disponible", True),
                "message": suite.get("message", ""),
            }
        sortie.append(ligne)
    return {
        "ok": True,
        "famille": famille,
        "slug": slug,
        "version": courante,
        "agents": sortie,
        "elements": [{"statut": "ok" if a["etat"] in (ETAT_A_JOUR, ETAT_BROUILLON) else "avertissement", "message": f"agent {a['agent']} : {a['etat']}"} for a in sortie],
        "publie": 0,
    }
