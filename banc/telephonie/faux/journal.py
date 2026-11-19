"""Le journal des faux fournisseurs : une ligne JSON par événement, horodatée.

L'horloge est celle du noyau, la même que celle de la capture réseau prise dans
le conteneur SIPp : les deux se croisent sans correction.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, fichier: Path) -> None:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        # Tampon d'une ligne : chaque événement est sur le disque dès qu'il est noté.
        self._sortie = fichier.open("a", buffering=1, encoding="utf-8")

    def noter(self, service: str, evenement: str, **details: Any) -> None:
        ligne = {
            "t_ns": time.time_ns(),
            "service": service,
            "evenement": evenement,
            **details,
        }
        self._sortie.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def fermer(self) -> None:
        self._sortie.close()
