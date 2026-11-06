"""[.mark] builder partie 2, D1 (D5 du 03/11) : la durée maximale d'un appel vaut 600 s partout.

| Test | Ce qu'il prouve |
|---|---|
| schéma | le défaut du schéma est 600 s, sous le plafond de 1200 s |
| moniteur | le moniteur d'un appel sans réglage coupe à 600 s |
| appel sans réglage | la lecture de la configuration d'un appel (``run_pipeline``) part du même défaut |
| écran | le repli de l'écran et l'aide du thème « Rythme » disent 600 (les deux textes sont lus dans les sources) |
"""

import inspect
import re
from pathlib import Path

from api.schemas.workflow_configurations import (
    DEFAULT_MAX_CALL_DURATION_SECONDS,
    MAX_CALL_DURATION_SECONDS,
    WorkflowConfigurationDefaults,
)
from api.services.pipecat import call_monitor_processor, run_pipeline

RACINE = Path(__file__).resolve().parents[3]


def test_le_defaut_du_schema_est_600_secondes():
    assert DEFAULT_MAX_CALL_DURATION_SECONDS == 600
    assert WorkflowConfigurationDefaults().max_call_duration == 600
    assert 600 <= MAX_CALL_DURATION_SECONDS


def test_le_moniteur_sans_reglage_coupe_a_600_secondes():
    signature = inspect.signature(call_monitor_processor.CallMonitorProcessor.__init__)
    assert signature.parameters["max_call_duration_seconds"].default == 600


def test_la_lecture_d_un_appel_part_du_meme_defaut():
    source = inspect.getsource(run_pipeline)
    assert "max_call_duration_seconds = DEFAULT_MAX_CALL_DURATION_SECONDS" in source
    assert run_pipeline.DEFAULT_MAX_CALL_DURATION_SECONDS == 600


def test_le_repli_de_l_ecran_et_l_aide_disent_600():
    types = (RACINE / "ui/src/types/workflow-configurations.ts").read_text(encoding="utf-8")
    assert re.search(r"FALLBACK_WORKFLOW_CONFIGURATIONS[^=]*=\s*\{.*?max_call_duration:\s*600,", types, re.S)
    theme = (RACINE / "ui/src/components/mark/reglages-agent/ThemeRythme.tsx").read_text(encoding="utf-8")
    # SA-12 (bulles réécrites) : l'aide dit la valeur en secondes et le plafond du serveur ; le défaut reste 600.
    assert "Default: 600 s (10 minutes)" in theme and "Défaut : 600 s (10 minutes)" in theme
