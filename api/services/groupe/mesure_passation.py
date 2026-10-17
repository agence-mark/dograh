"""[.mark] Lot 3 d'orchestrateur-trois-cerveaux (D7, D18) : l'horodatage « passation demandée, premier octet de voix ».

Le plan veut savoir, au banc d'après le chantier, **ce que la voix unique fait gagner** à une passation : la
latence de passation (0,9 à 3,4 s mesurées sur Qwen, seuil 2 s) n'avait jamais isolé la part de la voix.
Aucun banc ne se joue pendant le chantier (D18) ; le code **horodate**, le banc **lira**.

Trois instants par passation, pris sur l'horloge monotone du processus :
- la demande (le coordinateur accepte la passation) ;
- le commit (l'agent appelé prend la main) ;
- le premier octet de la voix de l'APPEL après le commit (le premier ``TTSAudioRawFrame`` que la voix pousse).

Ils s'écrivent dans l'enregistrement de la passation (``agent_transfers`` de la fiche de l'appel, donc la trace
du run) : ``voix_premier_octet_s`` (demande → premier octet) et ``voix_apres_commit_s`` (commit → premier octet,
ce qui reste quand la voix est déjà ouverte). Une passation non commise n'a pas de mesure. Tout est
défensif : une erreur ici ne coûte jamais l'appel.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from loguru import logger
from pipecat.frames.frames import TTSAudioRawFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed

CLE_PREMIER_OCTET = "voix_premier_octet_s"
CLE_APRES_COMMIT = "voix_apres_commit_s"


class MesureDePassation:
    """L'état d'une mesure à la fois (une passation à la fois par appel)."""

    def __init__(self, horloge: Callable[[], float] = time.monotonic):
        self._horloge = horloge
        self._request_id: str | None = None
        self._demande: float | None = None
        self._commit: float | None = None
        self._resultat: dict[str, float] | None = None

    def demandee(self, request_id: str) -> None:
        """Le coordinateur accepte une passation : on repart de zéro."""
        self._request_id = request_id
        self._demande = self._horloge()
        self._commit = None
        self._resultat = None

    def commise(self) -> None:
        """L'agent appelé prend la main (``commit_agent``)."""
        if self._demande is not None:
            self._commit = self._horloge()

    def premier_octet(self) -> dict[str, float] | None:
        """La voix de l'appel pousse son premier audio après le commit. Rend la mesure la première
        fois (et seulement alors), ``None`` sinon."""
        if self._demande is None or self._commit is None or self._resultat is not None:
            return None
        maintenant = self._horloge()
        self._resultat = {
            CLE_PREMIER_OCTET: round(maintenant - self._demande, 3),
            CLE_APRES_COMMIT: round(maintenant - self._commit, 3),
        }
        return dict(self._resultat)

    @property
    def request_id(self) -> str | None:
        return self._request_id

    @property
    def resultat(self) -> dict[str, float] | None:
        return dict(self._resultat) if self._resultat else None

    def completer(self, enregistrement: dict) -> dict:
        """Ajoute la mesure à l'enregistrement d'une passation commise, si elle est déjà prise."""
        if (
            self._resultat
            and enregistrement.get("request_id") == self._request_id
            and enregistrement.get("to_visit_id")
        ):
            enregistrement.update(self._resultat)
        return enregistrement


class ObservateurPremierOctet(BaseObserver):
    """Observe la voix de l'appel : son premier ``TTSAudioRawFrame`` après un commit clôt la mesure.

    Attaché au worker de l'appel (``task.add_observer``). N'agit que si la mesure est ouverte ; ne
    change rien au flux."""

    def __init__(self, engine: Any, voix: Any):
        super().__init__()
        self._engine = engine
        self._voix = voix

    async def on_push_frame(self, data: FramePushed):
        try:
            if data.source is not self._voix or not isinstance(data.frame, TTSAudioRawFrame):
                return
            mesure: MesureDePassation | None = getattr(self._engine, "mesure_passation", None)
            if mesure is None:
                return
            resultat = mesure.premier_octet()
            if resultat is None:
                return
            # La passation a pu finir (enregistrement écrit) avant le premier octet : on le complète.
            for enregistrement in getattr(self._engine, "_transfer_outcomes", []):
                mesure.completer(enregistrement)
            logger.info(f"[transfer] {mesure.request_id}: premier octet de voix {resultat}")
        except Exception as erreur:  # noqa: BLE001 -- une mesure ne coûte jamais l'appel
            logger.warning(f"[transfer] mesure du premier octet illisible : {erreur!r}")
