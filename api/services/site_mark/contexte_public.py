"""[.mark] S1 / D182 : le contexte posé par la page du client, en LISTE BLANCHE pour une session publique.

Constat (vérifié) : ``initial_context.py`` ne réserve que cinq clés ; or ``choisir_etablissement`` lit
``etablissement_id`` et ``called_number`` dans le contexte : un visiteur pouvait choisir son établissement depuis
la console de son navigateur. Règle : une session publique ne reçoit que les clés que l'agent déclare
(réglage ``contexte_public_cles`` de sa version publiée) plus un petit socle sans risque ; tout le reste est
écarté, et les clés qui pilotent le moteur (``CLES_MARK_INTERDITES``) le sont toujours, même déclarées.
"""

from __future__ import annotations

from typing import Any, Mapping

from loguru import logger

CLE_DECLAREES = "contexte_public_cles"
CLE_CANAL = "canal_mark"  # posée par le serveur à /init, jamais par la page (voir RESERVED_INITIAL_CONTEXT_KEYS)
CANAL_SITE = "site"

# Le socle du snippet fourni par .mark (page_url, today) et deux repères de page sans effet sur le moteur.
SOCLE = frozenset({"page_url", "page_title", "today", "referrer", "langue"})

# Jamais acceptées d'une page, même si un agent les déclare par erreur : elles choisissent le lieu, le numéro,
# la salutation ou l'état du moteur.
CLES_MARK_INTERDITES = frozenset(
    {
        "etablissement_id",
        "etablissement_de_lappel",
        "_mark_fiche_sans_heritage",
        "called_number",
        "caller_number",
        "numero_transfert",
        "horaires_ouverture",
        "adresse_etablissement",
        "etablissement",
        "greeting_override",
        "greffier_passes",
        "equipe",
        "equipe_gestes",
        "equipe_assignation",
        "verification_appelant",
        "hub_rendez_vous",
        "phrases_du_code",
        "fiche_etat",
        "fiche_journal",
        "provider",
        "direction",
        "workflow_run_id",
        "call_id",
        "runtime_configuration",
        CLE_CANAL,
    }
)


def cles_permises(configurations: Mapping | None) -> frozenset[str]:
    declarees = (configurations or {}).get(CLE_DECLAREES)
    extra = {c for c in declarees if isinstance(c, str)} if isinstance(declarees, list) else set()
    return frozenset((SOCLE | extra) - CLES_MARK_INTERDITES)


def filtrer_contexte_public(contexte: Mapping[str, Any] | None, configurations: Mapping | None) -> dict[str, Any]:
    """Les seules variables de page qu'une session publique reçoit. Les autres sont écartées et comptées dans le journal."""
    if not isinstance(contexte, Mapping):
        return {}
    permises = cles_permises(configurations)
    gardees = {k: v for k, v in contexte.items() if isinstance(k, str) and k.strip() in permises}
    ecartees = [str(k) for k in contexte if not (isinstance(k, str) and k.strip() in permises)]
    if ecartees:
        logger.warning(f"[.mark] Public context keys dropped: {', '.join(sorted(ecartees))[:300]}")
    return gardees
