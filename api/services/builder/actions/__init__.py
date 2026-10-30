"""[.mark] Builder : les actions, communes à l'écran et à Claude Code (voir ``registre``).

Importer ce paquet remplit ``REGISTRE`` (une seule fois, à l'import).
"""

from api.services.builder.actions import (  # noqa: F401 -- l'import inscrit les actions
    bibliotheque,
    construction,
    fiche_et_reglages,
    points_d_entree,
)
from api.services.builder.actions.registre import (  # noqa: F401
    INTERDITES,
    REGISTRE,
    Action,
    Contexte,
    executer,
    outils_du_moteur,
)
