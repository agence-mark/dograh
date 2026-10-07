"""[.mark] Which fields are a phone, a postcode, an e-mail, a date (L7, QD1).

Recognised by their NAME, a default per type, set agent by agent (« Field recognition »). Read
ALONE at call time: an unreadable value is the default, with a warning (the call goes on).
The towns keep their own setting (``variables_commune``), never duplicated.
"""

from __future__ import annotations

from loguru import logger

from api.schemas.workflow_configurations import (
    VARIABLES_RECONNUES,
    decouper_variables_commune,
)

INTERRUPTEUR = "controle_donnees"
TYPES = {
    "telephone": "variables_telephone",
    "code_postal": "variables_code_postal",
    "courriel": "variables_courriel",
    "date": "variables_date",
}


def controle_allume(run_configs: dict | None) -> bool:
    return bool((run_configs or {}).get(INTERRUPTEUR))


def noms(run_configs: dict | None, type_: str) -> tuple[str, ...]:
    cle = TYPES[type_]
    defaut = VARIABLES_RECONNUES[cle]
    try:
        return decouper_variables_commune((run_configs or {}).get(cle), defaut)
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] {cle} unreadable, default used ({defaut}): {erreur!r}")
        return decouper_variables_commune(defaut, defaut)


def tous_les_noms(run_configs: dict | None) -> dict[str, tuple[str, ...]]:
    sortie = {t: noms(run_configs, t) for t in TYPES}
    from api.services.pipecat.verification_communes import variables_commune

    sortie["commune"] = variables_commune(run_configs)
    return sortie
