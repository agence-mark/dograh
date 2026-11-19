"""Les faux fournisseurs du banc : transcription, modèle et voix, sans clé.

Un seul petit serveur, trois protocoles, ceux que le fork parle déjà :

- transcription : WebSocket de Soniox, sur /transcribe-websocket ;
- modèle : API de conversation compatible OpenAI, sur /v1/chat/completions ;
- voix : WebSocket d'ElevenLabs, sur /v1/text-to-speech/<voix>/multi-stream-input.

Aucun code du fork ne change : l'organisation du banc règle l'adresse de ses
trois fournisseurs sur ce serveur. Les délais se règlent par PUT /reglages et
valent zéro par défaut. Chaque événement est écrit dans /resultats/faux.jsonl.

Deux écoutes : le port 8080 en clair pour le fork, et le port 443 en TLS pour la
vérification de clé de Soniox, qui vise une adresse fixe (voir certificat.py).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aiohttp import web
from certificat import contexte_du_serveur
from journal import Journal
from modele import FauxModele
from reglages import ReglagesCourants
from transcription import FausseTranscription
from voix import FausseVoix

PORT = 8080
PORT_TLS = 443
DOSSIER_RESULTATS = Path(os.environ.get("BANC_FAUX_RESULTATS", "/resultats"))
DOSSIER_CERTIFICATS = Path(os.environ.get("BANC_FAUX_CERTIFICATS", "/certificats"))

journal_du_serveur = logging.getLogger("faux")


def application() -> web.Application:
    reglages = ReglagesCourants()
    journal = Journal(DOSSIER_RESULTATS / "faux.jsonl")
    requetes = Journal(DOSSIER_RESULTATS / "faux-requetes-modele.jsonl")
    transcription = FausseTranscription(reglages, journal)
    modele = FauxModele(reglages, journal, requetes)
    voix = FausseVoix(reglages, journal)

    async def sante(_requete: web.Request) -> web.Response:
        return web.json_response({"etat": "pret"})

    async def lire_reglages(_requete: web.Request) -> web.Response:
        return web.json_response(reglages.valeur.en_dictionnaire())

    async def modifier_reglages(requete: web.Request) -> web.Response:
        try:
            nouveaux = reglages.modifier(await requete.json())
        except ValueError as refus:
            return web.json_response({"refus": str(refus)}, status=400)
        journal.noter("reglages", "modifies", **nouveaux.en_dictionnaire())
        return web.json_response(nouveaux.en_dictionnaire())

    async def remettre_a_zero(_requete: web.Request) -> web.Response:
        nouveaux = reglages.remettre_a_zero()
        journal.noter("reglages", "remis_a_zero", **nouveaux.en_dictionnaire())
        return web.json_response(nouveaux.en_dictionnaire())

    async def marquer(requete: web.Request) -> web.Response:
        """Écrit un repère dans le journal : le début d'une mesure, son nom."""
        journal.noter("banc", "repere", **(await requete.json()))
        return web.json_response({})

    async def fermer(_application: web.Application) -> None:
        journal.fermer()
        requetes.fermer()

    app = web.Application()
    app.on_cleanup.append(fermer)
    app.add_routes(
        [
            web.get("/sante", sante),
            web.get("/reglages", lire_reglages),
            web.put("/reglages", modifier_reglages),
            web.delete("/reglages", remettre_a_zero),
            web.post("/repere", marquer),
            web.get("/v1/models", modele.modeles),
            web.post("/v1/chat/completions", modele.conversation),
            web.get("/transcribe-websocket", transcription.flux),
            web.get("/v1/text-to-speech/{voix}/multi-stream-input", voix.flux),
        ]
    )
    return app


async def demarrer() -> web.AppRunner:
    lanceur = web.AppRunner(application())
    await lanceur.setup()
    await web.TCPSite(lanceur, "0.0.0.0", PORT).start()
    await web.TCPSite(
        lanceur,
        "0.0.0.0",
        PORT_TLS,
        ssl_context=contexte_du_serveur(DOSSIER_CERTIFICATS),
    ).start()
    journal_du_serveur.info(
        "Faux fournisseurs prêts : %d en clair, %d en TLS", PORT, PORT_TLS
    )
    return lanceur


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    async def principal() -> None:
        lanceur = await demarrer()
        try:
            await asyncio.Event().wait()
        finally:
            await lanceur.cleanup()

    asyncio.run(principal())
