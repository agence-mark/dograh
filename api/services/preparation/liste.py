"""[.mark] Builder partie 3, SA-L3a (sous-lot 1, décisions 05 § 11 et § 14) : « Prêt à publier », UNE seule liste.

La même partout : la carte des Réglages, la fenêtre « Publier » et le builder (action ``publication_controler``) lisent ce que
rend ``assembler``. Elle réunit :

* les huit lignes de la préparation (``services/preparation``), dont les lignes **conditionnelles** (« hérité du principal » pour un
  spécialisé, fiche « sans objet » en temps réel, outils « sans objet » sans outil) ;
* les contrôles de la fenêtre « Publier » (``services/publication/controles``, SA-4) : bilan du prompt, liste vocale, attaques,
  garde-fous ;
* les réglages « sans effet », la sortie d'impasse et les deux webhooks (``services/publication/sans_effet``).

**Quatre états** : ``fait`` · ``a_faire`` · ``bloquant`` (la ligne est obligatoire, non faite, et son contrôle est sur « bloque ») ·
``herite``. ``sans_objet`` ne se montre pas (aussi le contrôle éteint : il n'est pas joué). Une ligne dit ce qui manque
(``manquants``, ``noms``) et où la régler (``theme``, ``noeud_id``, ``onglet``). Obligatoires en tête, puis ce qui bloque, ce qui reste
à faire, ce qui est fait. Rien n'est stocké : chaque lecture recalcule (l'écran relit après chaque enregistrement).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from api.services.preparation import A_FAIRE, BLOQUANT, CONSEILLE, FAIT, HERITE, REQUIS, SANS_OBJET, Etape

# Où se règlent les contrôles de la fenêtre « Publier » qui n'ont pas de ligne de préparation.
ENDROIT_DES_CONTROLES = {
    "bilan_du_prompt": {"theme": "agent", "onglet": "parcours"},
    "liste_vocale": {"theme": "agent", "onglet": None},
    "attaques": {"theme": "agent", "onglet": "tests"},
    "garde_fous": {"theme": "securite", "onglet": None},
    "annonce_ia": {"theme": "phrases", "onglet": None},
    "etiquettes": {"theme": "agent", "onglet": "parcours"},
    "blocs_a_jour": {"theme": "agent", "onglet": "parcours"},
    # Lot « façon Tala par motif » : les contrôles de rédaction et le poids se règlent dans le parcours (l'étape visée est ouverte).
    "valeur_en_dur": {"theme": "agent", "onglet": "parcours"},
    "verbe_ecran": {"theme": "agent", "onglet": "parcours"},
    "action_sans_outil": {"theme": "agent", "onglet": "parcours"},
    "sortie_non_citee": {"theme": "agent", "onglet": "parcours"},
    "poids_agent": {"theme": "agent", "onglet": "parcours"},
}
STATUT_VERS_ETAT = {"ok": FAIT, "alerte": A_FAIRE, "echec": BLOQUANT, "eteint": SANS_OBJET}


def _ligne_de_la_preparation(etape: Etape, positions: Mapping[str, str]) -> dict[str, Any]:
    ligne = asdict(etape)
    position = positions.get(etape.controle or "")
    ligne["position"] = position
    if position == "eteint":
        ligne["etat"] = SANS_OBJET  # un contrôle éteint n'est pas joué
    elif etape.etat == A_FAIRE and position == "bloque" and etape.niveau == REQUIS:
        ligne["etat"] = BLOQUANT
    ligne["onglet"] = "tests" if etape.id == "tests" else ("outils" if etape.id == "outils_a_jour" else None)
    return ligne


def _ligne_d_un_controle(controle: Mapping[str, Any]) -> dict[str, Any]:
    cle = controle["cle"]
    endroit = ENDROIT_DES_CONTROLES.get(cle, {})
    return {
        "id": cle,
        "niveau": REQUIS if controle["position"] == "bloque" else CONSEILLE,
        "etat": STATUT_VERS_ETAT.get(controle["statut"], A_FAIRE),
        "theme": endroit.get("theme", "agent"),
        "source": cle,
        "manquants": list(controle.get("problemes") or []),
        "manquants_details": list(controle.get("details") or []),
        "noeud_id": None,
        "controle": cle,
        "position": controle["position"],
        "corrections": [],
        "constat": None,
        "liaison_id": None,
        "noms": [],
        "onglet": endroit.get("onglet"),
    }


def _ligne_d_un_constat(constat: Any, position: str) -> dict[str, Any]:
    return {
        "id": constat.identifiant,
        "niveau": REQUIS if position == "bloque" else CONSEILLE,
        "etat": BLOQUANT if position == "bloque" else A_FAIRE,
        "theme": "agent",
        "source": constat.cle,
        "manquants": [],
        "noeud_id": constat.noeud_id,
        "controle": constat.controle,
        "position": position,
        "corrections": [asdict(c) for c in constat.corrections],
        "constat": constat.cle,
        "liaison_id": constat.liaison_id,
        "noms": list(constat.noms),
        "onglet": None,
    }


def _rang(ligne: Mapping[str, Any]) -> tuple[int, int]:
    ordre = {BLOQUANT: 0, A_FAIRE: 1, FAIT: 2, HERITE: 2}
    return (0 if ligne["niveau"] == REQUIS else 1, ordre.get(ligne["etat"], 3))


def assembler(
    etapes: list[Etape],
    constats: list[Any],
    controles: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Les lignes de « Prêt à publier » : pure. ``controles`` : les blocs de ``controles.evaluer`` (position, statut, problèmes)."""
    positions = {c["cle"]: c["position"] for c in controles}
    lignes = [_ligne_de_la_preparation(e, positions) for e in etapes]
    # Le contrôle des tests obligatoires est déjà la ligne « tests » ; les autres contrôles de la fenêtre ont leur propre ligne.
    deja = {l["controle"] for l in lignes if l["controle"]}
    for controle in controles:
        if controle["cle"] in ENDROIT_DES_CONTROLES and controle["cle"] not in deja and controle["statut"] != "eteint":
            lignes.append(_ligne_d_un_controle(controle))
    for constat in constats:
        position = positions.get(constat.controle, "eteint")
        if position != "eteint":
            lignes.append(_ligne_d_un_constat(constat, position))
    lignes = [l for l in lignes if l["etat"] != SANS_OBJET]
    lignes.sort(key=_rang)
    return lignes


def resume(lignes: list[Mapping[str, Any]]) -> dict[str, Any]:
    """L'état d'un agent en un mot, comme le dit la carte des Réglages (partie 3, L5b : la page de pilotage d'un client).

    ``pret`` : plus rien à faire ou à voir ; ``bloque`` : au moins un contrôle bloque la publication (``n`` = combien) ;
    ``afaire`` : rien ne bloque mais des lignes restent à voir (``n`` = combien). Les lignes « sans objet » ne comptent pas."""
    reste = [l for l in lignes if l["etat"] in (A_FAIRE, BLOQUANT)]
    bloquantes = sum(1 for l in reste if l["etat"] == BLOQUANT)
    if bloquantes:
        return {"etat": "bloque", "n": bloquantes}
    if reste:
        return {"etat": "afaire", "n": len(reste)}
    return {"etat": "pret", "n": 0}


async def lire_la_liste(organisation_id: int, workflow_id: int) -> list[dict[str, Any]]:
    """La liste « Prêt à publier » d'un agent de l'organisation (``ModeleRefuse`` 404 pour l'agent d'une autre). Lecture seule.

    C'est ``publication.controles.evaluer`` qui l'assemble, sur le brouillon (ou, sans brouillon, sur la version publiée) : la
    fenêtre « Publier » et cette page lisent donc le MÊME calcul."""
    from types import SimpleNamespace

    from api.db import db_client
    from api.services.modeles_reglages.service import ModeleRefuse
    from api.services.publication import controles

    workflow = await db_client.get_workflow(workflow_id, organization_id=organisation_id)
    if workflow is None:
        raise ModeleRefuse("Workflow not found", statut=404)
    source = await db_client.get_draft_version(workflow_id) or getattr(workflow, "released_definition", None)
    brouillon = SimpleNamespace(
        workflow_json=getattr(source, "workflow_json", None) or getattr(workflow, "workflow_definition", None) or {},
        workflow_configurations=getattr(source, "workflow_configurations", None) or {},
        version_number=getattr(source, "version_number", None),
    )
    vue = await controles.evaluer(workflow, brouillon, organisation_id)
    return vue["lignes"]
