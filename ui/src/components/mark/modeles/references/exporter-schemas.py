"""[.mark] Writes the JSON schemas the Models screen renders, for the screen tests.

Chantier reorganisation-ecran-reglages, steps 1 and 6. The screen is generated
from these schemas (`GET /api/v1/user/configurations/defaults`), so the tests of
the Models screen render the REAL ones, never a copy written by hand. Run from
the repository root, in the API's environment:

    python ui/src/components/mark/modeles/references/exporter-schemas.py

`api/tests/mark/test_schemas_ecran_modeles_a_jour.py` fails when this file is
stale, so a schema changed without re-exporting is caught.
"""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(RACINE))

from api.services.configuration.registry import REGISTRY, ServiceType  # noqa: E402

FOURNISSEURS = {
    "llm": (ServiceType.LLM, ["mistral"]),
    "tts": (ServiceType.TTS, ["elevenlabs"]),
    "stt": (ServiceType.STT, ["deepgram"]),
}

SORTIE = Path(__file__).with_name("schemas-fournisseurs.json")


def schemas() -> dict:
    return {
        service: {nom: REGISTRY[type_][nom].model_json_schema() for nom in noms}
        for service, (type_, noms) in FOURNISSEURS.items()
    }


if __name__ == "__main__":
    SORTIE.write_text(json.dumps(schemas(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written: {SORTIE}")
