"""Fausse voix : le protocole WebSocket d'ElevenLabs, tel que le fork le parle.

Lu dans pipecat/src/pipecat/services/elevenlabs/tts.py : le client ouvre
/v1/text-to-speech/<voix>/multi-stream-input?output_format=pcm_8000..., envoie
{"text": " ", "context_id": ...} pour ouvrir un contexte, {"text": "...",
"context_id": ...} pour chaque texte à dire, {"close_context": true} pour le
fermer, et {"text": ""} pour garder la liaison ouverte. Le serveur rend
{"audio": <base64>, "contextId": ..., "alignment": {...}}, puis
{"isFinal": true, "contextId": ...} quand le contexte est fermé.

Le faux rend, pour chaque texte reçu, un ton pur de durée connue, au format
demandé dans l'adresse. Le fork demande du PCM (pcm_8000 au téléphone) : c'est
lui qui en fait de la loi mu pour Asterisk. Même texte, même son.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from aiohttp import WSMsgType, web
from journal import Journal
from reglages import ReglagesCourants
from son import fabriquer_ton_pcm, fabriquer_ton_ulaw

# Le son part par blocs de cette durée, sans attendre entre deux blocs : un
# fournisseur de voix rend le son plus vite qu'il ne se joue.
DUREE_D_UN_BLOC_MS = 200
FORMAT_PAR_DEFAUT = "pcm_24000"


def fabriquer_son(format_demande: str, duree_ms: int) -> tuple[bytes, int]:
    """Le son d'un texte et le nombre d'octets par milliseconde, pour le découper."""
    famille, _, frequence = format_demande.partition("_")
    if famille == "ulaw":
        return fabriquer_ton_ulaw(duree_ms), 8
    if famille != "pcm" or not frequence.isdigit():
        famille, _, frequence = FORMAT_PAR_DEFAUT.partition("_")
    return fabriquer_ton_pcm(duree_ms, int(frequence)), int(frequence) * 2 // 1000


def decouper(son: bytes, octets_par_ms: int) -> list[bytes]:
    taille = octets_par_ms * DUREE_D_UN_BLOC_MS
    return [son[debut : debut + taille] for debut in range(0, len(son), taille)]


def alignement(texte: str, duree_ms: int) -> dict[str, Any]:
    """Les lettres du texte réparties sur la durée du son, comme le rend ElevenLabs."""
    lettres = list(texte)
    pas = duree_ms // max(len(lettres), 1)
    return {
        "chars": lettres,
        "charStartTimesMs": [rang * pas for rang in range(len(lettres))],
        "charDurationsMs": [pas] * len(lettres),
    }


class FausseVoix:
    def __init__(self, reglages: ReglagesCourants, journal: Journal) -> None:
        self._reglages = reglages
        self._journal = journal
        self._connexions = 0

    async def flux(self, requete: web.Request) -> web.WebSocketResponse:
        liaison = web.WebSocketResponse()
        await liaison.prepare(requete)
        self._connexions += 1
        connexion = self._connexions
        format_demande = requete.query.get("output_format", FORMAT_PAR_DEFAUT)
        # Les textes d'un même contexte se disent dans l'ordre : chaque envoi
        # attend la fin du précédent.
        en_cours: dict[str, list[asyncio.Task[None]]] = {}
        fermetures: list[asyncio.Task[None]] = []
        textes_recus = 0

        def noter(evenement: str, **details: Any) -> None:
            self._journal.noter("voix", evenement, connexion=connexion, **details)

        async def dire(
            contexte: str, texte: str, numero: int, precedent: asyncio.Task[None] | None
        ) -> None:
            if precedent is not None:
                await asyncio.gather(precedent, return_exceptions=True)
            reglages = self._reglages.valeur
            await asyncio.sleep(reglages.delai_voix_ms / 1000)
            son, octets_par_ms = fabriquer_son(format_demande, reglages.duree_voix_ms)
            for rang, bloc in enumerate(decouper(son, octets_par_ms)):
                envoi: dict[str, Any] = {
                    "audio": base64.b64encode(bloc).decode(),
                    "contextId": contexte,
                }
                if rang == 0:
                    envoi["alignment"] = alignement(texte, reglages.duree_voix_ms)
                await liaison.send_str(json.dumps(envoi, ensure_ascii=False))
                if rang == 0:
                    noter("premier_son_rendu", contexte=contexte, texte_numero=numero)
            noter(
                "son_rendu",
                contexte=contexte,
                texte_numero=numero,
                duree_ms=reglages.duree_voix_ms,
                octets=len(son),
            )

        async def fermer(contexte: str, taches: list[asyncio.Task[None]]) -> None:
            await asyncio.gather(*taches, return_exceptions=True)
            await liaison.send_str(json.dumps({"isFinal": True, "contextId": contexte}))
            noter("contexte_ferme", contexte=contexte, textes=len(taches))

        noter(
            "connexion_ouverte",
            format=format_demande,
            voix=requete.match_info.get("voix"),
        )
        try:
            async for recu in liaison:
                if recu.type != WSMsgType.TEXT:
                    continue
                contenu: dict[str, Any] = json.loads(recu.data)
                contexte = contenu.get("context_id")
                if contenu.get("close_context"):
                    # Fermer un contexte ne jette pas les textes déjà reçus : leur
                    # son part, puis vient le message de fin. Le fork ferme ainsi
                    # un contexte dès qu'il a envoyé son dernier texte.
                    fermetures.append(
                        asyncio.create_task(
                            fermer(contexte, en_cours.pop(contexte, []))
                        )
                    )
                    continue
                texte = str(contenu.get("text") or "")
                if contexte is None or not texte.strip():
                    # Ouverture de contexte (" "), maintien de liaison ("") ou vidage.
                    continue
                textes_recus += 1
                noter(
                    "texte_recu",
                    contexte=contexte,
                    texte_numero=textes_recus,
                    texte=texte,
                )
                file = en_cours.setdefault(contexte, [])
                file.append(
                    asyncio.create_task(
                        dire(contexte, texte, textes_recus, file[-1] if file else None)
                    )
                )
        finally:
            for tache in [
                *fermetures,
                *(t for taches in en_cours.values() for t in taches),
            ]:
                tache.cancel()
            noter("connexion_fermee", textes=textes_recus)
        return liaison
