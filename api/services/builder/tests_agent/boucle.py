"""[.mark] Builder, lot 6 : la boucle d'amélioration (À trier → test → correction → rejeu → publication).

* **Historique des corrections et retour arrière** : chaque fois qu'on rejoue la suite sur une version du brouillon qu'on n'avait pas
  encore testée, on garde ``{version, empreinte, résumé du changement, suite verte ou non, instantané du graphe}`` dans
  ``MARK_BUILDER:<agent>:corrections`` (10 au plus, instantané borné). Le retour arrière remet l'instantané choisi EN BROUILLON
  (jamais une publication) ; la suite doit être rejouée ensuite (B38).
* **Tri par origine** : le défaut vient du client (→ la fiche), de la recette (→ une proposition à la bibliothèque) ou du code
  (→ un chantier du fork). L'origine est une suggestion tirée du type de signalement, que la personne change.

Le statut, l'assigné et l'origine d'un signalement vivent dans ``annotations["tri"]`` du run (``db/tri_client``), sans migration.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from api.db import db_client
from api.services.builder import stock
from api.services.builder.constantes import cle_builder
from api.services.builder.tests_agent import stockage

CORRECTIONS_GARDEES = 10
SNAPSHOT_MAX_OCTETS = 100_000

ORIGINE_CLIENT = "client"
ORIGINE_RECETTE = "recette"
ORIGINE_CODE = "code"
ORIGINES_DE_TRI = (ORIGINE_CLIENT, ORIGINE_RECETTE, ORIGINE_CODE)

# Ce que chaque origine déclenche (plan lot 6 et 07-boucle-et-coherence § 2).
SUITE_DE_L_ORIGINE = {
    ORIGINE_CLIENT: {"suite": "fiche", "libelle": "Fix the client sheet, then have the builder regenerate the step: this agent only."},
    ORIGINE_RECETTE: {"suite": "proposition", "libelle": "Propose a change to the library, prove it on a bench: every following agent benefits."},
    ORIGINE_CODE: {"suite": "chantier", "libelle": "A work item of the fork: every agent benefits once fixed."},
}
# Les types de signalement lus par ``tri.donnees`` : ce que l'on suggère par défaut.
ORIGINE_SUGGEREE_DES_TYPES_DU_CODE = ORIGINE_CODE
ORIGINE_SUGGEREE_PAR_CATEGORIE = {
    "demande ambiguë": ORIGINE_RECETTE,
    "règle inconnue": ORIGINE_CLIENT,
    "outil en échec": ORIGINE_CLIENT,
    "autre": ORIGINE_RECETTE,
}


def origine_suggeree(ligne: dict[str, Any]) -> str:
    if ligne.get("source") == "code":
        return ORIGINE_SUGGEREE_DES_TYPES_DU_CODE
    return ORIGINE_SUGGEREE_PAR_CATEGORIE.get(ligne.get("categorie") or "", ORIGINE_RECETTE)


# --- l'historique des corrections --------------------------------------------------------------------------------------------


def cle_corrections(workflow_id: int) -> str:
    return cle_builder(workflow_id, "corrections")


def empreinte(graphe: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(graphe, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def resumer_le_changement(avant: dict[str, Any] | None, apres: dict[str, Any]) -> str:
    """Une phrase sur ce qui a changé entre deux graphes (étapes ajoutées, retirées, prompts réécrits). Pur."""
    if not avant:
        return "First tested version."
    def noeuds(g):
        return {str(n.get("id")): n for n in g.get("nodes") or [] if isinstance(n, dict)}
    a, b = noeuds(avant), noeuds(apres)
    ajoutes = sorted(str((b[i].get("data") or {}).get("name") or i) for i in b.keys() - a.keys())
    retires = sorted(str((a[i].get("data") or {}).get("name") or i) for i in a.keys() - b.keys())
    modifies = sorted(
        str((b[i].get("data") or {}).get("name") or i) for i in a.keys() & b.keys() if (a[i].get("data") or {}) != (b[i].get("data") or {})
    )
    liaisons = len(avant.get("edges") or []) != len(apres.get("edges") or [])
    morceaux = []
    if ajoutes:
        morceaux.append("added: " + ", ".join(ajoutes[:4]))
    if retires:
        morceaux.append("removed: " + ", ".join(retires[:4]))
    if modifies:
        morceaux.append("changed: " + ", ".join(modifies[:4]))
    if liaisons:
        morceaux.append("links changed")
    return "; ".join(morceaux) or "Settings or tools only: the graph itself is unchanged."


async def lire_les_corrections(organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
    return list((await stock.lire(organization_id, cle_corrections(workflow_id)) or {}).get("entrees") or [])


async def noter_la_version_testee(
    organization_id: int, workflow_id: int, graphe: dict[str, Any], version: int | None, vert: bool, *, restaure_de: str | None = None
) -> dict[str, Any] | None:
    """Garde la version qu'on vient de tester si elle diffère de la dernière gardée ; sinon met à jour son résultat."""
    entrees = await lire_les_corrections(organization_id, workflow_id)
    cle = empreinte(graphe)
    if entrees and entrees[-1]["empreinte"] == cle:
        entrees[-1]["vert"] = bool(vert)
        entree = entrees[-1]
    else:
        brut = json.dumps(graphe, ensure_ascii=False)
        # L'instantané précédent sert à décrire le changement ; on ne le recopie pas deux fois.
        precedent = entrees[-1].get("instantane") if entrees else None
        entree = {
            "id": f"c{(int(entrees[-1]['id'][1:]) + 1) if entrees else 1}",
            "le": stockage.maintenant(),
            "version": version,
            "empreinte": cle,
            "vert": bool(vert),
            "resume": resumer_le_changement(precedent, graphe),
            "restaure_de": restaure_de,
            "instantane": graphe if len(brut.encode("utf-8")) <= SNAPSHOT_MAX_OCTETS else None,
        }
        entrees.append(entree)
    entrees = entrees[-CORRECTIONS_GARDEES:]
    await stock.ecrire(organization_id, cle_corrections(workflow_id), {"entrees": entrees})
    return entree


def sans_instantane(entree: dict[str, Any]) -> dict[str, Any]:
    return {**{k: v for k, v in entree.items() if k != "instantane"}, "retour_possible": entree.get("instantane") is not None}


async def historique(organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
    """Les corrections gardées, de la plus récente à la plus ancienne, sans les instantanés."""
    return [sans_instantane(e) for e in reversed(await lire_les_corrections(organization_id, workflow_id))]


class RetourImpossible(Exception):
    pass


async def retour_arriere(organization_id: int, workflow_id: int, correction_id: str) -> dict[str, Any]:
    """Remet l'instantané de ``correction_id`` en BROUILLON. Jamais une publication. La suite est à rejouer ensuite."""
    from api.services.builder import brouillon

    entrees = await lire_les_corrections(organization_id, workflow_id)
    entree = next((e for e in entrees if e["id"] == correction_id), None)
    if entree is None:
        raise RetourImpossible(f"Unknown correction: {correction_id}.")
    if not entree.get("instantane"):
        raise RetourImpossible("This correction's snapshot was too large to keep: it cannot be restored from here.")
    erreurs = await brouillon.valider(entree["instantane"], organization_id)
    if erreurs:
        raise RetourImpossible("The snapshot is not valid any more: " + "; ".join(erreurs[:2]))
    nouveau = await db_client.save_workflow_draft(workflow_id=workflow_id, workflow_definition=entree["instantane"])
    await brouillon.ecrire_en_attente(organization_id, workflow_id, {"operations": [], "base_version": nouveau.version_number})
    await noter_la_version_testee(organization_id, workflow_id, entree["instantane"], nouveau.version_number, False, restaure_de=correction_id)
    return {"ok": True, "version": nouveau.version_number, "restaure_de": correction_id, "message": "Restored as a draft. Replay the whole suite before calling it verified."}
