"""Les refus et nouvelles tentatives du modèle de conversation (.mark, langwatch-et-fenetre-du-run, lot 2).

Mistral passe par la bibliothèque cliente d'OpenAI, qui REFAIT une requête refusée (429, 5xx)
jusqu'à deux fois, en silence : l'appel continue, plus lent, et rien ne le dit. Seul le refus final
remontait (événement ``rtf-pipeline-error``). Ce module pose un crochet sur le client HTTP de ce
service : chaque tentative refusée ou recommencée devient un événement ``mark-model-request`` du
run (statut, numéro de tentative, durée, temps perdu depuis la première tentative), rattaché au
tour en cours.

⛔ Il ne change AUCUNE requête : il observe les réponses, ne lit ni le corps ni la clé.
⛔ Un crochet qui ne se pose pas ne fait pas tomber l'appel ; il est dit dans le journal, et la
fenêtre affiche « not captured ». ``test_capture_requetes_modele.py`` le pose sur le vrai service
construit par la fabrique : une bibliothèque qui changerait sa structure le fait rougir.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

TYPE_EVENEMENT = "mark-model-request"
ENTETE_TENTATIVE = "x-stainless-retry-count"
_DEBUT = "mark_debut"


def _client_http(llm: Any) -> Any:
    """Le client HTTP de la bibliothèque (``AsyncOpenAI._client``), ou ``None``."""
    client = getattr(llm, "_client", None)
    http = getattr(client, "_client", None)
    crochets = getattr(http, "event_hooks", None)
    if not isinstance(crochets, dict) or "response" not in crochets:
        return None
    return http


def brancher_le_journal_des_requetes(llm: Any, journal: Any) -> bool:
    """Pose les crochets ; ``False`` (et un avertissement) s'ils ne peuvent pas l'être."""
    try:
        http = _client_http(llm)
        if http is None:
            logger.warning(
                f"[captures] refus du modèle non captés : le client HTTP de "
                f"{type(llm).__name__} n'est pas accessible"
            )
            return False
        service = type(llm).__name__
        chaine = {"debut": None}

        async def a_la_requete(requete):
            requete.extensions[_DEBUT] = time.monotonic()

        async def a_la_reponse(reponse):
            try:
                debut = reponse.request.extensions.get(_DEBUT)
                maintenant = time.monotonic()
                tentative = int(reponse.request.headers.get(ENTETE_TENTATIVE, "0") or 0)
                if tentative == 0:
                    chaine["debut"] = debut
                if reponse.status_code < 400 and tentative == 0:
                    return
                perdu = (
                    debut - chaine["debut"]
                    if debut is not None and chaine["debut"] is not None
                    else None
                )
                await journal.append(
                    {
                        "type": TYPE_EVENEMENT,
                        "payload": {
                            "service": service,
                            "status": reponse.status_code,
                            "attempt": tentative,
                            "secs": None
                            if debut is None
                            else round(maintenant - debut, 3),
                            "lost_secs": None if perdu is None else round(perdu, 3),
                        },
                    }
                )
            except Exception as erreur:  # noqa: BLE001 — une mesure n'emporte pas l'appel
                logger.warning(f"[captures] refus du modèle non noté : {erreur!r}")

        http.event_hooks["request"].append(a_la_requete)
        http.event_hooks["response"].append(a_la_reponse)
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[captures] crochet des requêtes du modèle non posé : {erreur!r}"
        )
        return False
