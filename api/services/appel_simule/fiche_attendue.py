"""[.mark] The call record a scenario expects, rated by the code (réparation globale, L8, D7).

A scenario may carry ``fiche_attendue``: field -> expected value (None: the field must stay empty).
At the end of the run the CODE rates each field, never the judge model:

- ``juste_sur``: the right value, and the record holds it as sure;
- ``juste_a_confirmer``: the right value, still to confirm with the caller;
- ``vide``: nothing written where a value was expected;
- ``faux``: another value (or a value where the field had to stay empty).

The same function rates the replay of real calls (``tests/mark/rejeu_corpus.py``), so a bench and a
replay speak the same language. Zero trade vocabulary: the fields and values are the scenario's.
"""

from __future__ import annotations

from api.schemas.lexique_metier import normaliser_terme
from api.services.workflow.fiche_au_fil_de_leau import CLE_ETAT

# The rank of a field against its target, best to worst (no loss = never worse).
JUSTE_SUR, JUSTE_A_CONFIRMER, VIDE, FAUX = 3, 2, 1, 0
NOMS_DES_RANGS = {JUSTE_SUR: "juste_sur", JUSTE_A_CONFIRMER: "juste_a_confirmer", VIDE: "vide", FAUX: "faux"}


def pareil(a, b) -> bool:
    return normaliser_terme(str(a or "")) == normaliser_terme(str(b or ""))


def rang(fiche: dict, champ: str, cible) -> int:
    """The rank of ``champ`` in ``fiche`` against ``cible`` (None: it must stay empty)."""
    valeur = fiche.get(champ)
    if cible is None:
        return JUSTE_SUR if valeur in (None, "") else FAUX
    if valeur in (None, ""):
        return VIDE
    if not pareil(valeur, cible):
        return FAUX
    sure = ((fiche.get(CLE_ETAT) or {}).get(champ) or {}).get("sure")
    return JUSTE_SUR if sure else JUSTE_A_CONFIRMER


def fiche_de_l_appel(contexte: dict | None) -> dict:
    """The record of a finished call, from its gathered context: the extracted variables (the
    values) and the state of each field (``fiche_etat``, whether it is sure)."""
    contexte = contexte or {}
    fiche = dict(contexte.get("extracted_variables") or {})
    if isinstance(contexte.get(CLE_ETAT), dict):
        fiche[CLE_ETAT] = contexte[CLE_ETAT]
    return fiche


def rangs_de_la_fiche(attendue: dict | None, contexte: dict | None) -> dict[str, str]:
    """The rating of each expected field of a scenario against the call's record. Empty when the
    scenario expects nothing."""
    if not attendue:
        return {}
    fiche = fiche_de_l_appel(contexte)
    return {champ: NOMS_DES_RANGS[rang(fiche, champ, cible)] for champ, cible in attendue.items()}
