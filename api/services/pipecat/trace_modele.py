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
- ``usage`` : le compte de jetons du fournisseur ;
- ``fin`` : ``complet`` (le flux s'est fini de lui-même), ``ferme_avant_la_fin`` (notre chaîne
  a cessé de le lire) ou ``erreur: <type>`` ;
- ``texte_dit`` : ce que le lecteur de portes a laissé partir à la voix (et donc à l'historique,
  qui est fait de ce qui est dit) ; ``interrompue`` si une interruption est passée.

Une case par agent, ``trace_requetes_modele``, éteinte par défaut, sans écran : allumée sur nos
agents d'essai seulement (les messages pèsent quelques dizaines de kilo-octets par appel).
Éteinte, rien n'est écrit et le service se comporte comme avant, à l'octet. Seules les réponses
de la conversation sont tracées (``get_chat_completions``) : jamais les appels ponctuels du même
service (``run_inference``). ⛔ La trace ne coûte jamais l'appel : elle ne lève jamais.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from loguru import logger

# La case, dans la configuration de l'agent.
CLE_TRACE_REQUETES = "trace_requetes_modele"
# La trace, dans la fiche de l'appel (``gathered_context``).
TRACE_REQUETES = "requetes_modele"
# L'attribut du moteur qui porte la trace de l'appel (le lecteur de portes la lit).
ATTRIBUT_TRACE = "trace_du_modele"



def sans_la_trace(fiche: dict | None) -> dict:
    """La fiche de l'appel sans la trace, pour ce qui sort vers un client (webhooks des
    intégrations). Revue du 14/10, retenue par Evan : la trace porte le prompt et toute la
    conversation, elle ne quitte jamais Dograh. Sans trace, la fiche telle quelle."""
    if not fiche or TRACE_REQUETES not in fiche:
        return fiche or {}
    return {cle: valeur for cle, valeur in fiche.items() if cle != TRACE_REQUETES}


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


class TraceDuModele:
    """La trace d'UN appel : une entrée par réponse demandée au cerveau."""

    def __init__(self, fiche: Callable[[], dict]):
        self._fiche = fiche
        self._derniere: dict | None = None

    def ouvrir(self) -> dict | None:
        """Une requête part : son entrée, rangée dans la fiche de l'appel."""
        try:
            fiche = self._fiche()
            from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

            entree = {
                "tour": fiche.get(CLE_TOUR),
                "parametres": None,
                "morceaux": [],
                "usage": None,
                "fin": None,
                "texte_dit": "",
            }
            fiche.setdefault(TRACE_REQUETES, []).append(entree)
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

    def finir(self, entree: dict | None, fin: str) -> None:
        if entree is not None and entree.get("fin") is None:
            entree["fin"] = fin

    def flux(self, flux: Any, entree: dict | None) -> Any:
        if entree is None:
            return flux
        return FluxTrace(flux, self, entree)

    def morceau(self, entree: dict, morceau: Any, depart: float) -> None:
        try:
            note: dict = {"ms": round((time.monotonic() - depart) * 1000)}
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
            entree["morceaux"].append(note)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[trace] morceau du modèle non tracé : {erreur!r}")

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

    def __init__(self, flux: Any, trace: TraceDuModele, entree: dict):
        self._flux = flux
        self._trace = trace
        self._entree = entree
        self._depart = time.monotonic()

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
                self._trace.morceau(self._entree, morceau, self._depart)
                yield morceau
        finally:
            self._trace.finir(self._entree, fin)
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
    _mark_entree_en_cours: dict | None = None

    async def get_chat_completions(self, context):  # type: ignore[override]
        trace = self.mark_trace
        if trace is None:
            return await super().get_chat_completions(context)  # type: ignore[misc]
        entree = trace.ouvrir()
        self._mark_entree_en_cours = entree
        try:
            flux = await super().get_chat_completions(context)  # type: ignore[misc]
        except BaseException as erreur:
            trace.finir(entree, f"erreur: {type(erreur).__name__}")
            raise
        finally:
            self._mark_entree_en_cours = None
        return trace.flux(flux, entree)

    def _mark_tracer_parametres(self, params: dict) -> dict:
        """Appelé par l'enveloppe que pose ``brancher_la_trace``, par-dessus toutes les
        autres : la requête telle qu'elle part. Hors d'une réponse de la conversation
        (``run_inference``), rien."""
        entree = self._mark_entree_en_cours
        if entree is not None and self.mark_trace is not None:
            self.mark_trace.parametres(entree, params)
        return params


def brancher_la_trace(engine: Any, llm: Any, run_configs: dict | None) -> TraceDuModele | None:
    """La trace de l'appel, case allumée et service qui la porte ; sinon ``None`` et rien
    ne change. Téléphone et clavier. Ne lève jamais."""
    try:
        if (run_configs or {}).get(CLE_TRACE_REQUETES) is not True:
            return None
        if llm is None or not hasattr(llm, "mark_trace"):
            return None
        trace = TraceDuModele(lambda: engine._gathered_context)
        llm.mark_trace = trace
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
