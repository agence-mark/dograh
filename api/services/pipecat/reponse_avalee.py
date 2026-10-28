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
import time
from typing import Any

from loguru import logger

# L'attribut du service où le moteur pose la phrase de repli de son agent (``brancher_les_phrases``).
ATTRIBUT_PHRASE_DE_REPLI = "mark_phrase_de_repli"


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


class ArgumentsLisibles:
    """Pipecat jette un appel d'outil dont les arguments ne se lisent pas (``services/openai/base_llm.py``,
    « Failed to parse function call arguments »). Pour un OUTIL DE PASSATION, l'appelant a bien demandé la
    passation : l'appel est exécuté avec ``{}``.

    Dès le premier morceau d'appel d'outil, la suite du flux est tenue jusqu'à la fin (Pipecat n'agit
    qu'à la fin de toute façon) ; le texte d'avant passe sans attente. Si aucun appel de passation n'est
    illisible, les morceaux repartent tels quels, dans leur ordre. Un morceau qui porte plusieurs appels à la fois (que Pipecat
    ne lit pas) désactive la correction : le flux passe sans changement. Sans outil de passation connu,
    le flux passe tel quel."""

    def __init__(self, flux: Any, noms):
        self._flux = flux
        self._noms = noms

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        noms = set(self._noms() if callable(self._noms) else (self._noms or ()))
        if not noms:
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
            tenus = self._corriger(tenus, noms)
        except Exception as erreur:  # noqa: BLE001 -- jamais à la place du flux
            logger.warning(f"[cerveau] arguments d'appel non corrigés : {erreur!r}")
        for tenu in tenus:
            yield tenu

    @staticmethod
    def _corriger(tenus: list[Any], noms: set) -> list[Any]:
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
            if e["nom"] in noms and e["arguments"].strip() and not _est_lisible(e["arguments"])
        }
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
                fonction.arguments = "{}" if index not in vus else ""
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


class RepliqueVerifiee:
    """Le flux du cerveau, tenu jusqu'à sa fin quand l'étape offre un outil d'action (case « vérité des actions »).

    - un flux qui porte un appel d'outil passe tel quel, dans son ordre ;
    - une réplique de texte seul est contrôlée (``controler(texte)`` rend ``None`` ou une retenue) ; sans retenue,
      elle passe telle quelle ;
    - retenue : le modèle est relancé UNE fois, sans flux, avec la consigne de la retenue (``relancer(retenue)``) ;
      la relance est rendue telle quelle, quoi qu'elle dise. Relance vide ou en erreur : la réplique d'origine passe.

    Coût : la réplique part à la fin de la génération, non au premier morceau (étapes qui offrent une action
    seulement). ⛔ Ne lève jamais à la place du service."""

    def __init__(self, flux: Any, controler, relancer):
        self._flux = flux
        self._controler = controler
        self._relancer = relancer

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
        if not appel and texte:
            try:
                retenue = self._controler("".join(texte))
                if inspect.isawaitable(retenue):
                    retenue = await retenue
            except Exception as erreur:  # noqa: BLE001
                logger.warning(f"[cerveau] réplique non contrôlée : {erreur!r}")
        if retenue is not None:
            reprise = None
            try:
                reprise = await self._relancer(retenue)
            except Exception as erreur:  # noqa: BLE001 -- jamais à la place du service
                logger.warning(f"[cerveau] relance de la réplique retenue en échec : {erreur!r}")
            if reprise is not None:
                morceaux = en_morceaux(reprise, usage)
                if any(porte_quelque_chose(m) for m in morceaux):
                    logger.warning(
                        f"[cerveau] réplique retenue ({getattr(retenue, 'raison', '?')}) : réponse rendue par la relance"
                    )
                    for morceau in morceaux:
                        yield morceau
                    return
        for tenu in tenus:
            yield tenu

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
            return bool(messages) and messages[-1].get("role") == "user"

        repris = FluxRepris(flux, relancer, l_appelant_attend, lambda: phrase_de_repli(self))
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

            repris = RepliqueVerifiee(repris, controle, relancer_la_replique)
        return ArgumentsLisibles(
            repris,
            lambda: getattr(self, ATTRIBUT_NOMS_DE_PASSATION, None) or (),
        )
