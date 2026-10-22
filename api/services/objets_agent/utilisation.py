"""[.mark] Lot F7 : « utilisé par », calculé, jamais déclaré (D118).

Un objet est lu par un agent quand son ``{{nom}}`` figure dans les textes de la version PUBLIÉE de l'agent
(ce que lisent les appels) : prompts des étapes, consignes, phrases de ses réglages, tout ce que portent son
graphe et sa configuration ; ou dans une phrase du catalogue de l'organisation (ou d'une fiche) que
l'agent nomme en ``{{variable}}``. Rien à maintenir : on cherche au moment où l'on demande.

``synchroniser_utilisation`` écrit ce calcul dans la base du client (``objet_agent_utilisation``) : c'est ce
que lit la vue ``v_portail_objets`` (D119, condition b). Appelé à l'écran et à la publication d'un agent.
⛔ Ne lève jamais.
"""

from __future__ import annotations

import json
import re

from loguru import logger

from api.schemas.objets_agent import AgentUtilisateur


def motif_de(nom: str) -> re.Pattern:
    """``{{nom}}``, ``{{ nom }}``, ``{{nom | repli}}`` : la syntaxe du moteur (``template_renderer``)."""
    return re.compile(r"\{\{\s*" + re.escape(nom) + r"\s*(?:\|[^}]*)?\}\}")


def agents_qui_lisent(
    noms: list[str],
    agents: list[tuple[int, str, str]],
    phrases: dict[str, list[str]],
) -> dict[str, list[AgentUtilisateur]]:
    """Pure: ``agents`` = (id, name, all its published texts); ``phrases`` = variable -> its contents
    (organization's and fiches'). Returns each name's readers, in the agents' order."""
    sortie: dict[str, list[AgentUtilisateur]] = {}
    for nom in noms:
        cherche = motif_de(nom)
        variables = [v for v, contenus in phrases.items() if any(cherche.search(c or "") for c in contenus)]
        motifs = [cherche, *(motif_de(v) for v in variables)]
        sortie[nom] = [
            AgentUtilisateur(id=identifiant, nom=nom_agent)
            for identifiant, nom_agent, texte in agents
            if any(m.search(texte) for m in motifs)
        ]
    return sortie


async def _agents_publies(organization_id: int) -> list[tuple[int, str, str]]:
    from api.db import db_client
    from api.services.groupe.agents_servis import _statut, _version_publiee

    sortie = []
    for workflow in await db_client.list_workflows_for_model_configuration_migration(organization_id):
        if _statut(workflow.status) != "active":
            continue
        publiee = _version_publiee(workflow)
        if publiee is None:
            continue
        texte = json.dumps(
            [publiee.workflow_json or {}, publiee.workflow_configurations or {}], ensure_ascii=False
        )
        sortie.append((workflow.id, workflow.name, texte))
    return sortie


async def _phrases(organization_id: int) -> dict[str, list[str]]:
    from api.services.etablissements.copie import lire_copie_complete

    copie = await lire_copie_complete(organization_id)
    contenus: dict[str, list[str]] = {}
    for phrase in copie.phrases.phrases:
        contenus.setdefault(phrase.variable, []).append(phrase.contenu)
    for etablissement in copie.etablissements.etablissements:
        for variable, contenu in (etablissement.phrases or {}).items():
            contenus.setdefault(variable, []).append(contenu)
    return contenus


async def calculer_utilisation(organization_id: int, noms: list[str]) -> dict[str, list[AgentUtilisateur]]:
    return agents_qui_lisent(noms, await _agents_publies(organization_id), await _phrases(organization_id))


async def synchroniser_utilisation(organization_id: int | None) -> bool:
    """Compute and write who reads which object, in THIS organization's database. ``True``: written.
    No database, a database before the 019, or one that does not answer: nothing, never an error."""
    if organization_id is None:
        return False
    try:
        from api.db.bases_clients.connexion import connecter
        from api.db.bases_clients.objets import ecrire_utilisation, lire_objets
        from api.services.base_client.rattachement import nom_de_la_base
        from api.services.objets_agent.stockage import retenir_noms

        base = await nom_de_la_base(organization_id)
        if not base:
            return False
        connexion = await connecter(base)
        try:
            objets = await lire_objets(connexion)
            if not objets:
                return False
            utilisation = await calculer_utilisation(organization_id, [o.nom for o in objets])
            await ecrire_utilisation(connexion, {n: [a.id for a in agents] for n, agents in utilisation.items()})
        finally:
            await connexion.close()
        await retenir_noms(organization_id, [o.nom for o in objets])
        return True
    except Exception as erreur:  # noqa: BLE001 -- never a reason to fail a publication or a screen
        logger.warning(
            f"[.mark] Object readers of organization {organization_id} not written ({type(erreur).__name__}): {erreur}"
        )
        return False
