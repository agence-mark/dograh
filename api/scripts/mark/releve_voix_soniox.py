"""[.mark] Relevé de la liste des voix Soniox (chantier voix-soniox, lot 2 bis, D2).

Soniox publie ses voix par ``GET /v1/tts-models`` : environ 200 voix, chacune avec
un identifiant, une description et un genre. Le 21/10/2026 seules les 11 voix
françaises ont été consignées (note ``2026-10-21-note-etat-de-l-art-conversation-
naturelle.md``, § 6) ; la liste complète n'a pas été enregistrée. Ce script la
relève et l'écrit dans un fichier JSON, à relire puis à reporter dans
``api/services/configuration/options/soniox.py`` (``SONIOX_TTS_VOIX``, avec la
date du relevé).

⛔ Jamais lancé par le chantier voix-soniox (aucun appel à un fournisseur la nuit,
consigne d'Evan). À lancer à la main, par Evan ou sur son accord.

🔒 La clé est lue dans la variable d'environnement ``SONIOX_API_KEY`` ou dans
``Labo-agent-vocal/.env.local`` ; elle n'est jamais écrite ni affichée, et le
fichier de sortie ne la contient pas. ⚠️ La clé du labo est celle d'un projet hors
UE : elle est acceptée par ``api.soniox.com`` (point mondial, par défaut) et
refusée par ``api.eu.soniox.com``. La liste des voix est la même.

    python -m api.scripts.mark.releve_voix_soniox <sortie.json> [adresse_de_l_api]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
ENV_LABO = RACINE.parent.parent / "Labo-agent-vocal/.env.local"
ADRESSE_DE_L_API = "https://api.soniox.com"
CHEMIN = "/v1/tts-models"


def lire_la_cle() -> str:
    """La clé, depuis l'environnement puis le fichier du labo. Jamais affichée."""
    cle = os.environ.get("SONIOX_API_KEY", "").strip()
    if not cle and ENV_LABO.exists():
        for ligne in ENV_LABO.read_text(encoding="utf-8").splitlines():
            nom, _, valeur = ligne.partition("=")
            if nom.strip() == "SONIOX_API_KEY":
                cle = valeur.strip().strip('"').strip("'")
    if not cle:
        raise SystemExit("SONIOX_API_KEY est absente (environnement ou Labo-agent-vocal/.env.local).")
    return cle


def releve(adresse_de_l_api: str = ADRESSE_DE_L_API) -> dict:
    """La réponse brute de Soniox, telle quelle : on ne la réécrit pas ici."""
    requete = urllib.request.Request(
        adresse_de_l_api.rstrip("/") + CHEMIN,
        headers={"Authorization": f"Bearer {lire_la_cle()}"},
    )
    with urllib.request.urlopen(requete, timeout=30) as reponse:  # noqa: S310 (adresse choisie par l'appelant)
        return json.loads(reponse.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage : python -m api.scripts.mark.releve_voix_soniox <sortie.json> [adresse_de_l_api]")
        return 2
    sortie = Path(argv[0])
    adresse = argv[1] if len(argv) > 1 else ADRESSE_DE_L_API
    contenu = releve(adresse)
    sortie.write_text(json.dumps(contenu, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"écrit : {sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
