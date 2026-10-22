"""[.mark] Retention of the calls' copies (chantier cloture-code-avant-migration, lot 6).

Decisions of Evan: « verbatim yes, audio never » (09/09) and « verbatim 6 months » (06/10). What a call leaves
behind in Dograh's own tables and storage -- the transcript, the logs, the context, the annotations, the audio
files -- is kept for a duration, then emptied by a nightly task (``services/conservation_appels/purge.py``).
The run itself stays (cost, duration, state, technical ``extra``).

Stored as one row of ``organization_configurations`` under ``CONSERVATION_APPELS`` (no migration); the last
night's result under ``CONSERVATION_APPELS_BILAN``. Defaults are .mark's: purge on, 6 months, audio NOT
recorded (the environment variable ``ENABLE_CALL_RECORDING_UPLOAD`` is only a ceiling: at ``false`` nobody
can switch the audio on), audio kept 6 months if recorded, dry run on until it is unticked.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

FORMAT = "conservation-appels-mark"
VERSION = 1
MOIS_MIN = 1
MOIS_MAX = 120
# A month is 30 days here: the screen says « months », the purge counts days.
JOURS_PAR_MOIS = 30


class ReglagesConservationAppels(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: str = FORMAT
    version: int = VERSION
    purge_activee: bool = Field(
        default=True,
        description="Empty the copies of the calls older than the durations below, every night.",
    )
    duree_mois: int = Field(
        default=6,
        ge=MOIS_MIN,
        le=MOIS_MAX,
        description="Months the verbatim and the copies of a call are kept (transcript, logs, context, annotations).",
    )
    audio_enregistre: bool = Field(
        default=False,
        description="Record the audio of the calls. Off by default; the installation's ceiling can forbid it.",
    )
    audio_duree_mois: int = Field(
        default=6,
        ge=MOIS_MIN,
        le=MOIS_MAX,
        description="Months an audio file is kept, if the audio is recorded (or was before).",
    )
    essai_a_blanc: bool = Field(
        default=True,
        description="Dry run: the nightly task counts what it would empty and empties nothing. Untick to empty.",
    )


class BilanDuPassage(BaseModel):
    """What the last nightly task found, kept so the screen can show it (and the dry run be read)."""

    model_config = ConfigDict(extra="ignore")

    passe_le: datetime
    a_blanc: bool
    runs_texte: int = Field(description="Runs whose text copies were (dry run: would be) emptied.")
    runs_audio: int = Field(description="Runs whose audio files were (dry run: would be) deleted.")
    objets: int = Field(description="Files in storage deleted (dry run: to delete).")
    echecs: int = Field(default=0, description="Runs left for the next night (a file could not be deleted).")
    incomplet: bool = Field(default=False, description="The task stopped on its time limit: the rest is for the next night.")
    duree_mois: int
    audio_duree_mois: int


class VueConservationAppels(BaseModel):
    """What the screen reads: the settings, the installation's ceiling and the last passage."""

    reglages: ReglagesConservationAppels
    audio_autorise_par_l_installation: bool = Field(
        description="False when ENABLE_CALL_RECORDING_UPLOAD forbids the audio whatever the setting says."
    )
    dernier_passage: BilanDuPassage | None = None
