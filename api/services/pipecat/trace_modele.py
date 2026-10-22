"""[.mark] La trace du cerveau : la requête exacte et le flux reçu, réponse par réponse.

Chantier repliques-coupees, lot 1 (décision D1 du 14/10). Des répliques sortent coupées en pleine
phrase (« C'est noté. Avez-vous une adresse mail pour que », run 1176) alors que le même tour,
rejoué en direct chez le fournisseur, sort entier 22 fois sur 22. Pour trancher entre « le
fournisseur envoie un flux coupé » et « notre chaîne en perd une partie », il faut voir, pour la
réponse coupée, ce qui est parti et ce qui est revenu :

- ``parametres`` : la requête exacte envoyée au cerveau (messages, outils, réglages), telle que
  le client HTTP la reçoit ; ⛔ jamais de clé : la clé vit dans le client, pas dans les
  paramètres, et les en-têtes ne sont jamais recopiés ;
- ``morceaux`` : chaque morceau du flux, avec son texte, son ``finish_reason`` et son arrivée en
  millisecondes depuis la requête ;
- ``envoye_a``, ``premier_morceau_ms``, ``premier_texte_ms``, ``fini_ms`` (B5 du tri du 17/10) :
  l'horodatage **côté serveur** de l'envoi de la requête (UTC) et, en millisecondes depuis cet
  envoi, l'arrivée du premier morceau, du premier morceau de texte et de la fin du flux. Au
  clavier, la session texte rejoue les morceaux à intervalles réguliers : ``ms`` n'y mesure rien,
  ces trois durées, si ;
- ``usage`` : le compte de jetons du fournisseur ;
- ``fin`` : ``complet`` (le flux s'est fini de lui-même), ``ferme_avant_la_fin`` (notre chaîne
  a cessé de le lire) ou ``erreur: <type>`` ;
- ``texte_dit`` : ce que le lecteur de portes a laissé partir à la voix (et donc à l'historique,
  qui est fait de ce qui est dit) ; ``interrompue`` si une interruption est passée.

Une case par agent, ``trace_requetes_modele``, éteinte par défaut, à l'écran (thème Agent, « Diagnostic », lot 6 bis) : allumée sur nos
agents d'essai seulement (environ 20 Ko par réponse : les messages complets à chaque tour).
Éteinte, rien n'est écrit et le service se comporte comme avant, à l'octet. Seules les réponses
de la conversation sont tracées (``get_chat_completions``) : jamais les appels ponctuels du même
service (``run_inference``). ⛔ La trace ne coûte jamais l'appel : elle ne lève jamais.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from loguru import logger

# La case, dans la configuration de l'agent.
CLE_TRACE_REQUETES = "trace_requetes_modele"
# La trace, dans la fiche de l'appel (``gathered_context``).
TRACE_REQUETES = "requetes_modele"
# L'attribut du moteur qui porte la trace de l'appel (le lecteur de portes la lit).
ATTRIBUT_TRACE = "trace_du_modele"



# Les résultats des outils (arguments et réponses), que le moteur garde depuis la montée Pipecat
# 1.12 (amont ``b10e829f``, ``PipecatEngine.record_tool_result``) : la clé est celle de l'amont.
RESULTATS_DES_OUTILS = "tool_results"
# Ce qui ne quitte jamais Dograh, quelle que soit l'intégration (lot 3 de cloture-code, 22/10).
CLES_JAMAIS_ENVOYEES = frozenset({TRACE_REQUETES, RESULTATS_DES_OUTILS})


def sans_la_trace(fiche: dict | None) -> dict:
    """La fiche de l'appel sans la trace ni les résultats des outils, pour ce qui sort vers un
    client (webhooks des intégrations, sessions d'intégration en fin d'appel). Revue du 14/10,
    retenue par Evan : la trace porte le prompt et toute la conversation, elle ne quitte jamais
    Dograh ; les résultats des outils portent les arguments et les réponses des actions, même
    règle (plan cloture-code, lot 3). Sans l'une ni l'autre, la fiche telle quelle."""
    if not fiche or not CLES_JAMAIS_ENVOYEES.intersection(fiche):
        return fiche or {}
    return {cle: valeur for cle, valeur in fiche.items() if cle not in CLES_JAMAIS_ENVOYEES}


FIN_COMPLETE = "complet"
FIN_FERMEE = "ferme_avant_la_fin"

# Jamais recopié, même si une configuration l'y mettait : des en-têtes peuvent porter une clé.
_CLES_JAMAIS_TRACEES = frozenset(
    {"api_key", "extra_headers", "default_headers", "headers", "authorization"}
)


def _en_clair(valeur: Any) -> Any:
    """Une copie lisible en JSON, détachée de l'original (la conversation continue de
    changer après la requête). Les valeurs « non données » du client disparaissent."""
    if type(valeur).__name__ in ("NotGiven", "Omit"):
        return None
    if isinstance(valeur, dict):
        return {
            str(cle): _en_clair(v)
            for cle, v in valeur.items()
            if str(cle).lower() not in _CLES_JAMAIS_TRACEES
            and type(v).__name__ not in ("NotGiven", "Omit")
        }
    if isinstance(valeur, (list, tuple)):
        return [_en_clair(v) for v in valeur]
    if valeur is None or isinstance(valeur, (str, int, float, bool)):
        return valeur
    vider = getattr(valeur, "model_dump", None)
    if callable(vider):
        return _en_clair(vider())
    return repr(valeur)


def _est_un_evenement_responses(morceau: Any) -> bool:
    """Un événement de l'API Responses (``response.…``), pas un morceau de chat completions."""
    type_ = getattr(morceau, "type", None)
    return isinstance(type_, str) and type_.startswith("response.")


class TraceDuModele:
    """La trace d'UN appel : une entrée par réponse demandée au cerveau."""

    def __init__(self, fiche: Callable[[], dict]):
        self._fiche = fiche
        self._derniere: dict | None = None

    def ouvrir(self, agent: str | None = None, *, parle: bool = True) -> dict | None:
        """Une requête part : son entrée, rangée dans la fiche de l'appel. ``agent`` : le
        nom de l'agent qui la pose (lot 8 de fiabilite-orchestration, R12), pour lire à qui
        appartient chaque réponse quand plusieurs agents parlent dans l'appel."""
        try:
            fiche = self._fiche()
            from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

            entree = {
                "tour": fiche.get(CLE_TOUR),
                "parametres": None,
                "envoye_a": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "morceaux": [],
                "usage": None,
                "fin": None,
                "texte_dit": "",
            }
            if agent:
                entree["agent"] = agent
            fiche.setdefault(TRACE_REQUETES, []).append(entree)
            # Revue du 19/10 : une requête du cerveau de fond (``parle`` faux), qui tourne en
            # parallèle de la conversation, ne devient jamais « la dernière » où le lecteur de
            # portes écrit le texte dit à l'appelant.
            if parle:
                self._derniere = entree
            return entree
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[trace] requête du modèle non tracée : {erreur!r}")
            return None

    def parametres(self, entree: dict | None, params: dict) -> None:
        if entree is None:
            return
        try:
            entree["parametres"] = _en_clair(params)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[trace] paramètres du modèle non tracés : {erreur!r}")

    def finir(self, entree: dict | None, fin: str, envoi: float | None = None) -> None:
        if entree is not None and entree.get("fin") is None:
            entree["fin"] = fin
            if envoi is not None and "fini_ms" not in entree:
                entree["fini_ms"] = round((time.monotonic() - envoi) * 1000)

    def flux(self, flux: Any, entree: dict | None, envoi: float | None = None) -> Any:
        if entree is None:
            return flux
        return FluxTrace(flux, self, entree, envoi)

    def morceau(
        self, entree: dict, morceau: Any, depart: float, envoi: float | None = None
    ) -> None:
        try:
            note: dict = {"ms": round((time.monotonic() - depart) * 1000)}
            if envoi is not None:
                # B5 : le vrai délai, compté depuis l'envoi de la requête.
                depuis = round((time.monotonic() - envoi) * 1000)
                entree.setdefault("premier_morceau_ms", depuis)
                note["depuis_l_envoi_ms"] = depuis
            if _est_un_evenement_responses(morceau):
                self._evenement_responses(entree, note, morceau)
                if envoi is not None and (note.get("texte") or note.get("outils")):
                    entree.setdefault("premier_texte_ms", note["depuis_l_envoi_ms"])
                entree["morceaux"].append(note)
                return
            choix = getattr(morceau, "choices", None) or []
            if choix:
                delta = getattr(choix[0], "delta", None)
                texte = getattr(delta, "content", None)
                if texte:
                    note["texte"] = texte
                raisonnement = getattr(delta, "reasoning_content", None)
                if raisonnement:
                    note["raisonnement"] = raisonnement
                outils = getattr(delta, "tool_calls", None)
                if outils:
                    note["outils"] = _en_clair(outils)
                arret = getattr(choix[0], "finish_reason", None)
                if arret:
                    note["finish_reason"] = arret
            usage = getattr(morceau, "usage", None)
            if usage:
                entree["usage"] = _en_clair(usage)
                note["usage"] = True
            if envoi is not None and (note.get("texte") or note.get("outils")):
                entree.setdefault("premier_texte_ms", note["depuis_l_envoi_ms"])
            entree["morceaux"].append(note)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[trace] morceau du modèle non tracé : {erreur!r}")

    @staticmethod
    def _evenement_responses(entree: dict, note: dict, evenement: Any) -> None:
        """Lot 1 d'orchestrateur-trois-cerveaux : un événement de l'API Responses, noté avec les
        mêmes clés que le morceau de chat completions (texte, raisonnement, outils, fin, jetons)."""
        type_ = getattr(evenement, "type", "")
        if type_ == "response.output_text.delta" and getattr(evenement, "delta", None):
            note["texte"] = evenement.delta
        elif type_ == "response.reasoning_text.delta" and getattr(evenement, "delta", None):
            note["raisonnement"] = evenement.delta
        elif type_ == "response.output_item.added":
            item = getattr(evenement, "item", None)
            if getattr(item, "type", None) == "function_call":
                note["outils"] = [{"name": getattr(item, "name", None)}]
        elif type_ == "response.function_call_arguments.done":
            note["outils"] = [
                {"name": getattr(evenement, "name", None), "arguments": getattr(evenement, "arguments", None)}
            ]
        elif type_ == "response.completed":
            reponse = getattr(evenement, "response", None)
            note["finish_reason"] = getattr(reponse, "status", None) or "completed"
            usage = getattr(reponse, "usage", None)
            if usage:
                entree["usage"] = _en_clair(usage)
                note["usage"] = True

    # --- Côté lecteur de portes ----------------------------------------------

    def dit(self, texte: str) -> None:
        """Ce que le lecteur laisse partir à la voix, pour la dernière réponse demandée."""
        if self._derniere is not None and texte:
            self._derniere["texte_dit"] += texte

    def interrompue(self) -> None:
        if self._derniere is not None:
            self._derniere["interrompue"] = True


class FluxTrace:
    """Le flux du cerveau, chaque morceau noté au passage, sans rien changer à ce qui passe."""

    def __init__(
        self, flux: Any, trace: TraceDuModele, entree: dict, envoi: float | None = None
    ):
        self._flux = flux
        self._trace = trace
        self._entree = entree
        self._depart = time.monotonic()
        # B5 : l'instant d'envoi de la requête (horloge monotone du serveur).
        self._envoi = envoi

    def __aiter__(self):
        return self._parcourir()

    async def _parcourir(self):
        iterateur = self._flux.__aiter__()
        fin = FIN_FERMEE
        try:
            while True:
                try:
                    morceau = await iterateur.__anext__()
                except StopAsyncIteration:
                    fin = FIN_COMPLETE
                    return
                except Exception as erreur:
                    fin = f"erreur: {type(erreur).__name__}"
                    raise
                self._trace.morceau(self._entree, morceau, self._depart, self._envoi)
                yield morceau
        finally:
            self._trace.finir(self._entree, fin, self._envoi)
            fermer = getattr(iterateur, "aclose", None)
            if fermer is not None:
                await fermer()

    async def close(self):
        fermer = getattr(self._flux, "close", None) or getattr(
            self._flux, "aclose", None
        )
        if fermer is not None:
            await fermer()


class TraceModeleMixin:
    """Mêlé aux services de la conversation (``DograhOpenAILLMService``,
    ``DograhMistralLLMService``), AVANT la garde du délai : la trace voit le flux tel que
    le service le lit. ``mark_trace`` à ``None`` (le défaut) : rien ne change."""

    mark_trace: TraceDuModele | None = None
    # Lot 8 de fiabilite-orchestration (R12) : le nom de l'agent que ce service porte.
    mark_agent: str | None = None
    # Faux pour le cerveau de fond : ses réponses ne sont jamais dites à l'appelant.
    mark_trace_parle: bool = True
    _mark_entree_en_cours: dict | None = None

    async def get_chat_completions(self, context):  # type: ignore[override]
        trace = self.mark_trace
        if trace is None:
            return await super().get_chat_completions(context)  # type: ignore[misc]
        entree = trace.ouvrir(self.mark_agent, parle=self.mark_trace_parle)
        self._mark_entree_en_cours = entree
        envoi = time.monotonic()
        try:
            flux = await super().get_chat_completions(context)  # type: ignore[misc]
        except BaseException as erreur:
            trace.finir(entree, f"erreur: {type(erreur).__name__}")
            raise
        finally:
            self._mark_entree_en_cours = None
        return trace.flux(flux, entree, envoi)

    def _mark_tracer_parametres(self, params: dict) -> dict:
        """Appelé par l'enveloppe que pose ``brancher_la_trace``, par-dessus toutes les
        autres : la requête telle qu'elle part. Hors d'une réponse de la conversation
        (``run_inference``), rien."""
        entree = self._mark_entree_en_cours
        if entree is not None and self.mark_trace is not None:
            self.mark_trace.parametres(entree, params)
        return params


def brancher_la_trace(
    engine: Any,
    llm: Any,
    run_configs: dict | None,
    nom: str | None = None,
    *,
    parle: bool = True,
) -> TraceDuModele | None:
    """La trace de l'appel, case allumée et service qui la porte ; sinon ``None`` et rien
    ne change. Téléphone et clavier. Ne lève jamais.

    Lot 8 de fiabilite-orchestration (R12) : la trace est UNE par appel (celle du moteur, si
    un agent l'a déjà ouverte) et se branche sur le service de chaque agent construit à la
    passation et du cerveau de fond, case de CET agent allumée ; ``nom`` est écrit dans chaque
    entrée. Sans ``nom``, l'entrée est celle d'avant, à l'octet."""
    try:
        # Evan, 19/10 : UNE case pour tout le groupe, celle du principal (les réglages de l'appel,
        # ``reglages_appel``) : on l'allume et chaque agent du groupe, fond compris, est tracé ; on
        # l'éteint et personne ne l'est. Jamais d'agent tracé à côté d'un agent qui ne l'est pas.
        reglages_appel = (getattr(engine, "__dict__", None) or {}).get("reglages_appel")
        decision = reglages_appel if isinstance(reglages_appel, dict) and reglages_appel else run_configs
        if (decision or {}).get(CLE_TRACE_REQUETES) is not True:
            return None
        if llm is None or not hasattr(llm, "mark_trace"):
            return None
        existante = getattr(engine, ATTRIBUT_TRACE, None)
        if isinstance(existante, TraceDuModele):
            trace = existante
        else:
            trace = TraceDuModele(lambda: engine._gathered_context)
        llm.mark_trace = trace
        llm.mark_agent = nom or None
        llm.mark_trace_parle = parle
        # La requête se photographie en DERNIER : le moteur a déjà enveloppé le
        # constructeur de requête pour y glisser l'état de la fiche
        # (``montrer_la_fiche``, à sa création). Prise dans la méthode du service,
        # la trace la voyait sans ce message (constat du 14/10, run 1185).
        construire = llm.build_chat_completion_params

        def build_chat_completion_params(params_from_context):
            return llm._mark_tracer_parametres(construire(params_from_context))

        llm.build_chat_completion_params = build_chat_completion_params
        setattr(engine, ATTRIBUT_TRACE, trace)
        return trace
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[trace] trace du modèle non branchée : {erreur!r}")
        return None
