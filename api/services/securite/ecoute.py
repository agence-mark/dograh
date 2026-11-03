"""[.mark] Couche 3 : l'écoute de l'appelant (U3 quinquies, `reference/29` § XXIX.5). Éteinte par défaut.

Un classifieur court (deux questions : manipulation, détresse) lit la dernière phrase de la personne, **en parallèle** de la réponse
de l'agent, jamais attendu. Son résultat s'applique au tour SUIVANT, sous forme d'une notice d'un tour posée avant la dernière
parole (jamais dite, jamais gardée dans l'historique). Le modèle est celui de l'arbitre (sinon du greffier, sinon de la
conversation) : même clé, aucun compte de plus. Chaque déclenchement est marqué (``marques``).

Le moteur est le même au téléphone et au clavier : le hook est dans ``avant_la_requete.preparer_la_requete`` (parité).
Conduites construites : ``rappel`` / ``urgence`` (la notice du tour suivant) et ``noter`` (seulement marquer). La fin d'appel et le
transfert immédiat ne sont pas construits (ils passent par l'orchestration du moteur).
Coût : un appel court par phrase de l'appelant (consigne ~120 jetons, phrase, sortie ~15 jetons), mesuré au banc avant d'être affiché au devis.
⛔ Ne lève jamais.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from loguru import logger

from api.schemas.securite_conversation import SecuriteConversation
from api.services.securite import marques, textes
from api.services.securite.reglages import de_l_agent

Interroger = Callable[[str, str], Awaitable[tuple[str | None, dict]]]
DELAI = 4.0
LONGUEUR_MAX = 800


def lire_les_scores(texte: str | None) -> dict[str, float] | None:
    """``{"manipulation": 0..1, "detresse": 0..1}`` depuis la sortie du modèle, ou ``None`` si elle est illisible."""
    try:
        brut = json.loads(texte or "")
        if not isinstance(brut, dict):
            return None
        sortie: dict[str, float] = {}
        for cle in ("manipulation", "detresse"):
            valeur = brut.get(cle)
            if isinstance(valeur, bool):
                valeur = 1.0 if valeur else 0.0
            if not isinstance(valeur, (int, float)):
                return None
            sortie[cle] = max(0.0, min(1.0, float(valeur)))
        return sortie
    except (ValueError, TypeError):
        return None


class EcouteDeLAppelant:
    def __init__(self, reglages: SecuriteConversation, interroger: Interroger | None, contexte: Callable[[], Any]):
        self._r = reglages
        self._interroger = interroger
        self._contexte = contexte
        self._tache: asyncio.Task | None = None
        self._en_attente: list[str] = []
        self._derniere = ""

    @property
    def actif(self) -> bool:
        return bool(self._r.ecoute.actif and self._interroger is not None)

    def observer(self, texte: str) -> bool:
        """Lance la lecture de ``texte`` en parallèle. Rend ``True`` si une demande est partie. Ne bloque jamais."""
        try:
            texte = " ".join((texte or "").split())[:LONGUEUR_MAX]
            if not self.actif or not texte or texte == self._derniere:
                return False
            self._derniere = texte
            if self._tache is not None and not self._tache.done():
                self._tache.cancel()
            self._tache = asyncio.get_running_loop().create_task(self._lire(texte))
            return True
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[securite] écoute non lancée : {erreur!r}")
            return False

    async def _lire(self, texte: str) -> None:
        try:
            consigne = (self._r.ecoute.consigne or "").strip() or textes.CONSIGNE_DU_CLASSIFIEUR
            sortie, _jetons = await asyncio.wait_for(self._interroger(consigne, texte), timeout=DELAI)
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001 -- rien ne se passe, c'est tracé
            logger.info(f"[securite] écoute sans résultat : {type(erreur).__name__}")
            return
        scores = lire_les_scores(sortie)
        if scores is None:
            logger.info("[securite] écoute : sortie illisible, ignorée")
            return
        seuil = textes.SEUILS[self._r.ecoute.sensibilite]
        contexte = self._contexte()
        if scores["manipulation"] >= seuil:
            if self._r.ecoute.sur_manipulation == "rappel":
                self._en_attente.append(textes.RAPPEL_MANIPULATION)
            if self._r.marquer:
                marques.noter(contexte, couche=marques.COUCHE_ECOUTE, nom="manipulation", detail=f"{scores['manipulation']:.2f}", extrait=texte)
        if scores["detresse"] >= seuil:
            if self._r.ecoute.sur_detresse == "urgence":
                self._en_attente.append(textes.RAPPEL_DETRESSE)
            if self._r.marquer:
                marques.noter(contexte, couche=marques.COUCHE_ECOUTE, nom="detresse", detail=f"{scores['detresse']:.2f}", extrait=texte)

    def rappel_du_tour(self) -> str | None:
        """La notice du tour qui commence (consommée), ou ``None``."""
        if not self._en_attente:
            return None
        notice, self._en_attente = "\n".join(dict.fromkeys(self._en_attente)), []
        return notice


def _service(moteur: Any) -> Any:
    """Le modèle de l'arbitre, sinon du greffier, sinon de la conversation (même ordre que l'arbitre du passage)."""
    service = getattr(moteur, "arbitre_service", None)
    if service is None:
        service = getattr(getattr(moteur, "greffier", None), "_service", None)
    if service is None:
        service = getattr(getattr(moteur, "active_agent", None), "llm", None)
    return service


def de_l_appel(moteur: Any) -> EcouteDeLAppelant | None:
    """L'écoute de cet appel, créée au premier besoin d'après les réglages de l'agent actif. ``None`` si éteinte. Ne lève jamais."""
    try:
        existante = getattr(moteur, "_ecoute_securite", None)
        if existante is not None:
            return existante if existante.actif else None
        reglages = de_l_agent(getattr(getattr(moteur, "active_agent", None), "reglages", None))
        if not reglages.ecoute.actif:
            return None
        service = _service(moteur)
        if service is None:
            return None

        async def interroger(systeme: str, message: str) -> tuple[str | None, dict]:
            from api.services.pipecat.greffier import interroger as interroger_le_modele

            return await interroger_le_modele(service, systeme, message)

        ecoute = EcouteDeLAppelant(reglages, interroger, lambda: getattr(moteur, "_gathered_context", None))
        moteur._ecoute_securite = ecoute
        return ecoute
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[securite] écoute non montée : {erreur!r}")
        return None


def contexte_avec_le_rappel(moteur: Any, context: Any) -> Any | None:
    """Au début d'une requête qui répond à la personne : lance la lecture de sa parole et rend une COPIE du contexte avec la notice
    du résultat d'avant, ou ``None``. Le contexte partagé n'est pas touché. ⛔ Ne lève jamais."""
    try:
        ecoute = de_l_appel(moteur)
        if ecoute is None:
            return None
        from api.services.workflow import passage_sur_la_fiche as passage

        if not passage._derniere_parole_de_la_personne(context):
            return None
        messages = list(context.get_messages())
        dernier = messages[-1].get("content")
        texte = dernier if isinstance(dernier, str) else " ".join(p.get("text", "") for p in dernier if isinstance(p, dict)) if isinstance(dernier, list) else ""
        notice = ecoute.rappel_du_tour()
        ecoute.observer(texte)
        if not notice:
            return None
        nouveaux = passage._inserer_avant_la_derniere_parole(messages, notice)
        if nouveaux is None:
            return None
        from pipecat.processors.aggregators.llm_context import LLMContext

        return LLMContext(messages=nouveaux, tools=context.tools, tool_choice=context.tool_choice)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[securite] rappel non posé : {erreur!r}")
        return None


def ecoute_allumee(agent: Any) -> bool:
    try:
        return bool(de_l_agent(getattr(agent, "reglages", None)).ecoute.actif)
    except Exception:  # noqa: BLE001
        return False
