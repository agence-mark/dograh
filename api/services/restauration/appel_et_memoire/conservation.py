"""[.mark] Module Restauration, lot 2 : la conservation de 30 jours, de bout en bout (E-10, T-15, T-23).

Une tâche planifiée (``tasks/arq.py``, de nuit) qui, pour chaque organisation rattachée à une base cliente :

1. efface dans la base du client le détail des commandes, réservations et messages de plus de 30 jours et GARDE le
   récapitulatif chiffré par jour (``restauration_purge.purger``) ;
2. efface, dans la base de Dograh, ce qui porte la conversation (transcription, enregistrements, textes) des appels de
   plus de 30 jours **des agents qui portent le module** (les agents où le module est allumé, lus dans la base du client) ;
   la ligne de l'appel (coût, durée, état) et son ``extra`` technique restent, comme pour la purge générale.

L'heure vient de la source d'heure de l'organisation (D6), jamais d'un appel direct. Rejouable sans effet double : la
base du client n'a plus rien à compter, les appels déjà vidés portent leur marqueur. Une organisation en échec ne
bloque pas les autres. Une purge de Dograh qui échoue sur un fichier laisse l'appel entier (repris la nuit suivante).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from api.db import db_client
from api.db.bases_clients import connexion as base_client
from api.db.bases_clients.horloge import horloge
from api.db.bases_clients.restauration_purge import agents_du_module, purger
from api.services.base_client.rattachement import organisations_rattachees
from api.services.conservation_appels.purge import (
    TAILLE_DU_LOT,
    _Stockages,
    _supprimer,
    adresses_de_l_audio,
    adresses_du_texte,
    adresses_non_reconnues,
)

JOURS_DE_CONSERVATION = 30
LOTS_MAX = 500  # une passe s'arrête d'elle-même ; le reste attend la nuit suivante


async def purger_les_copies_du_module(
    organization_id: int, agent_ids: list[int], avant: datetime, *, quand: datetime, lots_max: int = LOTS_MAX
) -> dict[str, int]:
    """Vide les copies d'appel (texte puis audio) de ces agents, dans cette organisation, plus vieilles que ``avant``."""
    bilan = {"texte": 0, "audio": 0, "echecs": 0}
    if not agent_ids:
        return bilan
    stockages = _Stockages()
    horodatage = quand.isoformat()
    for partie in ("texte", "audio"):
        apres_id = 0
        for _ in range(lots_max):
            lot = await db_client.lister_runs_a_purger(
                organization_id, avant=avant, partie=partie, apres_id=apres_id, limite=TAILLE_DU_LOT, agent_ids=agent_ids
            )
            if not lot:
                break
            apres_id = lot[-1]["id"]
            for run in lot:
                adresses = adresses_du_texte(run) if partie == "texte" else adresses_de_l_audio(run)
                if adresses_non_reconnues(run, partie) or not await _supprimer(stockages, run, adresses):
                    bilan["echecs"] += 1
                    continue
                if partie == "texte":
                    fait = await db_client.vider_les_copies_texte(run["id"], organization_id, horodatage)
                else:
                    fait = await db_client.marquer_audio_supprime(run["id"], organization_id, horodatage)
                bilan[partie] += 1 if fait else 0
            if len(lot) < TAILLE_DU_LOT:
                break
    return bilan


async def purger_une_organisation_du_module(
    organization_id: int, nom_base: str, *, maintenant: datetime | None = None, jours: int = JOURS_DE_CONSERVATION
) -> dict[str, Any]:
    """La base du client, puis les copies d'appel de Dograh des agents du module."""
    maintenant = maintenant or horloge(nom_base).maintenant()
    avant = maintenant - timedelta(days=jours)
    connexion = await base_client.connecter(nom_base)
    try:
        base = await purger(connexion, avant)
        agents = await agents_du_module(connexion)
    finally:
        await connexion.close()
    copies = await purger_les_copies_du_module(organization_id, agents, avant, quand=maintenant)
    return {"base": base, "copies": copies, "agents": agents}


async def purge_restauration_de_nuit(_ctx=None, bases: list[tuple[int, str]] | None = None) -> dict[int, dict]:
    """La tâche planifiée : chaque base rattachée, une par une ; l'échec de l'une n'arrête pas les autres."""
    sortie: dict[int, dict] = {}
    for organization_id, nom_base in bases if bases is not None else await organisations_rattachees():
        try:
            sortie[organization_id] = {"statut": "faite", **await purger_une_organisation_du_module(organization_id, nom_base)}
        except Exception as erreur:  # noqa: BLE001 -- rejouée la nuit suivante, sans effet double
            message = f"{type(erreur).__name__}"
            logger.error(f"[.mark] Restauration retention failed (org {organization_id}): {message}")
            sortie[organization_id] = {"statut": "echec", "erreur": message}
    return sortie
