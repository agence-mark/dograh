"""[.mark] La réponse avalée par le fournisseur : relancée une fois, sans flux.

Chantier agents-specialises, banc d'architecture du 16/10 (runs 1315 à 1346). Le cerveau
compatible OpenAI (Mistral Small chez Scaleway) rend parfois un flux **vide** : ni texte, ni
appel d'outil, ``finish_reason = stop``, alors que le fournisseur compte des jetons générés
(10, la taille d'un appel d'outil). Le modèle a répondu ; c'est la conversion de sa réponse
en flux qui l'a perdue. Résultat : un agent muet, 23 fois sur un banc, jamais sur un autre
cerveau du même fournisseur.

Ce que fait ce module, et rien d'autre :

- le flux passe tel quel dès qu'un morceau porte du texte ou un appel d'outil ;
- un flux fini sans rien de tout cela, avec des jetons générés comptés par le fournisseur,
  est **relancé une fois sans flux** (même requête, ``stream`` à faux) ; la réponse est
  rendue en morceaux comme si elle avait coulé, pour que la suite (Pipecat, la trace, le
  lecteur de portes) ne voie aucune différence ;
- C2, filet du silence (Evan, 16/10) : un flux sans texte ni appel d'outil n'est jamais une
  réponse ; il est relancé même sans jeton compté ; si la relance est vide aussi (ou en
  erreur) et que l'appelant attend une réponse (le dernier message est le sien), le code dit
  la phrase « la réponse du modèle est perdue » (``phrase_de_repli`` : la règle du thème Phrases,
  fiabilite-orchestration lot 4 bis) plutôt qu'un silence ; règle éteinte, ou l'appelant n'attend
  pas : le flux d'origine est rendu, comme avant.

⛔ Ne lève jamais à la place du service : toute erreur de la relance rend le comportement
d'avant. Un flux qui a déjà porté du texte n'est jamais relancé (rien n'est dit deux fois).
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
from functools import partial
import json
import re
import time
from types import SimpleNamespace
from typing import Any

from loguru import logger

# L'attribut du service où le moteur pose la phrase de repli de son agent (``brancher_les_phrases``).
ATTRIBUT_PHRASE_DE_REPLI = "mark_phrase_de_repli"


def phrase_de_repli_par_defaut() -> str:
    """La phrase « la réponse du modèle est perdue » du catalogue : la seule valeur écrite pour cette phrase, lue quand le réglage de l'agent manque. ⛔ Ne lève jamais à la place du service."""
    from api.services.phrases.catalogue import MOTIFS, REPONSE_PERDUE

    return MOTIFS[REPONSE_PERDUE].variantes_defaut[0]


def phrase_de_repli(service: Any) -> str | None:
    """C2 : la phrase dite quand le cerveau n'a rien rendu, deux fois. Celle que le moteur a posée
    sur ``service`` (la règle « la réponse du modèle est perdue », tracée ; ``None`` : éteinte) ;
    sans moteur (un service seul), le défaut du catalogue. ⛔ Ne lève jamais."""
    try:
        prendre = getattr(service, ATTRIBUT_PHRASE_DE_REPLI, None)
        if callable(prendre):
            return prendre()
        from api.services.phrases.catalogue import MOTIFS, REPONSE_PERDUE

        return MOTIFS[REPONSE_PERDUE].variantes_defaut[0]
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cerveau] phrase de repli illisible : {erreur!r}")
        return None


def dernier_message_est_un_resultat_a_reprendre(messages: Any) -> bool:
    """SA-33 (appel 2557) : le DERNIER message est un résultat d'outil qui propose un texte (``texte_a_dire``, ``suggestion``, au premier niveau ou dans ``data``) ou qui porte une ``consigne`` au modèle :
    la personne attend alors la réponse de l'agent, comme après sa propre réplique, et un flux muet du modèle est relancé. Lot 8d (décision d'Evan 25/11 8 h 45, « le
    modèle parle, jamais le code ») : ce texte n'est plus JAMAIS dit par le code ; il ne sert qu'à savoir que le modèle doit parler (relance, puis phrase réglée). Faux
    pour un texte déjà dit par le code (W17 : le silence du modèle y est la bonne réponse). ⛔ Ne lève jamais."""
    try:
        from api.services.outils_mark.pour_la_voix import CLE_DEJA_DIT, CLE_SUGGESTION, CLE_TEXTE_A_DIRE

        dicts = [m for m in (messages or []) if isinstance(m, dict)]
        if not dicts or dicts[-1].get("role") != "tool":
            return False
        contenu = dicts[-1].get("content")
        resultat = json.loads(contenu) if isinstance(contenu, str) else contenu
        if not isinstance(resultat, dict) or resultat.get(CLE_DEJA_DIT):
            return False
        donnees = resultat.get("data") if isinstance(resultat.get("data"), dict) else {}
        propose = any(isinstance(t, str) and t.strip() for t in (resultat.get(CLE_TEXTE_A_DIRE), resultat.get(CLE_SUGGESTION), donnees.get(CLE_SUGGESTION)))
        # Reprise R2 (8d) : un résultat qui porte une consigne au modèle (échec répété, confirmation trop tôt, plafond) attend aussi sa réponse, sans texte à dire.
        return propose or (isinstance(resultat.get("consigne"), str) and bool(resultat["consigne"].strip()))
    except Exception:  # noqa: BLE001 -- un résultat illisible ne propose rien
        return False


def _delta(morceau: Any) -> Any:
    choix = getattr(morceau, "choices", None) or []
    return getattr(choix[0], "delta", None) if choix else None


def porte_quelque_chose(morceau: Any) -> bool:
    """Le morceau porte-t-il du texte ou un appel d'outil ?"""
    delta = _delta(morceau)
    if delta is None:
        return False
    return bool(getattr(delta, "content", None) or getattr(delta, "tool_calls", None))


def _porte_du_texte(morceau: Any) -> bool:
    """Le morceau porte-t-il du texte (ce qui part vers la voix) ?"""
    delta = _delta(morceau)
    return bool(delta is not None and getattr(delta, "content", None))


def jetons_generes(morceau: Any) -> int:
    usage = getattr(morceau, "usage", None)
    try:
        return int(getattr(usage, "completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


def additionner(usage_a: Any, usage_b: Any) -> Any:
    """Les deux comptes de jetons additionnés (le flux vide a coûté aussi)."""
    if usage_a is None:
        return usage_b
    if usage_b is None:
        return usage_a
    from openai.types.completion_usage import CompletionUsage

    def n(u, cle):
        return int(getattr(u, cle, 0) or 0)

    return CompletionUsage(
        prompt_tokens=n(usage_a, "prompt_tokens") + n(usage_b, "prompt_tokens"),
        completion_tokens=n(usage_a, "completion_tokens") + n(usage_b, "completion_tokens"),
        total_tokens=n(usage_a, "total_tokens") + n(usage_b, "total_tokens"),
    )


def en_morceaux(reponse: Any, usage_d_avant: Any = None) -> list[Any]:
    """Une réponse sans flux, rendue comme les morceaux d'un flux (texte, appels d'outil,
    fin, compte de jetons)."""
    from openai.types.chat.chat_completion_chunk import (
        ChatCompletionChunk,
        Choice,
        ChoiceDelta,
        ChoiceDeltaToolCall,
        ChoiceDeltaToolCallFunction,
    )

    choix = (getattr(reponse, "choices", None) or [None])[0]
    message = getattr(choix, "message", None)
    contenu = getattr(message, "content", None) or None
    appels = [
        ChoiceDeltaToolCall(
            index=i,
            id=getattr(appel, "id", None),
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name=getattr(appel.function, "name", None),
                arguments=getattr(appel.function, "arguments", None) or "{}",
            ),
        )
        for i, appel in enumerate(getattr(message, "tool_calls", None) or [])
    ]
    commun = {
        "id": getattr(reponse, "id", None) or "reprise",
        "created": int(getattr(reponse, "created", None) or time.time()),
        "model": getattr(reponse, "model", None) or "",
        "object": "chat.completion.chunk",
    }
    # Revue du 16/10 : Pipecat lit dans un morceau « appel d'outil, sinon texte », et seulement
    # le premier appel : un morceau pour le texte, puis un morceau par appel d'outil.
    morceaux = []
    if contenu:
        morceaux.append(
            ChatCompletionChunk(
                **commun,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(role="assistant", content=contenu),
                        finish_reason=None,
                    )
                ],
            )
        )
    for appel in appels:
        morceaux.append(
            ChatCompletionChunk(
                **commun,
                choices=[
                    Choice(index=0, delta=ChoiceDelta(tool_calls=[appel]), finish_reason=None)
                ],
            )
        )
    morceaux.append(
        ChatCompletionChunk(
            **commun,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(),
                    finish_reason=getattr(choix, "finish_reason", None) or "stop",
                )
            ],
        )
    )
    usage = additionner(usage_d_avant, getattr(reponse, "usage", None))
    if usage is not None:
        morceaux.append(ChatCompletionChunk(**commun, choices=[], usage=usage))
    return morceaux


def morceaux_de_texte(texte: str) -> list[Any]:
    """Un texte dit comme une réponse du cerveau (un morceau de texte, puis la fin)."""
    from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta

    commun = {"id": "repli", "created": int(time.time()), "model": "", "object": "chat.completion.chunk"}
    return [
        ChatCompletionChunk(
            **commun,
            choices=[Choice(index=0, delta=ChoiceDelta(role="assistant", content=texte), finish_reason=None)],
        ),
        ChatCompletionChunk(
            **commun, choices=[Choice(index=0, delta=ChoiceDelta(), finish_reason="stop")]
        ),
    ]


class FluxEnErreur:
    """Un flux qui lève, à sa première lecture, l'erreur de la requête refusée à son ouverture."""

    def __init__(self, erreur: Exception):
        self._erreur = erreur

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        raise self._erreur
        yield  # pragma: no cover -- fait de cette méthode un générateur

    async def close(self):
        return None


class FluxRepris:
    """Le flux du cerveau, relancé une fois sans flux s'il finit vide alors que des jetons
    ont été générés."""

    def __init__(self, flux: Any, relancer, l_appelant_attend=None, repli=None):
        self._flux = flux
        self._relancer = relancer
        self._l_appelant_attend = l_appelant_attend
        # Le texte de la phrase de repli, pris au moment où il faut la dire (``None`` : éteinte).
        self._repli = repli

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        tenus: list[Any] = []
        quelque_chose = False
        jetons = 0
        usage_d_avant = None
        # Lot 1 (K1) : une erreur du flux AVANT le premier morceau utile (le fournisseur coupe le flux
        # sur une réponse qu'il a pourtant générée) est traitée comme un flux vide : même relance sans
        # flux. Une erreur après un morceau utile remonte comme avant (rien n'est dit deux fois).
        # actions-sures-et-parite-clavier, lot D (run 2054) : seul un TEXTE est « déjà dit ». Un appel d'outil ne
        # s'exécute qu'à la fin de la réponse : ses morceaux sont gardés jusqu'à la fin du flux (aucune latence) ; un
        # flux qui casse après un début d'appel, avant toute parole, suit la relance puis la phrase de repli.
        appel_tenu = False
        erreur_du_flux = None
        try:
            async for morceau in self._flux:
                if quelque_chose:
                    yield morceau
                    continue
                jetons = max(jetons, jetons_generes(morceau))
                if getattr(morceau, "usage", None) is not None:
                    usage_d_avant = morceau.usage
                if _porte_du_texte(morceau):
                    quelque_chose = True
                    for tenu in tenus:
                        yield tenu
                    tenus = []
                    yield morceau
                else:
                    appel_tenu = appel_tenu or porte_quelque_chose(morceau)
                    tenus.append(morceau)
        except Exception as erreur:  # noqa: BLE001
            if quelque_chose:
                raise
            erreur_du_flux = erreur
            logger.warning(f"[cerveau] flux en erreur avant toute parole : {erreur!r}")
        if quelque_chose:
            return
        if appel_tenu and erreur_du_flux is None:
            for tenu in tenus:
                yield tenu
            return
        if erreur_du_flux is None and jetons <= 0 and not self._attend():
            for tenu in tenus:
                yield tenu
            return
        reprise = None
        try:
            reprise = await self._relancer()
        except Exception as erreur:  # noqa: BLE001 -- jamais à la place du service
            logger.warning(f"[cerveau] relance sans flux en échec : {erreur!r}")
        if reprise is not None:
            morceaux = en_morceaux(reprise, usage_d_avant)
            if any(porte_quelque_chose(m) for m in morceaux):
                logger.warning(
                    f"[cerveau] flux vide ({jetons} jetons comptés) : réponse rendue par la "
                    "relance sans flux"
                )
                for morceau in morceaux:
                    yield morceau
                return
        texte = self._repli() if self._attend() and self._repli is not None else None
        if texte:
            logger.warning(
                f"[cerveau] flux vide ({jetons} jetons comptés), relance vide : phrase de repli"
            )
            for morceau in morceaux_de_texte(texte):
                yield morceau
            return
        if erreur_du_flux is not None:
            # La relance n'a rien rendu non plus : l'erreur d'origine remonte, comme avant.
            raise erreur_du_flux
        logger.warning(f"[cerveau] flux vide ({jetons} jetons comptés), relance vide")
        for tenu in tenus:
            yield tenu

    def _attend(self) -> bool:
        try:
            return bool(self._l_appelant_attend is not None and self._l_appelant_attend())
        except Exception:  # noqa: BLE001
            return False

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


# --- Lot 1 (K1) : l'outil de passation aux arguments illisibles est exécuté comme ``{}`` ------------

# L'attribut du service où le moteur range les noms de ses outils de passation.
ATTRIBUT_NOMS_DE_PASSATION = "mark_noms_de_passation"


def noter_un_outil_de_passation(service: Any, nom: str) -> None:
    """Le moteur dit au cerveau que ``nom`` est un outil de passation. ⛔ Ne lève jamais."""
    try:
        if service is None or not nom:
            return
        noms = getattr(service, ATTRIBUT_NOMS_DE_PASSATION, None)
        if not isinstance(noms, set):
            noms = set()
            setattr(service, ATTRIBUT_NOMS_DE_PASSATION, noms)
        noms.add(nom)
    except Exception:  # noqa: BLE001
        pass


# P5 (lot 19 bis) : la fiche d'un connecteur aux arguments illisibles n'est pas exécutée comme ``{}`` (une fiche vide ne dit rien) : elle arrive marquée, la porte la refuse
# (``arguments_illisibles``, un refus de LA FICHE) et le modèle repasse ; au bout des passes, le code relance le modèle avec le fait (C5), puis dit la suite réglée déjà posée ou la phrase réglée (P3). Jamais un tour muet.
ATTRIBUT_NOMS_DES_FICHES = "mark_noms_des_fiches"
ARGUMENTS_D_UNE_FICHE_ILLISIBLE = '{"arguments_illisibles": true}'


def noter_un_outil_de_fiche(service: Any, nom: str) -> None:
    """Le moteur dit au cerveau que ``nom`` est l'outil de fiche d'un connecteur. ⛔ Ne lève jamais."""
    try:
        if service is None or not nom:
            return
        noms = getattr(service, ATTRIBUT_NOMS_DES_FICHES, None)
        if not isinstance(noms, set):
            noms = set()
            setattr(service, ATTRIBUT_NOMS_DES_FICHES, noms)
        noms.add(nom)
    except Exception:  # noqa: BLE001
        pass


def _appel_du_morceau(morceau: Any) -> Any:
    delta = _delta(morceau)
    appels = getattr(delta, "tool_calls", None) if delta is not None else None
    return appels[0] if appels else None


def _est_lisible(arguments: str) -> bool:
    import json

    try:
        return isinstance(json.loads(arguments or "{}"), dict)
    except (TypeError, ValueError):
        return False


# --- Chantier Partie 1, lot 6 : aucune balise dite (appel 4 du chantier : « <thought > » sorti dans la phrase dite) ------------------------------

LONGUEUR_MAX_D_UNE_BALISE = 40  # la borne de ``barriere_des_chiffres.sans_balisage`` (B10 point 4) : au-delà, « < » n'ouvrait pas une balise


class SansBalise:
    """Le texte du modèle sans balise (« <thought> », « </b> ») : rien de ce qui n'est pas une phrase ne sort (B10 point 4, la règle que
    ``sans_balisage`` applique déjà aux textes du code et à ``a_dire``). Filtre de flux : un « < » retient le texte qui suit jusqu'à « > » (la
    balise est retirée) ou jusqu'à ``LONGUEUR_MAX_D_UNE_BALISE`` caractères (rendu tel quel : ce n'était pas une balise) ; les morceaux qui
    portent une balise ouverte sont tenus jusqu'à ce qu'elle se ferme, l'ordre est gardé, les appels d'outil passent intacts. Seule la balise est
    retirée, jamais le texte qui l'entoure. ⛔ Ne lève jamais à la place du service : une erreur rend le flux tel quel."""

    def __init__(self, flux: Any):
        self._flux = flux

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        ouverte = ""  # la balise en cours de lecture (« <thou… »), vide hors d'une balise
        tenus: list[Any] = []  # les morceaux qui portent la balise ouverte
        async for morceau in self._flux:
            delta = _delta(morceau)
            texte = getattr(delta, "content", None) if delta is not None else None
            if not isinstance(texte, str) or not texte:
                if ouverte:
                    tenus.append(morceau)
                else:
                    yield morceau
                continue
            rendu = []
            for c in texte:
                if ouverte:
                    ouverte += c
                    if c == ">":
                        ouverte = ""  # une balise entière : retirée
                    elif len(ouverte) > LONGUEUR_MAX_D_UNE_BALISE + 1:
                        rendu.append(ouverte)
                        ouverte = ""
                elif c == "<":
                    ouverte = "<"
                else:
                    rendu.append(c)
            try:
                delta.content = "".join(rendu)
            except Exception:  # noqa: BLE001 -- un morceau en lecture seule : rendu tel quel
                pass
            tenus.append(morceau)
            if not ouverte:
                for tenu in tenus:
                    yield tenu
                tenus = []
        if tenus:
            if ouverte:
                # le flux finit sur un « < » jamais refermé : ce n'était pas une balise, il est rendu
                dernier = next((m for m in reversed(tenus) if isinstance(getattr(_delta(m), "content", None), str)), None)
                if dernier is not None:
                    try:
                        _delta(dernier).content += ouverte
                    except Exception:  # noqa: BLE001
                        pass
            for tenu in tenus:
                yield tenu

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


class SansPhraseAvecLaPassation:
    """[.mark] Lot 20 (relecture, D-C : n7, H1, H4) : une réponse qui appelle un outil de passation ne dit rien d'elle-même : l'agent qui reçoit parle
    (« sans un mot de plus »). Avant, l'agent principal disait « Une reine à emporter, c'est noté. Puis-je faire autre chose ? » en passant la main, puis
    l'agent commande répondait : deux réponses de suite. Sur un agent qui a un outil de passation seulement, la réponse est tenue jusqu'à sa fin (même coût
    que sur les agents qui portent une action) ; sans passation appelée, les morceaux repartent tels quels, dans leur ordre. Critère sur la forme de la
    réponse (le nom de l'outil appelé), jamais sur les mots. ⛔ Ne lève jamais à la place du service."""

    def __init__(self, flux: Any, noms):
        self._flux = flux
        self._noms = noms

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        try:
            noms = set(self._noms() if callable(self._noms) else (self._noms or ()))
        except Exception:  # noqa: BLE001
            noms = set()
        if not noms:
            async for morceau in self._flux:
                yield morceau
            return
        tenus: list[Any] = []
        appeles: set[str] = set()
        async for morceau in self._flux:
            tenus.append(morceau)
            delta = _delta(morceau)
            for appel in (getattr(delta, "tool_calls", None) or []) if delta is not None else []:
                nom = getattr(getattr(appel, "function", None), "name", None)
                if nom:
                    appeles.add(nom)
        if not (appeles & noms):
            for morceau in tenus:
                yield morceau
            return
        for morceau in tenus:
            delta = _delta(morceau)
            if delta is not None and getattr(delta, "content", None) and not getattr(delta, "tool_calls", None):
                continue  # le texte dit avec la passation : jamais dit
            yield morceau


class ArgumentsLisibles:
    """Pipecat jette un appel d'outil dont les arguments ne se lisent pas (``services/openai/base_llm.py``,
    « Failed to parse function call arguments »). Pour un OUTIL DE PASSATION, l'appelant a bien demandé la
    passation : l'appel est exécuté avec ``{}``.

    Dès le premier morceau d'appel d'outil, la suite du flux est tenue jusqu'à la fin (Pipecat n'agit
    qu'à la fin de toute façon) ; le texte d'avant passe sans attente. Si aucun appel de passation n'est
    illisible, les morceaux repartent tels quels, dans leur ordre. Un morceau qui porte plusieurs appels à la fois (que Pipecat
    ne lit pas) désactive la correction : le flux passe sans changement. Sans outil de passation connu,
    le flux passe tel quel."""

    def __init__(self, flux: Any, noms, fiches=None):
        self._flux = flux
        self._noms = noms
        self._fiches = fiches  # P5 : les noms des outils de fiche d'un connecteur (arguments illisibles = fiche marquée, refusée par la porte)

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        noms = set(self._noms() if callable(self._noms) else (self._noms or ()))
        fiches = set(self._fiches() if callable(self._fiches) else (self._fiches or ()))
        if not noms and not fiches:
            async for morceau in self._flux:
                yield morceau
            return
        tenus: list[Any] = []
        passer_tel_quel = False
        async for morceau in self._flux:
            delta = _delta(morceau)
            appels = getattr(delta, "tool_calls", None) if delta is not None else None
            if passer_tel_quel or (not appels and not tenus):
                yield morceau
                continue
            if not appels:
                tenus.append(morceau)
                continue
            if len(appels) > 1:
                passer_tel_quel = True
                for tenu in tenus:
                    yield tenu
                tenus = []
                yield morceau
                continue
            tenus.append(morceau)
        if not tenus:
            return
        try:
            tenus = self._corriger(tenus, noms, fiches)
        except Exception as erreur:  # noqa: BLE001 -- jamais à la place du flux
            logger.warning(f"[cerveau] arguments d'appel non corrigés : {erreur!r}")
        for tenu in tenus:
            yield tenu

    @staticmethod
    def _corriger(tenus: list[Any], noms: set, fiches: set = frozenset()) -> list[Any]:
        par_index: dict[int, dict] = {}
        for morceau in tenus:
            appel = _appel_du_morceau(morceau)
            if appel is None:
                continue
            index = getattr(appel, "index", 0) or 0
            entree = par_index.setdefault(index, {"nom": "", "arguments": ""})
            fonction = getattr(appel, "function", None)
            if fonction is not None:
                entree["nom"] += getattr(fonction, "name", None) or ""
                entree["arguments"] += getattr(fonction, "arguments", None) or ""
        a_vider = {
            i
            for i, e in par_index.items()
            if (e["nom"] in noms or e["nom"] in fiches) and e["arguments"].strip() and not _est_lisible(e["arguments"])
        }
        marques = {i for i in a_vider if par_index[i]["nom"] in fiches and par_index[i]["nom"] not in noms}
        if not a_vider:
            return tenus
        logger.warning(
            "[cerveau] arguments d'appel illisibles pour un outil de passation : exécuté comme {}"
        )
        vus: set[int] = set()
        corriges = []
        for morceau in tenus:
            appel = _appel_du_morceau(morceau)
            index = getattr(appel, "index", 0) or 0
            if appel is None or index not in a_vider:
                corriges.append(morceau)
                continue
            copie = morceau.model_copy(deep=True)
            fonction = _appel_du_morceau(copie).function
            if fonction is not None:
                fonction.arguments = (ARGUMENTS_D_UNE_FICHE_ILLISIBLE if index in marques else "{}") if index not in vus else ""
            vus.add(index)
            corriges.append(copie)
        return corriges

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


# --- Lot 5 (K7) : la réplique qui dit une date ou une action sans outil est retenue, relancée UNE fois ----------

# L'attribut du service où le moteur pose le contrôle des répliques de l'étape (``None`` : éteint).
ATTRIBUT_VERITE = "mark_verite_des_actions"
# Lot 6 (K8) : l'attribut du service où le moteur pose le déclencheur de l'outil d'action de l'étape (``None`` : libre).
ATTRIBUT_DECLENCHEUR = "mark_declencheur"


def phrase_de_repli_reglee(service: Any) -> str:
    """Lot 7b, ligne 29 : la phrase réglée de l'agent (le diseur de phrases, posée sur ``service`` par ``garde_modele.poser_la_reponse_perdue``) ; la valeur du catalogue seulement quand
    le réglage manque, avec une ligne au journal. ⛔ Ne lève jamais."""
    phrase = phrase_de_repli(service)
    if phrase:
        return phrase
    logger.warning("[cerveau] phrase de repli réglée absente : la phrase du catalogue est dite")
    return phrase_de_repli_par_defaut()


class RepliqueVerifiee:
    """Le flux du cerveau, tenu jusqu'à sa fin quand l'étape offre un outil d'action (case « vérité des actions »).

    - un flux qui porte un appel d'outil passe tel quel, dans son ordre ;
    - une réplique de texte seul est contrôlée (``controler(texte)`` rend ``None`` ou une retenue) ; sans retenue,
      elle passe telle quelle ;
    - retenue : le modèle est relancé UNE fois, sans flux, avec la consigne de la retenue (``relancer(retenue)``) ; une relance retenue à son tour avec le fait à redonner
      est relancée au plus UNE fois encore (la relance du fait). Sinon, ou sans réponse : le texte que porte la retenue, la suite réglée déjà posée ou la phrase réglée de l'agent (P3) ;
      jamais la réplique retenue, jamais un tour muet (une retenue sans consigne ni appel exigé n'a pas de requête de plus : elle va droit à la phrase du code).
    - SA-36 (M87) : une retenue qui porte un texte à dire à la place (``a_dire``) est remplacée par lui, sans relance ; une relance
      qui affirme comme fait ce qu'aucun outil du tour n'a fait (``controler_la_relance``) est remplacée de même.

    Coût : la réplique part à la fin de la génération, non au premier morceau (étapes qui offrent une action
    seulement). ⛔ Ne lève jamais à la place du service."""

    def __init__(self, flux: Any, controler, relancer, controler_avant_outil=None, controler_la_relance=None, controler_le_silence=None, phrase_reglee=None):
        self._flux = flux
        # Lot 7b (ligne 29) : la phrase réglée de l'agent, dite quand rien d'autre ne remplace la réplique retenue (``None`` : la phrase du catalogue, avec une ligne au journal).
        self._phrase_reglee = phrase_reglee
        # Point de contrôle du lot 7 : un flux fini sans texte ni appel (relance comprise) ; ``None`` : rendu tel quel, comme avant.
        self._silence = controler_le_silence
        self._controler = controler
        self._relancer = relancer
        # Lot 24 : le texte dit avant un appel d'outil (``None`` : jamais contrôlé, comme avant).
        self._avant_outil = controler_avant_outil
        # SA-36 (M87) : la relance, contrôlée sur un seul point (une retenue qui a un texte à dire à la place). ``None`` : rendue telle quelle.
        self._controler_la_relance = controler_la_relance

    @staticmethod
    def _a_dire(texte: str, usage: Any) -> list[Any]:
        """SA-36 (M87) : le texte dit à la place de la réplique retenue, en morceaux de flux (compte de jetons gardé)."""
        message = SimpleNamespace(content=texte, tool_calls=None)
        return en_morceaux(SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")]), usage)

    @staticmethod
    def _relance_appelle(reprise: Any, outil: str) -> bool:
        """SA-49 : la réponse de la relance appelle-t-elle ``outil`` ? ⛔ Ne lève jamais (``False`` dans le doute)."""
        try:
            choix = (getattr(reprise, "choices", None) or [None])[0]
            appels = getattr(getattr(choix, "message", None), "tool_calls", None) or []
            return any(getattr(getattr(a, "function", None), "name", None) == outil for a in appels)
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _appel_du_code(outil: str, usage: Any) -> list[Any]:
        """SA-49 : l'appel de ``outil`` sans arguments, en morceaux de flux, comme si le modèle l'avait fait (Pipecat l'exécute)."""
        import uuid

        appel = SimpleNamespace(id=f"mark-{uuid.uuid4().hex[:16]}", function=SimpleNamespace(name=outil, arguments="{}"))
        message = SimpleNamespace(content=None, tool_calls=[appel])
        return en_morceaux(SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")]), usage)

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        tenus: list[Any] = []
        texte: list[str] = []
        appel = False
        usage = None
        async for morceau in self._flux:
            tenus.append(morceau)
            if getattr(morceau, "usage", None) is not None:
                usage = morceau.usage
            delta = _delta(morceau)
            if delta is not None:
                if getattr(delta, "tool_calls", None):
                    appel = True
                if getattr(delta, "content", None):
                    texte.append(delta.content)
        retenue = None
        if not appel and not texte and self._silence is not None:
            try:
                retenue = self._silence()
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[cerveau] silence non contrôlé : {erreur!r}")
        elif not appel and texte:
            try:
                retenue = self._controler("".join(texte))
                if inspect.isawaitable(retenue):
                    retenue = await retenue
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[cerveau] réplique non contrôlée : {erreur!r}")
        elif appel and texte and self._avant_outil is not None:
            try:
                retenue = self._avant_outil("".join(texte))
                if inspect.isawaitable(retenue):
                    retenue = await retenue
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[cerveau] texte avant l'outil non contrôlé : {erreur!r}")
        async for morceau in self._relancer_sans_lever(retenue, appel, tenus, usage):
            yield morceau

    async def _relancer_sans_lever(self, retenue, appel, tenus, usage, du_fait=False):
        """Ce que rend la réplique quand elle est retenue : relancée UNE fois, et si cette relance est retenue à son tour avec une consigne (le fait, C5), relancée UNE fois encore (``du_fait``, la
        même méthode, appelée par elle-même : une seule façon de relancer, un seul ``except`` qui ne laisse jamais une erreur sortir à la place du service). Chemin direct, sans requête : une retenue
        qui porte son texte, ou n'a ni consigne ni outil (``_rien_a_relancer``, dont la retenue vide du silence en erreur sur la fiche, T1) va à ``_dire_sans_relancer``. ⛔ Ne lève jamais."""
        if retenue is not None:
            if self._rien_a_relancer(retenue):
                async for morceau in self._dire_sans_relancer(retenue, appel, tenus, usage):
                    yield morceau
                return
            reprise = None
            try:
                reprise = await self._relancer(retenue)
            except Exception as erreur:  # noqa: BLE001 -- jamais à la place du service
                logger.warning(f"[cerveau] relance de la réplique retenue en échec : {erreur!r}")
            outil_du_code = getattr(retenue, "outil", None) if getattr(retenue, "appel_par_le_code", False) else None
            if outil_du_code and not self._relance_appelle(reprise, outil_du_code):
                # SA-49 (M115, appel 2599) : la relance avec l'appel obligatoire a encore rendu du texte (le fournisseur ne tient pas
                # ``tool_choice``) : le code fait l'appel annoncé, jamais l'annonce fausse.
                logger.warning(f"[cerveau] réplique retenue ({getattr(retenue, 'raison', '?')}) : l'appel de {outil_du_code} est fait par le code")
                for morceau in self._appel_du_code(outil_du_code, additionner(usage, getattr(reprise, "usage", None))):
                    yield morceau
                return
            async for morceau in self._rendre_la_relance(retenue, reprise, appel, tenus, usage, du_fait):
                yield morceau
            return
        for tenu in tenus:
            yield tenu

    @staticmethod
    def _rien_a_relancer(retenue) -> bool:
        """La retenue porte son texte à dire (SA-36), ou n'a ni consigne ni appel exigé (un second silence du tour, C5) : aucune requête de plus."""
        a_dire = getattr(retenue, "a_dire", None)
        return bool(isinstance(a_dire, str) and a_dire.strip()) or not (getattr(retenue, "consigne", None) or getattr(retenue, "outil", None))

    async def _dire_sans_relancer(self, retenue, appel, tenus, usage):
        """Le texte de la retenue, dit sans relance (SA-36 : la question du dernier outil) ; sans texte, la phrase du code : la suite réglée ou la phrase réglée (P3), jamais un tour muet."""
        a_dire = getattr(retenue, "a_dire", None)
        if isinstance(a_dire, str) and a_dire.strip():
            logger.warning(f"[cerveau] réplique retenue ({getattr(retenue, 'raison', '?')}) : remplacée par le texte de l'outil")
            for morceau in self._a_dire(a_dire.strip(), usage):
                yield morceau
            return
        async for morceau in self._sans_reponse_de_la_relance(retenue, appel, tenus, usage):
            yield morceau

    async def _rendre_la_relance(self, retenue, reprise, appel, tenus, usage, du_fait):
        """La réponse de la relance, dite telle quelle ; retenue à son tour avec le fait à redonner, la méthode de relance est rappelée UNE fois (``du_fait``) ; sans réponse : la suite réglée ou la phrase réglée (P3)."""
        if reprise is not None:
            morceaux, encore = await self._morceaux_de_la_relance(reprise, usage, du_fait)
            if encore is not None:
                async for morceau in self._relancer_sans_lever(encore, appel, tenus, usage, du_fait=True):
                    yield morceau
                return
            if any(porte_quelque_chose(m) for m in morceaux):
                logger.warning(
                    f"[cerveau] réplique retenue ({getattr(retenue, 'raison', '?')}) : réponse rendue par la relance"
                )
                for morceau in morceaux:
                    yield morceau
                return
        async for morceau in self._sans_reponse_de_la_relance(retenue, appel, tenus, usage):
            yield morceau

    async def _sans_reponse_de_la_relance(self, retenue, appel, tenus, usage):
        """La relance a échoué ou n'a rien rendu : la réplique retenue n'est jamais dite telle quelle (la suite réglée ou la phrase réglée la remplace)."""
        # D26 (note de Pierre du 20/11, point 4) : la relance a échoué (429, délai) ou n'a rien rendu : la réplique retenue n'est JAMAIS dite
        # telle quelle ; la suite réglée déjà posée, sinon la phrase réglée de l'agent la remplace (jamais un refus, une question ni un fait accompli composés par le code ; R1 de C6)
        logger.warning(f"[cerveau] réplique retenue ({getattr(retenue, 'raison', '?')}) : relance sans réponse, phrase du code")
        if appel:
            # le texte retenu précédait un appel d'outil : l'appel part, le texte jamais (l'outil rend ce qui se dit)
            for tenu in tenus:
                if getattr(_delta(tenu), "tool_calls", None) or getattr(tenu, "usage", None) is not None:
                    yield tenu
            return
        for morceau in self._a_dire(self._phrase_du_code(), usage):
            yield morceau

    def _retenue_de_la_relance(self, morceaux: list[Any]) -> Any:
        """SA-36 (M87) : la réponse de la relance, contrôlée sur un seul point (une retenue qui a un texte à dire à la place, ou une consigne). ``None`` : rendue telle quelle."""
        if self._controler_la_relance is None or not any(porte_quelque_chose(m) for m in morceaux):
            return None
        texte_repris = "".join(getattr(_delta(m), "content", None) or "" for m in morceaux if _delta(m) is not None)
        appel_repris = any(getattr(_delta(m), "tool_calls", None) for m in morceaux if _delta(m) is not None)
        if not texte_repris or appel_repris:
            return None
        return self._controler_la_relance(texte_repris)  # ``controler_la_relance`` ne lève jamais (contrat du contrôle de la fiche)

    async def _morceaux_de_la_relance(self, reprise: Any, usage: Any, du_fait: bool = False) -> tuple[list[Any], Any]:
        """La réponse de la relance, rendue telle quelle ; retenue à son tour (D26), elle n'est jamais dite : le texte que la retenue porte, sinon (C5, décision d'Evan 25/11 8 h 45) la retenue
        elle-même, à relancer UNE fois avec le fait (``du_fait`` : déjà fait, plus de relance), sinon la phrase du code (la suite réglée, ou la phrase réglée de l'agent). Rend ``(morceaux, retenue à relancer)``."""
        morceaux = en_morceaux(reprise, usage)
        seconde = self._retenue_de_la_relance(morceaux)
        if seconde is None:
            return morceaux, None
        usage_d_ici = additionner(usage, getattr(reprise, "usage", None))
        a_dire = getattr(seconde, "a_dire", None)
        if isinstance(a_dire, str) and a_dire.strip():
            logger.warning(f"[cerveau] relance retenue ({getattr(seconde, 'raison', '?')}) : remplacée par le texte du code")
            return self._a_dire(a_dire.strip(), usage_d_ici), None
        if not du_fait and getattr(seconde, "consigne", None):
            return morceaux, seconde
        logger.warning(f"[cerveau] relance retenue ({getattr(seconde, 'raison', '?')}) : remplacée par la phrase du code")
        return self._a_dire(self._phrase_du_code(), usage_d_ici), None

    def _phrase_du_code(self) -> str:
        """Ce que dit le code quand une réplique retenue n'a pas de remplaçant et que la relance a échoué (C5, décision d'Evan 25/11 8 h 45) : la suite réglée déjà posée
        (motifs de ``PHRASES_DU_CODE``, reprise R1 de C6), sinon la phrase réglée « pas compris » de l'agent (P3). Jamais le refus, la question ni le fait accompli composés par le code."""
        if self._silence is not None:
            try:
                repli = getattr(self._silence(sans_relance=True), "a_dire", None)
                if isinstance(repli, str) and repli.strip():
                    return repli.strip()
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[cerveau] repli non lu : {erreur!r}")
        if self._phrase_reglee is not None:
            return self._phrase_reglee()
        logger.warning("[cerveau] phrase de repli réglée absente : la phrase du catalogue est dite")
        return phrase_de_repli_par_defaut()

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


# --- SA-38 (M89, appel 2574) : la réplique du modèle ne redit pas ce que le code vient de dire ------------------------------


def phrases_dites_par_le_code(service: Any, messages: Any) -> set[str]:
    """Les empreintes des phrases que le code a dites dans le tour en cours de la personne : le registre du moteur (posé sur le service,
    ``pour_la_voix.noter_dit_par_le_code``), et, dans les messages depuis la dernière réplique de la personne, chaque réplique de l'agent
    (au clavier, le texte du code y entre aussitôt ; M111 : celle que le modèle a dite avant un appel d'outil compte aussi). ⛔ Ne lève jamais."""
    try:
        from api.services.outils_mark.pour_la_voix import (
            ATTRIBUT_LECTEUR_DU_SERVICE,
            empreinte_de_phrase,
            phrases_de,
        )

        textes: list[str] = []
        lire = getattr(service, ATTRIBUT_LECTEUR_DU_SERVICE, None)
        if callable(lire):
            textes += [t for t in (lire() or []) if isinstance(t, str)]
        dicts = [m for m in (messages or []) if isinstance(m, dict)]
        debut = max((i for i, m in enumerate(dicts) if m.get("role") == "user"), default=-1) + 1
        for message in dicts[debut:]:
            role, contenu = message.get("role"), message.get("content")
            if role == "assistant" and isinstance(contenu, str) and contenu.strip():
                # M111 (appel 2594) : une réplique de l'agent déjà dite dans ce tour (avant un appel d'outil) ne se redit pas non plus
                # après le résultat ; avant, seule la réplique qui suivait un texte « déjà dit par le code » comptait.
                textes.append(contenu)
        empreintes = {empreinte_de_phrase(p) for t in textes for p in phrases_de(t)}
        empreintes.discard("")
        return empreintes
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[cerveau] phrases du code non lues : {erreur!r}")
        return set()


# Une fin de phrase sûre au fil du flux : la ponctuation suivie d'un blanc (en fin de morceau, la phrase peut encore continuer).
_FIN_SURE = re.compile(r"[.!?…][\"'»\)]?\s+")


class SansRediteDuCode:
    """Le flux du cerveau, dont la réplique qui RECOMMENCE par une ou plusieurs phrases déjà dites par le code dans ce tour en est
    retirée (le reste passe : « Votre commande est enregistrée … Puis-je faire autre chose ? » rend « Puis-je faire autre chose ? »).

    Seul le début de la réplique est tenu, le temps de savoir : dès qu'une phrase ne fait pas partie de ce que le code a dit, tout repart
    tel quel. Sans phrase du code dans ce tour, le flux passe octet pour octet. Un appel d'outil arrivé avant tout texte passe aussitôt.
    Réplique entièrement redite : l'agent se tait (le code vient de parler). ⛔ Ne lève jamais à la place du service."""

    def __init__(self, flux: Any, phrases: set[str]):
        self._flux = flux
        self._phrases = phrases

    def __aiter__(self):
        return self._parcourir()

    def _retirer(self, texte: str, fin: bool) -> tuple[str, bool, int]:
        """(texte restant, décidé, phrases retirées)."""
        from api.services.outils_mark.pour_la_voix import empreinte_de_phrase

        retirees = 0
        while True:
            debut = len(texte) - len(texte.lstrip())
            coupe = _FIN_SURE.search(texte, debut)
            if coupe is None:
                reste = texte.strip()
                empreinte = empreinte_de_phrase(reste)
                if fin:
                    if empreinte and empreinte in self._phrases:
                        return "", True, retirees + 1
                    return texte, True, retirees
                if not empreinte or any(p.startswith(empreinte) for p in self._phrases):
                    return texte, False, retirees  # encore possible : on attend la suite
                return texte, True, retirees
            phrase = texte[debut : coupe.end()]
            if empreinte_de_phrase(phrase) not in self._phrases:
                return texte, True, retirees
            texte = texte[coupe.end() :]
            retirees += 1

    async def _parcourir(self):
        if not self._phrases:
            async for morceau in self._flux:
                yield morceau
            return
        modele = None  # le premier morceau de texte, pour rendre le reste sous sa forme
        texte = ""
        tenus: list[Any] = []  # les morceaux sans texte arrivés après le premier texte
        originaux: list[Any] = []  # tout ce qui est tenu, dans l'ordre : rendu tel quel si rien n'est retiré
        retirees = 0
        decide = False

        def rendre(reste: str) -> list[Any]:
            if not retirees:
                return originaux
            sortie = []
            if reste and modele is not None:
                copie = modele.model_copy(deep=True)
                copie.choices[0].delta.content = reste
                sortie.append(copie)
            return sortie + tenus

        async for morceau in self._flux:
            if decide:
                yield morceau
                continue
            delta = _delta(morceau)
            contenu = getattr(delta, "content", None) if delta is not None else None
            if not contenu:
                if modele is None:
                    yield morceau
                else:
                    tenus.append(morceau)
                    originaux.append(morceau)
                continue
            if modele is None:
                modele = morceau
            originaux.append(morceau)
            texte += contenu
            texte, decide, n = self._retirer(texte, fin=False)
            retirees += n
            if decide:
                if retirees:
                    logger.info(f"[cerveau] {retirees} phrase(s) déjà dite(s) par le code retirée(s) de la réplique")
                for sortie in rendre(texte):
                    yield sortie
        if decide:
            return
        texte, _, n = self._retirer(texte, fin=True)
        retirees += n
        if retirees:
            logger.info(f"[cerveau] {retirees} phrase(s) déjà dite(s) par le code retirée(s) de la réplique")
        for sortie in rendre(texte.strip() if retirees else texte):
            yield sortie

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(self._flux, "aclose", None)
        if fermer is not None:
            await fermer()


class RepriseSansFluxMixin:
    """Mêlé au cerveau compatible OpenAI (``DograhOpenAILLMService``), sous la trace : la
    trace voit le flux tel que l'agent le reçoit, relance comprise."""

    async def get_chat_completions(self, context):  # type: ignore[override]
        # Revue du 16/10 : la relance part avec la réflexion de secours si cette réponse-ci
        # l'avait (l'armement est consommé par la requête d'origine), et se dit dans la trace.
        secours = bool(getattr(self, "_mark_relance_armee", False))
        entree = getattr(self, "_mark_entree_en_cours", None)
        # Revue du 26/10 (R-1) : les enveloppes de l'instance (état de la fiche, notices) ne s'ajoutent qu'« en
        # conversation », le temps de cet appel ; la relance, construite pendant la lecture du flux, part dans ce contexte.
        contexte_de_l_appel = contextvars.copy_context()
        try:
            flux = await super().get_chat_completions(context)  # type: ignore[misc]
        except Exception as erreur:
            # fiabilite-de-la-conversation (26/10, runs 2019 et 2026) : une requête refusée dès l'ouverture du
            # flux (``APIError``, aucun morceau) suit le chemin d'une erreur avant le premier morceau (K1) : même
            # relance sans flux, puis la phrase de repli ; l'agent ne se tait plus. Le délai de garde dépassé
            # garde sa propre riposte (``garde_modele``) : il passe tel quel.
            from api.services.panne.delai_modele import DelaiModeleDepasse

            if isinstance(erreur, DelaiModeleDepasse):
                raise
            logger.warning(f"[cerveau] requête refusée à l'ouverture du flux : {erreur!r}")
            flux = FluxEnErreur(erreur)

        async def relancer():
            if isinstance(entree, dict):
                entree["relance_sans_flux"] = True
            delai = getattr(self, "mark_delai_modele_s", None)
            if delai:
                # Revue du 16/10 : la relance a le même délai de garde que la requête d'origine ;
                # dépassé, l'erreur est rattrapée et la phrase de repli est dite.
                return await asyncio.wait_for(requeter(), delai)
            return await requeter()

        async def relancer_la_replique(retenue):
            # Lot 5 (K7) : la même requête, avec la consigne de ce qui a été retenu, sans flux.
            if isinstance(entree, dict):
                entree["replique_retenue"] = getattr(retenue, "raison", True)
            consigne = getattr(retenue, "consigne", None)
            outil = getattr(retenue, "outil", None)
            delai = getattr(self, "mark_delai_modele_s", None)
            if delai:
                return await asyncio.wait_for(requeter(consigne, outil), delai)
            return await requeter(consigne, outil)

        async def requeter(consigne=None, outil=None):
            from pipecat.utils.types import assert_given

            adapter = self.get_llm_adapter()  # type: ignore[attr-defined]
            # Lot 6 (K8) : l'appel obligatoire d'un outil, pour CETTE requête seulement (``LLMContext.set_tool_choice``
            # de Pipecat), remis comme avant dès les paramètres construits.
            avant_choix = getattr(context, "tool_choice", None)
            if outil and hasattr(context, "set_tool_choice"):
                context.set_tool_choice({"type": "function", "function": {"name": outil}})
            try:
                params = adapter.get_llm_invocation_params(
                    context,
                    system_instruction=assert_given(self._settings.system_instruction),  # type: ignore[attr-defined]
                    convert_developer_to_user=not self.supports_developer_role,  # type: ignore[attr-defined]
                )
            finally:
                # Lot 11 (revue 10) : le choix d'avant, quel qu'il soit.
                if outil and hasattr(context, "set_tool_choice"):
                    context.set_tool_choice(avant_choix)
            # Par l'attribut de l'instance : les enveloppes posées par le moteur (l'état de
            # la fiche) s'appliquent à la relance comme à la requête d'origine.
            avant = getattr(self, "_mark_secours_en_cours", False)
            self._mark_secours_en_cours = secours
            try:
                requete = dict(contexte_de_l_appel.run(self.build_chat_completion_params, params))  # type: ignore[attr-defined]
            finally:
                self._mark_secours_en_cours = avant
            requete["stream"] = False
            requete.pop("stream_options", None)
            if consigne and isinstance(requete.get("messages"), list):
                from api.services.workflow.fiche_au_fil_de_leau import inserer_l_etat

                requete["messages"] = inserer_l_etat(list(requete["messages"]), consigne)
            return await self._client.chat.completions.create(**requete)  # type: ignore[attr-defined]

        def l_appelant_attend() -> bool:
            messages = [
                m for m in (getattr(context, "messages", None) or []) if isinstance(m, dict)
            ]
            # SA-33 (appel 2557) : après un résultat d'outil, la personne attend aussi (le texte de l'outil n'est plus dit, lot 8d).
            return bool(messages) and (
                messages[-1].get("role") == "user" or dernier_message_est_un_resultat_a_reprendre(messages)
            )

        def texte_de_repli() -> str | None:
            # Lot 8d : à défaut de relance, la phrase réglée « réponse perdue », jamais le texte d'un outil.
            return phrase_de_repli(self)

        repris = FluxRepris(flux, relancer, l_appelant_attend, texte_de_repli)
        # Lot 5 (K7) : seulement sur une étape qui offre un outil d'action (case allumée) ; sinon le flux est
        # celui d'avant, octet pour octet.
        verificateur = getattr(self, ATTRIBUT_VERITE, None)
        if verificateur is not None and not hasattr(verificateur, "controler"):
            verificateur = None
        # Lot 6 (K8), position « relance » : une réplique sans question ni appel, alors que tout est prêt, est retenue.
        relanceur = getattr(self, ATTRIBUT_DECLENCHEUR, None)
        if relanceur is not None and getattr(relanceur, "position", None) != "relance":
            relanceur = None
        if verificateur is not None or relanceur is not None:
            messages = [m for m in (getattr(context, "messages", None) or []) if isinstance(m, dict)]
            # Lot 11 (F-1, revue 4) : le prompt de l'étape vit hors des messages ; ses dates sont connues aussi.
            systeme = getattr(getattr(self, "_settings", None), "system_instruction", None)
            if isinstance(systeme, str) and systeme:
                messages = [{"role": "system", "content": systeme}, *messages]
            if relanceur is None:
                controle = lambda texte: verificateur.controler(texte, messages)  # noqa: E731
            else:

                async def controle(texte):
                    retenue = verificateur.controler(texte, messages) if verificateur is not None else None
                    if retenue is None:
                        retenue = await relanceur.controler_la_replique(texte)
                    return retenue

            avant_outil = None
            if verificateur is not None and hasattr(verificateur, "controler_avant_outil"):
                avant_outil = lambda texte: verificateur.controler_avant_outil(texte, messages)  # noqa: E731
            la_relance = None
            if verificateur is not None and hasattr(verificateur, "controler_la_relance"):
                la_relance = lambda texte: verificateur.controler_la_relance(texte, messages)  # noqa: E731
            le_silence = None
            if verificateur is not None and hasattr(verificateur, "controler_le_silence"):
                le_silence = partial(verificateur.controler_le_silence, messages)  # ``sans_relance`` s'y ajoute à l'appel
            repris = RepliqueVerifiee(repris, controle, relancer_la_replique, avant_outil, la_relance, le_silence, lambda: phrase_de_repli_reglee(self))
        # SA-38 (M89) : en dernier, sur ce que l'agent dirait vraiment (relances comprises) ; sans phrase du code dans ce tour, rien.
        dites = phrases_dites_par_le_code(self, getattr(context, "messages", None))
        if dites:
            repris = SansRediteDuCode(repris, dites)
        return ArgumentsLisibles(
            SansPhraseAvecLaPassation(SansBalise(repris), lambda: getattr(self, ATTRIBUT_NOMS_DE_PASSATION, None) or ()),
            lambda: getattr(self, ATTRIBUT_NOMS_DE_PASSATION, None) or (),
            lambda: getattr(self, ATTRIBUT_NOMS_DES_FICHES, None) or (),
        )
