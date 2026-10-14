"""[.mark] Le lecteur de portes du greffier : la porte prise dans la réponse, sans note.

Chantier greffier-conversation, lot A (décision D5 du 09/10, D2 du 13/10). En mode greffier,
l'agent ne note rien (la fiche est tenue à côté de lui) ; case « Transitions in the reply »
allumée, il prend une porte DANS sa réponse et dit déjà la première réplique de l'étape
d'arrivée :

    → nom_de_la_porte
    Quelle est la marque de votre appareil ?

Un seul appel au modèle par changement d'étape au lieu de deux (la porte en fonction, puis la
relance dans l'étape d'arrivée).

Ce lecteur est le processeur du Post-scriptum **sans la note** : la lecture de la ligne « → » et
ses parades restent celles du Post-scriptum (liste sans flèche Q1 dans la consigne, porte inconnue
relancée une fois Q3, porte en fin de phrase Q4, porte prise même si la personne coupe la parole
D6, porte coupée en route jamais prise), et rien d'autre :

- aucun séparateur n'est cherché, aucune note n'est lue ni écrite ; ⛔ il ne touche jamais aux
  notices du greffier (une réponse de l'agent n'efface pas le retour de la dernière passe) ;
- une ligne de JSON n'est toujours jamais dite (D7) : le modèle peut garder un vieux réflexe ;
- la ligne « → » n'est jamais dite, et comme la mémoire de l'agent est faite de ce que la voix a
  dit, le greffier ne la relit jamais non plus ;
- la trace va dans ``portes_lues`` (une ligne par porte écrite), jamais dans ``post_scriptums`` ;
- case ``trace_requetes_modele`` allumée (repliques-coupees, D1), ce qu'il laisse partir à la
  voix et les interruptions vont à la trace du cerveau (``trace_modele.py``) ;
- ⛔ il ne lève jamais (patron du Post-scriptum).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from loguru import logger

from api.services.pipecat.post_scriptum import PostScriptumProcessor, sans_json
from api.services.pipecat.trace_modele import ATTRIBUT_TRACE, TraceDuModele
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_TOUR,
    MODE_GREFFIER,
    ReglagesFiche,
)
from pipecat.frames.frames import Frame, InterruptionFrame, LLMTextFrame
from pipecat.processors.frame_processor import FrameDirection

# La trace de chaque porte écrite dans la réponse, en mode greffier.
TRACE_PORTES_LUES = "portes_lues"


class LecteurDePortes(PostScriptumProcessor):
    """Prend la porte écrite dans la réponse ; laisse la phrase aller à la voix."""

    def __init__(
        self,
        *,
        reglages: ReglagesFiche,
        fiche: Callable[[], dict],
        messages: Callable[[], Iterable[dict]],
        attendu: Callable[[], bool],
        portes: Any,
        trace: TraceDuModele | None = None,
        **kwargs,
    ):
        # D1 de repliques-coupees : ``None`` (case éteinte), rien n'est noté.
        self._trace_du_modele = trace
        super().__init__(
            reglages=reglages,
            fiche=fiche,
            messages=messages,
            # ⛔ Jamais les notices du greffier : elles sont à lui seul.
            notices=None,
            attendu=attendu,
            notes_en_cours=set(),
            portes=portes,
            **kwargs,
        )

    async def push_frame(self, frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM):
        trace = self._trace_du_modele
        if trace is not None and direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, InterruptionFrame):
                trace.interrompue()
            elif isinstance(frame, LLMTextFrame) and not getattr(frame, "skip_tts", False):
                trace.dit(frame.text)
        await super().push_frame(frame, direction)

    # Pas de séparateur ni de note : la réponse est une phrase, avec peut-être une porte.
    def _separateur_dans(self, texte: str) -> tuple[int, int] | None:
        return None

    # « Je note » (B6) est un défaut du format du Post-scriptum : rien à retenir ici.
    def _prose_en_cours(self, texte: str) -> bool:
        return False

    async def _relancer_la_prose(self) -> bool:
        return False

    async def _finir(self, direction: FrameDirection) -> dict | None:
        """Fin de la réponse : le reste de la phrase à la voix, rien d'autre."""
        self._dit = False
        if not self._apres and self._attente.strip(" \t\n|"):
            await self._dire(self._attente, None, direction, fin=True)
        if self._apres:
            # D7 : du JSON dans la réponse n'est jamais dit ; la parole autour l'est.
            await self._dire(sans_json(self._note), None, direction, fin=True)
        muette = (
            self._vu_du_texte
            and not self._a_dit
            and not self._portes_lues
            and self._attendu()
        )
        self._dit = self._a_dit
        self._oublier()
        if muette:
            # Revue du 13/10 : une réponse faite seulement de JSON (un vieux réflexe) ne
            # dit rien et ne prend aucune porte : le modèle reparle, une fois par réplique
            # (la garde du moteur), jamais un tour muet.
            relancer = getattr(self._moteur, "relancer_une_reponse_muette", None)
            if relancer is not None and await relancer():
                logger.info("[porte] réponse sans phrase ni porte : le modèle reparle")
        return None

    def _tracer(self, etat: str, champs: list[str], **detail) -> dict | None:
        """Seules les portes laissent une trace (une coupure sans porte, rien)."""
        if "porte" not in detail:
            return None
        try:
            fiche = self._fiche()
            trace = {"tour": fiche.get(CLE_TOUR), **detail}
            if etat != "absent":
                trace["etat"] = etat
            fiche.setdefault(TRACE_PORTES_LUES, []).append(trace)
            return trace
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[porte] trace de la porte non écrite : {erreur!r}")
            return None


def lecteur_de_portes_du_moteur(engine: Any) -> LecteurDePortes | None:
    """Le lecteur, branché sur le moteur de l'appel, ou ``None`` : hors mode greffier ou
    case éteinte (le comportement d'avant, à l'octet). Téléphone et clavier."""
    reglages = engine.fiche
    if (
        reglages is None
        or reglages.mode != MODE_GREFFIER
        or not reglages.portes_dans_la_reponse
    ):
        return None
    return LecteurDePortes(
        reglages=reglages,
        fiche=lambda: engine._gathered_context,
        messages=lambda: engine.context.get_messages() if engine.context else [],
        attendu=engine.post_scriptum_attendu,
        portes=engine,
        trace=_trace_du(engine),
    )


def _trace_du(engine: Any) -> TraceDuModele | None:
    trace = getattr(engine, ATTRIBUT_TRACE, None)
    return trace if isinstance(trace, TraceDuModele) else None
