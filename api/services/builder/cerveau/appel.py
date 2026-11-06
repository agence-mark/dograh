"""[.mark] Builder : la couche d'appel unique (B46, R0-2), sur ``httpx``, deux formats de fil.

Un seul contrat pour le moteur : ``Cerveau.tour(systeme, messages, outils)`` rend un flux d'événements

* ``{"type": "texte", "texte": str}``                                      un morceau de réponse ;
* ``{"type": "appel", "id", "nom", "arguments": dict}``                    une action demandée ;
* ``{"type": "usage", "entree", "sortie", "cache_lu", "cache_ecrit"}``     la consommation du tour ;
* ``{"type": "fin", "raison": "outils" | "fin" | "longueur"}``             la fin du tour.

Messages (neutres, c'est ce que le moteur range) :
``{"role": "user", "content"}``, ``{"role": "assistant", "content", "appels": [...]}``,
``{"role": "outil", "appel_id", "nom", "content"}``.

Les erreurs sont normalisées en ``ErreurCerveau`` (code, message, réessayable), quel que soit le fournisseur.
⛔ La clé ne sort jamais : ni dans un message d'erreur, ni dans un journal (on n'enregistre ni en-têtes ni corps).
Aucune dépendance ajoutée (ni LangChain, ni LiteLLM, ni le SDK du fournisseur).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from api.services.builder.cerveau.reglages import ADRESSE_PAR_DEFAUT, ReglagesCerveau

DELAI_REPONSE_S = 120.0
TENTATIVES_MAX = 3
VERSION_ANTHROPIC = "2023-06-01"

CODE_CLE = "cle_refusee"
CODE_LIMITE = "limite"
CODE_INDISPONIBLE = "indisponible"
CODE_REQUETE = "requete"
CODE_RESEAU = "reseau"
CODE_ILLISIBLE = "reponse_illisible"
CODE_CLE_ABSENTE = "cle_absente"


class ErreurCerveau(Exception):
    def __init__(self, code: str, message: str, *, reessayable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.reessayable = reessayable


class Cerveau(Protocol):
    def tour(
        self, *, systeme: str, messages: list[dict[str, Any]], outils: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]: ...


async def _dormir(secondes: float) -> None:
    await asyncio.sleep(secondes)


def _erreur_de_statut(statut: int, corps: bytes, cle: str) -> ErreurCerveau:
    message = ""
    try:
        donnees = json.loads(corps.decode("utf-8", errors="replace"))
        brut = donnees.get("error", donnees) if isinstance(donnees, dict) else {}
        message = (brut.get("message") if isinstance(brut, dict) else str(brut)) or ""
    except (ValueError, AttributeError):
        message = ""
    message = str(message)[:300]
    if cle:
        message = message.replace(cle, "***")
    if statut in (401, 403):
        return ErreurCerveau(CODE_CLE, message or "The brain's key was refused.")
    if statut == 429:
        return ErreurCerveau(CODE_LIMITE, message or "The brain's rate limit is reached.", reessayable=True)
    if statut >= 500 or statut == 529:
        return ErreurCerveau(CODE_INDISPONIBLE, message or "The brain is unavailable.", reessayable=True)
    return ErreurCerveau(CODE_REQUETE, message or f"The brain refused the request ({statut}).")


async def _lignes_sse(reponse: httpx.Response) -> AsyncIterator[tuple[str | None, str]]:
    """(nom de l'événement, données) pour chaque événement SSE."""
    evenement: str | None = None
    donnees: list[str] = []
    async for ligne in reponse.aiter_lines():
        if ligne == "":
            if donnees:
                yield evenement, "\n".join(donnees)
            evenement, donnees = None, []
        elif ligne.startswith("event:"):
            evenement = ligne[6:].strip()
        elif ligne.startswith("data:"):
            donnees.append(ligne[5:].strip())
    if donnees:
        yield evenement, "\n".join(donnees)


def _arguments(brut: str) -> tuple[dict[str, Any], bool]:
    """(arguments, illisible). Des arguments vides valent un objet vide."""
    if not brut.strip():
        return {}, False
    try:
        valeur = json.loads(brut)
    except ValueError:
        return {}, True
    return (valeur, False) if isinstance(valeur, dict) else ({}, True)


class _FilBase:
    def __init__(self, reglages: ReglagesCerveau, cle: str, transport: httpx.AsyncBaseTransport | None = None):
        if not cle:
            raise ErreurCerveau(CODE_CLE_ABSENTE, "No key is set for the builder's brain.")
        self.reglages = reglages
        self._cle = cle
        self._transport = transport
        self.base = (reglages.adresse or ADRESSE_PAR_DEFAUT[reglages.format]).rstrip("/")

    # -- à définir par format ------------------------------------------------------------------------------
    def _requete(self, systeme: str, messages: list[dict], outils: list[dict]) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def _evenements(self, evenement: str | None, donnees: str, etat: dict) -> list[dict[str, Any]]:
        raise NotImplementedError

    # -- commun --------------------------------------------------------------------------------------------
    async def tour(
        self, *, systeme: str, messages: list[dict[str, Any]], outils: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        adresse, en_tetes, corps = self._requete(systeme, messages, outils)
        derniere: ErreurCerveau | None = None
        for tentative in range(TENTATIVES_MAX):
            if tentative:
                await _dormir(min(2.0**tentative, 8.0))
            etat: dict[str, Any] = {}
            servi = False  # un événement déjà rendu : on ne rejoue plus (le moteur aurait des doublons)
            try:
                async with httpx.AsyncClient(timeout=DELAI_REPONSE_S, transport=self._transport) as client:
                    async with client.stream("POST", adresse, headers=en_tetes, json=corps) as reponse:
                        if reponse.status_code >= 400:
                            tout = await reponse.aread()
                            raise _erreur_de_statut(reponse.status_code, tout, self._cle)
                        async for evenement, donnees in _lignes_sse(reponse):
                            for sortie in self._evenements(evenement, donnees, etat):
                                servi = True
                                yield sortie
                        for sortie in self._evenements("__fin_du_flux__", "", etat):
                            servi = True
                            yield sortie
                        return
            except ErreurCerveau as erreur:
                if not erreur.reessayable or servi:
                    raise
                derniere = erreur
            except httpx.TimeoutException:
                derniere = ErreurCerveau(CODE_RESEAU, "The brain did not answer in time.", reessayable=True)
            except httpx.HTTPError:
                derniere = ErreurCerveau(CODE_RESEAU, "The brain could not be reached.", reessayable=True)
            if servi and derniere is not None and derniere.code == CODE_RESEAU:
                raise derniere
        assert derniere is not None
        raise derniere


# --- Anthropic Messages ---------------------------------------------------------------------------------------


class FilAnthropic(_FilBase):
    def _requete(self, systeme, messages, outils):
        blocs_systeme = [{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral"}}]
        description = [
            {"name": o["name"], "description": o["description"], "input_schema": o["parameters"]} for o in outils
        ]
        if description:
            description[-1]["cache_control"] = {"type": "ephemeral"}
        corps = {
            "model": self.reglages.modele,
            "max_tokens": self.reglages.sortie_max,
            "system": blocs_systeme,
            "messages": self._messages(messages),
            "stream": True,
        }
        if description:
            corps["tools"] = description
        en_tetes = {
            "x-api-key": self._cle,
            "anthropic-version": VERSION_ANTHROPIC,
            "content-type": "application/json",
        }
        return f"{self.base}/v1/messages", en_tetes, corps

    @staticmethod
    def _messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sortie: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "user":
                sortie.append({"role": "user", "content": [{"type": "text", "text": m["content"]}]})
            elif m["role"] == "assistant":
                blocs: list[dict[str, Any]] = []
                if m.get("content"):
                    blocs.append({"type": "text", "text": m["content"]})
                for a in m.get("appels") or []:
                    blocs.append({"type": "tool_use", "id": a["id"], "name": a["nom"], "input": a["arguments"]})
                sortie.append({"role": "assistant", "content": blocs})
            else:  # outil
                bloc = {"type": "tool_result", "tool_use_id": m["appel_id"], "content": m["content"]}
                precedent = sortie[-1] if sortie else None
                if (
                    precedent is not None
                    and precedent["role"] == "user"
                    and precedent["content"]
                    and precedent["content"][0].get("type") == "tool_result"
                ):
                    precedent["content"].append(bloc)
                else:
                    sortie.append({"role": "user", "content": [bloc]})
        return sortie

    def _evenements(self, evenement, donnees, etat):
        if evenement == "__fin_du_flux__":
            return []
        try:
            d = json.loads(donnees)
        except ValueError:
            raise ErreurCerveau(CODE_ILLISIBLE, "The brain's stream is unreadable.") from None
        genre = d.get("type")
        sorties: list[dict[str, Any]] = []
        if genre == "message_start":
            etat["demarre"] = True
            u = (d.get("message") or {}).get("usage") or {}
            etat["usage"] = {
                "entree": u.get("input_tokens", 0),
                "sortie": u.get("output_tokens", 0),
                "cache_lu": u.get("cache_read_input_tokens", 0),
                "cache_ecrit": u.get("cache_creation_input_tokens", 0),
            }
        elif genre == "content_block_start":
            bloc = d.get("content_block") or {}
            if bloc.get("type") == "tool_use":
                etat.setdefault("blocs", {})[d.get("index")] = {"id": bloc.get("id"), "nom": bloc.get("name"), "json": ""}
        elif genre == "content_block_delta":
            delta = d.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                sorties.append({"type": "texte", "texte": delta["text"]})
            elif delta.get("type") == "input_json_delta":
                bloc = etat.get("blocs", {}).get(d.get("index"))
                if bloc is not None:
                    bloc["json"] += delta.get("partial_json", "")
        elif genre == "content_block_stop":
            bloc = etat.get("blocs", {}).pop(d.get("index"), None)
            if bloc is not None:
                arguments, illisible = _arguments(bloc["json"])
                appel = {"type": "appel", "id": bloc["id"], "nom": bloc["nom"], "arguments": arguments}
                if illisible:
                    appel["illisible"] = True
                etat["appels"] = etat.get("appels", 0) + 1
                sorties.append(appel)
        elif genre == "message_delta":
            u = d.get("usage") or {}
            if "output_tokens" in u:
                etat.setdefault("usage", {})["sortie"] = u["output_tokens"]
            etat["raison"] = (d.get("delta") or {}).get("stop_reason")
        elif genre == "message_stop":
            sorties.append({"type": "usage", **{"entree": 0, "sortie": 0, "cache_lu": 0, "cache_ecrit": 0}, **etat.get("usage", {})})
            raison = etat.get("raison")
            sorties.append(
                {"type": "fin", "raison": "outils" if raison == "tool_use" else "longueur" if raison == "max_tokens" else "fin"}
            )
        elif genre == "error":
            e = d.get("error") or {}
            surcharge = e.get("type") in ("overloaded_error", "api_error")
            raise ErreurCerveau(
                CODE_INDISPONIBLE if surcharge else CODE_REQUETE,
                str(e.get("message") or "The brain stopped the answer.")[:300],
                reessayable=surcharge,
            )
        return sorties


# --- compatible OpenAI ----------------------------------------------------------------------------------------


class FilOpenAI(_FilBase):
    def _requete(self, systeme, messages, outils):
        corps: dict[str, Any] = {
            "model": self.reglages.modele,
            "messages": self._messages(systeme, messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": self.reglages.sortie_max,
        }
        if outils:
            corps["tools"] = [
                {"type": "function", "function": {"name": o["name"], "description": o["description"], "parameters": o["parameters"]}}
                for o in outils
            ]
        en_tetes = {"authorization": f"Bearer {self._cle}", "content-type": "application/json"}
        return f"{self.base}/chat/completions", en_tetes, corps

    @staticmethod
    def _messages(systeme: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sortie: list[dict[str, Any]] = [{"role": "system", "content": systeme}]
        for m in messages:
            if m["role"] == "user":
                sortie.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                message: dict[str, Any] = {"role": "assistant", "content": m.get("content") or None}
                if m.get("appels"):
                    message["tool_calls"] = [
                        {
                            "id": a["id"],
                            "type": "function",
                            "function": {"name": a["nom"], "arguments": json.dumps(a["arguments"], ensure_ascii=False)},
                        }
                        for a in m["appels"]
                    ]
                sortie.append(message)
            else:
                sortie.append({"role": "tool", "tool_call_id": m["appel_id"], "content": m["content"]})
        return sortie

    def _evenements(self, evenement, donnees, etat):
        sorties: list[dict[str, Any]] = []
        if evenement == "__fin_du_flux__":
            # Le flux est fini sans [DONE] : on clôt proprement ce qui est en cours.
            return self._clore(etat) if not etat.get("clos") else []
        if donnees == "[DONE]":
            return self._clore(etat)
        try:
            d = json.loads(donnees)
        except ValueError:
            raise ErreurCerveau(CODE_ILLISIBLE, "The brain's stream is unreadable.") from None
        if "error" in d:
            e = d["error"] if isinstance(d["error"], dict) else {}
            raise ErreurCerveau(CODE_REQUETE, str(e.get("message") or "The brain stopped the answer.")[:300])
        u = d.get("usage")
        if u:
            detail = u.get("prompt_tokens_details") or {}
            etat["usage"] = {
                "entree": u.get("prompt_tokens", 0),
                "sortie": u.get("completion_tokens", 0),
                "cache_lu": detail.get("cached_tokens", 0),
                "cache_ecrit": 0,
            }
        for choix in d.get("choices") or []:
            delta = choix.get("delta") or {}
            if delta.get("content"):
                sorties.append({"type": "texte", "texte": delta["content"]})
            for fragment in delta.get("tool_calls") or []:
                bloc = etat.setdefault("blocs", {}).setdefault(fragment.get("index", 0), {"id": None, "nom": "", "json": ""})
                if fragment.get("id"):
                    bloc["id"] = fragment["id"]
                fonction = fragment.get("function") or {}
                if fonction.get("name"):
                    bloc["nom"] += fonction["name"]
                bloc["json"] += fonction.get("arguments") or ""
            if choix.get("finish_reason"):
                etat["raison"] = choix["finish_reason"]
        return sorties

    @staticmethod
    def _clore(etat: dict) -> list[dict[str, Any]]:
        etat["clos"] = True
        sorties: list[dict[str, Any]] = []
        for _index, bloc in sorted(etat.get("blocs", {}).items()):
            arguments, illisible = _arguments(bloc["json"])
            appel = {"type": "appel", "id": bloc["id"] or f"appel-{_index}", "nom": bloc["nom"], "arguments": arguments}
            if illisible:
                appel["illisible"] = True
            sorties.append(appel)
        sorties.append({"type": "usage", **{"entree": 0, "sortie": 0, "cache_lu": 0, "cache_ecrit": 0}, **etat.get("usage", {})})
        raison = etat.get("raison")
        sorties.append(
            {"type": "fin", "raison": "outils" if raison == "tool_calls" else "longueur" if raison == "length" else "fin"}
        )
        return sorties


def fabriquer(
    reglages: ReglagesCerveau, cle: str | None, transport: httpx.AsyncBaseTransport | None = None
) -> Cerveau:
    """Le cerveau réel pour ces réglages. ``transport`` sert aux tests (``httpx.MockTransport``)."""
    if not reglages.modele:
        raise ErreurCerveau(CODE_REQUETE, "Choose the builder's model first.")
    classe = FilAnthropic if reglages.format == "anthropic" else FilOpenAI
    return classe(reglages, cle or "", transport)  # type: ignore[return-value]
