"""[.mark] Chantier Partie 1 : les corrections du point de contrôle du lot 7 (SA-C), une par défaut trouvé au clavier.

Chacune a été vue rouge sur ``dbd209f1`` (le code joué au point de contrôle) avant sa correction.
"""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[3]


def test_l_image_ecrit_la_pile_d_un_plantage_natif():
    """Défaut 1 (19/11, 16:05 et 16:09 UTC) : deux segfaults du serveur sans aucune pile Python. L'image allume ``faulthandler``
    pour chaque processus Python (uvicorn, arq, ari) : la prochaine fois, la pile de chaque fil est écrite dans les journaux."""
    dockerfile = (API / "Dockerfile").read_text(encoding="utf-8")
    image_finale = dockerfile.split("AS runner", 1)[1]
    assert re.search(r"^ENV PYTHONFAULTHANDLER=1\s*$", image_finale, re.M)
