"""Faux modèle : l'API de conversation compatible OpenAI, telle que le fork la parle.

Lu dans pipecat/src/pipecat/services/openai/base_llm.py : le client envoie
POST <adresse>/chat/completions avec « stream » à vrai et lit un flux d'événements
(« data: {...} », puis « data: [DONE] »). La vérification de la clé à
l'enregistrement de la configuration appelle GET <adresse>/models
(api/services/configuration/check_validity.py).

Le faux rend toujours la même phrase. Il appelle un outil seulement sur
demande : quand la dernière parole de l'appelant contient « outil <motif> » et
que la requête propose un outil dont le nom contient ce motif. Après le résultat
de l'outil, il rend une phrase fixe. Même requête, même réponse.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from aiohttp import web
from journal import Journal
from reglages import Reglages, ReglagesCourants

MODELE = "faux-modele"
IDENTIFIANT = "chatcmpl-faux"
DEMANDE_D_OUTIL = re.compile(r"\boutil\s+([a-z0-9_]+)", re.IGNORECASE)


@dataclass(frozen=True)
class Parole:
    texte: str


@dataclass(frozen=True)
class AppelOutil:
    nom: str
    arguments: dict[str, Any]
    identifiant: str


Reponse = Parole | AppelOutil


def texte_du_message(message: dict[str, Any]) -> str:
    contenu = message.get("content")
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return " ".join(
            str(partie.get("text", ""))
            for partie in contenu
            if isinstance(partie, dict)
        )
    return ""


def valeur_d_essai(schema: dict[str, Any]) -> Any:
    """La plus petite valeur qui respecte un schéma d'argument d'outil."""
    if schema.get("enum"):
        return schema["enum"][0]
    genre = schema.get("type")
    if genre == "string":
        return "essai"
    if genre in ("integer", "number"):
        return 0
    if genre == "boolean":
        return False
    if genre == "array":
        return []
    if genre == "object":
        return arguments_d_essai(schema)
    return "essai"


def arguments_d_essai(parametres: dict[str, Any]) -> dict[str, Any]:
    proprietes = parametres.get("properties") or {}
    return {
        nom: valeur_d_essai(proprietes.get(nom) or {})
        for nom in parametres.get("required") or []
    }


def outil_demande(texte: str, outils: list[dict[str, Any]]) -> dict[str, Any] | None:
    """La fonction dont le nom contient le motif demandé par l'appelant."""
    demande = DEMANDE_D_OUTIL.search(texte)
    if demande is None:
        return None
    motif = demande.group(1).lower()
    for outil in outils:
        fonction = outil.get("function") or {}
        if motif in str(fonction.get("name", "")).lower():
            return fonction
    return None


def choisir_reponse(corps: dict[str, Any], reglages: Reglages) -> Reponse:
    messages: list[dict[str, Any]] = corps.get("messages") or []
    if corps.get("response_format"):
        # Une requête qui exige du JSON (extraction, classement) reçoit un objet vide.
        return Parole("{}")
    rangs_appelant = [
        rang for rang, message in enumerate(messages) if message.get("role") == "user"
    ]
    if not rangs_appelant:
        return Parole(reglages.phrase)
    dernier = rangs_appelant[-1]
    if any(message.get("role") == "tool" for message in messages[dernier + 1 :]):
        return Parole(reglages.phrase_apres_outil)
    fonction = outil_demande(
        texte_du_message(messages[dernier]), corps.get("tools") or []
    )
    if fonction is None:
        return Parole(reglages.phrase)
    return AppelOutil(
        nom=str(fonction["name"]),
        arguments=arguments_d_essai(fonction.get("parameters") or {}),
        # Unique dans une conversation : le rang du message qui suivra.
        identifiant=f"call_faux_{len(messages)}",
    )


def _morceau(delta: dict[str, Any], fin: str | None = None) -> dict[str, Any]:
    return {
        "id": IDENTIFIANT,
        "object": "chat.completion.chunk",
        "created": 0,
        "model": MODELE,
        "choices": [{"index": 0, "delta": delta, "finish_reason": fin}],
    }


def morceaux(reponse: Reponse) -> list[dict[str, Any]]:
    """Le flux rendu, morceau par morceau, sans le compte des jetons."""
    if isinstance(reponse, AppelOutil):
        appel = {
            "index": 0,
            "id": reponse.identifiant,
            "type": "function",
            "function": {
                "name": reponse.nom,
                "arguments": json.dumps(reponse.arguments, ensure_ascii=False),
            },
        }
        return [
            _morceau({"role": "assistant", "content": None, "tool_calls": [appel]}),
            _morceau({}, "tool_calls"),
        ]
    mots = reponse.texte.split()
    flux = [
        _morceau({"role": "assistant", "content": mot if rang == 0 else f" {mot}"})
        for rang, mot in enumerate(mots)
    ]
    flux.append(_morceau({}, "stop"))
    return flux


def compte_des_jetons(corps: dict[str, Any], reponse: Reponse) -> dict[str, int]:
    """Un compte stable, tiré du nombre de mots : pas une mesure."""
    entree = sum(len(texte_du_message(m).split()) for m in corps.get("messages") or [])
    sortie = len(reponse.texte.split()) if isinstance(reponse, Parole) else 1
    return {
        "prompt_tokens": entree,
        "completion_tokens": sortie,
        "total_tokens": entree + sortie,
    }


def reponse_entiere(corps: dict[str, Any], reponse: Reponse) -> dict[str, Any]:
    """La réponse d'une requête sans flux."""
    if isinstance(reponse, AppelOutil):
        message: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": reponse.identifiant,
                    "type": "function",
                    "function": {
                        "name": reponse.nom,
                        "arguments": json.dumps(reponse.arguments, ensure_ascii=False),
                    },
                }
            ],
        }
        fin = "tool_calls"
    else:
        message = {"role": "assistant", "content": reponse.texte}
        fin = "stop"
    return {
        "id": IDENTIFIANT,
        "object": "chat.completion",
        "created": 0,
        "model": MODELE,
        "choices": [{"index": 0, "message": message, "finish_reason": fin}],
        "usage": compte_des_jetons(corps, reponse),
    }


class FauxModele:
    def __init__(
        self, reglages: ReglagesCourants, journal: Journal, requetes: Journal
    ) -> None:
        self._reglages = reglages
        self._journal = journal
        # Les requêtes entières, à part : elles disent ce que le fork envoie.
        self._requetes = requetes
        self._compteur = 0

    async def modeles(self, _requete: web.Request) -> web.Response:
        return web.json_response(
            {
                "object": "list",
                "data": [{"id": MODELE, "object": "model", "owned_by": "banc"}],
            }
        )

    async def conversation(self, requete: web.Request) -> web.StreamResponse:
        corps: dict[str, Any] = await requete.json()
        self._compteur += 1
        numero = self._compteur
        reglages = self._reglages.valeur
        reponse = choisir_reponse(corps, reglages)
        messages = corps.get("messages") or []
        self._requetes.noter("modele", "requete", numero=numero, corps=corps)
        self._journal.noter(
            "modele",
            "requete_recue",
            numero=numero,
            messages=len(messages),
            dernier_role=messages[-1].get("role") if messages else None,
            outils=[
                (outil.get("function") or {}).get("name")
                for outil in corps.get("tools") or []
            ],
            flux=bool(corps.get("stream")),
            reponse="outil" if isinstance(reponse, AppelOutil) else "parole",
        )

        if not corps.get("stream"):
            await asyncio.sleep(reglages.delai_modele_ms / 1000)
            self._journal.noter("modele", "reponse_rendue", numero=numero)
            return web.json_response(reponse_entiere(corps, reponse))

        sortie = web.StreamResponse(
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
        )
        await sortie.prepare(requete)
        await asyncio.sleep(reglages.delai_modele_ms / 1000)
        for rang, morceau in enumerate(morceaux(reponse)):
            if rang:
                await asyncio.sleep(reglages.delai_entre_morceaux_ms / 1000)
            await sortie.write(
                f"data: {json.dumps(morceau, ensure_ascii=False)}\n\n".encode()
            )
            if rang == 0:
                self._journal.noter("modele", "premier_morceau_rendu", numero=numero)
        if (corps.get("stream_options") or {}).get("include_usage"):
            compte = {
                **_morceau({}),
                "choices": [],
                "usage": compte_des_jetons(corps, reponse),
            }
            await sortie.write(f"data: {json.dumps(compte)}\n\n".encode())
        await sortie.write(b"data: [DONE]\n\n")
        await sortie.write_eof()
        self._journal.noter("modele", "reponse_rendue", numero=numero)
        return sortie
