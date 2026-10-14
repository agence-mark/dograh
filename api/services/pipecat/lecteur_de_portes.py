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
- filet des répliques inachevées (repliques-coupees, D2 et D10, ``replique_inachevee.py``) :
  seules des phrases finies partent à la voix ; un reste sans ponctuation finale n'est ni dit ni
  gardé, et le modèle reparle une fois par réplique de l'appelant (avec la réflexion de secours
  de l'agent, s'il en a une) ;
- case ``trace_requetes_modele`` allumée (repliques-coupees, D1), ce qu'il laisse partir à la
  voix et les interruptions vont à la trace du cerveau (``trace_modele.py``) ;
- ⛔ il ne lève jamais (patron du Post-scriptum).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from loguru import logger

from api.services.pipecat.post_scriptum import PostScriptumProcessor, sans_json
from api.services.pipecat.replique_inachevee import (
    ATTRIBUT_RELANCE,
    TRACE_INACHEVEES,
    ReflexionDeRelanceMixin,
    fin_de_la_derniere_phrase,
)
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
        relance: ReflexionDeRelanceMixin | None = None,
        **kwargs,
    ):
        # D1 de repliques-coupees : ``None`` (case éteinte), rien n'est noté.
        self._trace_du_modele = trace
        # D10 : le service qui relance avec la réflexion de secours (``None`` : sans secours).
        self._relance_de_secours = relance
        # D2 : une seule relance d'une réplique inachevée par réplique de l'appelant.
        self._tour_relance: Any = object()
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

    def _a_retenir(self, texte: str) -> int:
        """D2 : ce qui suit la dernière phrase finie attend la fin de la réponse (la voix
        l'attend déjà : aucune latence), en plus de ce que le Post-scriptum retient."""
        return max(super()._a_retenir(texte), len(texte) - fin_de_la_derniere_phrase(texte))

    async def _finir(self, direction: FrameDirection) -> dict | None:
        """Fin de la réponse : les phrases finies à la voix ; un reste inachevé retenu (D2)."""
        self._dit = False
        reste = ""
        if not self._apres and self._attente.strip(" \t\n|"):
            coupe = fin_de_la_derniere_phrase(self._attente)
            if self._attente[coupe:].strip(" \t\n|  "):
                # D2 : ni dit ni gardé (l'historique est fait de ce qui est dit).
                reste = self._attente[coupe:].strip()
                if self._attente[:coupe].strip():
                    await self._dire(self._attente[:coupe], None, direction, fin=True)
            else:
                await self._dire(self._attente, None, direction, fin=True)
        if self._apres:
            # D7 : du JSON dans la réponse n'est jamais dit ; la parole autour l'est.
            await self._dire(sans_json(self._note), None, direction, fin=True)
        muette = (
            self._vu_du_texte
            and not self._a_dit
            and not self._portes_lues
            and self._attendu()
            and not reste
        )
        self._dit = self._a_dit
        portes = bool(self._portes_lues)
        self._oublier()
        if reste:
            await self._retenir_l_inachevee(reste, portes=portes)
        if muette:
            # Revue du 13/10 : une réponse faite seulement de JSON (un vieux réflexe) ne
            # dit rien et ne prend aucune porte : le modèle reparle, une fois par réplique
            # (la garde du moteur), jamais un tour muet.
            relancer = getattr(self._moteur, "relancer_une_reponse_muette", None)
            if relancer is not None and await relancer():
                logger.info("[porte] réponse sans phrase ni porte : le modèle reparle")
        return None

    async def _retenir_l_inachevee(self, reste: str, *, portes: bool) -> None:
        """D2 et D10 : le modèle reparle une fois par réplique de l'appelant, avec la
        réflexion de secours s'il y en a une. Une porte écrite : la relance se fait dans
        l'étape d'arrivée (``relancer`` de la porte). ⛔ Ne lève jamais."""
        secours = self._relance_de_secours
        try:
            fiche = self._fiche()
            tour = fiche.get(CLE_TOUR)
            trace: dict = {"tour": tour, "reste": reste, "relance": False}
            fiche.setdefault(TRACE_INACHEVEES, []).append(trace)
            if tour is not None and tour == self._tour_relance:
                logger.info("[filet] réplique inachevée déjà relancée à cette réplique : retenue")
                return
            if secours is not None:
                secours.armer_la_relance()
                trace["reflexion"] = secours.mark_reflexion_de_relance
            if portes:
                # La porte relance le modèle dans l'étape d'arrivée (fin de réponse du parent).
                self._dit = False
                relancee = True
            else:
                relancer = getattr(self._moteur, "relancer_une_reponse_muette", None)
                relancee = relancer is not None and await relancer()
            if relancee:
                self._tour_relance = tour
                trace["relance"] = True
                logger.info("[filet] réplique inachevée retenue : le modèle reparle")
            elif secours is not None:
                secours.desarmer_la_relance()
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[filet] réplique inachevée non traitée : {erreur!r}")

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
        relance=_relance_du(engine),
    )


def _relance_du(engine: Any) -> ReflexionDeRelanceMixin | None:
    relance = getattr(engine, ATTRIBUT_RELANCE, None)
    return relance if isinstance(relance, ReflexionDeRelanceMixin) else None


def _trace_du(engine: Any) -> TraceDuModele | None:
    trace = getattr(engine, ATTRIBUT_TRACE, None)
    return trace if isinstance(trace, TraceDuModele) else None
