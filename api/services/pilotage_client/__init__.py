"""[.mark] Partie 3, L5b (décision 16 de l'audit) : la page de pilotage d'un client, assemblée en UNE réponse.

Ce module ne compte rien lui-même : chaque chiffre vient d'un calcul qui existe déjà.

| Bloc | Calcul réutilisé |
|---|---|
| chiffres, motifs, note, agents (appels, note) | ``boucle.qualite`` (``_resume`` / ``_motifs`` : la page Qualité) |
| alertes actives | ``alertes_agent.reglages`` (les alertes levées, une lecture pour tous les agents) |
| problèmes graves | ``mark_ameliorations`` (« À améliorer », état « à trier », gravité haute) |
| installation | ``installation_client.moteur.vue`` (les neuf étapes) |
| branche en ligne, part du trafic | ``workflow_branches`` (``db_client.agents_et_branches_pour_le_pilotage``) |
| « Prêt à publier » | ``preparation.liste.lire_la_liste`` + ``resume`` (la liste de la carte des Réglages et de la fenêtre Publier) |
| Relation client, activité récente | ``mark_relation_*`` et ``mark_journal`` (le Hub, le journal de l'équipe) |

Toutes les lectures partent ensemble (``asyncio.gather``), chacune filtrée par l'organisation DANS la requête. La seule lecture
par agent est « Prêt à publier » (sa liste n'existe qu'agent par agent) : bornée (``AGENTS_PRET_MAX`` agents, ``PRET_EN_PARALLELE``
à la fois, un délai), et un agent qui ne répond pas rend ``null`` (jamais un état inventé). Une lecture qui échoue rend ``null`` et
son nom dans ``illisibles`` : l'écran dit « illisible » pour ce bloc, le reste s'affiche.

⛔ Lecture seule. Aucun appel à un fournisseur, aucune dépense.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable

from loguru import logger

from api.db import db_client

PERIODES = {"24h": 1, "7j": 7, "30j": 30, "90j": 90}
PERIODE_PAR_DEFAUT = "7j"
# Une alerte levée reste « active » (À faire maintenant) ce nombre de jours : le service d'alertes ne les résout pas.
ALERTE_ACTIVE_JOURS = 7
ALERTES_MAX = 5
AGENTS_PRET_MAX = 24
PRET_EN_PARALLELE = 4
PRET_DELAI_S = 8.0
ACTIVITE_MAX = 8
PHRASE_MAX = 200
# Les gestes qui comptent pour l'« Activité récente » (le journal de l'équipe écrit aussi chaque enregistrement : trop bruyant).
ACTIONS_D_ACTIVITE = (
    "agents.publier",
    "agents.supprimer",
    "agents.branche_creee",
    "agents.branche_fusionnee",
    "agents.branche_publiee",
    "agents.repartition_du_trafic",
    "agents.branche_mise_a_jour",
    "builder.lancer",
    "connecteurs.geste",
    "installation.demarrer",
    "installation.terminer",
)


def tendance(courante: float | None, precedente: float | None) -> float | None:
    """La variation relative en % (arrondie), ``None`` quand l'une des deux périodes n'a rien de mesuré ou que la précédente vaut 0."""
    if courante is None or precedente is None or precedente == 0:
        return None
    return round((courante - precedente) / precedente * 100)


def _chiffre(identifiant: str, courante: float | None, precedente: float | None, *, appels: int, raison: str) -> dict[str, Any]:
    """Un chiffre de la période. ``raison`` : pourquoi il manque quand il manque (l'écran dit comment l'activer)."""
    disponible = courante is not None
    return {
        "id": identifiant,
        "valeur": courante,
        "precedente": precedente,
        "tendance": tendance(courante, precedente),
        "disponible": disponible,
        "raison": None if disponible else ("aucun_appel" if appels == 0 else raison),
    }


def chiffres_de_la_periode(courante: dict[str, Any], precedente: dict[str, Any]) -> list[dict[str, Any]]:
    """Les six chiffres, tous lus dans ``qualite._resume`` (les parts en %, la durée en secondes, le coût moyen d'un appel)."""
    appels = courante["appels"]

    def pct(valeur: float | None) -> float | None:
        return None if valeur is None else round(valeur * 100, 1)

    return [
        _chiffre("appels", appels if appels else None, precedente["appels"] or None, appels=appels, raison="aucun_appel"),
        _chiffre("resolus", pct(courante["part_resolu_sans_transfert"]), pct(precedente["part_resolu_sans_transfert"]), appels=appels, raison="bilan"),
        _chiffre("transferes", pct(courante["part_transferts"]), pct(precedente["part_transferts"]), appels=appels, raison="bilan"),
        _chiffre("note", courante["note"], precedente["note"], appels=appels, raison="juge"),
        _chiffre("cout", courante["cout_moyen"], precedente["cout_moyen"], appels=appels, raison="prix"),
        _chiffre("duree", courante["duree_moyenne"], precedente["duree_moyenne"], appels=appels, raison="duree"),
    ]


def alertes_actives(lignes: list[tuple[str, dict[str, Any]]], *, maintenant: datetime | None = None) -> list[dict[str, Any]]:
    """Les alertes levées depuis ``ALERTE_ACTIVE_JOURS`` jours, la plus récente d'abord (une lecture pour tous les agents)."""
    limite = (maintenant or datetime.now(UTC)) - timedelta(days=ALERTE_ACTIVE_JOURS)
    trouvees: list[tuple[datetime, dict[str, Any]]] = []
    for _cle, valeur in lignes:
        for alerte in valeur.get("levees") or []:
            if not isinstance(alerte, dict):
                continue
            try:
                quand = datetime.fromisoformat(str(alerte.get("levee_le")))
            except ValueError:
                continue
            if quand.tzinfo is None:
                quand = quand.replace(tzinfo=UTC)
            if quand >= limite:
                trouvees.append((quand, alerte))
    trouvees.sort(key=lambda p: p[0], reverse=True)
    return [
        {
            "id": a.get("id"),
            "type": a.get("type"),
            "workflow_id": a.get("workflow_id"),
            "workflow_nom": a.get("workflow_nom") or "",
            "resume": str(a.get("resume") or ""),
            "levee_le": quand.isoformat(),
        }
        for quand, a in trouvees
    ]


def installation_resumee(vue: dict[str, Any] | None) -> dict[str, Any] | None:
    """Les étapes de l'installation ouverte (numéro, titre, état : jamais un résultat), la prochaine et combien sont closes."""
    if vue is None:
        return None
    etapes = [{"numero": e["numero"], "titre": e["titre"], "etat": e["etat"]} for e in vue["etapes"]]
    return {
        "etapes": etapes,
        "prochaine": vue["prochaine"],
        "faites": sum(1 for e in etapes if e["etat"] in ("faite", "passee")),
        "total": len(etapes),
    }


def agents_du_client(
    agents: list[dict[str, Any]],
    par_agent: dict[int, dict[str, Any]],
    prets: dict[int, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Une ligne par agent : branche en ligne (la principale), part du trafic, autres branches, appels de la période, note, état prêt."""
    lignes = []
    for a in agents:
        branches = a["branches"]
        principale = next((b for b in branches if b["principale"]), None)
        version = (principale or {}).get("version") or a["version_publiee"]
        chiffres = par_agent.get(a["id"]) or {}
        lignes.append(
            {
                "id": a["id"],
                "nom": a["nom"],
                "version": version,
                "publie": a["version_publiee"] is not None,
                "part": principale["part"] if principale else 100,
                "autres": [{"nom": b["nom"], "part": b["part"], "version": b["version"]} for b in branches if not b["principale"] and b["part"] > 0],
                "appels": chiffres.get("appels", 0),
                "note": chiffres.get("note"),
                "pret": prets.get(a["id"]),
            }
        )
    return lignes


def activite_recente(lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les gestes du journal de l'équipe pour ce client : l'action (code), qui (prénom et nom, ``None`` si inconnu : jamais une
    adresse ni un identifiant de compte), quand, et si c'est le builder qui l'a fait."""
    sortie = []
    for j in lignes:
        qui = " ".join(p for p in (j.get("prenom"), j.get("nom")) if p) or None
        detail = j.get("detail") if isinstance(j.get("detail"), dict) else {}
        sortie.append(
            {
                "id": j["id"],
                "action": j["action"],
                "qui": qui,
                "par_builder": detail.get("par") == "builder" or j["action"] == "builder.lancer",
                "quand": j["quand"].isoformat(),
            }
        )
    return sortie


async def _relation(organisation_id: int) -> dict[str, Any]:
    """Le Hub en petit : fils non lus, demandes de logiciel nouvelles, la dernière phrase REÇUE du client (jamais une note interne)."""
    comptes, dernier = await asyncio.gather(
        db_client.compter_fils_relation([organisation_id]), db_client.dernier_message_du_client(organisation_id)
    )
    c = comptes.get(organisation_id) or {"ouverts": 0, "non_lus": 0, "demandes_nouvelles": 0}
    return {
        "ouverts": c["ouverts"],
        "non_lus": c["non_lus"],
        "demandes_nouvelles": c["demandes_nouvelles"],
        "dernier": None
        if dernier is None
        else {
            "fil_id": dernier["fil_id"],
            "sujet": dernier["sujet"],
            "texte": dernier["texte"][:PHRASE_MAX],
            "auteur": dernier["auteur"],
            "cree_le": dernier["cree_le"].isoformat(),
        },
    }


async def _lire(nom: str, lecture: Awaitable[Any], illisibles: list[str]) -> Any:
    """Une lecture qui échoue ne casse pas la page : ``None`` et son nom dans ``illisibles`` (jamais le texte de l'erreur)."""
    try:
        return await lecture
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[pilotage-client] {nom} non lu : {type(erreur).__name__}")
        illisibles.append(nom)
        return None


async def _prets(organisation_id: int, identifiants: list[int]) -> dict[int, dict[str, Any] | None]:
    from api.services.preparation import liste

    libre = asyncio.Semaphore(PRET_EN_PARALLELE)

    async def un(workflow_id: int) -> tuple[int, dict[str, Any] | None]:
        async with libre:
            try:
                lignes = await asyncio.wait_for(liste.lire_la_liste(organisation_id, workflow_id), PRET_DELAI_S)
                return workflow_id, liste.resume(lignes)
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[pilotage-client] prêt à publier non lu : {type(erreur).__name__}")
                return workflow_id, None

    return dict(await asyncio.gather(*(un(i) for i in identifiants[:AGENTS_PRET_MAX])))


async def _installation(organisation_id: int) -> dict[str, Any] | None:
    from api.services.installation_client import moteur

    ouverte = await db_client.installation_ouverte(organisation_id)
    return None if ouverte is None else await moteur.vue(ouverte, complements=False)


async def assembler(organisation_id: int, periode: str) -> dict[str, Any]:
    """La page de pilotage de l'organisation (à lire seulement après avoir contrôlé que l'appelant l'ouvre)."""
    from api.services.alertes_agent import reglages as reglages_alertes
    from api.services.boucle import qualite
    from api.services.builder import stock

    jours = PERIODES[periode]
    illisibles: list[str] = []
    qualite_deux, agents, alertes, graves, installation, relation, journal = await asyncio.gather(
        _lire("chiffres", qualite.calculer_deux_periodes(organisation_id, jours=jours), illisibles),
        _lire("agents", db_client.agents_et_branches_pour_le_pilotage(organisation_id), illisibles),
        _lire("alertes", stock.lister(organisation_id, reglages_alertes.PREFIXE), illisibles),
        _lire("problemes", db_client.compter_les_ameliorations_graves(organisation_id), illisibles),
        _lire("installation", _installation(organisation_id), illisibles),
        _lire("relation", _relation(organisation_id), illisibles),
        _lire(
            "activite",
            db_client.lister_journal(limit=ACTIVITE_MAX, offset=0, organization_id=organisation_id, actions=list(ACTIONS_D_ACTIVITE)),
            illisibles,
        ),
    )
    prets = await _lire("pret", _prets(organisation_id, [a["id"] for a in agents or []]), illisibles) if agents else {}
    actives = alertes_actives(alertes) if alertes is not None else None
    return {
        "periode": periode,
        "jours": jours,
        "en_service": any(a["version_publiee"] is not None for a in agents or []),
        "chiffres": chiffres_de_la_periode(qualite_deux["courante"], qualite_deux["precedente"]) if qualite_deux else None,
        "tronque": bool(qualite_deux and qualite_deux["tronque"]),
        "motifs": qualite_deux["motifs"] if qualite_deux else None,
        "agents": agents_du_client(agents, qualite_deux["agents"] if qualite_deux else {}, prets or {}) if agents is not None else None,
        "alertes": {"total": len(actives), "liste": actives[:ALERTES_MAX]} if actives is not None else None,
        "problemes_graves": graves,
        "installation": installation_resumee(installation),
        "relation": relation,
        "activite": activite_recente(journal[0]) if journal is not None else None,
        "illisibles": illisibles,
    }
