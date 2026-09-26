"""[.mark] The schemas the Models screen tests render are the ones the API serves.

Chantier reorganisation-ecran-reglages (steps 1 and 6). The screen tests of the
Models screen render `ui/src/components/mark/modeles/references/schemas-fournisseurs.json`,
an export of the registry for Mistral, ElevenLabs and Deepgram. An export
nobody compares drifts: a field added or regrouped in Python would leave the
screen tests green on a screen that no longer exists. So the comparison is made
here, from the side that owns the truth.

Re-exporting: `python ui/src/components/mark/modeles/references/exporter-schemas.py`.
"""

import json
from pathlib import Path

import pytest

from api.services.configuration.registry import REGISTRY, ServiceType

EXPORT = (
    Path(__file__).resolve().parents[3]
    / "ui/src/components/mark/modeles/references/schemas-fournisseurs.json"
)

FOURNISSEURS = [
    ("llm", ServiceType.LLM, "mistral"),
    ("tts", ServiceType.TTS, "elevenlabs"),
    ("stt", ServiceType.STT, "deepgram"),
]


@pytest.mark.parametrize("service, type_, nom", FOURNISSEURS)
def test_l_export_des_schemas_de_l_ecran_modeles_est_a_jour(service, type_, nom):
    exporte = json.loads(EXPORT.read_text(encoding="utf-8"))
    servi = json.loads(json.dumps(REGISTRY[type_][nom].model_json_schema()))
    assert exporte[service][nom] == servi, (
        f"{nom}: the schema changed without re-exporting schemas-fournisseurs.json. "
        "Run ui/src/components/mark/modeles/references/exporter-schemas.py."
    )
