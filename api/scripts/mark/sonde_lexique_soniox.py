"""[.mark] Probe of the ceiling of Soniox's context (chantier communes-cp-et-lexique-soniox, lot 3, Q4 and Q7).

Soniox documents a context of 8 000 tokens at most, all sections together, and
refuses beyond with a MESSAGE inside the session (``error_code`` 400). No list
leaves for a provider until its ceiling is MEASURED (rule Q1 of the lexicon,
2026-09-26): this script measures it.

What one attempt is
-------------------
One connection: the configuration message a call sends (same fields as
Pipecat's connector, the context built by ``contexte_soniox``, the very function
the factory uses), one second of silence, the end of audio, then every message
until Soniox finishes or refuses. Logged per attempt: characters, terms, our
estimate of the tokens, accepted or refused, and Soniox's message.

The lists
---------
1. the 181 real terms of the vocabulary (corpus ``rejeu_runs_963_967.json``);
2. the same with a domain description of 300 characters (Q5-bis);
3. synthetic lists that double in size until the first refusal (Q4: up to the
   real refusal), then a dichotomy on the number of terms between the last list
   accepted and the first refused.

🔒 The key is read from ``SONIOX_API_KEY`` (environment) or from
``Labo-agent-vocal/.env.local``; it is never printed.

    python -m api.scripts.mark.sonde_lexique_soniox <sortie.jsonl> [adresse]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import websockets

from api.services.configuration.plafond_lexique import (
    jetons_du_terme,
    plafond_du_lexique,
)
from api.services.configuration.registry import DESCRIPTION_DU_DOMAINE_MAX
from api.services.pipecat.service_factory import contexte_soniox

RACINE = Path(__file__).resolve().parents[3]
CORPUS = RACINE / "api/tests/mark/donnees/rejeu_runs_963_967.json"
ENV_LABO = RACINE.parent.parent / "Labo-agent-vocal/.env.local"
ADRESSE_MONDIALE = "wss://stt-rt.soniox.com/transcribe-websocket"
TAUX = 8000  # telephony, as the calls
SILENCE = b"\x00\x00" * TAUX  # one second
# The content plays no part in the measure, only its length: a neutral text,
# never a trade's words (rule « zéro vocabulaire métier dans le code »).
DESCRIPTION_300 = (
    "Description neutre du domaine, utilisée seulement pour mesurer la place qu'elle prend. "
    * 5
)[:DESCRIPTION_DU_DOMAINE_MAX]
# The estimate our ceilings use, taken from the declaration (never a second ceiling
# written here: test_aucun_plafond_nest_ecrit_hors_de_la_declaration_du_fournisseur),
# to recalibrate on the frontier this probe finds.
ESTIMATEUR = plafond_du_lexique("soniox", "stt-rt-v5")


def _cle() -> str:
    cle = os.environ.get("SONIOX_API_KEY")
    if not cle and ENV_LABO.exists():
        for ligne in ENV_LABO.read_text(encoding="utf-8").splitlines():
            if ligne.strip().startswith("SONIOX_API_KEY="):
                cle = ligne.split("=", 1)[1].strip().strip('"').strip("'")
    if not cle:
        sys.exit(
            "SONIOX_API_KEY absente (environnement ou Labo-agent-vocal/.env.local)."
        )
    return cle


def _termes_reels() -> list[str]:
    lexique = json.loads(CORPUS.read_text(encoding="utf-8"))["lexique"]["termes"]
    return [t["terme"] for t in lexique]


def _synthetiques(reels: list[str], nombre: int) -> list[str]:
    return [
        reels[i % len(reels)] + ("" if i < len(reels) else f" {i // len(reels)}")
        for i in range(nombre)
    ]


def _mesure(termes: list[str], description: str | None) -> dict:
    jetons = sum(jetons_du_terme(t, ESTIMATEUR) for t in termes)
    if description:
        jetons += jetons_du_terme(description, ESTIMATEUR)
    return {
        "termes": len(termes),
        "caracteres": sum(len(t) for t in termes) + len(description or ""),
        "jetons_estimes": jetons,
        "description": len(description or ""),
    }


async def _essai(
    adresse: str, cle: str, termes: list[str], description: str | None
) -> dict:
    contexte = contexte_soniox(termes, description).model_dump()
    configuration = {
        "api_key": cle,
        "model": "stt-rt-v5",
        "audio_format": "pcm_s16le",
        "num_channels": 1,
        "sample_rate": TAUX,
        "enable_endpoint_detection": True,
        "language_hints": ["fr"],
        "context": contexte,
    }
    resultat = _mesure(termes, description) | {
        "taille_du_contexte_json": len(json.dumps(contexte))
    }
    try:
        async with websockets.connect(adresse, open_timeout=10) as socket:
            await socket.send(json.dumps(configuration))
            await socket.send(SILENCE)
            await socket.send("")  # end of audio
            async with asyncio.timeout(15):
                async for message in socket:
                    contenu = json.loads(message)
                    if contenu.get("error_code") or contenu.get("error_message"):
                        return resultat | {
                            "accepte": False,
                            "code": contenu.get("error_code"),
                            "message": contenu.get("error_message"),
                        }
                    if contenu.get("finished"):
                        return resultat | {"accepte": True}
        return resultat | {"accepte": True, "note": "fermé sans « finished »"}
    except Exception as erreur:  # noqa: BLE001 -- logged, never raised: the probe goes on
        return resultat | {
            "accepte": None,
            "erreur": f"{type(erreur).__name__}: {erreur}"[:300],
        }


async def principal(sortie: Path, adresse: str) -> None:
    cle = _cle()
    reels = _termes_reels()
    journal = sortie.open("a", encoding="utf-8")

    async def essai(
        nom: str, termes: list[str], description: str | None = None
    ) -> dict:
        r = {"essai": nom, "adresse": adresse} | await _essai(
            adresse, cle, termes, description
        )
        journal.write(json.dumps(r, ensure_ascii=False) + "\n")
        journal.flush()
        print(
            json.dumps(
                {k: v for k, v in r.items() if k != "adresse"}, ensure_ascii=False
            )
        )
        return r

    await essai("181 termes réels", reels)
    await essai("181 termes réels + description 300", reels, DESCRIPTION_300)
    await essai("description seule", [], DESCRIPTION_300)

    # Doubling until the first refusal (Q4).
    accepte, refuse = len(reels), None
    nombre = len(reels) * 2
    while refuse is None and nombre <= 40_000:
        r = await essai(f"synthétique {nombre}", _synthetiques(reels, nombre))
        if r["accepte"] is False:
            refuse = nombre
        elif r["accepte"] is None:
            print("Essai sans réponse claire : arrêt, rien n'est conclu.")
            return
        else:
            accepte = nombre
            nombre *= 2
    if refuse is None:
        print(f"Aucun refus jusqu'à {accepte} termes.")
        return
    # Dichotomy on the number of terms, to within 1 %.
    while refuse - accepte > max(1, accepte // 100):
        milieu = (accepte + refuse) // 2
        r = await essai(f"dichotomie {milieu}", _synthetiques(reels, milieu))
        if r["accepte"] is None:
            print("Essai sans réponse claire : arrêt de la dichotomie.")
            return
        accepte, refuse = (milieu, refuse) if r["accepte"] else (accepte, milieu)
    print(f"Frontière : {accepte} termes acceptés, {refuse} refusés.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(
        principal(
            Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else ADRESSE_MONDIALE
        )
    )
