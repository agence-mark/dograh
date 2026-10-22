"""[.mark] Les variables que le CODE pose dans le contexte de l'appel (cloture-code, revue 4).

Un objet de l'agent se pose dans le contexte sous son nom et se lit ``{{nom}}``. Un objet qui porterait le nom
d'une variable que le code pose lui-même (l'établissement, le numéro de transfert, l'état d'ouverture, la
date, l'adresse, l'équipe...) la masquerait en silence : ``injecter_objets`` passe AVANT la plupart d'entre
elles, qui gardent alors la valeur de l'objet. Le nom est donc refusé à l'écriture de l'objet (409).

⛔ UNE seule liste, ici. Chaque injection de ``run_pipeline.py`` y figure avec les clés qu'elle écrit, lues
dans les constantes de son propre module (jamais recopiées à la main). Un test lit le source de
``run_pipeline.py`` : une injection nouvelle qui n'est pas ici le fait échouer.

Les noms de phrases du catalogue de l'organisation ne sont pas ici : ils viennent des données du client et
se lisent à l'écriture (``routes/objets_agent.py``).

Pur : aucune base, rien de levé.
"""

from __future__ import annotations

from api.schemas.fiche_agent import NOMS_RESERVES
from api.services.communes.adresse import CLE_ADRESSE
from api.services.equipe.appel import CLE_CLES, CLE_EQUIPE
from api.services.etablissements.appel import (
    CLE_FICHE_DE_LAPPEL,
    CLE_NOM,
    CLE_NUMERO_TRANSFERT,
)
from api.services.lexique.ecoute import CLE_A_ECOUTER, CLE_PROPOSE
from api.services.pipecat.etat_ouverture import (
    CLE_ANNONCE,
    CLE_DATE_APPEL,
    CLE_ETAT,
    CLE_HEURE_APPEL,
    CLE_HORAIRES,
    CLE_REOUVERTURE,
)

# Les injections de ``run_pipeline.py`` (par le nom de la fonction) et ce que chacune écrit.
INJECTIONS_DU_CODE: dict[str, frozenset[str]] = {
    "injecter_etablissement": frozenset({CLE_NOM, CLE_NUMERO_TRANSFERT, CLE_FICHE_DE_LAPPEL}),
    "injecter_equipe": frozenset({CLE_EQUIPE, CLE_CLES}),
    "injecter_etat_ouverture": frozenset({CLE_ETAT, CLE_REOUVERTURE, CLE_HORAIRES, CLE_ANNONCE}),
    "injecter_date_heure_appel": frozenset({CLE_DATE_APPEL, CLE_HEURE_APPEL}),
    "injecter_adresse_etablissement": frozenset({CLE_ADRESSE}),
    "injecter_lexique_propose": frozenset({CLE_PROPOSE, CLE_A_ECOUTER}),
}

# Les injections dont les noms viennent des DONNÉES du client (jamais une liste fixe) : les objets eux-mêmes et
# le catalogue de phrases. Elles sont déclarées pour que le test sache qu'elles ne sont pas oubliées.
INJECTIONS_DES_DONNEES_DU_CLIENT: frozenset[str] = frozenset({"injecter_objets", "injecter_phrases"})

# Posées une à une par ``run_pipeline.py`` lui-même, hors injection.
CLES_POSEES_PAR_LE_PIPELINE: frozenset[str] = frozenset({"workflow_run_id", "call_id", "runtime_configuration"})


def variables_posees_par_le_code() -> frozenset[str]:
    """Tous les noms qu'un objet ne peut pas prendre : les injections, le pipeline, et les clés que le moteur
    et les modules écrivent dans la fiche de l'appel (``NOMS_RESERVES``)."""
    posees: set[str] = set(CLES_POSEES_PAR_LE_PIPELINE) | set(NOMS_RESERVES)
    for cles in INJECTIONS_DU_CODE.values():
        posees |= cles
    try:
        from api.services.managed_model_services import MPS_CORRELATION_ID_CONTEXT_KEY

        posees.add(MPS_CORRELATION_ID_CONTEXT_KEY)
    except Exception:  # noqa: BLE001 -- un service absent ne rend pas la liste plus courte pour autant
        pass
    return frozenset(posees)


VARIABLES_POSEES_PAR_LE_CODE: frozenset[str] = variables_posees_par_le_code()
