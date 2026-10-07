"""[.mark] Compare a control answer with the record (L6, V1, V2). Pure, no model.

- ``reference``: one of the record's references, digits only (« la 1 2 4 » = 124);
- ``code_postal``: the five digits;
- ``mail``: lower case, spaces removed;
- ``commune``: our normalisation (accents, hyphens, « st » = « saint »);
- ``nom``: same spelling once normalised, or the same French sound (``phonetic_fr``, the key our
  town and name modules use): the transcription spells names its own way (decision of 24/09:
  names go through our modules). Never a looser match: a wrong name is a failed attempt.
"""

from __future__ import annotations

import re


def _chiffres(texte) -> str:
    return "".join(c for c in str(texte or "") if c.isdigit())


def egal(champ: str, reponse, dossier: dict) -> bool:
    from api.services.communes.base import cle_phonetique, normaliser

    if reponse in (None, "") or not isinstance(dossier, dict):
        return False
    if champ == "reference":
        dite = _chiffres(reponse).lstrip("0")
        return bool(dite) and dite in {_chiffres(r).lstrip("0") for r in dossier.get("references") or []}
    attendu = dossier.get(champ)
    if attendu in (None, ""):
        return False
    if champ == "code_postal":
        return len(_chiffres(reponse)) == 5 and _chiffres(reponse) == _chiffres(attendu)
    if champ == "mail":
        return re.sub(r"\s+", "", str(reponse)).lower() == re.sub(r"\s+", "", str(attendu)).lower()
    a, b = normaliser(str(reponse)), normaliser(str(attendu))
    if not a or not b:
        return False
    if a == b:
        return True
    if champ == "nom":
        try:
            return cle_phonetique(a) == cle_phonetique(b) and len(cle_phonetique(b)) >= 2
        except Exception:  # noqa: BLE001 -- no phonetic module: spelling only
            return False
    return False
