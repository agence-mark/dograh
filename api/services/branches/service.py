"""[.mark] Partie 3, SA-L3b (05 § 12) : les branches d'un agent, vues et gestes.

Un geste = un appel de cette couche, qui contrôle puis écrit par ``db_client`` (toujours avec l'organisation). Les refus sont des
``ErreurDeBranche`` (message anglais, code court) que la route traduit en réponse d'erreur unique.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from api.db import db_client
from api.db.branches_client import ErreurDeBranche
from api.services.publication.reglages import deploiement_actif

LONGUEUR_MAX = 60


def nom_valide(brut: str) -> str:
    """Le nom nettoyé (espaces) ; refusé s'il est vide, trop long ou s'il contient un caractère de contrôle."""
    nom = " ".join((brut or "").split())
    if not nom:
        raise ErreurDeBranche("A branch needs a name", "nom")
    if len(nom) > LONGUEUR_MAX or any(unicodedata.category(c).startswith("C") for c in nom):
        raise ErreurDeBranche("A branch name is 60 characters at most, without control characters", "nom")
    return nom


def _configurations(agent: Any) -> dict[str, Any] | None:
    return getattr(getattr(agent, "released_definition", None), "workflow_configurations", None) or getattr(
        agent, "workflow_configurations", None
    )


async def _version_de_la_principale(organization_id: int, workflow_id: int, numero: int | None) -> int | None:
    """L'identifiant de la version publiée ou archivée de la PRINCIPALE portant ce numéro (``None`` si pas de numéro)."""
    if numero is None:
        return None
    versions = await db_client.get_workflow_version_summaries(workflow_id, organization_id)
    trouvee = next((v for v in versions if v["version_number"] == numero), None)
    if trouvee is None:
        raise ErreurDeBranche("Published or archived agent version not found", "introuvable")
    return trouvee["id"]


async def vue(organization_id: int, agent: Any, user_id: int | None) -> dict[str, Any]:
    """Les branches, leurs versions et brouillons, leur part. Quatre lectures, aucune en cascade."""
    branches = await db_client.lister_les_branches(organization_id, agent.id)
    principales = await db_client.get_workflow_version_summaries(agent.id, organization_id)
    autres = await db_client.versions_des_branches(organization_id, agent.id)
    brouillons = await db_client.brouillons_de_l_agent(organization_id, agent.id)
    numeros = {v["id"]: v["version_number"] for v in principales} | {v["id"]: v["version_number"] for v in autres}
    principale = next(b for b in branches if b.est_principale)
    protegee_en_fait, protegee_par_la_regle = await db_client.protection_de_la_principale(organization_id, agent.id)
    protection_reglee = principale.protection_choisie
    en_ligne_principale = principale.head_definition_id or getattr(agent, "released_definition_id", None)
    resultat = []
    for b in branches:
        if b.est_principale:
            versions = [{"id": v["id"], "numero": v["version_number"], "publiee_le": v["published_at"]} for v in principales]
            tete = en_ligne_principale
        else:
            versions = [
                {"id": v["id"], "numero": v["version_number"], "publiee_le": v["published_at"]}
                for v in autres
                if v["branch_id"] == b.id
            ]
            tete = b.head_definition_id
        propres = [
            {"id": d["id"], "numero": d["version_number"], "a_moi": d["draft_owner_id"] == user_id or (b.est_principale and d["draft_owner_id"] is None)}
            for d in brouillons
            if (d["branch_id"] or principale.id) == b.id
        ]
        resultat.append(
            {
                "id": b.id,
                "nom": b.nom,
                "principale": b.est_principale,
                "protegee": protegee_en_fait if b.est_principale else b.protegee,
                "protegee_par_defaut": bool(b.est_principale and protegee_par_la_regle),
                "protection_reglee": protection_reglee if b.est_principale else None,
                "part": b.part_trafic,
                "version_en_ligne": numeros.get(tete),
                "versions": versions,
                "brouillons": propres,
            }
        )
    return {"repartition_active": deploiement_actif(_configurations(agent)), "branches": resultat}


async def creer(
    organization_id: int, agent: Any, nom: str, *, depuis_version: int | None, user_id: int | None, protegee: bool
) -> dict[str, Any]:
    nom = nom_valide(nom)
    existantes = await db_client.lister_les_branches(organization_id, agent.id, avec_archivees=True)
    if any(b.nom.casefold() == nom.casefold() for b in existantes):
        raise ErreurDeBranche("A branch with this name already exists", "nom_pris")
    depuis = await _version_de_la_principale(organization_id, agent.id, depuis_version)
    branche, brouillon = await db_client.creer_une_branche(
        organization_id, agent.id, nom, depuis_definition_id=depuis, user_id=user_id, protegee=protegee
    )
    return {"id": branche.id, "nom": branche.nom, "brouillon": brouillon.id}


async def publier(organization_id: int, agent: Any, branch_id: int, user_id: int | None) -> dict[str, Any]:
    version = await db_client.publier_le_brouillon_de_branche(organization_id, agent.id, branch_id, user_id)
    return {"id": version.id, "version_number": version.version_number, "status": version.status}


async def regler_la_repartition(organization_id: int, agent: Any, parts: dict[int, int]) -> dict[str, Any]:
    """Écrit les parts. Éteint (réglage de l'agent), une part non nulle sur une branche est refusée ; une branche sans version
    publiée ne reçoit rien."""
    branches = await db_client.lister_les_branches(organization_id, agent.id)
    pour_les_autres = {b.id: b for b in branches if not b.est_principale}
    if any(parts.get(i, 0) > 0 for i in pour_les_autres) and not deploiement_actif(_configurations(agent)):
        raise ErreurDeBranche("The traffic split is off for this agent (Settings > Publication).", "eteint")
    for identifiant, b in pour_les_autres.items():
        if parts.get(identifiant, 0) > 0 and b.head_definition_id is None:
            raise ErreurDeBranche("A branch without a published version cannot take calls", "sans_version")
    ecrites = await db_client.regler_la_repartition(organization_id, agent.id, parts)
    return {"parts": {b.id: b.part_trafic for b in ecrites}}


async def epingler_la_principale(organization_id: int, agent: Any, version: int | None) -> dict[str, Any]:
    """« Revenir à la vN » sur la principale : elle sert cette version tant qu'on ne la libère pas (``None``) ou qu'on ne publie pas."""
    identifiant = await _version_de_la_principale(organization_id, agent.id, version)
    await db_client.epingler_la_principale(organization_id, agent.id, identifiant)
    return {"version": version}


async def proteger_la_principale(organization_id: int, agent: Any, protegee: bool) -> dict[str, Any]:
    """Clôture, lot B (D5) : le réglage « Protéger la version en ligne » de CET agent. ``True`` / ``False`` : le choix de l'équipe (levable même chez un
    client) ; ``None`` : retour à la règle par défaut (allumée chez un client à la première publication par une personne, éteinte au Labo)."""
    await db_client.regler_la_protection_de_la_principale(organization_id, agent.id, protegee)
    en_fait, par_la_regle = await db_client.protection_de_la_principale(organization_id, agent.id)
    return {"protegee": en_fait, "protegee_par_defaut": par_la_regle, "reglee": protegee}
