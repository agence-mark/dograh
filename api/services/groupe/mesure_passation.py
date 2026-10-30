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

fiabilite-orchestration, lot 3 : la passation DÉCOUPÉE, à chaque appel : ``installation_s`` (demande
→ agent installé : construit, pris dans la réserve ou principal resté chaud, ``installation``),
``premier_mot_s`` (demande → premier mot du modèle de l'agent appelé), puis le premier son ; et la
mémoire du processus (``memoire_mo``) au moment de l'installation.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from loguru import logger
from pipecat.frames.frames import TTSAudioRawFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed

CLE_PREMIER_OCTET = "voix_premier_octet_s"
CLE_APRES_COMMIT = "voix_apres_commit_s"
CLE_INSTALLATION = "installation_s"
CLE_ORIGINE = "installation"
CLE_MEMOIRE = "memoire_mo"
CLE_PREMIER_MOT = "premier_mot_s"
# agent-facon-tala, C3 bis : les morceaux qui manquaient pour dire où part le délai.
CLE_DECISION = "decision_s"  # début de la requête qui a décidé la passation -> demande
CLE_COMMIT = "commit_s"  # demande -> l'agent appelé prend la main
CLE_REQUETE_COLLEGUE = "requete_collegue_s"  # demande -> départ de la 1re requête du collègue


class MesureDePassation:
    """L'état d'une mesure à la fois (une passation à la fois par appel)."""

    def __init__(
        self,
        horloge: Callable[[], float] = time.monotonic,
        enregistrements: Callable[[], list] | None = None,
    ):
        self._horloge = horloge
        # Les enregistrements de passation déjà écrits, à compléter quand un morceau arrive après coup.
        self._enregistrements = enregistrements
        # Le départ de la dernière requête au modèle de chaque visite (``depart_de_requete``).
        self._departs: dict[str, float] = {}
        self._request_id: str | None = None
        self._demande: float | None = None
        self._commit: float | None = None
        self._resultat: dict[str, float] | None = None
        self._decoupe: dict = {}
        self._visite: str | None = None

    def demandee(self, request_id: str, visite_origine: str | None = None) -> None:
        """Le coordinateur accepte une passation : on repart de zéro. ``visite_origine`` : l'agent qui
        la demande, dont la dernière requête au modèle est la décision."""
        self._request_id = request_id
        self._demande = self._horloge()
        self._commit = None
        self._resultat = None
        self._decoupe = {}
        self._visite = None
        depart = self._departs.get(visite_origine) if visite_origine else None
        if depart is not None and depart <= self._demande:
            self._decoupe[CLE_DECISION] = round(self._demande - depart, 3)

    def depart_de_requete(self, visite: str | None, instant: float) -> None:
        """Une requête part vers le modèle de ``visite`` (``noter_les_departs_de_requete``). La première
        du collègue après le commit date son entrée dans la mesure."""
        try:
            if visite is None:
                return
            self._departs[visite] = instant
            if (
                self._demande is not None
                and self._commit is not None
                and visite == self._visite
                and CLE_REQUETE_COLLEGUE not in self._decoupe
            ):
                self._decoupe[CLE_REQUETE_COLLEGUE] = round(instant - self._demande, 3)
                self._reporter()
        except Exception as erreur:  # noqa: BLE001 -- une mesure ne coûte jamais l'appel
            logger.warning(f"[transfer] départ de requête non daté : {erreur!r}")

    def _reporter(self) -> None:
        """Un morceau arrivé après l'écriture de l'enregistrement y est ajouté."""
        if self._enregistrements is None:
            return
        for enregistrement in self._enregistrements() or []:
            self.completer(enregistrement)

    def installee(
        self, duree_s: float, origine: str, memoire_mo: float | None, visite: str | None = None
    ) -> None:
        """L'agent appelé est installé (fiabilite-orchestration, lot 3)."""
        if self._demande is None:
            return
        self._decoupe.update(
            {
                CLE_INSTALLATION: round(float(duree_s), 3),
                CLE_ORIGINE: origine,
                CLE_MEMOIRE: memoire_mo,
            }
        )
        self._visite = visite

    def premier_mot(self, visite: str | None) -> None:
        """Le premier texte du modèle de l'agent appelé (une fois)."""
        if (
            self._demande is None
            or CLE_PREMIER_MOT in self._decoupe
            or visite is None
            or visite != self._visite
        ):
            return
        self._decoupe[CLE_PREMIER_MOT] = round(self._horloge() - self._demande, 3)
        self._reporter()

    def commise(self) -> None:
        """L'agent appelé prend la main (``commit_agent``)."""
        if self._demande is not None:
            self._commit = self._horloge()
            self._decoupe[CLE_COMMIT] = round(self._commit - self._demande, 3)

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
        if enregistrement.get("request_id") == self._request_id and enregistrement.get(
            "to_visit_id"
        ):
            enregistrement.update(self._decoupe)
            if self._resultat:
                enregistrement.update(self._resultat)
        return enregistrement

    @property
    def decoupe(self) -> dict:
        return {**self._decoupe, **(self._resultat or {})}


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
            logger.info(
                f"[transfer] {mesure.request_id}: passation découpée {mesure.decoupe}"
            )
        except Exception as erreur:  # noqa: BLE001 -- une mesure ne coûte jamais l'appel
            logger.warning(f"[transfer] mesure du premier octet illisible : {erreur!r}")
