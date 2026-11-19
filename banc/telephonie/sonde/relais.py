"""Relais du flux audio entre Asterisk et le fork, pour lire la file d'Asterisk.

Le flux audio d'un appel est une liaison WebSocket qu'Asterisk ouvre vers le
fork. Pour connaître la longueur de la file d'Asterisk pendant un appel du fork
réel, sans toucher au fork, ce relais se place entre les deux :

- il transmet tout, dans les deux sens, sans rien changer ;
- il demande à Asterisk, à intervalle fixe, la longueur de sa file
  (« GET_STATUS ») et garde la réponse pour lui ;
- il note chaque commande en texte que le fork envoie à Asterisk (par exemple
  « FLUSH_MEDIA »), avec son heure.

Asterisk n'est tourné vers le relais que le temps d'un essai
(./banc.sh relais on, puis off) : les mesures de latence se font sans lui.

Chaque relevé part dans /resultats/relais.jsonl, à l'horloge du noyau, la même
que celle de la capture réseau de SIPp et du journal des faux fournisseurs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import WSMsgType, web

PORT = 8091
ADRESSE_DU_FORK = os.environ.get("BANC_RELAIS_FORK", "ws://api:8000")
INTERVALLE_DE_LECTURE_S = 0.1
FICHIER = Path(os.environ.get("BANC_RELAIS_FICHIER", "/resultats/relais.jsonl"))
PROTOCOLE = "media"

journal = logging.getLogger("relais")


def longueur_de_file(reponse: str) -> int | None:
    """« STATUS queue_length:12 ... » vers 12 (en blocs de 20 ms)."""
    for champ in reponse.split():
        nom, _, valeur = champ.partition(":")
        if nom == "queue_length" and valeur.isdigit():
            return int(valeur)
    return None


class Releves:
    """Les relevés du relais. Le fichier est rouvert à chaque ligne : effacé
    entre deux essais, il renaît au relevé suivant."""

    def __init__(self, fichier: Path) -> None:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        self._fichier = fichier

    def noter(self, evenement: str, **details: Any) -> None:
        ligne = {"t_ns": time.time_ns(), "evenement": evenement, **details}
        with self._fichier.open("a", encoding="utf-8") as sortie:
            sortie.write(json.dumps(ligne, ensure_ascii=False) + "\n")


async def relayer(requete: web.Request) -> web.WebSocketResponse:
    releves: Releves = requete.app["releves"]
    cote_asterisk = web.WebSocketResponse(protocols=(PROTOCOLE,))
    await cote_asterisk.prepare(requete)
    appel = requete.query.get("workflow_run_id", "")
    blocs_vers_asterisk = 0

    async with aiohttp.ClientSession() as session:
        adresse = f"{ADRESSE_DU_FORK}{requete.path}?{requete.query_string}"
        async with session.ws_connect(adresse, protocols=(PROTOCOLE,)) as cote_fork:
            releves.noter("liaison_ouverte", run=appel)

            async def d_asterisk_vers_le_fork() -> None:
                async for recu in cote_asterisk:
                    if recu.type == WSMsgType.BINARY:
                        await cote_fork.send_bytes(recu.data)
                    elif recu.type == WSMsgType.TEXT:
                        if recu.data.startswith("STATUS"):
                            # La réponse à notre question : le fork ne l'a pas posée.
                            releves.noter(
                                "file",
                                run=appel,
                                blocs=longueur_de_file(recu.data),
                                blocs_recus_du_fork=blocs_vers_asterisk,
                            )
                            continue
                        releves.noter(
                            "asterisk_dit", run=appel, texte=recu.data.split()[0]
                        )
                        await cote_fork.send_str(recu.data)

            async def du_fork_vers_asterisk() -> None:
                nonlocal blocs_vers_asterisk
                async for recu in cote_fork:
                    if recu.type == WSMsgType.BINARY:
                        blocs_vers_asterisk += 1
                        await cote_asterisk.send_bytes(recu.data)
                    elif recu.type == WSMsgType.TEXT:
                        releves.noter("fork_dit", run=appel, texte=recu.data)
                        await cote_asterisk.send_str(recu.data)

            async def lire_la_file() -> None:
                while True:
                    await asyncio.sleep(INTERVALLE_DE_LECTURE_S)
                    await cote_asterisk.send_str("GET_STATUS")

            taches = [
                asyncio.create_task(d_asterisk_vers_le_fork()),
                asyncio.create_task(du_fork_vers_asterisk()),
                asyncio.create_task(lire_la_file()),
            ]
            # Le premier côté qui ferme met fin au relais.
            await asyncio.wait(taches, return_when=asyncio.FIRST_COMPLETED)
            for tache in taches:
                tache.cancel()
            await asyncio.gather(*taches, return_exceptions=True)
            releves.noter(
                "liaison_fermee", run=appel, blocs_recus_du_fork=blocs_vers_asterisk
            )
    await cote_asterisk.close()
    return cote_asterisk


def application() -> web.Application:
    app = web.Application()
    app["releves"] = Releves(FICHIER)
    app.add_routes([web.get("/api/v1/telephony/ws/ari", relayer)])
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    web.run_app(application(), port=PORT, access_log=None)
